"""Day 3 context validation and actual MuJoCo parameter/safety integration."""
from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import json

import mujoco
import numpy as np
from PIL import Image
import pytest

from core.bodybase import BodyBase, CarriageGeometry
from core.worldbase import WorldBase
from core.day3 import load_scenarios, measure_force_probes
from core.day2 import diagnose_and_save
from core.diagnostics import failure_diagnostics, independently_verify_safety
from core.simulation import DEFAULT_MODEL_PATH, ROOT, compile_context_model, run_simulation, sha256
from robot.controller import faulty_braking_controller


@pytest.fixture(scope='module')
def scenario_runs(tmp_path_factory):
    output = tmp_path_factory.mktemp('contexts')
    return {name: run_simulation(bodybase=body, worldbase=world, controller=faulty_braking_controller,
                                 save_render=False, artifacts_dir=output / name)
            for name, (body, world) in load_scenarios().items()}


@pytest.fixture(scope='module')
def reports(scenario_runs):
    return {name: diagnose_and_save(run) for name, run in scenario_runs.items()}


@pytest.fixture(scope='module')
def rendered_context(tmp_path_factory):
    body, world = load_scenarios()['C']
    return run_simulation(bodybase=body, worldbase=world, controller=faulty_braking_controller,
                          artifacts_dir=tmp_path_factory.mktemp('context-native'))


def test_bodybase_loads_si_json_and_readonly_context(tmp_path):
    values = json.loads((ROOT / 'configs/bodybase.json').read_text())
    path = tmp_path / 'body.json'
    path.write_text(json.dumps(values))
    body = BodyBase.from_json(path)
    assert body.robot_id == 'linear_axis_01'
    assert body.mass_kg == 2 and body.max_force_n == 4
    assert body.max_velocity_ms == 1.2 and body.axis == 'x' and body.joint_type == 'prismatic'
    assert body.max_deceleration_ms2 == 2
    assert body.stopping_distance_m(1.2) == pytest.approx(0.36)
    assert body.context['units']['mass'] == 'kg'
    with pytest.raises(FrozenInstanceError):
        body.mass_kg = 9
    with pytest.raises(TypeError):
        body.context['collision_geometry']['bumper_half_size_m'][0] = 9
    copy = body.to_dict()
    copy['collision_geometry']['bumper_half_size_m'][0] = 9
    assert body.collision_geometry.bumper_half_size_m[0] == 0.025


def test_worldbase_loads_json_and_readonly_safety_context(tmp_path):
    path = tmp_path / 'world.json'
    path.write_text((ROOT / 'configs/worldbase.json').read_text())
    world = WorldBase.from_json(path)
    assert world.scenario == 'braking_before_wall'
    assert world.wall_position_x_m == 2 and world.wall_reference == 'center'
    assert world.initial_velocity_ms == 1.2
    assert world.simulation_timestep_s == 0.005 and world.simulation_duration_s == 3
    assert world.context['safety_criteria']['minimum_clearance_m'] == 0.05
    assert world.context['safety_criteria']['final_speed_strictly_below_ms'] == 0.03
    with pytest.raises(FrozenInstanceError):
        world.initial_velocity_ms = 8
    with pytest.raises(TypeError):
        world.context['safety_criteria']['minimum_clearance_m'] = 8


@pytest.mark.parametrize('changes', [{'mass_kg': 0}, {'mass_kg': -2}, {'mass_kg': '2 kg'},
    {'mass_kg': True}, {'max_force_n': 0}, {'max_force_n': float('nan')},
    {'max_velocity_ms': float('inf')}, {'max_velocity_ms': -1}, {'axis': 'y'},
    {'joint_type': 'hinge'}, {'robot_id': ''}])
def test_invalid_body_parameters_rejected(changes):
    with pytest.raises(ValueError):
        replace(BodyBase.from_json(), **changes)


@pytest.mark.parametrize('changes', [{'wall_reference': 'near_face'}, {'simulation_timestep_s': 0},
    {'simulation_timestep_s': True}, {'simulation_duration_s': -1}, {'simulation_duration_s': 0.012},
    {'minimum_clearance_m': -0.1}, {'wall_position_x_m': '165 cm'}, {'initial_velocity_ms': float('inf')},
    {'wall_half_size_m': [0, 0.5, 0.5]}, {'wall_center_yz_m': [0]},
    {'max_final_speed_ms': 0}, {'completion_deadline_s': -1}, {'gravity_ms2': [1, 0, -9.81]}])
def test_invalid_world_parameters_rejected(changes):
    with pytest.raises(ValueError):
        replace(WorldBase.from_json(), **changes)


def test_unknown_fields_and_invalid_collision_dimensions_rejected(tmp_path):
    values = BodyBase.from_json().to_dict()
    values['mass_g'] = 2000
    path = tmp_path / 'body.json'
    path.write_text(json.dumps(values))
    with pytest.raises(ValueError, match='schema'):
        BodyBase.from_json(path)
    with pytest.raises(ValueError):
        CarriageGeometry((0.13, 0.16, 0.08), (-0.025, 0.18, 0.085), 0.155)
    with pytest.raises(ValueError):
        CarriageGeometry((0.13, 0.16, 0.08), (0.025, 0.18, 0.085), 1.0)


@pytest.mark.parametrize('mass, force, sign', [(2, 4, 1), (3, 4, 1), (2, 2, -1), (2, 6, 1)])
def test_configured_mass_force_change_real_dynamics(tmp_path, mass, force, sign):
    body = replace(BodyBase.from_json(), mass_kg=mass, max_force_n=force)
    world = replace(WorldBase.from_json(), initial_velocity_ms=0, simulation_duration_s=0.05)
    run = run_simulation(bodybase=body, worldbase=world, control=sign * 40,
                         save_render=False, artifacts_dir=tmp_path)
    assert run['model'].body('carriage').mass[0] == mass
    assert run['data'].qfrc_actuator[0] == sign * force
    assert run['data'].actuator_force[0] == sign * force
    assert run['data'].qvel[0] == pytest.approx(sign * force / mass * 0.05, abs=1e-12)
    assert run['telemetry'][0]['acceleration'] == pytest.approx(sign * force / mass)
    assert run['data'].qpos[0] != 0
    saved = mujoco.MjModel.from_xml_path(str(tmp_path / 'effective_model.xml'))
    assert saved.body('carriage').mass[0] == mass
    np.testing.assert_array_equal(saved.actuator_forcerange[0], [-force, force])
    probes = measure_force_probes(run['effective_model_xml'], 0)
    for probe in probes:
        assert abs(probe['generalized_force_n']) == force
        assert probe['measured_acceleration_from_velocity_ms2'] == pytest.approx(probe['generalized_force_n'] / mass)


def test_mass_change_preserves_unrelated_geometry_and_scales_inertia(scenario_runs):
    a, b = scenario_runs['A']['model'], scenario_runs['B']['model']
    np.testing.assert_array_equal(a.geom_size, b.geom_size)
    np.testing.assert_array_equal(a.geom_pos, b.geom_pos)
    np.testing.assert_array_equal(a.jnt_axis, b.jnt_axis)
    np.testing.assert_array_equal(a.geom_contype, b.geom_contype)
    np.testing.assert_array_equal(a.geom_solref, b.geom_solref)
    np.testing.assert_allclose(b.body('carriage').inertia, a.body('carriage').inertia * 1.5, atol=1e-15)


def test_body_collision_dimensions_reach_actual_model(tmp_path):
    body = BodyBase.from_json()
    geometry = replace(body.collision_geometry, bumper_half_size_m=(0.035, 0.18, 0.085))
    body = replace(body, collision_geometry=geometry)
    world = replace(WorldBase.from_json(), initial_velocity_ms=0, simulation_duration_s=0)
    run = run_simulation(bodybase=body, worldbase=world, save_render=False, artifacts_dir=tmp_path)
    assert run['model'].geom('front_bumper').size[0] == 0.035
    assert run['telemetry'][0]['wall_clearance'] == pytest.approx(1.76)


def test_wall_position_initial_velocity_and_timestep_are_actual_state(scenario_runs, tmp_path):
    c = scenario_runs['C']
    assert c['model'].body('obstacle').pos[0] == 1.65
    assert c['telemetry'][0]['wall_near_x'] == pytest.approx(1.60)
    assert c['telemetry'][0]['wall_clearance'] == pytest.approx(1.42)
    assert c['telemetry'][0]['velocity'] == 1.0
    body, world = load_scenarios()['C']
    world = replace(world, initial_position_x_m=0.1, simulation_timestep_s=0.01, simulation_duration_s=0.1)
    run = run_simulation(bodybase=body, worldbase=world, save_render=False, artifacts_dir=tmp_path)
    assert run['model'].opt.timestep == 0.01
    assert len(run['telemetry']) == 11
    assert run['telemetry'][0]['position'] == 0.1
    assert run['data'].time == pytest.approx(0.1)
    assert run['data'].qpos[0] == pytest.approx(0.2)


@pytest.mark.parametrize('changes', [{'initial_velocity_ms': 1.3}, {'initial_position_x_m': 2}, {'wall_center_yz_m': (10, 0.5)}])
def test_inconsistent_joint_world_setup_rejected(changes):
    with pytest.raises(ValueError):
        compile_context_model(DEFAULT_MODEL_PATH, BodyBase.from_json(), replace(WorldBase.from_json(), **changes))


@pytest.mark.parametrize('name, distance', [('A', 0.36), ('B', 0.54), ('C', 0.25)])
def test_scenarios_theory_real_dynamics_and_independent_verification(scenario_runs, reports, name, distance):
    run, report = scenario_runs[name], reports[name]
    body, world = load_scenarios()[name]
    assert body.stopping_distance_m(world.initial_velocity_ms) == pytest.approx(distance)
    assert report['analytical_prediction']['stopping_distance_m'] == pytest.approx(distance)
    assert run['model'].body('carriage').mass[0] == body.mass_kg
    assert len(run['telemetry']) == 601
    assert report['software_execution'] == report['physics_simulation'] == 'PASS'
    assert report['safety_policy'] == 'stop_before_wall'
    assert report['physical_safety_task'] == report['safety_acceptance']['status'] == 'FAIL'
    assert report['safety_acceptance']['wall_collision_events'] == 1
    assert report['safety_acceptance']['checks']['completion_within_deadline'] == 'PASS'
    assert len(report['safety_acceptance']['failure_reasons']) == 3
    assert report['first_wall_contact']['velocity'] > 0
    brake, contact = report['braking_initiation'], report['first_wall_contact']
    assert brake['acceleration'] == pytest.approx(-body.max_force_n / body.mass_kg)
    deceleration = (brake['velocity'] - contact['velocity']) / (contact['time'] - brake['time'])
    assert deceleration == pytest.approx(body.max_deceleration_ms2, abs=1e-12)
    assert report['unintended_contact_points'] == 0
    independent = report['independent_safety_verification']
    assert independent['verification_execution'] == 'PASS'
    assert independent['effective_context_matches'] and independent['telemetry_matches']
    assert independent['safety_acceptance']['status'] == 'FAIL'
    assert sha256(run['artifacts_dir'] / 'effective_model.xml') == run['metadata']['effective_mjcf_sha256']


def test_same_controller_and_default_day2_trajectory_preserved(scenario_runs):
    historic = json.loads((ROOT / 'artifacts/day2/baseline/telemetry.json').read_text())
    assert scenario_runs['A']['telemetry'] == historic['samples']
    for run in scenario_runs.values():
        assert run['metadata']['controller'] == historic['metadata']['controller']
        assert run['metadata']['controller']['source_sha256'] == sha256(ROOT / 'robot/controller.py')


def test_clearance_threshold_changes_safety_without_changing_dynamics(tmp_path):
    body, world = BodyBase.from_json(), WorldBase.from_json()
    world = replace(world, initial_velocity_ms=0, simulation_duration_s=0.1)
    runs = [run_simulation(bodybase=body, worldbase=replace(world, minimum_clearance_m=gap),
                           controller=faulty_braking_controller, save_render=False, artifacts_dir=tmp_path / str(gap))
            for gap in (0.05, 2.0)]
    assert runs[0]['telemetry'] == runs[1]['telemetry']
    assert runs[0]['effective_model_xml'] == runs[1]['effective_model_xml']
    checks = [independently_verify_safety(run) for run in runs]
    assert checks[0]['physical_safety_task'] == 'PASS'
    assert checks[1]['physical_safety_task'] == 'FAIL'
    assert checks[1]['safety_acceptance']['checks']['minimum_clearance'] == 'FAIL'


def test_avoiding_contact_is_not_enough_and_speed_limit_is_strict(tmp_path):
    body = BodyBase.from_json()
    world = replace(WorldBase.from_json(), initial_velocity_ms=0.2)
    results = []
    for limit in (0.03, 0.2, 0.3):
        run = run_simulation(bodybase=body, worldbase=replace(world, max_final_speed_ms=limit),
                             controller=faulty_braking_controller, save_render=False, artifacts_dir=tmp_path / str(limit))
        independent = independently_verify_safety(run)
        report = failure_diagnostics(run, independent)
        assert report['first_wall_contact'] is None
        assert report['safety_acceptance']['checks']['minimum_clearance'] == 'PASS'
        results.append((run, report))
    assert [r['physical_safety_task'] for _, r in results] == ['FAIL', 'FAIL', 'PASS']
    assert all(run['telemetry'] == results[0][0]['telemetry'] for run, _ in results)


def test_completion_deadline_is_evaluated_from_runtime(tmp_path):
    world = replace(WorldBase.from_json(), initial_velocity_ms=0, simulation_duration_s=0.1, completion_deadline_s=0.05)
    run = run_simulation(worldbase=world, controller=faulty_braking_controller, save_render=False, artifacts_dir=tmp_path)
    verified = independently_verify_safety(run)
    assert verified['physical_safety_task'] == 'FAIL'
    assert verified['safety_acceptance']['checks']['completion_within_deadline'] == 'FAIL'
    assert verified['safety_acceptance']['checks']['final_speed'] == 'PASS'


def test_independent_geometry_query_does_not_clip_far_wall_distances(tmp_path):
    world = replace(WorldBase.from_json(), wall_position_x_m=20, initial_velocity_ms=0.2,
                    simulation_duration_s=0.1)
    run = run_simulation(worldbase=world, controller=faulty_braking_controller,
                         save_render=False, artifacts_dir=tmp_path)
    verified = independently_verify_safety(run)
    assert verified['verification_execution'] == 'PASS'
    assert verified['minimum_clearance_m'] > 10
    assert verified['safety_acceptance']['checks']['zero_wall_collision_events'] == 'PASS'


@pytest.mark.rendering
def test_changed_world_native_images_match_effective_model_and_telemetry(rendered_context, reports):
    run = rendered_context
    model = mujoco.MjModel.from_xml_string(run['effective_model_xml'])
    data = mujoco.MjData(model)
    frames = run['metadata']['rendering']['frames']
    for event in ('braking_initiation', 'first_wall_contact'):
        assert reports['C'][event]['step'] in [f['step'] for f in frames]
    with mujoco.Renderer(model, height=768, width=1024) as renderer:
        for frame in frames:
            sample = run['telemetry'][frame['step']]
            assert frame['time'] == sample['time']
            assert min(frame['visible_geom_pixels'].values()) > 20
            data.qpos[0], data.qvel[0], data.time = sample['position'], sample['velocity'], sample['time']
            mujoco.mj_forward(model, data)
            renderer.update_scene(data, camera='demo_camera')
            with Image.open(run['artifacts_dir'] / frame['path']) as image:
                np.testing.assert_array_equal(np.asarray(image), renderer.render())
