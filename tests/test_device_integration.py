"""Genuine MuJoCo tests; outputs remain explicit trusted reference-model evidence."""
from dataclasses import replace
import copy
import json
import mujoco
import numpy as np
import pytest
from hardware.template import barrier
from hardware.assemblies import endpoint,connect,identity
from devices.contracts import DeviceSpec
from devices.controller import Reading,ReferenceLogic
from devices.simulation import run,compile_model,RaySensor,object_position,verify_dynamics,verify_reconstruction,analytical


@pytest.fixture(scope='module')
def reference(tmp_path_factory):return run(barrier(),output=tmp_path_factory.mktemp('device-evidence')/'reference')


def test_cross_domain_contract_native_dynamics_and_acceptance(reference):
    r=reference;assert r['status']=='VERIFIED_IN_SIMULATION'
    assert r['execution']=='COMPLETED' and len(r['samples'])==4001
    assert r['assembly_sha256']==identity(barrier()) and len(r['contract_sha256'])==64
    assert all(r['acceptance']['checks'].values())
    assert max(s['q_rad'] for s in r['samples'])>1.3
    assert r['independent_dynamics']['status']=='PASS' and r['independent_reconstruction']['status']=='PASS'
    assert r['model_api_requests']==r['vm_executions']==0
    assert r['electrical']['status']=='UNKNOWN'


def test_sensor_native_geometry_sampling_latency_and_environment_coupling(reference):
    r=reference;spec=DeviceSpec();history=r['sensor_readings']
    assert history[1]['sampled_s']==pytest.approx(.07) and history[0]['delivered_s']==.02
    for reading in history:
        # Native ray intersects the FRONT surface of the moving object, not its center.
        expected=round((object_position(reading['sampled_s'],spec.environment)-.04)/.001)*.001
        assert reading['distance_m']==pytest.approx(expected)
    assert r['samples'][9]['distance_m'] is None and r['samples'][10]['distance_m']==.76
    assert min(s['distance_m'] for s in r['samples'] if s['distance_m'] is not None)<.23
    assert len({s['sensor_sequence'] for s in r['samples']})<len(r['samples'])


def test_compiled_mass_inertia_generalized_force_and_joint_limits():
    s=DeviceSpec();m,_,p=compile_model(s)
    assert p['mass_kg']==pytest.approx(.035) and m.nq==m.nv==m.nu==1
    assert p['generalized_inertia_initial_kg_m2']==pytest.approx(.035*(.24**2/3+.016**2/12))
    assert [r['generalized_torque_nm'] for r in p['force_probes']]==[-.12,0,.12]
    heavier=replace(s,mechanical=replace(s.mechanical,mass_kg=.07))
    m2,_,p2=compile_model(heavier)
    np.testing.assert_allclose(m2.body('barrier').inertia,m.body('barrier').inertia*2)


def test_invalid_electrical_connection_blocks_before_compilation(monkeypatch,tmp_path):
    def forbidden(*a,**k):raise AssertionError('Invalid wiring must not run physics')
    monkeypatch.setattr('devices.simulation.compile_model',forbidden)
    bad=connect(barrier(),endpoint('sensor','ECHO'),endpoint('board','IO19'))
    r=run(bad,output=tmp_path/'blocked')
    assert r['status']=='INVALID' and r['execution']=='NOT_RUN' and 'samples' not in r
    assert (tmp_path/'blocked/result.json').is_file()


def test_graph_that_passes_static_rules_cannot_silently_bind_wrong_signal():
    a=barrier();a['components'][0]['roles']={'IO18':'pwm','IO19':'input','IO23':'output'}
    r=run(a);assert r['status']=='BLOCKED' and r['execution']=='NOT_RUN'


def test_meaningful_control_failure_and_reference_correction(reference,tmp_path):
    s=DeviceSpec();broken=replace(s,logic=replace(s.logic,close_while_near=True))
    r=run(barrier(),broken,output=tmp_path/'control-defect')
    assert r['status']=='MEASURED_REQUIREMENT_FAILURE'
    assert 'no_closing_on_near_object' in r['acceptance']['failed_requirements']
    assert r['acceptance']['unsafe_closing_samples']>0
    assert reference['acceptance']['unsafe_closing_samples']==0
    assert r['compiled']['model_sha256']==reference['compiled']['model_sha256']
    assert r['contract_sha256']!=reference['contract_sha256']


def test_mechanical_insufficiency_is_measured_without_unsound_guard_proof(tmp_path):
    s=DeviceSpec();s=replace(s,mechanical=replace(s.mechanical,mass_kg=2.,torque_limit_nm=.005))
    guard=analytical(s);assert guard['status']=='UNKNOWN' and guard['ideal_rigid_stop_deadline_bound_fails']
    r=run(barrier(),s,output=tmp_path/'weak-actuator')
    assert r['execution']=='COMPLETED' and r['status']=='MEASURED_REQUIREMENT_FAILURE'
    assert 'opening_deadline' in r['acceptance']['failed_requirements']
    assert r['acceptance']['peak_measured_torque_nm']==.005 and r['acceptance']['first_open_s'] is None
    assert guard['initial_gravity_torque_nm']>2.


def test_sensor_invalid_measurements_fault_open(tmp_path):
    s=DeviceSpec();s=replace(s,sensor=replace(s.sensor,direction=(-1.,0.,0.)))
    r=run(barrier(),s,output=tmp_path/'invalid-sensor')
    assert any(x['distance_m'] is None for x in r['sensor_readings'])
    assert any(x['state']=='FAULT' and x['target_rad']==1.4 for x in r['samples'])
    assert 'no_fault' in r['acceptance']['failed_requirements']


def test_debounce_hysteresis_and_stale_fault_are_stateful():
    c=ReferenceLogic(DeviceSpec().logic)
    def reading(i,t,d):return Reading(i,t,t,d,0,'TEST_INPUT_FIXTURE')
    assert c.update(0,reading(0,0,.3),0).state=='IDLE'
    assert c.update(.02,reading(0,0,.3),0).state=='IDLE' # held sample is not a second measurement
    assert c.update(.08,reading(1,.07,.3),0).state=='OBJECT_DETECTED'
    assert c.update(.1,reading(1,.07,.3),0).state=='OPENING'
    assert c.update(.2,reading(2,.14,.5),1.4).state=='OPEN'
    assert c.update(.6,None,1.4).state=='FAULT'


@pytest.mark.parametrize('which',['force','pose','state','distance'])
def test_fresh_verification_detects_corrupt_measured_evidence(reference,which):
    r=copy.deepcopy(reference)
    if which=='force':r['samples'][500]['generalized_torque_nm']+=.01
    elif which=='pose':r['samples'][500]['geom_poses'][2]['position'][0]+=.01
    elif which=='state':r['samples'][500]['q_rad']+=.01
    else:r['samples'][500]['distance_m']=2.
    with pytest.raises((ValueError,AssertionError)):
        verify_reconstruction(r) if which in ('force','pose') else verify_dynamics(r)


def test_device_contract_rejects_code_paths_unknown_fields_and_nonfinite_values():
    for key,value in [('mechanical',{'source':'untrusted.py'}),('logic',{'update_s':.0001})]:
        raw=DeviceSpec().to_dict();raw[key].update(value)
        with pytest.raises(ValueError):DeviceSpec.from_dict(raw)
    raw=DeviceSpec().to_dict();raw['sensor']['direction']=[0,0,0]
    with pytest.raises(ValueError):DeviceSpec.from_dict(raw)


def test_deterministic_goal_plan_binds_real_netlist_and_threshold_without_execution():
    from devices.planner import plan
    p=plan('Build a sensor barrier that opens within 40 cm of an object and closes afterward.')
    assert p['status']=='PLAN_FOR_REVIEW' and p['model_requests']==0
    assert p['diagnostics']['errors']==0 and p['assembly_sha256']==identity(barrier())
    assert p['spec']['logic']['threshold_m']==.4
    with pytest.raises(ValueError):plan('Build a drone')
    with pytest.raises(ValueError):plan('Build sensor barrier open close within 10 m')
    raw=DeviceSpec().to_dict();raw['mechanical']['mass_kg']=True
    with pytest.raises(ValueError):DeviceSpec.from_dict(raw)
    raw=DeviceSpec().to_dict();raw['mechanical']['mass_kg']=float('nan')
    with pytest.raises(ValueError):DeviceSpec.from_dict(raw)


def test_evidence_is_real_write_once_and_json_round_trip(reference,tmp_path):
    a=barrier();bad=connect(a,endpoint('sensor','ECHO'),endpoint('board','IO19'))
    folder=tmp_path/'once';r=run(bad,output=folder)
    assert json.loads((folder/'result.json').read_text())['assembly_sha256']==identity(bad)
    with pytest.raises(FileExistsError):run(bad,output=folder)
    assert verify_reconstruction(json.loads(json.dumps(reference)))['status']=='PASS'
