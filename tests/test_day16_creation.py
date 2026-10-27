"""Actual empty construction, native control, concepts and interruption boundaries."""
import copy,json
from pathlib import Path
import pytest
from engineering.creation import CreationManager
from engineering.requirements import interpret,DEFAULTS
from engineering.synthesis import empty_project,recipe,build_copy
from engineering.project import identity
from engineering.created_simulation import run,compile_created,verify
from engineering.creation_tools import CreationTools
from engineering.diagnosis import diagnose
from core.agent.trace import ExecutionTrace
from core.agent.models import MockModelAdapter,ModelTurn,ToolCall
from core.agent.orchestration import AgentOrchestrator
from ide_api.engineering import EngineeringService
from physics.contracts import digest

def proposal(manager,request='Build a sensor-controlled barrier.',parameters=None):return manager.start(request,parameters)
def build(manager,p):return manager.decide(p['proposal_id'],p['base_sha256'],p['base_revision'],'build','BUILD REVIEWED SUPPORTED PROJECT')['project']

def test_empty_project_independent_identity_atomic_build_and_restart(tmp_path):
    m=CreationManager(tmp_path/'registry');a=proposal(m);b=proposal(m)
    assert a['project_id']!=b['project_id'] and a['initial_project']['world']['objects']==a['initial_project']['circuit']['components']==[]
    assert not m.active() and m.project(a['project_id']).current()['revision']==0
    assert all(1<=len(batch)<=16 for batch in a['batches']) and len(a['batches'])<=16
    with pytest.raises(ValueError):m.decide(a['proposal_id'],a['base_sha256'],0,'build','YES')
    result=build(m,a);assert len(result['world']['objects'])==7 and len(result['circuit']['components'])==6 and len(result['circuit']['wires'])==12
    assert CreationManager(m.root).active().current()==result and m.project(b['project_id']).current()==b['initial_project']
    assert result['creation']['empty_project_sha256']==a['base_sha256']

@pytest.mark.parametrize('description,params',[
 ('Build a robotic gripper.',None),('Build a barrier and smart glasses.',None),('Build a camera barrier.',None),
 ('Build a barrier.',{'mass_kg':0}),('Build a barrier.',{'mass_kg':True}),('Build a barrier.',{'mass_kg':float('nan')}),('Build a barrier.',{'source':'print(1)'}),
])
def test_invalid_requirements_create_no_projects(tmp_path,description,params):
    m=CreationManager(tmp_path/'registry')
    with pytest.raises(ValueError):m.start(description,params)
    assert m.list_projects()==[]

def test_stale_rejection_duplicate_and_malformed_batches(tmp_path):
    m=CreationManager(tmp_path/'registry');p=proposal(m);svc=m.project(p['project_id'])
    with pytest.raises(ValueError):m.decide(p['proposal_id'],'f'*64,0,'build','BUILD REVIEWED SUPPORTED PROJECT')
    rejected=m.decide(p['proposal_id'],p['base_sha256'],0,'reject','REJECT DEVICE CREATION');assert rejected['project']==p['initial_project']
    with pytest.raises(FileExistsError):build(m,p)
    batches=copy.deepcopy(p['batches']);batches[0].append(batches[0][0])
    with pytest.raises(ValueError):build_copy(p['initial_project'],batches,p['metadata'])
    batches=copy.deepcopy(p['batches']);batches[0][0]={'kind':'execute_source','source':'print(1)'}
    with pytest.raises(ValueError):build_copy(p['initial_project'],batches,p['metadata'])
    assert svc.current()==p['initial_project']

def test_interrupted_atomic_build_never_records_success_or_partial_objects(tmp_path,monkeypatch):
    m=CreationManager(tmp_path/'registry');p=proposal(m)
    def fail(*args):raise OSError('TEST interrupted atomic head')
    with monkeypatch.context() as patch:
        patch.setattr('ide_api.engineering.os.replace',fail)
        with pytest.raises(ValueError,match='interrupted'):build(m,p)
    assert m.project(p['project_id']).current()==p['initial_project'] and m.active() is None
    decisions=list((m.root/'projects'/p['project_id']).glob('creation_decision_*'));assert len(decisions)==1 and json.loads(decisions[0].read_text())['decision']=='APPROVED_FOR_ATOMIC_BUILD'
    with pytest.raises(FileExistsError):build(m,p)

def test_real_generated_barrier_two_models_failure_repair_and_sensor_geometry(tmp_path):
    m=CreationManager(tmp_path/'registry');a=build(m,proposal(m));b=build(m,proposal(m,parameters={'span_m':.3,'torque_nm':.17,'height_m':.22}))
    ar=run(a,tmp_path/'a',False);br=run(b,tmp_path/'b',False)
    assert ar['status']==br['status']=='VERIFIED_IN_SIMULATION' and ar['compiled']['model_sha256']!=br['compiled']['model_sha256']
    assert ar['world']['id']!=br['world']['id'] and ar['compiled']['length_m']==.24 and br['compiled']['length_m']==.3
    service=m.project(a['id']);heavy=service.edit(identity(a),a['revision'],[{'kind':'set_device_mass','mass_kg':.5}]);failure=run(heavy,tmp_path/'heavy',False)
    assert not failure['acceptance']['checks']['opening_deadline'] and any(f['category']=='ACTUATOR_CAPABILITY' for f in diagnose(heavy,failure)['findings'])
    q=service.propose(identity(heavy),heavy['revision'],[{'kind':'set_device_mass','mass_kg':.035}],'Deterministic test correction; not model output')
    repaired=run(q['proposed_project'],tmp_path/'repair_preview',False);assert repaired['status']=='VERIFIED_IN_SIMULATION' and service.current()==heavy
    sensor=heavy['creation']['world_roles']['sensor'];turned=service.edit(identity(heavy),heavy['revision'],[{'kind':'rotate_object','target':sensor,'rotation_rad':[0,0,3.141592653589793]}]);away=run(turned,tmp_path/'away',False)
    assert away['acceptance']['first_detection_s'] is None and not away['acceptance']['checks']['no_fault']
    assert all(r['independent_verification']['status']=='PASS' for r in (ar,br,failure,repaired,away))

def test_concept_has_editable_envelopes_no_fake_electronics_or_controller(tmp_path):
    m=CreationManager(tmp_path/'registry');p=proposal(m,'Design lightweight AI smart glasses with camera, microphone, speakers, battery and wireless.');project=build(m,p)
    assert len(project['world']['objects'])==14 and not project['circuit']['components'] and not project['interfaces']
    assert len(project['creation']['concept_envelopes'])==14 and all(not e['verified_functionality'] for e in project['creation']['concept_envelopes'])
    with pytest.raises(ValueError):compile_created(project)
    s=m.project(project['id']);target=project['creation']['world_roles']['camera'];changed=s.edit(identity(project),project['revision'],[{'kind':'move_object','target':target,'position_m':[.02,.02,.01]}])
    assert EngineeringService(s.root).current()==changed and changed['creation']['unsupported']

def test_pose_coupling_exact_pins_and_no_paths_or_symlinks(tmp_path):
    m=CreationManager(tmp_path/'registry');p=build(m,proposal(m));s=m.project(p['id']);roles=p['creation'];sensor=roles['component_roles']['sensor'];mount=roles['world_roles']['sensor']
    a=copy.deepcopy(p['circuit']);next(c for c in a['components'] if c['id']==sensor)['position_m']=[.02,-.12,.08];updated=s.replace_circuit(identity(p),p['revision'],a)
    assert next(o for o in updated['world']['objects'] if o['id']==mount)['position_m']==[.02,-.12,.08]
    beam=roles['world_roles']['beam'];resized=s.edit(identity(updated),updated['revision'],[{'kind':'set_geometry','target':beam,'dimensions_m':[.3,.02,.016]}]);assert next(o for o in resized['world']['objects'] if o['id']==beam)['position_m']==[.15,0,0]
    with pytest.raises(ValueError):m.project('../project')
    (tmp_path/'linked').symlink_to(m.root,target_is_directory=True)
    with pytest.raises(ValueError):CreationManager(tmp_path/'linked')

def test_existing_orchestrator_mock_creation_tools_cannot_build(tmp_path):
    m=CreationManager(tmp_path/'registry');trace=ExecutionTrace(tmp_path/'mock.jsonl',model_mode='deterministic_mock');tools=CreationTools(m,trace)
    model=MockModelAdapter([ModelTurn(tool_calls=(ToolCall('inspect','inspect_creation_capabilities',{}),)),ModelTurn(tool_calls=(ToolCall('plan','create_device_plan',{'request':'Build a barrier.','parameters':DEFAULTS}),))])
    r=AgentOrchestrator(model,tools,trace,max_turns=2,max_tool_calls=2).run('Explicit deterministic mock; no genuine model generation.')
    assert r['model_mode']=='deterministic_mock' and m.active() is None and not tools.dispatch('build_project',{})['ok']
    assert m.list_projects()[0]['state']=='EMPTY'

def test_saved_native_evidence_reloads_with_original_input_and_reference_boundary(tmp_path):
    m=CreationManager(tmp_path/'registry');p=build(m,proposal(m));service=m.project(p['id']);measured=service.simulate(identity(p),p['revision'],'device')
    restarted=EngineeringService(service.root);loaded=restarted.load_evidence(measured['evidence']['sha256'])
    # JSON storage canonicalizes tuple-valued diagnostic intervals to arrays.
    assert digest(loaded['result'])==digest(measured['result']) and loaded['evidence']['base_project_sha256']==identity(p) and loaded['origin'].startswith('RECORDED')
    with pytest.raises(PermissionError):restarted.load_evidence('f'*64)
