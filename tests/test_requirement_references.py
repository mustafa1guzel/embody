"""Offline contract tests. Synthetic positives are NOT live AI qualification.

The exact rejected GPT answer is a negative fixture, never rewritten in place.
No physics, provider, HTTP server, credential or application is needed.
"""
import ast,copy,hashlib,json
from pathlib import Path
from decimal import Decimal
import pytest
from jsonschema import Draft202012Validator,ValidationError
from ide_api.engineering_agent_live import EngineeringAgentLive,final_schema,body_for,SYSTEM
from workspace.data import decode_json
from tests.test_engineering_agent_live import live,OfflineClient,response,function,message
from tests.test_engineering_agent import agent
from tests.test_native_results import saved,recorded

FIXTURE=Path(__file__).parent/'fixtures/agent_requirement_contract/historical_unaccepted_gpt54.json'

@pytest.fixture
def rejected():
 return decode_json(FIXTURE.read_bytes())

@pytest.fixture
def actual_record(agent):
 service,c=agent
 return service.context(c)['result']

@pytest.fixture
def synthetic(rejected):
 value=copy.deepcopy(rejected)
 # Explicit test-authored canonical references, not a translation algorithm or
 # a new accepted model result. Original observations remain byte-equivalent.
 rid=value['observations'][0]['result_id']
 value['requirements']=[{'result_id':rid,'check':key,'passed':flag} for key,flag in (
  ('minimum_clearance',False),('selected_contact_episodes',True),
  ('selected_final_speed',True),('selected_settling_time',True))]
 return value

def test_historical_exact_output_remains_rejected(rejected,actual_record):
 assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest()=='e40f3ea48b244dafd45a2de3a2e31bad09c0e49a8b634ab3859265b3e190da2e'
 Draft202012Validator(final_schema()).validate(rejected) # Original broad shape.
 with pytest.raises(ValueError,match='Unsupported requirement reference'):
  EngineeringAgentLive.validate_answer(rejected,{actual_record['id']:actual_record},[])
 with pytest.raises(ValidationError):Draft202012Validator(final_schema([actual_record])).validate(rejected)

@pytest.mark.parametrize('index',range(4))
def test_every_historical_requirement_is_independently_invalid(rejected,actual_record,index):
 value=copy.deepcopy(rejected);value['requirements']=[value['requirements'][index]]
 with pytest.raises(ValueError,match='Unsupported requirement reference'):
  EngineeringAgentLive.validate_answer(value,{actual_record['id']:actual_record},[])


def test_explicit_synthetic_canonical_answer_passes_only_contract_boundary(synthetic,rejected,actual_record):
 assert synthetic['observations']==rejected['observations']
 Draft202012Validator(final_schema([actual_record])).validate(synthetic)
 EngineeringAgentLive.validate_answer(synthetic,{actual_record['id']:actual_record},[])
 assert actual_record['verdict']=='FAIL' # Unit compatibility does not repair physics.

@pytest.mark.parametrize('key',['Minimum clearance','clearance','minimumClearance','minimum_clearance_m','hallucinated_requirement',' minimum_clearance','MINIMUM_CLEARANCE'])
def test_labels_diagnostic_ids_criteria_metrics_unknown_or_normalized_names_reject(key,synthetic,actual_record):
 synthetic['requirements'][0]['check']=key
 with pytest.raises(ValidationError):Draft202012Validator(final_schema([actual_record])).validate(synthetic)
 with pytest.raises(ValueError,match='Unsupported requirement reference'):
  EngineeringAgentLive.validate_answer(synthetic,{actual_record['id']:actual_record},[])


def test_unrelated_project_identity_is_rejected(synthetic,actual_record):
 synthetic['requirements'][0]['result_id']='unrelated-project-result'
 with pytest.raises(ValidationError):Draft202012Validator(final_schema([actual_record])).validate(synthetic)
 with pytest.raises(ValueError,match='Unsupported requirement reference'):
  EngineeringAgentLive.validate_answer(synthetic,{actual_record['id']:actual_record},[])

@pytest.mark.parametrize('field',['requirements','check','result_id','passed'])
def test_missing_currently_required_fields_reject(field,synthetic,actual_record):
 if field=='requirements':del synthetic[field]
 else:del synthetic['requirements'][0][field]
 with pytest.raises(ValidationError):EngineeringAgentLive.validate_answer(synthetic,{actual_record['id']:actual_record},[])


def test_empty_reference_array_preserves_existing_optional_reference_policy(synthetic,actual_record):
 synthetic['requirements']=[]
 EngineeringAgentLive.validate_answer(synthetic,{actual_record['id']:actual_record},[])


def test_display_labels_and_order_cannot_change_canonical_identity(actual_record):
 original=final_schema([actual_record]);changed=copy.deepcopy(actual_record)
 changed['display_labels']={k:'Completely different display wording' for k in changed['checks']}
 changed['criteria']={k:v for k,v in reversed(list(changed['criteria'].items()))}
 changed['checks']=dict(reversed(list(changed['checks'].items())))
 assert final_schema([changed])==original
 assert original['properties']['requirements']['items']['properties']['check']['enum']==sorted(actual_record['checks'])


def test_wrong_pass_claim_after_outcome_change_rejects(synthetic,actual_record):
 changed=copy.deepcopy(actual_record);changed['checks']['selected_final_speed']=False
 with pytest.raises(ValueError,match='Unsupported requirement reference'):
  EngineeringAgentLive.validate_answer(synthetic,{changed['id']:changed},[])


def test_requirement_threshold_change_cannot_reuse_bound_context(agent):
 service,context=agent;original=service.context(context)
 changed=copy.deepcopy(context);changed['requirements']['minimumClearance']+=.001
 with pytest.raises(ValueError):service.dispatch(changed,original['context_sha256'],'inspect_result',{})

@pytest.mark.parametrize('field',['value','metric','result_id'])
def test_numeric_evidence_validation_stays_strict(field,synthetic,actual_record):
 synthetic['observations'][0][field]={'value':.05,'metric':'invented_measurement','result_id':'other-result'}[field]
 with pytest.raises(ValueError,match='Unsupported or altered metric reference'):
  EngineeringAgentLive.validate_answer(synthetic,{actual_record['id']:actual_record},[])


def test_parser_still_rejects_duplicate_fields_and_nonfinite_json():
 for text in (b'{"requirements":[],"requirements":[]}',b'{"value":NaN}'):
  with pytest.raises(ValueError):decode_json(text)


def custom_record(rid,check):
 return {'id':rid,'metrics':{'custom_measurement':.4},'checks':{check:True}}


def test_nonrail_contexts_and_multiple_record_pairs_remain_supported(synthetic):
 a=custom_record('project-A','height.within_target');b=custom_record('project-B','custom_joint_check')
 value=copy.deepcopy(synthetic);value['observations']=[{'result_id':a['id'],'metric':'custom_measurement','value':.4}]
 value['requirements']=[{'result_id':a['id'],'check':'height.within_target','passed':True},{'result_id':b['id'],'check':'custom_joint_check','passed':True}]
 schema=final_schema([a,b]);assert schema==final_schema([b,a])
 Draft202012Validator(schema).validate(value);EngineeringAgentLive.validate_answer(value,{a['id']:a,b['id']:b},[])
 # The compact union enum does not replace semantic result/ID pairing validation.
 value['requirements'][0]['check']='custom_joint_check'
 Draft202012Validator(schema).validate(value)
 with pytest.raises(ValueError,match='Unsupported requirement reference'):
  EngineeringAgentLive.validate_answer(value,{a['id']:a,b['id']:b},[])


def test_missing_authoritative_checks_never_invents_diagnostic_ids(synthetic,actual_record):
 record=copy.deepcopy(actual_record);record.pop('checks');record['analysis']={'issues':[{'id':'invented_diagnostic','status':'PASS'}]}
 schema=final_schema([record]);assert schema['properties']['requirements']['maxItems']==0
 with pytest.raises(ValidationError):Draft202012Validator(schema).validate(synthetic)
 with pytest.raises(ValueError):EngineeringAgentLive.validate_answer(synthetic,{record['id']:record},[])


def test_actual_offline_protocol_synthetic_success_is_explicitly_not_live(live,synthetic):
 service,key,d,approval=live
 client=OfflineClient([response(0,[function()]),response(1,[message(synthetic)])])
 value=service.execute(key,approval,offline_client=client)
 assert value['status']=='COMPLETED' and value['state']['origin']=='OFFLINE_TRANSPORT_FIXTURE_NOT_AI'
 assert value['state']['explanation']==synthetic and len(client.calls)==2 and value['native_steps']==0 and not value['applied']
 schema=client.calls[1]['text']['format']['schema'];assert schema==final_schema([d['compact_context']['result']])
 assert client.calls[1]['previous_response_id']=='resp_offline_0' and client.calls[1]['tool_choice']=='none'
 assert client.calls[1]['input'][0]['call_id']=='call_offline_1'
 assert 'evidence.checks' in client.calls[0]['instructions'] and 'evidence.checks' in d['tools'][0]['description']


def test_historical_answer_is_still_rejected_through_offline_adapter(live,rejected):
 service,key,d,approval=live;client=OfflineClient([response(0,[function()]),response(1,[message(rejected)])])
 value=service.execute(key,approval,offline_client=client)
 assert value['status']=='VALIDATION_OR_CONTEXT_FAILURE' and not value['state'].get('explanation')
 assert len(value['state']['events'])==1 and len(client.calls)==2
 assert Decimal(value['state']['usage']['accounted_cost_usd'])==Decimal(value['state']['usage']['measured_cost_usd'])
 assert value['state']['origin']=='OFFLINE_TRANSPORT_FIXTURE_NOT_AI'


def test_same_real_task_and_frozen_envelope_still_fit_in_disposable_fixture(live):
 service,key,d,approval=live
 task='My rail robot failed its minimum-clearance requirement. Use the recorded simulation evidence to explain what happened, identify the failed physical requirement, and suggest one supported parameter change I could investigate. Do not apply any change or run physics.'
 value=service.prepare(d['context_input'],d['context_sha256'],task,'inspect');new=service.requests.get(value['request_id'])['definition']
 assert max(new['serialized_bounds'])<=32768 and new['policy']['hard_cap_usd']=='0.30' and new['policy']['maximum_reservation_usd']=='0.28672'
 assert not (service._folder(value['request_id'])/'consumed.json').exists()


def test_comparison_continuation_schema_uses_actual_inspected_contracts(live):
 service,key,d,approval=live;a=d['compact_context']['result'];b=custom_record('distinct-synthetic-inspected-result','independent_check')
 observed={a['id']:a,b['id']:b};wire=body_for(d,'fixture-response',[],observed=observed)
 assert wire['text']['format']['schema']==final_schema(list(observed.values()))
 ids=wire['text']['format']['schema']['properties']['requirements']['items']['properties']['check']['enum']
 assert 'independent_check' in ids and 'invented_display_label' not in ids


def test_no_inspected_checks_means_no_schema_authority(live):
 service,key,d,approval=live
 schema=body_for(d,'offline-response',[],observed={})['text']['format']['schema']
 assert schema['properties']['requirements']['maxItems']==0


def test_protocol_never_uses_diagnostic_ids_as_fallback_checks(live,synthetic,monkeypatch):
 service,key,d,approval=live;dispatch=service.agent.dispatch
 def missing_checks(*args,**kwargs):
  output=dispatch(*args,**kwargs)
  if output['name']=='inspect_result':output['data']['evidence'].pop('checks')
  return output
 monkeypatch.setattr(service.agent,'dispatch',missing_checks)
 value=copy.deepcopy(synthetic);value['requirements']=[{'result_id':d['context_input']['result_id'],'check':'clearance','passed':False}]
 client=OfflineClient([response(0,[function()]),response(1,[message(value)])]);result=service.execute(key,approval,offline_client=client)
 assert result['status']=='VALIDATION_OR_CONTEXT_FAILURE'
 assert client.calls[1]['text']['format']['schema']['properties']['requirements']['maxItems']==0
 assert not result['state'].get('explanation') and len(client.calls)==2
