"""Hand arithmetic, generated bounds and genuine trusted MuJoCo probes; no VM."""
from dataclasses import replace
import json
import math
import random
import xml.etree.ElementTree as ET
import mujoco
import pytest
from core.day3 import load_scenarios
from core.simulation import DEFAULT_MODEL_PATH, compile_context_model
from physics.analytical import stopping_bounds
from physics.contracts import PhysicsContract, canonical, UNITS
from physics.extraction import extract_contract
from physics.guard import assess_task, assess_program_source
from physics.reports import impossible_fixture


@pytest.fixture(scope='module')
def contract():
    return extract_contract('A')


@pytest.mark.parametrize('scenario,mass,speed,distance,deceleration', [
    ('A', 2, 1.2, .36, 2), ('B', 3, 1.2, .54, 4/3), ('C', 2, 1, .25, 2)])
def test_authoritative_contract_and_hand_calculated_references(scenario, mass, speed, distance, deceleration):
    c = extract_contract(scenario)
    assert c.mass_kg == c.generalized_inertia_kg == mass
    assert c.initial_velocity_mps == speed and c.braking_force_n == 4
    assert all(value for _, value in c.checks)
    result = assess_task(c)
    assert result['status'] == 'CONDITIONALLY_FEASIBLE'
    assert result['bounds']['continuous_zero_stop_m'] == pytest.approx(distance, abs=1e-15)
    assert result['bounds']['deceleration_mps2'] == deceleration
    assert c.wall_center_m[0]-c.wall_near_x_m == pytest.approx(c.wall_half_size_m[0])
    assert c.initial_clearance_m == pytest.approx(c.wall_near_x_m-c.initial_position_m-c.bumper_front_offset_m)
    assert UNITS['force'] == 'N' and UNITS['mass'] == 'kg' and UNITS['work'] == 'J'


def test_serialization_immutability_and_identity(contract):
    c = PhysicsContract.from_dict(json.loads(canonical(contract.to_dict())))
    assert c == contract and c.identity == contract.identity
    assert canonical(c.to_dict()) == canonical(contract.to_dict())
    with pytest.raises(AttributeError):
        c.mass_kg = 3
    assert isinstance(c.checks, tuple) and isinstance(c.wall_center_m, tuple)
    assert extract_contract('B').identity != c.identity
    assert replace(c, controller_sha256='a'*64).identity != c.identity
    assert replace(c, model_sha256='b'*64).identity != c.identity
    assert replace(c, scenario_id='different').identity != c.identity
    assert replace(c, timestep_s=.01).identity != c.identity


@pytest.mark.parametrize('field,value', [
    ('mass_kg', 0), ('mass_kg', -1), ('generalized_inertia_kg', 0),
    ('mass_kg', math.nan), ('timestep_s', 0), ('timestep_s', -1), ('deadline_s', math.inf), ('duration_s', .003),
    ('initial_velocity_mps', float('-inf')), ('braking_force_n', -1),
    ('minimum_clearance_m', -.01), ('distance_tolerance_m', .01), ('numeric_tolerance', 0),
    ('frame', 'unknown'), ('axis_world', (2, 0, 0)), ('wall_half_size_m', (-1, 1, 1)),
    ('wall_near_x_m', 100), ('initial_clearance_m', 100), ('control_range', (1, 4)),
    ('scalar_force_range_n', (-4, -1)), ('controller_sha256', 'no hash'), ('checks', ()),
    ('uncertainties', (('mass_kg', -1, 3),)), ('uncertainties', (('force_n', 5, 6),)),
    ('uncertainties', (('unknown', 1, 2),)), ('initial_velocity_mps', True),
])
def test_invalid_contract_rejected(contract, field, value):
    with pytest.raises(ValueError):
        replace(contract, **{field: value})


def test_uncertainty_ranges_valid_but_not_silently_certified(contract):
    c = replace(contract, uncertainties=(('mass_kg', 1.9, 2.1), ('force_n', 3.9, 4.1)))
    assert assess_task(c)['status'] == 'UNKNOWN'
    with pytest.raises(ValueError):
        replace(c, uncertainties=(('mass_kg', 2.1, 1.9),))


@pytest.mark.parametrize('v,status', [(0, 'CONDITIONALLY_FEASIBLE'), (-.1, 'UNKNOWN'), (100, 'UNKNOWN')])
def test_velocity_envelope(contract, v, status):
    assert assess_task(contract, velocity_mps=v)['status'] == status


@pytest.mark.parametrize('kwargs', [{'velocity_mps': math.nan}, {'reaction_delay_s': -1},
                                   {'remaining_time_s': math.inf}, {'contact_present': 'no'}])
def test_invalid_analysis_state_serializable_unknown(contract, kwargs):
    result = assess_task(contract, **kwargs)
    assert result['status'] == 'UNKNOWN'
    canonical(result)


def test_zero_authority_missing_assumptions_contact_and_deadline(contract):
    c = replace(contract, braking_force_n=0, control_range=(0, 0), scalar_force_range_n=(0, 0), provenance_kind='analytical_fixture')
    assert assess_task(c)['status'] == 'PROVEN_INFEASIBLE'
    assert assess_task(c, velocity_mps=0)['status'] == 'CONDITIONALLY_FEASIBLE'
    assert assess_task(replace(contract, checks=(('something_else', True),)))['status'] == 'UNKNOWN'
    assert assess_task(contract, contact_present=True)['status'] == 'UNKNOWN'
    assert assess_task(contract, remaining_time_s=.1)['status'] == 'PROVEN_INFEASIBLE'
    assert assess_task(replace(contract, deadline_s=1))['status'] == 'PROVEN_INFEASIBLE'


def test_exact_discrete_hand_example_and_delay_not_double_counted():
    # m=2,F=4,v=1,h=.1 -> v=.8,.6,.4,.2,0; travel=.20m vs continuous .25m.
    b = stopping_bounds(2, 4, 1, .1, .03)
    assert b['continuous_zero_stop_m'] == .25
    assert b['discrete_zero_stop_m'] == pytest.approx(.20)
    assert b['zero_stop_time_s'] == .5
    assert b['delay_distance_m'] == 0
    delayed = stopping_bounds(2, 4, 1, .1, .03, reaction_delay_s=.11)
    assert delayed['delay_steps'] == 2
    assert delayed['constructive_required_motion_m'] == pytest.approx(.40)
    assert delayed['continuous_required_motion_m'] == pytest.approx(.36)
    assert delayed['conservative_discrete_motion_m'] == pytest.approx(.45)


def test_strict_final_tolerance_necessary_bound_is_not_zero_stop_distance():
    b = stopping_bounds(2, 4, .08, .005, .03)
    assert b['necessary_travel_m'] < b['discrete_zero_stop_m'] < b['continuous_zero_stop_m']


@pytest.mark.parametrize('index,value', [(0, 0), (0, -1), (1, 0), (1, float('inf')),
                                       (2, -.1), (2, float('nan')), (3, 0), (4, 0)])
def test_invalid_equation_inputs(index, value):
    args = [2, 4, 1.2, .005, .03]; args[index] = value
    with pytest.raises(ValueError):
        stopping_bounds(*args)


def test_directed_numerical_bounds_and_explicit_delays(contract):
    b = stopping_bounds(2, 4, 1.2, .005, .03)
    assert b['necessary_motion_lower_bound_m'] <= b['necessary_required_motion_m']
    assert b['constructive_motion_upper_bound_m'] >= b['constructive_required_motion_m']
    assert b['constructive_time_upper_bound_s'] >= b['zero_stop_time_s']
    assert assess_task(contract, reaction_delay_s=3)['status'] == 'PROVEN_INFEASIBLE'
    tiny = replace(contract, braking_force_n=1e-300, control_range=(-1e-300, 1e-300), scalar_force_range_n=(-1e-300, 1e-300))
    assert assess_task(tiny)['status'] == 'UNKNOWN'
    with pytest.raises(ValueError):
        stopping_bounds(1e-300, 1e300, 1, .01, .03)


def test_dimensional_similarity_time_and_length_scaling():
    # N/kg has dimensions L/T². Scale lengths by 3 and times by 2;
    # v scales 3/2, a scales 3/4, distance by 3, stopping time by 2.
    base = stopping_bounds(2, 4, 1, .01, .03)
    scaled = stopping_bounds(2, 3, 1.5, .02, .045)
    assert scaled['continuous_zero_stop_m'] == pytest.approx(3*base['continuous_zero_stop_m'])
    assert scaled['discrete_zero_stop_m'] == pytest.approx(3*base['discrete_zero_stop_m'])
    assert scaled['zero_stop_time_s'] == pytest.approx(2*base['zero_stop_time_s'])


def test_generated_bounds_and_constructive_controls():
    rng = random.Random(829)
    for _ in range(300):
        m, f, v, h = rng.uniform(.1, 5), rng.uniform(.5, 20), rng.uniform(.01, 3), rng.uniform(.001, .05)
        b = stopping_bounds(m, f, v, h, .03)
        assert 0 <= b['necessary_travel_m'] <= b['discrete_zero_stop_m']+1e-12
        assert b['discrete_zero_stop_m'] <= b['continuous_zero_stop_m']+1e-12
        # Independent explicit sequence, including fractional last command.
        speed, distance = v, 0.0
        for _ in range(math.ceil(v/(f/m*h))):
            command = min(f, m*speed/h)
            assert 0 <= command <= f
            speed = max(0, speed-h*command/m)
            distance += h*speed
        assert distance == pytest.approx(b['discrete_zero_stop_m'], abs=1e-11)
        assert speed < 1e-11
        # SI similarity: scale F and m together, dynamics unchanged.
        scaled = stopping_bounds(3*m, 3*f, v, h, .03)
        assert scaled['continuous_zero_stop_m'] == pytest.approx(b['continuous_zero_stop_m'])


@pytest.mark.parametrize('scenario', ['A', 'B', 'C'])
def test_trusted_mujoco_fixed_force_matches_derived_discrete_stop(scenario):
    body, world = load_scenarios()[scenario]
    m, _ = compile_context_model(DEFAULT_MODEL_PATH, body, world)
    d = mujoco.MjData(m); d.qvel[0] = world.initial_velocity_ms
    c = extract_contract(scenario); bound = assess_task(c)['bounds']; count = 0
    while d.qvel[0] > 1e-12:
        old_v, old_x = float(d.qvel[0]), float(d.qpos[0])
        d.ctrl[0] = -min(c.braking_force_n, c.generalized_inertia_kg*old_v/c.timestep_s)
        mujoco.mj_step(m, d); count += 1
        assert float(d.qpos[0]) == pytest.approx(old_x+c.timestep_s*float(d.qvel[0]), abs=1e-14)
        assert d.ncon == 0
    assert float(d.qpos[0]) == pytest.approx(bound['discrete_zero_stop_m'], abs=2e-14)
    assert count*c.timestep_s == pytest.approx(bound['zero_stop_time_s'], abs=1e-12)


def test_impossible_fixture_and_tolerance_boundaries(contract):
    fixture = impossible_fixture(contract)
    assert fixture['analytical_feasibility']['status'] == 'PROVEN_INFEASIBLE'
    assert fixture['physics_contract']['scenario_id'] == 'analytical_impossible'
    result = assess_task(contract); boundary = result['bounds']['necessary_clearance_m']
    assert assess_task(contract, clearance_m=boundary)['status'] == 'UNKNOWN'
    assert assess_task(contract, clearance_m=boundary-1e-8)['status'] == 'PROVEN_INFEASIBLE'
    assert assess_task(contract, clearance_m=.049)['status'] == 'PROVEN_VIOLATION'
    assert assess_task(contract, clearance_m=.05-5e-13)['status'] != 'PROVEN_VIOLATION'


@pytest.mark.parametrize('mutation', ['gear', 'gain', 'damping', 'armature', 'integrator', 'gravity', 'margin', 'bias', 'spring'])
def test_unsupported_physics_never_conditionally_certified(mutation):
    body, world = load_scenarios()['A']; _, xml = compile_context_model(DEFAULT_MODEL_PATH, body, world)
    root = ET.fromstring(xml)
    if mutation == 'gear': root.find('./actuator/motor').set('gear', '2')
    if mutation == 'gain':
        motor = root.find('./actuator/motor'); motor.tag = 'general'; motor.set('gainprm', '2')
    if mutation == 'bias':
        motor = root.find('./actuator/motor'); motor.tag = 'general'; motor.set('biastype', 'affine'); motor.set('biasprm', '1 0 0')
    if mutation in ('damping', 'armature'): root.find('.//joint').set(mutation, '.1')
    if mutation == 'spring': root.find('.//joint').set('stiffness', '1')
    if mutation == 'integrator': root.find('./option').set('integrator', 'RK4')
    if mutation == 'gravity': root.find('./option').set('gravity', '1 0 -9.81')
    if mutation == 'margin': root.find('./default/geom').set('margin', '.01')
    c = extract_contract('A', model_xml=ET.tostring(root, encoding='unicode'))
    assert assess_task(c)['status'] == 'UNKNOWN'


def test_source_is_opaque_never_executed(contract, tmp_path):
    marker = tmp_path/'executed'
    source = f"from pathlib import Path\nPath({str(marker)!r}).write_text('bad')\nraise RuntimeError('executed')"
    assert assess_program_source(source, contract)['status'] == 'UNKNOWN'
    assert not marker.exists()
