"""Real native deterministic direction experiments; no paid transport or VM."""
import copy,json,math
from pathlib import Path
import pytest
from jsonschema import Draft202012Validator
from core.agent.trace import ExecutionTrace
from engineering.assembly import AssemblyComposer
from engineering.assembly_direction import kinematics,physical_feedback
from engineering.assembly_physical_repair import PhysicalRepairTools
from engineering.project import identity
from ide_api.engineering import EngineeringService
from robustness.contracts import write_once
ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT/'artifacts/phase18e_4/20261025/live_execution'

def initial_and_plan(*,yaw=0,command=.012,height=None):
    old=json.loads((OLD/'protocol_result.json').read_text());q=old['proposal']
    base=json.loads((OLD.parent/'live_project/projects'/(q['base_project_sha256']+'.json')).read_text())
    p=copy.deepcopy(old['attempts'][2]['arguments']['plan'])
    if yaw:p['steps'][0]['operations'].insert(1,{'kind':'rotate_object','target':p['roles']['root_body_id'],'rotation_rad':[0,0,yaw]})
    for s in p['steps']:
        for o in s['operations']:
            if o['kind']=='set_actuator':o['actuator']['command']=command
            if height is not None and o['kind']=='create_free_root':o['position_m'][2]=height
    return base,p

def construction(tmp_path,**settings):
    base,plan=initial_and_plan(**settings)
    c=AssemblyComposer(EngineeringService(tmp_path/'project',initial_project=base))
    write_once(c.root/'assembly_session.json',{'review_only':True,'task':'OFFLINE_DIRECTION_TEST'})
    q=c.propose(identity(base),0,plan,origin='DETERMINISTIC_RECONSTRUCTION_NOT_NEW_AI')
    return c,q

@pytest.fixture(scope='module')
def measured(tmp_path_factory):
    c,q=construction(tmp_path_factory.mktemp('shared_native_failure'))
    n=c.preview_native(q['base_project_sha256'],0,q['proposal_id'])
    return c,q,n

@pytest.mark.parametrize('yaw',[0,math.pi/2,math.pi])
@pytest.mark.parametrize('command',[.012,-.012])
def test_real_signed_travel_tracks_native_chassis_frame_not_world_y(tmp_path,yaw,command):
    c,q=construction(tmp_path,yaw=yaw,command=command);before=c.service.current()
    native=c.preview_native(q['base_project_sha256'],0,q['proposal_id']);f=physical_feedback(q,native)
    assert f['detected_stage']=='NATIVE_SIMULATION' and f['checks']['fresh_replay']
    assert f['checks']['ground_contacts_measured'] and f['contacts']['unexpected_contact_count']==0
    assert f['checks']['signed_forward_displacement']==(command<0)
    assert (f['measured_signed_forward_displacement_m']>.005)==(command<0)
    assert all(w['ideal_forward_projection_per_positive_joint_rate']==pytest.approx(-1) for w in f['wheels'])
    assert f['forward_axis_world']==pytest.approx([math.cos(yaw),math.sin(yaw),0])
    assert f['wheels'][0]['initial_native_axis_world']==pytest.approx([math.sin(yaw),-math.cos(yaw),0])
    assert c.service.current()==before and f['additional_integration_steps']==0

def test_reversal_without_ground_contact_is_not_predicted_as_success(tmp_path):
    c,q=construction(tmp_path,command=-.012,height=9.)
    k=kinematics(q['proposed_project'],q['assembly_plan']['roles'])
    assert k['status']=='COMPILED_KINEMATICS_ONLY_NOT_SIMULATED'
    n=c.preview_native(q['base_project_sha256'],0,q['proposal_id']);f=physical_feedback(q,n)
    assert f['status']=='PHYSICAL_FAILURE' and not f['checks']['ground_contacts_measured']
    assert not f['checks']['signed_forward_displacement'] and f['fresh_replay']['status']=='PASS'

def test_construction_accepts_both_command_signs_without_a_sign_exemption(tmp_path):
    for i,command in enumerate([.012,-.012]):
        c,q=construction(tmp_path/str(i),command=command)
        r=c.assess(q['base_project_sha256'],0,q['assembly_plan'])
        assert r['status']=='COMPILED_REVIEW_READY' and r['native']=='NOT_EXECUTED'
        assert r['direction_semantics']['status']=='COMPILED_KINEMATICS_ONLY_NOT_SIMULATED'

def repair_tools(tmp_path,c,q,n):
    copied=AssemblyComposer(EngineeringService(tmp_path/'repair_project',initial_project=c.service.current()))
    write_once(copied.root/'assembly_session.json',{'review_only':True,'task':'OFFLINE_REPAIR_PROTOCOL'})
    key=copied.proposals.put({k:v for k,v in q.items() if k!='proposal_id'});assert key==q['proposal_id']
    return PhysicalRepairTools(copied,copied.load(key),n,ExecutionTrace(tmp_path/'repair_trace',model_mode='OFFLINE_MOCK_AUTHOR_NOT_LIVE'))

def args_for(t,command):
    return {'expected_sha256':identity(t.before),'expected_revision':0,'baseline_proposal_id':t.baseline['proposal_id'],
        'physical_feedback_sha256':t.feedback['feedback_sha256'],'step_id':'author_supplied_repair',
        'operations':[{'kind':'set_actuator','target':target,'actuator':{**t.objects[target]['actuator'],'command':command}} for target in t.targets],
        'explanation':'Explicit deterministic author input, not a genuine AI repair or automatic sign correction.'}

@pytest.mark.parametrize('command',[.012,-.012])
def test_supplied_typed_repairs_preserve_arguments_and_original_plan(measured,tmp_path,command):
    c,q,n=measured;t=repair_tools(tmp_path,c,q,n);old=copy.deepcopy(q)
    assert t.dispatch('inspect_assembly_physical_failure',{})['ok']
    schema=t.schemas[0]['parameters'];Draft202012Validator.check_schema(schema)
    args=args_for(t,command);out=t.dispatch('propose_assembly_physical_repair',args)
    assert out['ok'] and not t.schemas and q==old
    after=out['result'];assert after['assembly_plan']['steps'][:-1]==q['assembly_plan']['steps']
    assert after['assembly_plan']['steps'][-1]['operations']==args['operations']
    assert t.composer.service.current()==c.service.current()
    assert not (t.composer.root/'assembly_decisions').exists()
    with pytest.raises(ValueError,match='review-only'):
        t.composer.decide(identity(t.before),0,after['proposal_id'],'apply','APPLY REVIEWED ASSEMBLY')
    assert not t.dispatch('propose_assembly_physical_repair',args)['ok']

@pytest.mark.parametrize('mode',['old_feedback','stale_head','front_target','zero','authority','unit','duplicate','extra','dialect'])
def test_invalid_physical_repairs_are_never_normalized_or_applied(measured,tmp_path,mode):
    c,q,n=measured;t=repair_tools(tmp_path,c,q,n);t.dispatch('inspect_assembly_physical_failure',{})
    a=args_for(t,-.012);o=a['operations'][0]
    if mode=='old_feedback':a['physical_feedback_sha256']='0'*64
    if mode=='stale_head':a['expected_revision']=1
    if mode=='front_target':o['target']=q['assembly_plan']['roles']['wheels']['front_left']['joint_body_id']
    if mode=='zero':o['actuator']['command']=0
    if mode=='authority':o['actuator']['limit']=.09
    if mode=='unit':o['actuator']['unit']='N'
    if mode=='duplicate':a['operations'][1]=copy.deepcopy(o)
    if mode=='extra':o['source']='no source permitted'
    if mode=='dialect':o['op']=o.pop('kind')
    snapshot=copy.deepcopy(a);out=t.dispatch('propose_assembly_physical_repair',a)
    assert not out['ok'] and a==snapshot and not t.schemas
    assert len(list(t.composer.proposals.root.glob('*.json')))==1
    assert t.composer.service.current()==c.service.current()

def test_feedback_rejects_tampered_trajectory_or_wrong_proposal(measured):
    c,q,n=measured
    for mode in ['trajectory','proposal','xml','structural']:
        changed=copy.deepcopy(n)
        if mode=='trajectory':changed['result']['samples'][0]['qpos'][0]+=.001
        elif mode=='proposal':changed['proposal_id']='0'*64
        elif mode=='xml':changed['result']['model_xml']+=' '
        else:changed['structural']['chassis_body']='floor'
        with pytest.raises(ValueError):physical_feedback(q,changed)

def test_historical_source_bound_proposal_remains_stale(tmp_path):
    old=json.loads((OLD/'protocol_result.json').read_text())['proposal'];base,_=initial_and_plan()
    c=AssemblyComposer(EngineeringService(tmp_path/'empty',initial_project=base))
    with pytest.raises(ValueError,match='source identity changed'):c.reconstruct(old)
    assert json.loads((ROOT/'artifacts/phase18e_5/20261026/status.json').read_text())['genuine_ai_construction']=='FAIL'

def test_failed_replay_does_not_authorize_a_model_physical_repair(measured,tmp_path):
    c,q,n=measured;changed=copy.deepcopy(n);changed['result']['independent_verification']['status']='FAIL'
    with pytest.raises(ValueError,match='replay required'):repair_tools(tmp_path,c,q,changed)

@pytest.mark.parametrize('command',[.012,-.012])
def test_future_budgeted_protocol_uses_only_supplied_commands_and_actual_inspection(measured,tmp_path,command):
    from types import SimpleNamespace
    from decimal import Decimal
    from core.agent.api_budget import ApiBudget,GPT54_POLICY,BudgetBlocked
    from core.agent.live_model import BudgetedOpenAIAdapter
    from tools.phase18e6_repair_live import run_protocol,audit_protocol,first_request,INPUT_BOUND,OUTPUT_BOUND,CAP,settings
    c,q,n=measured;t=repair_tools(tmp_path,c,q,n);requests=[]
    def create(**body):
        i=len(requests);requests.append(copy.deepcopy(body))
        args={} if i==0 else args_for(t,command)
        name='inspect_assembly_physical_failure' if i==0 else 'propose_assembly_physical_repair'
        r={'status':'completed','id':f'MOCK_RESP_{i}','model':'gpt-5.4','service_tier':'default',
            'output':[{'type':'function_call','name':name,'call_id':f'MOCK_CALL_{i}','arguments':json.dumps(args)}],
            'usage':{'input_tokens':1000,'output_tokens':100,'total_tokens':1100,'input_tokens_details':{'cached_tokens':0},'output_tokens_details':{'reasoning_tokens':20}}}
        return SimpleNamespace(model_dump=lambda **unused:r)
    budget=ApiBudget(tmp_path/'offline_mock_budget.json',policy=GPT54_POLICY,limit=CAP,max_requests=2,input_token_bound=INPUT_BOUND,max_output_tokens=OUTPUT_BOUND)
    adapter=BudgetedOpenAIAdapter(SimpleNamespace(max_retries=0,responses=SimpleNamespace(create=create)),budget,tmp_path/'mock_api',t.trace)
    out=run_protocol(adapter,t,tmp_path/'wire',lambda:None)
    assert out['status']=='COMPILED_REVIEW_ONLY' and len(requests)==2
    assert requests[1]['previous_response_id']=='MOCK_RESP_0' and requests[1]['input'][0]['call_id']=='MOCK_CALL_0'
    assert json.loads(requests[1]['input'][0]['output'])=={'ok':True,'result':t.inspection()}
    assert out['proposal']['assembly_plan']['steps'][-1]['operations']==args_for(t,command)['operations']
    assert Decimal(settings()['worst_case_reservation_usd'])==Decimal('.28672')
    root=tmp_path/'audit';root.mkdir();(tmp_path/'mock_api').rename(root/'api')
    assert audit_protocol(out,t,root,budget.snapshot())['status']=='PASS_INDEPENDENT_REPAIR_EVIDENCE_AUDIT'
    with pytest.raises(BudgetBlocked):adapter._request(**requests[0])
    assert len(requests)==2 and t.composer.service.current()==c.service.current()

def test_future_driver_without_approval_cannot_create_client(monkeypatch):
    from tools.phase18e6_repair_live import main
    monkeypatch.setattr('sys.argv',['phase18e6_repair_live.py'])
    with pytest.raises(SystemExit,match='fresh explicit approval'):main()
