"""Transactional cross-domain tools, true measured diagnosis and explicit mocks."""
import copy,json
from pathlib import Path
from dataclasses import replace
import pytest
from ide_api.engineering import EngineeringService
from engineering.project import identity,identities,new_project,validate
from engineering.actions import execute_copy,check_operations
from engineering.agent import EngineeringTools
from engineering.plans import create_plan,review_plan,compile_plan,validate_plan
from engineering.diagnosis import diagnose
from engineering.store import Store
from core.agent.trace import ExecutionTrace,read_trace
from core.agent.models import MockModelAdapter,ModelTurn,ToolCall
from core.agent.orchestration import AgentOrchestrator
from devices.contracts import DeviceSpec
from devices.simulation import run,verify_dynamics

@pytest.fixture
def service(tmp_path):return EngineeringService(tmp_path/'engineering')


def test_changeset_requires_explicit_review_and_matches_independent_replay(service):
    before=service.current();sha=identity(before);ops=[{'kind':'create_object','primitive':'motor','id':'beam','parent':None},{'kind':'set_mass','target':'beam','mass_kg':.4},{'kind':'set_actuator_limit','target':'beam','limit':.3}]
    proposal=service.propose(sha,0,ops,'Explicit deterministic test proposal')
    assert service.current()==before and proposal['approval_status']=='PROPOSED_NOT_APPLIED'
    assert proposal['proposed_project']==validate(execute_copy(before,ops))
    with pytest.raises(ValueError):service.decide(sha,0,proposal['proposal_id'],'apply','')
    assert service.current()==before
    result=service.decide(sha,0,proposal['proposal_id'],'apply','APPLY REVIEWED ENGINEERING CHANGE')
    assert result['project']==proposal['proposed_project'] and identities(result['project'])['world']!=identities(before)['world']
    with pytest.raises(ValueError):service.edit(sha,0,[{'kind':'set_device_mass','mass_kg':.2}])
    assert service.current()==result['project']


def test_failed_dependency_and_rejection_do_not_partially_mutate(service):
    p=service.current();sha=identity(p)
    with pytest.raises(ValueError):service.edit(sha,0,[{'kind':'create_object','primitive':'box','id':'new','parent':None},{'kind':'set_mass','target':'missing','mass_kg':.4}])
    assert service.current()==p
    q=service.propose(sha,0,[{'kind':'set_device_mass','mass_kg':.5}],'For rejection')
    service.decide(sha,0,q['proposal_id'],'reject','REJECT ENGINEERING CHANGE');assert service.current()==p
    with pytest.raises(ValueError):service.decide(sha,0,q['proposal_id'],'apply','APPLY REVIEWED ENGINEERING CHANGE')

@pytest.mark.parametrize('op',[
 {'kind':'set_device_mass','mass_kg':float('inf')},
 {'kind':'set_device_mass','mass_kg':True},
 {'kind':'set_device_mass','mass_kg':0},
 {'op':'remove_wire','wire_id':'wire_1'},
 {'kind':'execute_controller','source':'print(1)'},
 {'kind':'set_device_mass','mass_kg':.2,'approval':'apply'},
 {'kind':'create_object','primitive':'box','id':'../../p','parent':None},
])
def test_invalid_operations_are_rejected_without_mutation(service,op):
    p=service.current()
    with pytest.raises((ValueError,TypeError,OverflowError)):service.propose(identity(p),0,[op],'Invalid test')
    assert service.current()==p


def test_batch_size_revision_bool_and_untrusted_status_are_blocked(service):
    p=service.current()
    with pytest.raises(ValueError):service.edit(identity(p),False,[{'kind':'set_device_mass','mass_kg':.2}])
    with pytest.raises(ValueError):check_operations([{'kind':'set_device_mass','mass_kg':.2}]*17)
    with pytest.raises(ValueError):check_operations('[]')


def test_circuit_replay_has_stable_generated_ids_and_invalid_electrical_apply_blocked(service):
    p=service.current();sha=identity(p);ops=[{'kind':'connect_pins','a':{'component':'sensor','pin':'ECHO'},'b':{'component':'board','pin':'IO19'}}]
    a=execute_copy(p,ops);b=execute_copy(p,ops);assert a==b
    q=service.propose(sha,0,ops,'Deliberate graph defect for negative validation')
    assert q['approval_status']=='INVALID_REVIEW_ONLY' and q['validation']['electrical']['errors']>0
    with pytest.raises(ValueError):service.decide(sha,0,q['proposal_id'],'apply','APPLY REVIEWED ENGINEERING CHANGE')
    assert service.current()==p


def test_project_save_reload_safe_restore_and_symlink_paths(service,tmp_path):
    p=service.current();key=service.save(identity(p),0)['key'];after=service.edit(identity(p),0,[{'kind':'set_device_mass','mass_kg':.5}])
    restored=service.restore(identity(after),1,key);assert restored['device_spec']==p['device_spec'] and restored['revision']==2
    assert EngineeringService(service.root).current()==restored
    with pytest.raises(ValueError):service.projects.get('../head')
    (tmp_path/'linked').symlink_to(service.root,target_is_directory=True)
    with pytest.raises(ValueError):EngineeringService(tmp_path/'linked')

@pytest.mark.parametrize('goal,family,supported',[
 ('Build a sensor-controlled barrier.','sensor_barrier',True),
 ('Design a simple robotic gripper.','gripper',True),
 ('Create AI-powered smart glasses with a camera, microphone, speaker and voice assistant.','smart_glasses',False),
])
def test_three_actual_planning_cases_compile_only_supported_portions(service,goal,family,supported):
    before=service.current();p=service.plan(goal);assert p['plan']['family']==family
    assert service.current()['world']==before['world'] and service.current()['design_plans'][0]['sha256']==p['plan_id']
    with pytest.raises(ValueError):service.compile_plan(p['plan_id'])
    reviewed=service.review_plan(p['plan_id']);batch=service.compile_plan(reviewed['plan_id'])
    assert bool(batch['ordered_operations'])==supported and batch['blocked_steps']==reviewed['plan']['blocked_steps'] and batch['automatic_application'] is False
    assert batch['base_project_sha256']==identity(service.current())
    if family=='smart_glasses':
        assert all(c['availability']=='UNAVAILABLE' for c in p['plan']['component_candidates'])
        assert all(s in p['plan']['unknowns'] for s in ('Battery','Thermal','RF','Optics'))
    current=service.current();service.edit(identity(current),current['revision'],[{'kind':'set_device_mass','mass_kg':.5}])
    with pytest.raises(ValueError):service.compile_plan(reviewed['plan_id'])


def test_real_heavy_barrier_diagnosis_and_fresh_load_correction(tmp_path):
    p=new_project();spec=DeviceSpec();heavy=replace(spec,mechanical=replace(spec.mechanical,mass_kg=.5));p['device_spec']=json.loads(json.dumps(heavy.to_dict()))
    failure=run(p['circuit'],heavy,tmp_path/'heavy');assert failure['execution']=='COMPLETED' and not failure['acceptance']['checks']['opening_deadline']
    diagnosis=diagnose(p,failure);assert any(f['category']=='ACTUATOR_CAPABILITY' for f in diagnosis['findings']) and diagnosis['software_only_fix']=='NOT_ESTABLISHED'
    assert verify_dynamics(failure)['status']=='PASS'
    corrected=run(p['circuit'],spec,tmp_path/'corrected');assert corrected['status']=='VERIFIED_IN_SIMULATION'
    assert heavy.requirements==spec.requirements and verify_dynamics(corrected)['status']=='PASS'


def test_existing_orchestrator_mock_is_labelled_and_has_no_apply_tool(service,tmp_path):
    p=service.current();trace=ExecutionTrace(tmp_path/'mock_trace.jsonl',model_mode='mock');tools=EngineeringTools(service,trace)
    args={'expected_sha256':identity(p),'expected_revision':0,'operations':[{'kind':'set_device_mass','mass_kg':.035}],'explanation':'Deterministic fixture, not genuine AI reasoning.'}
    model=MockModelAdapter([ModelTurn(tool_calls=(ToolCall('inspect','inspect_engineering',{}),)),ModelTurn(tool_calls=(ToolCall('propose','propose_engineering_change',args),))])
    report=AgentOrchestrator(model,tools,trace,max_turns=2,max_tool_calls=2).run('Mock inspect/propose test; no model request.')
    assert report['orchestration_status']=='LIMIT_REACHED' and report['tool_calls']==2 and service.current()==p
    assert {s['name'] for s in tools.schemas}=={'inspect_engineering','propose_engineering_change'}
    assert not tools.dispatch('apply',{})['ok']
    assert not tools.dispatch('propose_engineering_change',{**args,'operations':[{'op':'remove_wire'}]})['ok']
    assert not tools.dispatch('inspect_engineering',{'source':'read everything'})['ok']
    assert read_trace(tmp_path/'mock_trace.jsonl')


def test_composable_dynamic_sphere_and_force_units_are_validated(service):
    p=service.current();ops=[{'kind':'create_object','primitive':'sphere','id':'ball','parent':None},{'kind':'set_body_kind','target':'ball','behavior':'dynamic'},{'kind':'set_mass','target':'ball','mass_kg':.1},{'kind':'create_joint','target':'ball','joint':{'kind':'free','axis':[0,0,1],'range':[-1,1],'initial_position':0,'initial_velocity':0,'damping':0}}]
    preview=service.propose(identity(p),0,ops,'Explicit supported dynamic sphere composition')
    assert preview['validation']['world']=='VALID_COMPILED' and service.current()==p
    bad=[{'kind':'create_object','primitive':'motor','id':'bad_motor','parent':None},{'kind':'set_actuator','target':'bad_motor','actuator':{'unit':'N','command':0,'limit':.1}}]
    with pytest.raises(ValueError,match='correct SI unit'):service.propose(identity(p),0,bad,'Wrong force dimension must fail')


def test_failed_atomic_head_write_never_claims_or_commits_application(service,monkeypatch):
    p=service.current();sha=identity(p);q=service.propose(sha,0,[{'kind':'set_device_mass','mass_kg':.5}],'Failure-injection review')
    def fail(*args):raise OSError('TEST deliberate head-write interruption')
    monkeypatch.setattr('ide_api.engineering.os.replace',fail)
    with pytest.raises(OSError):service.decide(sha,0,q['proposal_id'],'apply','APPLY REVIEWED ENGINEERING CHANGE')
    assert service.current()==p
    authorization=json.loads((service.root/'decisions'/q['proposal_id']).read_text());assert authorization['decision']=='APPROVED_FOR_DATA_COMMIT'
    assert 'APPLIED' not in authorization['decision']


def test_replanning_preserves_monotonic_versions_and_immutable_old_plan(service):
    first=service.plan('Build a sensor-controlled barrier.')
    reviewed=service.review_plan(first['plan_id'])
    replacement=service.plan('Build a sensor-controlled barrier with reviewed requirements.')
    assert first['plan']['revision']==0 and reviewed['plan']['revision']==1 and replacement['plan']['revision']==2
    assert replacement['plan']['status']=='DRAFT_FOR_REVIEW'
    assert service.plans.get(first['plan_id'])==first['plan']
    with pytest.raises(ValueError):service.review_plan(reviewed['plan_id'])
    with pytest.raises(ValueError):service.compile_plan(replacement['plan_id'])
    assert service.review_plan(replacement['plan_id'])['plan']['revision']==3
