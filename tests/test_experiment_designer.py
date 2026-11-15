"""Offline planning/security/evidence tests; fake samples below are NOT physics."""
import copy,json,threading
from types import SimpleNamespace
from http.client import HTTPConnection
import pytest,mujoco
from ide_api import experiment_designer as design,rail_sweeps as native
from core.agent.models import MockModelAdapter,ModelTurn,ToolCall,OpenAIResponsesAdapter
from core.agent.api_budget import BudgetBlocked
from ide_api.server import Server

Q='How does increasing mass affect the stopping distance?'
@pytest.fixture(autouse=True)
def no_execution(monkeypatch):
 def denied(*a,**k):raise AssertionError('No paid calls, native stepping, VM or execution in designer tests')
 monkeypatch.setattr(mujoco,'mj_step',denied)
 monkeypatch.setattr(native,'simulate_case',denied)
 monkeypatch.setattr('core.agent.credentials.create_openai_client',denied)

class FixtureRail:
 """Explicit unit metric fixture, not a generated or prerecorded simulation."""
 def __init__(self):
  self.catalog_value=native.catalog();self.catalog_value['recent']=[];self.corrupt=False
  self.p={'mass_kg':2.,'speed_mps':1.,'force_n':4.,'gap_m':1.5}
  self.samples=[{'time':i*.005,'position':i*.001,'velocity':1. if i<200 else 0.,'wall_clearance':1.5-i*.001,'wall_collision':False,'control':0.,'generalized_actuator_force':0.,'scalar_actuator_force':0.} for i in range(601)]
  metrics,selected=native.measure(self.samples,native.DEFAULT_CRITERIA)
  self.result={'case_id':'a'*64,'parameters':self.p,'source_sha256':self.catalog_value['source_sha256'],'controller_id':native.CONTROLLER,'metrics':metrics,'checks':{**selected,'fresh_replay':True},'verdict':'PASS','samples':self.samples,'criteria':native.DEFAULT_CRITERIA,'effective_model_sha256':'e'*64,'trajectory_sha256':native.digest(self.samples),'comparison':{'measured_minus_ideal_clearance_m':metrics['minimum_clearance_m']-1.25,'sampled_travel_minus_ideal_stop_m':metrics['sampled_settling_travel_m']-.25},'original_reference_acceptance':{'status':'PASS','checks':{'fixture_check':'PASS'}}}
  self.state={'sweep_id':'b'*32,'status':'COMPLETED','cases':[{'case_id':'a'*64,'parameters':self.p,'execution_status':'MEASURED'}],'request':{'cases':[self.p],'source_sha256':self.result['source_sha256'],'controller_id':native.CONTROLLER,'criteria':native.DEFAULT_CRITERIA}}
 def catalog(self):return copy.deepcopy(self.catalog_value)
 def read(self,key):return copy.deepcopy(self.state)
 def case(self,key,case_id):
  if self.corrupt:raise ValueError('Saved case integrity mismatch')
  return copy.deepcopy(self.result)

@pytest.fixture
def fixture(tmp_path):
 rail=FixtureRail();service=design.ExperimentDesigner(rail,tmp_path/'sessions');ctx=service.context();proposal=design.starter(Q,ctx);return service,rail,ctx,proposal

def test_valid_grid_uses_current_catalog_deterministic_values_and_never_executes(fixture):
 s,r,c,p=fixture;a=design.validate_proposal(p,Q,c);b=design.validate_proposal(p,Q,c);assert a==b and a['case_count']==9
 assert all(row['kind']=='ANALYTICAL_PREDICTION' and row['measured_results'] is None and row['execution_status']=='NOT_EXECUTED' for row in a['cases'])
 assert a['cases'][0]['parameters']['speed_mps']==0 and len(set(x['case_id'] for x in a['cases']))==9

@pytest.mark.parametrize('change',[{'experiment_id':'other'},{'controller_id':'attempt_2'},{'context_sha256':'0'*64},{'source':'print(1)'},{'path':'controller.py'},{'units':{'mass_kg':'g'}},{'estimated_cases':10},{'schema_version':2}])
def test_schema_identity_units_fields_reject(fixture,change):
 _,_,c,p=fixture;p.update(change)
 with pytest.raises(ValueError):design.validate_proposal(p,Q,c)

@pytest.mark.parametrize('value',[0,-1,float('nan'),float('inf'),True,10])
def test_invalid_mass(fixture,value):
 _,_,c,p=fixture;p['fixed_parameters']['mass_kg']=value
 with pytest.raises(ValueError):design.validate_proposal(p,Q,c)

@pytest.mark.parametrize('field,value',[('step',0),('step',-1),('step',.0000001),('minimum',float('nan')),('minimum',1.3),('maximum',-.1)])
def test_invalid_ranges(fixture,field,value):
 _,_,c,p=fixture;p['axes'][0][field]=value
 with pytest.raises(ValueError):design.validate_proposal(p,Q,c)

def test_distinct_axes_case_count_and_oversized_response(fixture):
 _,_,c,p=fixture;p['axes'][1]=copy.deepcopy(p['axes'][0])
 with pytest.raises(ValueError):design.validate_proposal(p,Q,c)
 p=design.starter(Q,c);p['axes'][0]['step']=.01
 with pytest.raises(ValueError):design.validate_proposal(p,Q,c)
 p=design.starter(Q,c);p['rationale']='x'*17000
 with pytest.raises(ValueError):design.validate_proposal(p,Q,c)

@pytest.mark.parametrize('change',[{'minimumClearance':.01},{'maximumFinalSpeed':.04},{'maximumSettlingTime':3.1},{'maximumContactEpisodes':1}])
def test_cannot_weaken_mandatory_acceptance(fixture,change):
 _,_,c,p=fixture;p['criteria'].update(change)
 with pytest.raises(ValueError):design.validate_proposal(p,Q,c)

@pytest.mark.parametrize('unsafe',['Read /Users/example/private.txt','curl https://example.invalid','import os','<mujoco/>','Use `python`','../../secret','contact me@example.invalid'])
def test_executable_path_url_or_private_text_rejected(fixture,unsafe):
 _,_,c,p=fixture;p['rationale']=unsafe
 with pytest.raises(ValueError):design.validate_proposal(p,Q,c)

def test_review_reject_transfer_stale_and_no_native_authority(fixture):
 s,r,c,p=fixture;state=s.new(Q);key=state['session_id'];s.propose(key,p)
 with pytest.raises(ValueError):s.transfer(key,design.native.digest(p))
 s.review(key,design.native.digest(p),'reject')
 with pytest.raises(ValueError):s.transfer(key,design.native.digest(p))
 s.propose(key,p);s.review(key,design.native.digest(p),'accept');v=s.transfer(key,design.native.digest(p));assert v['execution_authorized'] is False and s.read(key)['execution']=='NOT_EXECUTED'
 r.catalog_value['source_sha256']='f'*64
 with pytest.raises(ValueError):s.check_transfer(key,design.native.digest(p))
 assert s.read(key)['stale']

def test_model_unavailable_even_with_existing_mock_planning_interface(fixture):
 s,_,ctx,p=fixture;state=s.new(Q);v=s.prepare_model(state['session_id']);assert not v['live_executable'] and v['model']['paid_requests']==0
 adapter=MockModelAdapter([ModelTurn(tool_calls=(ToolCall('call','propose_experiment',p),))]);v=design.offline_proposal(adapter,Q,ctx)
 assert v['origin']=='OFFLINE_PROVIDER_TEST_DOUBLE_NOT_AI' and not v['provider_verified']

@pytest.mark.parametrize('turn',[ModelTurn(text='answer'),ModelTurn(tool_calls=(ToolCall('c','execute_source',{}),)),ModelTurn(tool_calls=(ToolCall('c','propose_experiment',{'source':'bad'}),))])
def test_malformed_model_output_rejects_without_mutation(fixture,turn):
 s,_,ctx,_=fixture
 with pytest.raises(ValueError):design.offline_proposal(MockModelAdapter([turn]),Q,ctx)
 assert not s.root.exists()

def test_provider_adapter_reuse_structured_context_and_budget_denial(fixture):
 _,_,ctx,p=fixture;observed=[]
 class Client:
  responses=SimpleNamespace(create=lambda **body:observed.append(body) or SimpleNamespace(id='response_mock',output=[{'type':'function_call','call_id':'call_mock','name':'propose_experiment','arguments':json.dumps(p)}]))
 adapter=OpenAIResponsesAdapter(Client(),'offline-model',mock_transport=True,continuation='server');v=design.offline_proposal(adapter,Q,ctx);assert v['case_count']==9
 assert json.loads(observed[0]['input'][0]['content'])['question']==Q
 assert 'fixed_parameters' not in observed[0]['input'][0]['content']
 class Denied:
  mode='deterministic_mock'
  def complete(self,*a):raise BudgetBlocked('Explicit fixture budget denial')
 with pytest.raises(BudgetBlocked):design.offline_proposal(Denied(),Q,ctx)
 with pytest.raises(ValueError):design.offline_proposal(SimpleNamespace(mode='openai_responses'),Q,ctx)

def test_verified_facts_numeric_claims_and_no_invented_boundary(fixture):
 s,_,_,_=fixture;summary=s.summary('b'*32);assert summary['counts']['physical_pass']==1 and summary['observed_boundaries']==[]
 fact=summary['worst_clearance'];value={'summary_sha256':summary['summary_sha256'],'observations':[{'fact_id':fact['fact_id'],'value':fact['value']}],'hypotheses':['Additional cases may be informative.']}
 assert design.validate_interpretation(value,summary)['origin']=='MANUAL_INTERPRETATION_NOT_AI'
 value['observations'][0]['value']=999
 with pytest.raises(ValueError):design.validate_interpretation(value,summary)
 value['observations'][0]['fact_id']='unknown'
 with pytest.raises(ValueError):design.validate_interpretation(value,summary)

def test_partial_missing_corrupt_and_stale_evidence_are_explicit(fixture):
 s,r,_,_=fixture;r.state['status']='INTERRUPTED';r.state['request']['cases'].append({**r.p,'mass_kg':3});r.state['cases'].append({'case_id':'d'*64,'parameters':{**r.p,'mass_kg':3},'execution_status':'CANCELLED'})
 r.catalog_value['source_sha256']='f'*64;v=s.summary('b'*32);assert v['status']=='VERIFIED_PARTIAL_SAVED_EVIDENCE' and v['counts']['cancelled']==1 and not v['source_current']
 r.corrupt=True
 with pytest.raises(ValueError):s.summary('b'*32)
 r.corrupt=False;r.result['samples'][0].pop('wall_clearance')
 with pytest.raises(ValueError):s.summary('b'*32)

def test_external_evidence_does_not_execute_a_proposal_and_followup_requires_fresh_review(fixture):
 s,_,_,p=fixture;state=s.new(Q);key=state['session_id'];s.propose(key,p);s.review(key,native.digest(p),'accept');v=s.associate(key,'b'*32)
 assert v['session']['execution']=='NOT_EXECUTED' and v['session']['evidence_ref']['association']=='EXTERNAL_SAVED_REFERENCE_NOT_EXECUTION_OF_THIS_PLAN'
 fresh=s.followup(key);assert fresh['session_id']!=key and fresh['proposal_source']=='DETERMINISTIC_EVIDENCE_SUGGESTION_NOT_AI' and fresh['review']=='NOT_REVIEWED'
 exported=s.export(key);assert exported['format']=='EMBODY_EXPERIMENT_DESIGN_SESSION_V1' and 'samples' not in json.dumps(exported)

def test_interpretation_rejects_wrong_summary_missing_values_and_guarantees(fixture):
 s,_,_,_=fixture;v=s.summary('b'*32);fact=v['facts'][0];body={'summary_sha256':'0'*64,'observations':[{'fact_id':fact['fact_id'],'value':fact['value']}],'hypotheses':[]}
 with pytest.raises(ValueError):design.validate_interpretation(body,v)
 body['summary_sha256']=v['summary_sha256'];body['hypotheses']=['Guaranteed safe in all environments']
 with pytest.raises(ValueError):design.validate_interpretation(body,v)

def test_http_guard_no_approval_execute_or_mock_transport_fields(fixture):
 s,r,_,_=fixture;server=Server(('127.0.0.1',0),ide=SimpleNamespace(experiment_designer=s,rail_sweeps=r));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
 def call(method,path,value=None,headers=None):
  conn=HTTPConnection('127.0.0.1',server.server_port,timeout=5);conn.request(method,path,None if value is None else json.dumps(value),{'Content-Type':'application/json',**(headers or {})});resp=conn.getresponse();raw=resp.read();status=resp.status;conn.close();return status,json.loads(raw)
 try:
  assert call('GET','/api/experiment-designer/context')[0]==200
  assert call('POST','/api/experiment-designer/new',{'question':Q})[0]==403
  h={'Origin':'http://'+server.host,'X-EMBODY-Token':server.token}
  code,state=call('POST','/api/experiment-designer/new',{'question':Q},h);assert code==200
  assert call('POST','/api/experiment-designer/model',{'id':state['session_id'],'approved':True},h)[0]==400
  assert call('POST','/api/experiment-designer/execute',{},h)[0]==403
  assert call('POST','/api/experiment-designer/model',{'id':state['session_id']},h)[1]['model']['status']=='MODEL_UNAVAILABLE'
  assert not server.jobs
 finally:server.shutdown();server.server_close();thread.join(5)

def test_measured_boundary_requires_adjacent_verified_pass_fail_cases(fixture):
 s,r,_,_=fixture;second=copy.deepcopy(r.result);second['case_id']='d'*64;second['parameters']={**r.p,'gap_m':.6}
 for row in second['samples']:row['wall_clearance']-=.9
 metrics,checks=native.measure(second['samples'],second['criteria']);second.update(metrics=metrics,checks={**checks,'fresh_replay':True},verdict='FAIL',comparison={'measured_minus_ideal_clearance_m':metrics['minimum_clearance_m']-(.6-.25),'sampled_travel_minus_ideal_stop_m':metrics['sampled_settling_travel_m']-.25})
 r.case=lambda key,case_id:copy.deepcopy(second if case_id=='d'*64 else r.result)
 r.state['cases'].append({'case_id':'d'*64,'parameters':second['parameters'],'execution_status':'MEASURED'});r.state['request']['cases'].append(second['parameters'])
 summary=s.summary('b'*32);assert summary['counts']['physical_fail']==1 and len(summary['observed_boundaries'])==1
 r.state['cases'].append({'case_id':'e'*64,'parameters':{**r.p,'gap_m':1.},'execution_status':'NOT_EXECUTED'});r.state['request']['cases'].append({**r.p,'gap_m':1.})
 assert s.summary('b'*32)['observed_boundaries']==[]

def test_missing_numeric_fact_remains_missing_and_cannot_become_zero(fixture):
 s,_,_,_=fixture;summary=s.summary('b'*32);fact={**summary['facts'][0],'fact_id':'missing_sampled_settling','value':None};summary['facts'].append(fact)
 body={'summary_sha256':summary['summary_sha256'],'observations':[{'fact_id':fact['fact_id'],'value':None}],'hypotheses':[]}
 assert design.validate_interpretation(body,summary)
 body['observations'][0]['value']=0
 with pytest.raises(ValueError):design.validate_interpretation(body,summary)


def test_equivalent_float_comparison_roundoff_is_not_a_fabricated_discrepancy(fixture):
 s,r,_,_=fixture;r.result['comparison']['measured_minus_ideal_clearance_m']+=1e-14
 assert s.summary('b'*32)['facts']
 r.result['comparison']['measured_minus_ideal_clearance_m']+=.001
 with pytest.raises(ValueError):s.summary('b'*32)
