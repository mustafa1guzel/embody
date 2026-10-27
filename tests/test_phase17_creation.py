"""Explicit MOCK provider protocol, strict rejection, and genuine native previews."""
import copy,json,time
from pathlib import Path
from types import SimpleNamespace
import pytest
from core.agent.api_budget import ApiBudget,GPT54_POLICY,BudgetBlocked
from core.agent.orchestration import AgentOrchestrator
from core.agent.trace import ExecutionTrace,read_trace
from engineering.creation import CreationManager,implementation_identity
from engineering.creation_experiment import CreationExperimentTools,SCHEMAS,FUNCTIONS,LIMITS,INTERFACES,preview_measurements
from engineering.device_bindings import PARTS
from engineering.creation_live import request_body,FrozenCreationAdapter,preflight,versions
from physics.contracts import digest
from robustness.contracts import file_hash

def mock_arguments():
    return {'goal_interpretation':'A supported sensor ray should trigger a bounded hinged barrier to open automatically.','template':'day16_hinged_barrier_v1','functional_requirements':FUNCTIONS,'mechanical':{'span_m':.22,'mass_kg':.025,'torque_nm':.12,'height_m':.18},'circuit_roles':PARTS,'interfaces':INTERFACES,'controller_family':'TRUSTED_BARRIER_V1','selection_rationale':'DETERMINISTIC MOCK fixture only: a light beam and bounded actuator selected for native protocol testing; no live model reasoning.','unsupported_domains':LIMITS}

def mock_response(arguments=None,status='completed',name='propose_barrier_from_template'):
    output=[{'type':'function_call','call_id':'call_explicit_mock','name':name,'arguments':json.dumps(arguments or mock_arguments())}]
    raw={'id':'resp_EXPLICIT_MOCK_ONLY','model':'gpt-5.4','status':status,'service_tier':'default','output':output,'usage':{'input_tokens':200,'input_tokens_details':{'cached_tokens':0},'output_tokens':300,'output_tokens_details':{'reasoning_tokens':20},'total_tokens':500}}
    return SimpleNamespace(id=raw['id'],output=output,model_dump=lambda **kw:copy.deepcopy(raw))

def protocol(tmp_path,response=None):
    captured=[]
    def create(**kw):captured.append(copy.deepcopy(kw));return response or mock_response()
    client=SimpleNamespace(max_retries=0,responses=SimpleNamespace(create=create))
    trace=ExecutionTrace(tmp_path/'mock_trace.jsonl',model_mode='mock_openai_transport')
    manager=CreationManager(tmp_path/'registry');tools=CreationExperimentTools(manager,trace)
    budget=ApiBudget(tmp_path/'mock_budget.json',limit='.13',max_requests=1,input_token_bound=24576,max_output_tokens=4096,policy=GPT54_POLICY)
    body=request_body();model=FrozenCreationAdapter(client,budget,tmp_path/'mock_api',trace,frozen_request=body);model.mode='mock_openai_transport'
    return manager,tools,budget,body,model,captured,trace

def test_strict_contract_documents_all_fields_without_final_example_actions():
    def visit(s):
        if s.get('type')=='object':assert s['additionalProperties'] is False and set(s['required'])==set(s['properties'])
        for v in s.get('properties',{}).values():visit(v)
        if isinstance(s.get('items'),dict):visit(s['items'])
    for s in SCHEMAS:assert s['strict'];visit(s['parameters'])
    body=request_body();assert body['tool_choice']=='auto' and not body['parallel_tool_calls']
    assert 'construction_batches' not in body['input'][0]['content'] and 'proposed_project' not in body['input'][0]['content']
    assert len(json.dumps(body,ensure_ascii=True).encode())+4096<=24576

def test_actual_existing_orchestrator_sends_exact_frozen_mock_wire_and_never_builds(tmp_path):
    m,t,b,body,model,captured,trace=protocol(tmp_path)
    report=AgentOrchestrator(model,t,trace,max_turns=1,max_tool_calls=1).run(body['input'][0]['content'])
    assert captured==[body] and report['model_mode']=='mock_openai_transport' and report['orchestration_status']=='LIMIT_REACHED'
    assert t.result['ok'] and t.result['result']['model_design_intent']==mock_arguments()
    p=t.result['result']['construction_proposal'];assert p['initial_project']['world']['objects']==p['initial_project']['circuit']['components']==[]
    assert m.project(p['project_id']).current()==p['initial_project'] and m.active() is None
    assert p['validation']['electrical']['errors']==0 and p['validation']['electrical']['unknowns']>0 and len(p['batches'])==10
    assert len(b.snapshot()['requests'])==1 and read_trace(trace.path)[0]['payload']['model_mode']=='mock_openai_transport'
    with pytest.raises(BudgetBlocked):model._request(**{k:v for k,v in body.items() if k not in ('tool_choice','reasoning','max_output_tokens','parallel_tool_calls','service_tier','store')})
    assert len(captured)==1

@pytest.mark.parametrize('mutate',[
 lambda a:a.update(op='build_now'),lambda a:a['mechanical'].update(mass_kg=3),lambda a:a['mechanical'].update(mass_kg=True),
 lambda a:a['mechanical'].update(mass_kg=float('nan')),lambda a:a.update(controller_family='NONE_GEOMETRY_ONLY'),
 lambda a:a['interfaces'].update(echo_conditioning='DIRECT_CONNECTION'),lambda a:a['interfaces'].update(actuator_supply='BOARD_GPIO'),
 lambda a:a['interfaces'].update(trigger_gpio='IO19'),lambda a:a['circuit_roles'].update(sensor='towerpro_sg90_digital'),
 lambda a:a.update(unsupported_domains=[LIMITS[0]]*5),lambda a:a.update(functional_requirements=[FUNCTIONS[0]]*4),
])
def test_unsafe_or_malformed_selection_rejected_without_local_project_or_translation(tmp_path,mutate):
    m,t,*_=protocol(tmp_path);a=copy.deepcopy(mock_arguments());mutate(a)
    assert not t.dispatch('propose_barrier_from_template',a)['ok'] and m.list_projects()==[] and m.active() is None
    assert not t.dispatch('propose_barrier_from_template',mock_arguments())['ok']

def test_unsupported_tool_choice_creates_nothing(tmp_path):
    m,t,b,body,model,captured,trace=protocol(tmp_path,mock_response({'reason':'Explicit MOCK unsupported selection; no design created.'},name='report_unsupported_creation'))
    AgentOrchestrator(model,t,trace,max_turns=1,max_tool_calls=1).run(body['input'][0]['content'])
    assert t.result['result']['status']=='MODEL_REPORTED_UNSUPPORTED' and m.list_projects()==[] and len(captured)==1

def test_incomplete_response_preserves_mock_usage_and_creates_no_plan(tmp_path):
    m,t,b,body,model,captured,trace=protocol(tmp_path,mock_response(status='incomplete'))
    result=AgentOrchestrator(model,t,trace,max_turns=1,max_tool_calls=1).run(body['input'][0]['content'])
    assert result['orchestration_status']=='ERROR' and m.list_projects()==[] and not t.attempted
    assert b.snapshot()['requests'][0]['state']=='FAILED_WITH_USAGE' and (tmp_path/'mock_api/response_000.json').exists()
    assert len(captured)==1

def test_duplicate_provider_json_is_rejected_before_deterministic_tool_dispatch(tmp_path):
    response=mock_response();response.output[0]['arguments']='{"template":"x","template":"y"}'
    m,t,b,body,model,captured,trace=protocol(tmp_path,response)
    result=AgentOrchestrator(model,t,trace,max_turns=1,max_tool_calls=1).run(body['input'][0]['content'])
    assert result['orchestration_status']=='ERROR' and not t.attempted and m.list_projects()==[] and len(captured)==1
    assert '"template"' in (tmp_path/'mock_api/response_000.json').read_text().replace('\\"','"')

def test_native_preview_failure_correction_never_changes_authoritative_empty_head(tmp_path):
    m,t,*_=protocol(tmp_path);assert t.dispatch('propose_barrier_from_template',mock_arguments())['ok']
    selection=t.result['result'];measured=preview_measurements(selection,m,tmp_path/'native',render_image=False)
    assert measured['primary_status']==measured['correction_status']=='VERIFIED_IN_SIMULATION'
    assert measured['heavy_status']=='MEASURED_REQUIREMENT_FAILURE' and measured['heavy_mass_kg']==.5
    assert 'ACTUATOR_CAPABILITY' in measured['diagnostic_categories'] and measured['simulation_scenarios']==3
    assert measured['empty_head_unchanged'] and not measured['proposal_applied'] and not m.active()
    for name in ('primary','heavy','correction_preview'):
        r=json.loads((tmp_path/'native'/name/'result.json').read_text());assert len(r['samples'])==1001 and r['independent_verification']['status']=='PASS'

def scope_fixture(tmp_path):
    body=request_body();(tmp_path/'wire.json').write_text(json.dumps(body));(tmp_path/'identity').write_text('exact frozen identity')
    d={'frozen_unix':time.time(),'endpoint':'https://api.openai.com/v1/responses','max_requests':1,'hard_cap_usd':'0.13','input_token_bound':24576,'max_output_tokens':4096,'model':'gpt-5.4','reasoning_effort':'low','tool_choice':'auto','versions':versions(),'creation_implementation_sha256':implementation_identity(),'source_sha256':{'identity':file_hash(tmp_path/'identity')},'request_path':'wire.json','request_sha256':digest(body),'serialized_payload_bound':len(json.dumps(body,ensure_ascii=True).encode())+4096}
    return {'definition':d,'sha256':digest(d)}

def test_exact_approval_then_identity_or_expiry_failure_before_credentials(tmp_path):
    scope=scope_fixture(tmp_path)
    with pytest.raises(ValueError,match='explicit approval'):preflight(tmp_path,scope,None)
    assert preflight(tmp_path,scope,scope['sha256'])==request_body()
    (tmp_path/'identity').write_text('changed')
    with pytest.raises(ValueError,match='identity changed'):preflight(tmp_path,scope,scope['sha256'])
    scope['definition']['frozen_unix']-=90000;scope['sha256']=digest(scope['definition'])
    with pytest.raises(ValueError,match='expired'):preflight(tmp_path,scope,scope['sha256'])
