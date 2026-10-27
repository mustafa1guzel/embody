"""Offline protocol doubles and real native checks; never live-model evidence."""
import copy
import json
from decimal import Decimal
from pathlib import Path
import pytest
from core.agent.models import MockModelAdapter, ModelTurn, ToolCall
from core.agent.orchestration import AgentOrchestrator
from core.agent.trace import ExecutionTrace
from core.agent.api_budget import GPT54_POLICY, cost
from engineering.project import identity
from engineering.shape_live import (ShapeExperimentTools, validate_task, inspection,
    first_request, second_request, schemas, preflight, INPUT_BOUND, OUTPUT_BOUND)
from engineering.shape_agent_review import load_review, publish_review
from shapebase.examples import create_disposable_arm
from physics.contracts import canonical
from robustness.contracts import write_once

@pytest.fixture
def arm(tmp_path): return create_disposable_arm((tmp_path / 'arm').resolve())[0]

def args(arm, length=.42):
    p=arm.current()
    return {'expected_sha256':identity(p),'expected_revision':p['revision'],
            'operations':[{'kind':'update_shape_parameter','target':'shape_link_one','parameter':'length_m','value':length}],
            'explanation':'OFFLINE PROTOCOL FIXTURE: fixed entered mass redistributes proxy inertia. Holes and child frames regenerate; not material/contact/hardware safety.'}

def tools(arm, tmp_path): return ShapeExperimentTools(arm, ExecutionTrace(tmp_path/'trace.jsonl', model_mode='deterministic_mock'))

def test_actual_protocol_selects_and_proposes_without_apply(arm,tmp_path):
    before=arm.current(); t=tools(arm,tmp_path)
    mock=MockModelAdapter([ModelTurn('',(ToolCall('inspect','inspect_engineering',{}),)),ModelTurn('',(ToolCall('proposal','propose_engineering_change',args(arm)),))])
    report=AgentOrchestrator(mock,t,t.trace,max_turns=2,max_tool_calls=2).run('OFFLINE fixture only')
    assert report['orchestration_status']=='LIMIT_REACHED' and t.result['ok'] and arm.current()==before
    proof=validate_task(arm,t.result['result']);assert proof['head_unchanged']
    native=arm.preview_shapes(identity(before),before['revision'],t.result['result']['proposal_id'])
    assert native['result']['independent_verification']['status']=='PASS'
    assert len(native['result']['samples'])==201 and native['result']['samples'][0]['qpos']!=native['result']['samples'][-1]['qpos']
    assert arm.current()==before

@pytest.mark.parametrize('change',[
    {'operations':[{'op':'resize','target':'shape_link_one','value':.42}]},
    {'expected_revision':3},{'expected_sha256':'0'*64},
    {'operations':[{'kind':'update_shape_parameter','target':'missing','parameter':'length_m','value':.42}]},
    {'operations':[{'kind':'update_shape_parameter','target':'shape_link_one','parameter':'length_m','value':True}]},
    {'operations':[{'kind':'update_mounting_hole','target':'shape_link_one','hole':{'id':'mount_a','diameter_m':.05,'u':.49,'v':.49}}]},
    {'operations':[{'kind':'attach_part_to_joint','target':'shape_link_one','joint_body_id':'elbow','frame_id':'mount_a'}]},
    {'operations':[{'kind':'set_mass','target':'link_one','mass_kg':.2}]},
])
def test_rejects_unsupported_stale_invalid_without_translation(arm,tmp_path,change):
    before=arm.current();t=tools(arm,tmp_path);assert t.dispatch('inspect_engineering',{})['ok']
    a=args(arm);a.update(change)
    assert not t.dispatch('propose_engineering_change',a)['ok'] and arm.current()==before

@pytest.mark.parametrize('name', ['propose_engineering_change','apply','execute','inspect_source'])
def test_no_proposal_before_inspection_or_execution_authority(arm,tmp_path,name):
    t=tools(arm,tmp_path);assert not t.dispatch(name,args(arm))['ok']
    assert not t.dispatch('inspect_engineering',{})['ok']

@pytest.mark.parametrize('value',[.3,.4,.6])
def test_valid_schema_is_insufficient_for_task(arm,value):
    a=args(arm,value);p=arm.propose(**{'sha':a['expected_sha256'],'revision':4,'operations':a['operations'],'explanation':a['explanation']})
    with pytest.raises(AssertionError):validate_task(arm,p)

def test_independent_validator_rejects_other_valid_geometry_changes(arm):
    a=args(arm);a['operations'].append({'kind':'update_shape_parameter','target':'shape_link_two','parameter':'length_m','value':.32})
    p=arm.propose(a['expected_sha256'],4,a['operations'],a['explanation'])
    with pytest.raises(ValueError,match='second part'):validate_task(arm,p)

def test_no_approval_preflight_fails_before_source_or_network(arm):
    with pytest.raises(ValueError,match='explicit approval'):preflight(Path('/nonexistent'),{'definition':{},'sha256':'x'},None,arm)
    assert cost(INPUT_BOUND,0,OUTPUT_BOUND,policy=GPT54_POLICY)*2==Decimal('.29952')

def test_strict_tools_have_closed_required_objects_and_only_six_existing_ops():
    def walk(x):
        if isinstance(x,dict):
            if x.get('type')=='object':assert x['additionalProperties'] is False and set(x['required'])==set(x['properties'])
            for v in x.values():walk(v)
        elif isinstance(x,list):
            for v in x:walk(v)
    walk(schemas());assert len(schemas()[1]['parameters']['properties']['operations']['items']['anyOf'])==6
    body=first_request();assert '.42' not in canonical(body) and '0.42' not in canonical(body)

def test_review_is_provenance_labelled_and_stale_safe(arm):
    assert load_review(arm)['status']=='NO_SESSION'
    write_once(arm.root/'shape_agent_session.json',{'task':'OFFLINE','project_sha256':identity(arm.current()),'project_revision':4})
    assert load_review(arm)['status']=='PENDING_APPROVAL'
    a=args(arm);p=arm.propose(a['expected_sha256'],4,a['operations'],a['explanation'])
    proof=validate_task(arm,p)
    publish_review(arm,{'status':'OFFLINE_VALIDATED','origin':'OFFLINE_PROTOCOL_FIXTURE','proposal':p,'validation':proof,'native':None})
    result=load_review(arm);assert result['application_allowed'] is False and result['origin']=='OFFLINE_PROTOCOL_FIXTURE'
    arm.decide(identity(arm.current()),4,p['proposal_id'],'apply','APPLY REVIEWED ENGINEERING CHANGE')
    with pytest.raises(ValueError,match='stale'):load_review(arm)


def test_frozen_two_turn_wire_protocol_with_explicit_fake_transport(arm,tmp_path):
    from types import SimpleNamespace
    from core.agent.api_budget import ApiBudget
    from engineering.shape_live import FrozenShapeAdapter,task_context
    bodies=[]
    def create(**wire):
        bodies.append(wire);n=len(bodies)
        call={'type':'function_call','call_id':'call_'+str(n),'name':'inspect_engineering' if n==1 else 'propose_engineering_change','arguments':json.dumps({} if n==1 else args(arm))}
        raw={'id':'resp_'+str(n),'model':'gpt-5.4','service_tier':'default','status':'completed','output':[call],
             'usage':{'input_tokens':100,'output_tokens':100,'total_tokens':200,'input_tokens_details':{'cached_tokens':0},'output_tokens_details':{'reasoning_tokens':0}}}
        return SimpleNamespace(id=raw['id'],output=raw['output'],model_dump=lambda **kw:copy.deepcopy(raw))
    fake=SimpleNamespace(max_retries=0,responses=SimpleNamespace(create=create))
    budget=ApiBudget(tmp_path/'fake_cost.json',policy=GPT54_POLICY,limit='.30',max_requests=2,input_token_bound=INPUT_BOUND,max_output_tokens=OUTPUT_BOUND)
    trace=ExecutionTrace(tmp_path/'fake_trace.jsonl',model_mode='mock_openai_transport')
    t=ShapeExperimentTools(arm,trace);adapter=FrozenShapeAdapter(fake,budget,tmp_path/'fake_api',trace,observation=t.observation)
    adapter.mode='mock_openai_transport'
    result=AgentOrchestrator(adapter,t,trace,max_turns=2,max_tool_calls=2).run(canonical(task_context()))
    assert result['orchestration_status']=='LIMIT_REACHED' and t.result['ok'] and len(bodies)==2
    assert bodies[0]==first_request() and bodies[1]==second_request(t.observation,'resp_1','call_1')
    from core.agent.api_budget import BudgetBlocked
    with pytest.raises(BudgetBlocked):adapter._request(**bodies[1])
    assert len(bodies)==2

@pytest.mark.parametrize('arguments,name,status',[('{"a":1,"a":2}','inspect_engineering','completed'),('{}','apply','completed'),('{}','inspect_engineering','incomplete')])
def test_invalid_actual_output_is_preserved_and_stops_no_retry(arm,tmp_path,arguments,name,status):
    from types import SimpleNamespace
    from engineering.shape_live import FrozenShapeAdapter
    from core.agent.api_budget import ApiBudget,BudgetBlocked
    calls=[]
    raw={'id':'resp_one','model':'gpt-5.4','service_tier':'default','status':status,'output':[{'type':'function_call','call_id':'call_one','name':name,'arguments':arguments}],
         'usage':{'input_tokens':100,'output_tokens':100,'total_tokens':200,'input_tokens_details':{'cached_tokens':0},'output_tokens_details':{'reasoning_tokens':0}}}
    def create(**kw):calls.append(kw);return SimpleNamespace(model_dump=lambda **kw:copy.deepcopy(raw))
    fake=SimpleNamespace(max_retries=0,responses=SimpleNamespace(create=create));trace=ExecutionTrace(tmp_path/'fake_trace.jsonl',model_mode='mock_openai_transport')
    b=ApiBudget(tmp_path/'fake_cost.json',policy=GPT54_POLICY,limit='.30',max_requests=2,input_token_bound=INPUT_BOUND,max_output_tokens=OUTPUT_BOUND)
    adapter=FrozenShapeAdapter(fake,b,tmp_path/'fake_api',trace,observation=inspection(arm))
    with pytest.raises(Exception):adapter._request(**first_request())
    assert len(calls)==1 and json.loads((tmp_path/'fake_api/response_000.json').read_text())==raw


def test_wire_tampering_blocks_before_even_fake_dispatch(arm,tmp_path):
    from types import SimpleNamespace
    from engineering.shape_live import FrozenShapeAdapter
    from core.agent.api_budget import ApiBudget,BudgetBlocked
    def forbidden(**kw):raise AssertionError('No dispatch allowed')
    fake=SimpleNamespace(max_retries=0,responses=SimpleNamespace(create=forbidden));trace=ExecutionTrace(tmp_path/'trace.jsonl',model_mode='mock_openai_transport')
    b=ApiBudget(tmp_path/'cost.json',policy=GPT54_POLICY,limit='.30',max_requests=2,input_token_bound=INPUT_BOUND,max_output_tokens=OUTPUT_BOUND)
    adapter=FrozenShapeAdapter(fake,b,tmp_path/'api',trace,observation=inspection(arm))
    bad=first_request();bad['input'][0]['content']='Changed task'
    with pytest.raises(BudgetBlocked,match='differs'):adapter._request(**bad)
    assert b.snapshot()['requests']==[]


def test_wire_schema_preserves_native_contract_for_all_six_operations():
    from jsonschema import Draft202012Validator
    from engineering.agent import PARAMETERS
    from shapebase.operations import SCHEMAS
    from shapebase.examples import part_input
    native=copy.deepcopy(PARAMETERS);native['properties']['operations']={'type':'array','minItems':1,'maxItems':16,'items':{'anyOf':SCHEMAS}}
    wire=schemas()[1]['parameters'];Draft202012Validator.check_schema(wire)
    examples=[
        {'kind':'create_parametric_part','part':part_input('newpart','body','shoulder')},
        {'kind':'update_shape_parameter','target':'shape_link_one','parameter':'length_m','value':.42},
        {'kind':'add_mounting_hole','target':'shape_link_one','hole':{'id':'newhole','diameter_m':.005,'u':0,'v':0}},
        {'kind':'update_mounting_hole','target':'shape_link_one','hole':{'id':'mount_a','diameter_m':.012,'u':-.32,'v':0}},
        {'kind':'set_attachment_frame','target':'shape_link_one','frame':{'id':'mount_b','source':'hole','hole_id':'mount_b','rotation_rad':[0,0,0]},'mounted_body_id':'elbow'},
        {'kind':'attach_part_to_joint','target':'shape_link_one','joint_body_id':'shoulder','frame_id':'mount_a'},
    ]
    def accepted(schema,op):return Draft202012Validator(schema).is_valid({'expected_sha256':'a'*64,'expected_revision':4,'operations':[op],'explanation':'Offline schema equivalence'})
    for op in examples:
        assert accepted(native,op) and accepted(wire,op)
        for bad in ({**op,'extra':True},{k:v for k,v in op.items() if k!='kind'},{**op,'kind':'unsupported'}):
            assert not accepted(native,bad) and not accepted(wire,bad)


def test_failed_session_without_provider_output_never_claims_live_authorship(arm):
    write_once(arm.root/'shape_agent_session.json',{'task':'Task','project_sha256':identity(arm.current()),'project_revision':4})
    publish_review(arm,{'status':'FAIL','origin':'NO_PROVIDER_RESPONSE','proposal':None,'validation':None,'native':None,'failure':{'reason':'No credentials'}})
    review=load_review(arm);assert review['origin']=='NO_PROVIDER_RESPONSE' and review['proposal'] is None and not review['application_allowed']
