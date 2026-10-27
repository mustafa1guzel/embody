"""Day 2 failures must come from the actual controller and MuJoCo dynamics."""
from __future__ import annotations

import json

import mujoco
import numpy as np
from PIL import Image
import pytest

from core.day2 import diagnose_and_save, write_replay
from core.diagnostics import failure_diagnostics, independently_verify_safety, stopping_prediction
from core.simulation import DEFAULT_MODEL_PATH, ROOT, run_simulation, sha256
from core.verification import compare_runs
from robot.controller import BRAKING_THRESHOLD_M, faulty_braking_controller


@pytest.fixture
def model():
    return mujoco.MjModel.from_xml_path(str(DEFAULT_MODEL_PATH))


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    directory = tmp_path_factory.mktemp("day2-runs")
    return [run_simulation(controller=faulty_braking_controller, save_render=False,
                           artifacts_dir=directory / str(i)) for i in range(3)]


@pytest.fixture(scope="module")
def diagnosed(runs):
    return diagnose_and_save(runs[0])


@pytest.fixture(scope="module")
def rendered(tmp_path_factory):
    return run_simulation(controller=faulty_braking_controller,
                          artifacts_dir=tmp_path_factory.mktemp("day2-native"), render_interval_steps=40)


@pytest.mark.parametrize("gap, velocity, expected", [(0.121, 1.2, 0), (0.12, 1.2, -4),
                                                     (0.119, 1.2, -4), (0.1, 0, 0), (0.1, -0.2, 0)])
def test_threshold_is_surface_clearance_and_controller_only_changes_control(model, gap, velocity, expected):
    data = mujoco.MjData(model)
    data.qpos[0], data.qvel[0] = 1.77 - gap, velocity
    mujoco.mj_forward(model, data)
    before = (data.qpos.copy(), data.qvel.copy(), float(data.time))
    measured_gap = mujoco.mj_geomDistance(model, data, model.geom("front_bumper").id,
                                         model.geom("wall").id, 10, None)
    assert measured_gap == pytest.approx(gap, abs=1e-14)
    faulty_braking_controller(model, data)
    assert data.ctrl[0] == expected
    np.testing.assert_array_equal(data.qpos, before[0])
    np.testing.assert_array_equal(data.qvel, before[1])
    assert data.time == before[2]
    mujoco.mj_forward(model, data)
    assert data.qfrc_actuator[0] == expected
    assert data.actuator_force[0] == expected


def test_controller_reads_actual_wall_and_bumper_geometry(model):
    model.body("obstacle").pos[0] += 0.4
    model.geom("front_bumper").size[0] += 0.01
    data = mujoco.MjData(model)
    data.qvel[0] = 1.2
    data.qpos[0] = 1.65
    mujoco.mj_forward(model, data)
    faulty_braking_controller(model, data)
    assert data.ctrl[0] == 0  # The original hardcoded 1.77-x formula would brake.
    data.qpos[0] = 1.65 + 0.4 - 0.01
    mujoco.mj_forward(model, data)
    assert mujoco.mj_geomDistance(model, data, model.geom("front_bumper").id,
                                  model.geom("wall").id, 10, None) == pytest.approx(0.12)
    faulty_braking_controller(model, data)
    assert data.ctrl[0] == -4


def test_braking_uses_model_force_limits_and_changes_actual_velocity(model):
    # An isolated instance proves the command is derived from compiled limits.
    model.actuator_ctrlrange[0] = [-3, 3]
    model.actuator_forcerange[0] = [-2, 2]
    data = mujoco.MjData(model)
    data.qpos[0], data.qvel[0] = 1.66, 1.2
    mujoco.mj_forward(model, data)
    faulty_braking_controller(model, data)
    mujoco.mj_forward(model, data)
    assert data.ctrl[0] == data.qfrc_actuator[0] == -2
    assert data.qacc[0] == pytest.approx(-1)
    mujoco.mj_step(model, data)
    assert data.qvel[0] == pytest.approx(1.195)


def test_theory_predicts_failure_without_claiming_measurements():
    p = stopping_prediction(2, 4, 1.2, BRAKING_THRESHOLD_M)
    assert p["max_deceleration_mps2"] == 2
    assert p["stopping_distance_m"] == pytest.approx(0.36)
    assert p["distance_shortfall_m"] == pytest.approx(0.24)
    assert not p["stop_before_wall_predicted"]
    assert p["predicted_wall_surface_speed_mps"] == pytest.approx(np.sqrt(0.96))
    assert "not_simulator_measurement" in p["kind"]
    assert stopping_prediction(4, 4, 1.2, 0.12)["stopping_distance_m"] == pytest.approx(0.72)


@pytest.mark.parametrize("mass, force", [(0, 4), (2, 0), (-1, 4), (float("nan"), 4)])
def test_invalid_analytical_inputs_are_rejected(mass, force):
    with pytest.raises(ValueError):
        stopping_prediction(mass, force, 1.2, 0.12)


def test_actual_late_braking_and_wall_contact(runs, diagnosed):
    samples = runs[0]["telemetry"]
    braking, contact = diagnosed["braking_initiation"], diagnosed["first_wall_contact"]
    assert braking["time"] == pytest.approx((1.77 - 0.12) / 1.2, abs=1e-12)
    assert braking["velocity"] == pytest.approx(1.2)
    assert braking["wall_clearance"] == pytest.approx(0.12, abs=1e-12)
    assert samples[braking["step"] - 1]["control"] == 0
    assert braking["control"] == braking["generalized_actuator_force"] == -4
    assert contact["time"] > braking["time"]
    assert 0.9 < contact["velocity"] < braking["velocity"]
    assert contact["contacts"] and contact["wall_collision"]
    assert contact["wall_clearance"] < 0
    wall, bumper = runs[0]["model"].geom("wall").id, runs[0]["model"].geom("front_bumper").id
    for sample in samples:
        for c in sample["contacts"]:
            assert set(c["geom_ids"]) == {wall, bumper}
            assert {c["geom_1"], c["geom_2"]} == {"wall", "front_bumper"}
    for i in range(braking["step"], contact["step"]):
        assert samples[i]["wall_collision"] is False
        assert samples[i]["generalized_actuator_force"] == -4
        assert samples[i + 1]["velocity"] - samples[i]["velocity"] == pytest.approx(-2 * 0.005, abs=1e-12)
    assert samples[-1]["velocity"] < 0
    assert samples[-1]["control"] == 0
    assert diagnosed["minimum_observed_clearance_m"] > -0.01


def test_diagnostics_and_independent_safety_execution_are_saved(runs, diagnosed):
    out = runs[0]["artifacts_dir"]
    report = json.loads((out / "diagnostics.json").read_text())
    assert report == diagnosed
    assert report["software_execution"] == report["physics_simulation"] == "PASS"
    assert report["physical_safety_task"] == "FAIL"
    assert report["expected_contact_failure_reproduced"]
    assert report["controller"]["source_sha256"] == sha256(ROOT / "robot/controller.py")
    assert report["controller"]["function_sha256"]
    assert report["actual_available_braking_distance_m"] < report["analytical_prediction"]["stopping_distance_m"]
    independent = json.loads((out / "independent_safety_trace.json").read_text())
    assert len(independent["trace"]) == 601
    assert independent["verification_execution"] == "PASS"
    assert independent["physical_safety_task"] == "FAIL"
    assert independent["telemetry_matches"] and independent["contact_ids_match"]
    assert independent["first_wall_contact"]["velocity"] == report["first_wall_contact"]["velocity"]
    assert max(independent["max_abs_telemetry_differences"].values()) < 1e-12
    assert not independent["desired_clearance_satisfied"]


def test_low_speed_negative_control_is_classified_from_observations(tmp_path):
    run = run_simulation(controller=faulty_braking_controller, initial_velocity=0.2,
                         save_render=False, artifacts_dir=tmp_path)
    independent = independently_verify_safety(run)
    report = failure_diagnostics(run, independent)
    assert report["braking_initiation"] is None and report["first_wall_contact"] is None
    assert report["physical_safety_task"] == independent["physical_safety_task"] == "PASS"
    assert not report["expected_contact_failure_reproduced"]


def test_three_controller_runs_match_configuration_onset_contacts_and_telemetry(runs):
    assert len({r["metadata"]["run_id"] for r in runs}) == 3
    comparison = compare_runs(runs)
    assert comparison["pass"]
    assert comparison["absolute_tolerance"] == 1e-12
    assert all(error == 0 for error in comparison["max_abs_differences"].values())
    for run in runs[1:]:
        assert run["model"] is not runs[0]["model"]
        assert run["metadata"]["controller"] == runs[0]["metadata"]["controller"]
        assert run["metadata"]["configuration"] == runs[0]["metadata"]["configuration"]
        assert run["telemetry"] == runs[0]["telemetry"]


@pytest.mark.rendering
def test_native_braking_and_contact_frames_match_original_trajectory(rendered, runs, diagnosed):
    assert rendered["telemetry"] == runs[0]["telemetry"]
    frames = rendered["metadata"]["rendering"]["frames"]
    assert rendered["metadata"]["rendering"]["interval_steps"] == 40
    assert set(range(0, 601, 40)) <= {f["step"] for f in frames}
    assert diagnosed["braking_initiation"]["step"] in [f["step"] for f in frames]
    assert diagnosed["first_wall_contact"]["step"] in [f["step"] for f in frames]
    model = rendered["model"]
    data = mujoco.MjData(model)
    with mujoco.Renderer(model, height=768, width=1024) as renderer:
        for frame in frames:
            sample = rendered["telemetry"][frame["step"]]
            assert frame["time"] == sample["time"]
            assert frame["control"] == sample["control"]
            assert frame["wall_collision"] == sample["wall_collision"]
            assert min(frame["visible_geom_pixels"].values()) > 20
            data.qpos[0], data.qvel[0], data.time = sample["position"], sample["velocity"], sample["time"]
            mujoco.mj_forward(model, data)
            renderer.update_scene(data, camera="demo_camera")
            path = rendered["artifacts_dir"] / frame["path"]
            assert sha256(path) == frame["sha256"]
            with Image.open(path) as image:
                np.testing.assert_array_equal(np.asarray(image), renderer.render())
    replay = write_replay(rendered, diagnosed)
    assert replay["duration_s"] == pytest.approx(3, abs=1e-12)
    for name, index in replay["event_frame_indices"].items():
        assert replay["frames"][index]["step"] == replay["events"][name]
    assert json.loads((rendered["artifacts_dir"] / "replay_timeline.json").read_text()) == replay


@pytest.mark.parametrize("kwargs", [{"control": 1}, {"render_interval_steps": 0},
                                   {"render_interval_steps": 1.5}])
def test_ambiguous_or_invalid_experiment_options_rejected(tmp_path, kwargs):
    with pytest.raises(ValueError):
        run_simulation(controller=faulty_braking_controller, save_render=False, artifacts_dir=tmp_path, **kwargs)


def test_controlled_run_cannot_overwrite_day1_directory():
    with pytest.raises(ValueError, match="preserve Day 1"):
        run_simulation(controller=faulty_braking_controller, save_render=False)
