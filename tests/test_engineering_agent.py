"""Actual saved public evidence + isolated proposals; zero model/native execution."""
import copy,json,threading
import pytest
from jsonschema import Draft202012Validator,ValidationError
from ide_api.engineering_agent import EngineeringAgent,CONTEXT,INPUTS,OUTPUT,schemas
from ide_api import rail_sweeps as rail,robot_import,native_models as models
from ide_api.product_alpha import ProductAlpha
from ide_api.experiment_designer import ExperimentDesigner
from ide_api.toolkit import Toolkit
from tests.test_native_results import saved,recorded

@pytest.fixture
def agent(saved,tmp_path):
 reader,req,raw=saved;p=ProductAlpha(ExperimentDesigner(reader.service),tmp_path/'rail');p.native=reader;t=Toolkit(tmp_path/'numeric',native=reader)
 service=EngineeringAgent(p,t,tmp_path/'assistant');r=p._historical_records()[0][0]
 c={'kind':'public_example','project_id':None,'project_sha256':None,'model_id':models.RAIL,'parameters':r['parameters'],'requirements':r['criteria'],'result_id':r['id'],'selection':'body:2'}
 return service,c

def call(agent,name,args=None,**kw):
 service,c=agent;ctx=service.context(c);r=service.dispatch(c,ctx['context_sha256'],name,args or {},**kw);Draft202012Validator(OUTPUT).validate(r);return r['data']

def test_registered_strict_schemas_and_model_authority_exclusion():
 assert len(INPUTS)==9
 for s in schemas():Draft202012Validator.check_schema(s['parameters']);Draft202012Validator.check_schema(s['output_schema']);assert s['parameters']['additionalProperties'] is False
 assert not {'review_proposal','prepare_verification'}&{s['name'] for s in schemas(model=True)}

def test_actual_public_saved_failure_and_predictions(agent):
 v=call(agent,'inspect_result');assert v['evidence']['verdict']=='FAIL';assert v['evidence']['metrics']['minimum_clearance_m']==pytest.approx(.003)
 assert v['analysis']['issues'][0]['required']==.05 and 'without contact' in v['analysis']['issues'][0]['interpretation']
 pred=call(agent,'calculate_physics');assert pred['prediction']['continuous']['stopping_distance_m']==1.44 and pred['prediction']['discrete']['native_steps']==0
 assert call(agent,'provider_status')['paid_calls']==0
 assert call(agent,'inspect_component')['component']['id']=='body:2'

def test_proposal_review_prepare_preserves_heads_and_original_failure(agent):
 service,c=agent;p=call(agent,'propose_parameters',{'changes':{'force_n':4},'rationale':'Explicit developer-authored offline test input, not AI.'});key=p['proposal_id']
 assert p['review_state']=='PROPOSED_NOT_APPLIED' and p['proposal']['changes']['force_n']['before']==2 and p['proposal']['proposed']['force_n']==4
 assert p['proposal']['fresh_verification_required'] and not p['proposal']['applied']
 with pytest.raises(ValueError,match='Human retention'):call(agent,'prepare_verification',{'proposal_id':key})
 with pytest.raises(PermissionError):call(agent,'review_proposal',{'proposal_id':key,'decision':'RETAINED'})
 call(agent,'review_proposal',{'proposal_id':key,'decision':'RETAINED'},human=True)
 v=call(agent,'prepare_verification',{'proposal_id':key});assert v['preparation']['request']['cases'][0]['force_n']==4 and not v['preparation']['execution_authorized']
 assert call(agent,'inspect_result')['evidence']['verdict']=='FAIL'
 assert not service.product.listing() and not service.toolkit.listing()

def test_permanent_cancel_and_no_reopen(agent):
 key=call(agent,'propose_parameters',{'changes':{'gap_m':1.49},'rationale':'Offline typed test'})['proposal_id']
 call(agent,'review_proposal',{'proposal_id':key,'decision':'REJECTED'},human=True)
 with pytest.raises(ValueError):call(agent,'review_proposal',{'proposal_id':key,'decision':'RETAINED'},human=True)
 with pytest.raises(ValueError):call(agent,'prepare_verification',{'proposal_id':key})

@pytest.mark.parametrize('changes',[{'force_n':0},{'force_n':True},{'force_n':float('nan')},{'speed_mps':2},{'chassis_mass_kg':.2},{'controller':'evil'},{'../source':1},{}])
def test_invalid_change_refused(agent,changes):
 with pytest.raises((ValueError,ValidationError)):call(agent,'propose_parameters',{'changes':changes,'rationale':'Rejected untrusted arguments'})

@pytest.mark.parametrize('name',['execute','apply','propose_patch','read_file','shell','model','authorize'])
def test_unsupported_or_unsafe_tools(agent,name):
 with pytest.raises(ValueError,match='Unsupported'):call(agent,name)

def test_context_drift_cannot_review_or_continue(agent):
 service,c=agent;bound=service.context(c);key=call(agent,'propose_parameters',{'changes':{'force_n':4},'rationale':'Offline typed test'})['proposal_id']
 c['parameters']={**c['parameters'],'force_n':4}
 with pytest.raises(ValueError,match='Stale engineering'):service.dispatch(c,bound['context_sha256'],'inspect_result',{})
 with pytest.raises(ValueError,match='Stale proposal'):call(agent,'review_proposal',{'proposal_id':key,'decision':'RETAINED'},human=True)
 c['parameters']['force_n']=2;c['selection']='joint:0'
 with pytest.raises(ValueError,match='Stale proposal'):call(agent,'prepare_verification',{'proposal_id':key})

def test_missing_wrong_result_model_and_bad_ids(agent):
 service,c=agent;c['result_id']=None
 with pytest.raises(ValueError,match='No verified'):call(agent,'inspect_result')
 c['result_id']='../../private'
 with pytest.raises(ValueError):service.context(c)
 c['model_id']=models.ROVER
 with pytest.raises(ValueError):service.context(c)

def test_numeric_exact_head_and_rover_limits_without_fabricated_evidence(agent):
 service,c=agent;d=robot_import.template(models.ROVER,'Explicit deterministic test declaration');p=service.toolkit.create(d)
 c.update(kind='numeric',project_id=p['id'],project_sha256=p['sha256'],model_id=models.ROVER,parameters=d['parameters'],requirements=d['requirements'],result_id=None,selection=None)
 with pytest.raises(ValueError,match='rail-only'):call(agent,'calculate_physics')
 with pytest.raises(ValueError,match='No verified'):call(agent,'inspect_result')
 key=call(agent,'propose_parameters',{'changes':{'torque_nm':.012},'rationale':'Bounded investigation; no predicted success'})['proposal_id'];assert key
 old=p['sha256'];service.toolkit.save(p['id'],old,{**d,'parameters':{**d['parameters'],'angle_deg':3}})
 with pytest.raises(ValueError,match='Stale'):call(agent,'inspect_context')

def test_model_tool_protocol_double_is_explicitly_offline(agent):
 # Real dispatch over a labelled test double, no alternate provider client.
 from core.agent.models import ModelTurn,ToolCall
 class OfflineModel:
  mode='MOCK_TRANSPORT_NOT_LIVE_AI'
  def complete(self):return ModelTurn(text='',tool_calls=(ToolCall('offline-1','inspect_result',{}),))
 m=OfflineModel();turn=m.complete();assert m.mode=='MOCK_TRANSPORT_NOT_LIVE_AI';assert call(agent,turn.tool_calls[0].name,turn.tool_calls[0].arguments)['evidence']['verdict']=='FAIL'

def test_guarded_real_http_extension_and_original_routes(agent):
 import requests
 from types import SimpleNamespace
 from ide_api.engineering_agent_http import EngineeringServer
 service,c=agent;ide=SimpleNamespace(_engineering_agent=service,_toolkit=service.toolkit,_product_alpha=service.product)
 server=EngineeringServer(('127.0.0.1',0),ide=ide);thread=threading.Thread(target=server.serve_forever);thread.start();url='http://'+server.host;headers={'Origin':url,'X-EMBODY-Token':server.token}
 try:
  assert requests.post(url+'/api/engineering-agent/context',json={'context':c}).status_code==403
  assert requests.post(url+'/api/engineering-agent/context',headers={**headers,'Host':'other'},json={'context':c}).status_code==403
  r=requests.post(url+'/api/engineering-agent/context',headers=headers,json={'context':c});assert r.status_code==200,r.text
  for extra in ['apply','execute','provider','authorize']:
   assert requests.post(url+'/api/engineering-agent/'+extra,headers=headers,json={}).status_code==403
  assert requests.post(url+'/api/engineering-agent/tool',headers=headers,json={'context':c,'expected_context':r.json()['context_sha256'],'name':'inspect_result','arguments':{}}).status_code==200
  assert requests.get(url+'/api/product/catalog').status_code==200
  assert requests.get(url+'/api/engineering-agent/context?path=/secret').status_code==400
  assert not server.jobs
 finally:server.shutdown();server.server_close();thread.join()

def test_review_storage_symlink_and_corruption_not_reinterpreted_as_missing(agent,tmp_path):
 service,c=agent;key=call(agent,'propose_parameters',{'changes':{'force_n':4},'rationale':'Offline typed security fixture'})['proposal_id']
 folder=service.root/'reviews';folder.mkdir();file=folder/(key+'.json');target=tmp_path/'untrusted.json';target.write_text('{}');file.symlink_to(target)
 with pytest.raises(ValueError,match='Symlink'):call(agent,'prepare_verification',{'proposal_id':key})
 file.unlink();file.write_text('{}')
 with pytest.raises(ValueError):call(agent,'prepare_verification',{'proposal_id':key})

def test_context_source_and_evidence_drift_rejected(agent,monkeypatch):
 service,c=agent;ctx=service.context(c)
 from tools.model_qualification import sources
 before=sources();monkeypatch.setattr('tools.model_qualification.sources',lambda:{**before,'offline-test-only.py':'f'*64})
 with pytest.raises(ValueError,match='Stale engineering'):service.dispatch(c,ctx['context_sha256'],'inspect_result',{})

def test_output_specific_contracts_validate_actual_tool_results(agent):
 from ide_api.engineering_agent import output_schema
 service,c=agent;ctx=service.context(c)
 for name in ['inspect_context','inspect_result','inspect_component','calculate_physics','provider_status']:
  result=service.dispatch(c,ctx['context_sha256'],name,{})
  Draft202012Validator(output_schema(name)).validate(result)
  broken=copy.deepcopy(result);broken['data']={}
  with pytest.raises(ValidationError):Draft202012Validator(output_schema(name)).validate(broken)

def test_proposal_retention_is_bounded_and_original_evidence_not_mutated(agent):
 service,c=agent;record_before=call(agent,'inspect_result')
 folder=service.root/'proposals';folder.mkdir(parents=True)
 for i in range(64):(folder/f'{i:064x}.json').write_text('{}')
 with pytest.raises(ValueError,match='retention'):call(agent,'propose_parameters',{'changes':{'force_n':4},'rationale':'Offline bounded quota test'})
 assert call(agent,'inspect_result')==record_before

def test_symlink_assistant_storage_refused(agent,tmp_path):
 service,c=agent;root=tmp_path/'alias';root.symlink_to(tmp_path/'elsewhere')
 with pytest.raises(ValueError,match='Symlink'):EngineeringAgent(service.product,service.toolkit,root)
