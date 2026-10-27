"""Explicit deterministic plan/protocol tests; no genuine AI decision claimed."""
import copy,json,time
from pathlib import Path
import pytest
from engineering.assembly import AssemblyComposer
from engineering.assembly_plan import validate_plan,construct,PlanError,GOAL
from engineering.assembly_fixture import fixture_plan
from engineering.assembly_live import (AssemblyTools,tools_for,context,request_first,request_second,observation,INPUT_BOUND,OUTPUT_BOUND,FrozenAssemblyAdapter)
from engineering.project import new_project,identity
from ide_api.engineering import EngineeringService
from core.agent.trace import ExecutionTrace
from core.agent.models import MockModelAdapter,ModelTurn,ToolCall
from core.agent.orchestration import AgentOrchestrator
from physics.contracts import canonical
from robustness.contracts import write_once

@pytest.fixture
def composer(tmp_path):
 p=new_project();p['world']['environment']['duration_s']=1.
 return AssemblyComposer(EngineeringService((tmp_path/'project').resolve(),initial_project=p))

def propose(c,plan=None):
 p=c.service.current();return c.propose(identity(p),p['revision'],plan or fixture_plan(),origin='OFFLINE_PROTOCOL_FIXTURE')


def test_raw_plan_constructs_from_actual_empty_r0_without_any_apply(composer):
 before=composer.service.current();head=(composer.root/'head.json').read_bytes();q=propose(composer)
 assert q['base_revision']==0 and q['resulting_revision']==1 and q['construction']['total_actions']==71
 assert len(q['construction']['schedule'])==9 and len(q['proposed_project']['shape_specs'])==9
 assert q['construction']['stage_trace'][-1]['result_stage_revision']==9
 assert composer.service.current()==before and (composer.root/'head.json').read_bytes()==head
 assert composer.reconstruct(q)[0]==q['proposed_project'] and q['origin']=='OFFLINE_PROTOCOL_FIXTURE'


def test_input_order_is_not_dependency_order(composer):
 p=fixture_plan();p['steps'].reverse();q=propose(composer,p)
 assert q['construction']['schedule']==['fixture_batch_'+str(i) for i in range(9)]

@pytest.mark.parametrize('mode',['cycle','unknown_dependency','duplicate_step','undeclared_dependency','forward_reference','wrong_axis','impossible_mount','invalid_dimension','unsupported_operation','extra_predicate'])
def test_invalid_plans_do_not_partially_commit(composer,mode):
 p=fixture_plan();before=(composer.root/'head.json').read_bytes()
 if mode=='cycle':p['steps'][0]['depends_on']=[p['steps'][-1]['id']]
 elif mode=='unknown_dependency':p['steps'][1]['depends_on']=['missing']
 elif mode=='duplicate_step':p['steps'][1]['id']=p['steps'][0]['id']
 elif mode=='undeclared_dependency':p['steps'][1]['depends_on']=[]
 elif mode=='forward_reference':p['steps'][0]['operations'][4]['part']['parent_body_id']='not_created'
 elif mode=='wrong_axis':next(o for o in p['steps'][2]['operations'] if o['kind']=='create_joint')['joint']['axis']=[1,0,0]
 elif mode=='impossible_mount':next(o for o in p['steps'][-1]['operations'] if o['kind']=='attach_part_to_mount')['mount_body_id']='floor'
 elif mode=='invalid_dimension':p['steps'][0]['operations'][-1]['part']['parameters']['length_m']=True
 elif mode=='unsupported_operation':p['steps'][0]['operations'][0]={'kind':'run_source','source':'no'}
 else:p['acceptance_predicates']={'contacts':'disabled'}
 with pytest.raises((ValueError,KeyError)):propose(composer,p)
 assert (composer.root/'head.json').read_bytes()==before and composer.service.current()['revision']==0
 assert not list(composer.proposals.root.glob('*.json'))
 assert list(composer.failures.root.glob('*.json'))

@pytest.mark.parametrize('which',['total','batch','deadline','local_budget'])
def test_resource_exhaustion_stops_before_commit(composer,which):
 p=fixture_plan();head=(composer.root/'head.json').read_bytes()
 if which=='total':
  for s in p['steps']:
   s['operations']=(s['operations']+[{'kind':'move_object','target':'rover_root','position_m':[0,0,.12]}]*16)[:16]
 if which=='batch':p['steps'][0]['operations']*=4
 args={'deadline':time.monotonic()-1} if which=='deadline' else {'action_budget':1} if which=='local_budget' else {}
 b=composer.service.current()
 with pytest.raises(ValueError):composer.propose(identity(b),0,p,**args)
 assert (composer.root/'head.json').read_bytes()==head


def test_separate_explicit_decision_commits_exactly_one_revision(composer):
 q=propose(composer);p=composer.service.current()
 with pytest.raises(ValueError,match='confirmation'):composer.decide(identity(p),0,q['proposal_id'],'apply','')
 assert composer.service.current()==p
 applied=composer.decide(identity(p),0,q['proposal_id'],'apply','APPLY REVIEWED ASSEMBLY')
 assert applied['project']==q['proposed_project'] and composer.service.current()['revision']==1
 with pytest.raises(ValueError,match='Stale'):composer.decide(identity(p),0,q['proposal_id'],'apply','APPLY REVIEWED ASSEMBLY')


def test_review_only_session_cannot_apply_even_with_confirmation(composer):
 write_once(composer.root/'assembly_session.json',{'task':GOAL,'status':'OFFLINE_PROTOCOL_FIXTURE','review_only':True})
 q=propose(composer);before=composer.service.current()
 with pytest.raises(ValueError,match='review-only'):composer.decide(identity(before),0,q['proposal_id'],'apply','APPLY REVIEWED ASSEMBLY')
 assert composer.service.current()==before


def test_tampering_and_changed_sources_never_apply(composer,monkeypatch):
 import engineering.assembly as module
 q=propose(composer);bad=copy.deepcopy(q);bad['assembly_plan']['steps'][-1]['operations'][-1]['frame_id']='origin'
 with pytest.raises(ValueError):composer.reconstruct(bad)
 original=module.sources();monkeypatch.setattr(module,'sources',lambda:{**original,'changed':'x'})
 with pytest.raises(ValueError,match='source identity'):composer.reconstruct(q)
 assert composer.service.current()['revision']==0


def test_real_rover_native_contacts_forces_movement_and_replay(composer):
 q=propose(composer);before=composer.service.current();native=composer.preview_native(identity(before),0,q['proposal_id'])
 assert native['status']=='MEASURED_ROVER_PROXY_PASS' and all(native['observations']['checks'].values())
 assert len(native['result']['samples'])==201 and native['result']['independent_verification']['fresh_native_integration_steps']==200
 assert native['observations']['wheel_ground_contact_events']>0 and not native['observations']['unexpected_contacts']
 assert native['observations']['horizontal_displacement_m']>=.005 and composer.service.current()==before
 with pytest.raises(FileExistsError):composer.preview_native(identity(before),0,q['proposal_id'])


def test_poor_locomotion_is_preserved_as_measured_failure(composer):
 p=fixture_plan()
 # Equal opposite rear torques: a real physical variant, not fabricated telemetry.
 op=next(o for s in p['steps'] for o in s['operations'] if o['kind']=='set_actuator' and 'rear_right' in o['target'])
 op['actuator']['command']=-op['actuator']['command']
 q=propose(composer,p);n=composer.preview_native(q['base_project_sha256'],0,q['proposal_id'])
 assert n['status']=='MEASURED_ROVER_REQUIREMENT_FAILURE'
 assert n['result']['independent_verification']['status']=='PASS' and not n['observations']['checks']['measurable_horizontal_movement']
 assert composer.service.current()['revision']==0


def test_deterministic_mock_protocol_is_explicitly_not_live(composer,tmp_path):
 trace=ExecutionTrace(tmp_path/'trace.jsonl',model_mode='deterministic_mock');t=AssemblyTools(composer,trace);p=composer.service.current()
 turns=[ModelTurn('',(ToolCall('inspect','inspect_assembly_capabilities',{}),)),ModelTurn('',(ToolCall('plan','propose_assembly_plan',{'expected_sha256':identity(p),'expected_revision':0,'plan':fixture_plan()}),))]
 result=AgentOrchestrator(MockModelAdapter(turns),t,trace,max_turns=2,max_tool_calls=2).run(canonical(context()))
 assert result['orchestration_status']=='LIMIT_REACHED' and t.result['ok'] and t.result['result']['resulting_revision']==1
 assert t.stage==2 and not t.schemas and composer.service.current()==p
 assert 'fixture_batch_' not in canonical(request_first()) and 'rover_root' not in canonical(observation(composer))


def test_two_turn_frozen_fake_sdk_and_budget_protocol(composer,tmp_path):
 from types import SimpleNamespace
 from core.agent.api_budget import ApiBudget,GPT54_POLICY
 trace=ExecutionTrace(tmp_path/'fake_trace.jsonl',model_mode='mock_openai_transport');t=AssemblyTools(composer,trace);b=composer.service.current();sent=[]
 def create(**wire):
  sent.append(wire);i=len(sent);args={} if i==1 else {'expected_sha256':identity(b),'expected_revision':0,'plan':fixture_plan()}
  call={'type':'function_call','call_id':'call_'+str(i),'name':tools_for(i-1)[0]['name'],'arguments':json.dumps(args)}
  raw={'id':'resp_'+str(i),'model':'gpt-5.4','service_tier':'default','status':'completed','output':[call],'usage':{'input_tokens':100,'output_tokens':100,'total_tokens':200,'input_tokens_details':{'cached_tokens':0},'output_tokens_details':{'reasoning_tokens':0}}}
  return SimpleNamespace(id=raw['id'],output=raw['output'],model_dump=lambda **kw:copy.deepcopy(raw))
 client=SimpleNamespace(max_retries=0,responses=SimpleNamespace(create=create));budget=ApiBudget(tmp_path/'fake_cost.json',policy=GPT54_POLICY,limit='.50',max_requests=2,input_token_bound=INPUT_BOUND,max_output_tokens=OUTPUT_BOUND)
 adapter=FrozenAssemblyAdapter(client,budget,tmp_path/'fake_api',trace,observation=t.obs);adapter.mode='mock_openai_transport'
 r=AgentOrchestrator(adapter,t,trace,max_turns=2,max_tool_calls=2).run(canonical(context()))
 assert r['orchestration_status']=='LIMIT_REACHED' and t.result['ok'] and len(sent)==2
 assert sent==[request_first(),request_second(t.obs,'resp_1','call_1')]
 assert composer.service.current()['revision']==0


def test_backend_accepts_different_plan_ids_and_dimensions_without_template_substitution(composer):
 p=fixture_plan();mapping={}
 for s in p['steps']:
  for op in s['operations']:
   if op['kind']=='create_object':mapping[op['id']]='own_'+op['id']
   if op['kind']=='create_parametric_part':mapping[op['part']['id']]='own_'+op['part']['id'];mapping[op['part']['body_id']]='own_'+op['part']['body_id']
 def remap(x,frame=False):
  if isinstance(x,list):return [remap(v,frame) for v in x]
  if frame:return copy.deepcopy(x)
  if isinstance(x,dict):return {k:remap(v,k=='frame') if k not in ('frame_id','source','hole_id','family','kind','primitive','parameter') else v for k,v in x.items()}
  return mapping.get(x,x) if isinstance(x,str) and not frame else x
 p=remap(p)
 for s in p['steps']:
  for op in s['operations']:
   if op['kind']=='create_parametric_part':
    part=op['part']
    if part['family']=='chassis':part['parameters']['length_m']=.28;part['parameters']['width_m']=.17
    if part['family']=='wheel':part['parameters']['outer_diameter_m']=.10;part['mass_kg']=.035
 q=propose(composer,p)
 assert q['assembly_plan']==p and q['proposed_project']['shape_specs'][0]['parameters']['length_m']==.28
 assert all(b.startswith('own_') for b in q['structural']['wheel_bodies']) and composer.service.current()['revision']==0


def test_native_fault_diagnostic_is_preserved_without_fabricated_success(composer,monkeypatch):
 q=propose(composer)
 def fault(*args,**kw):raise RuntimeError('DETERMINISTIC FAULT INJECTION, not a measured physical result')
 monkeypatch.setattr('world.simulation.run',fault)
 with pytest.raises(RuntimeError):composer.preview_native(q['base_project_sha256'],0,q['proposal_id'])
 failures=list((composer.root/'assembly_native').glob('*/failure.json'));assert len(failures)==1
 f=json.loads(failures[0].read_text());assert f['status']=='NATIVE_EXECUTION_FAILED' and not f['partial_telemetry_available'] and f['reservation_consumed']
 assert composer.service.current()['revision']==0
 with pytest.raises(FileExistsError):composer.preview_native(q['base_project_sha256'],0,q['proposal_id'])


def test_paid_budget_reservation_exhaustion_dispatches_nothing(composer,tmp_path):
 from types import SimpleNamespace
 from core.agent.api_budget import ApiBudget,GPT54_POLICY,BudgetBlocked
 def forbidden(**kw):raise AssertionError('No transport dispatch allowed')
 client=SimpleNamespace(max_retries=0,responses=SimpleNamespace(create=forbidden));trace=ExecutionTrace(tmp_path/'trace.jsonl',model_mode='mock_openai_transport')
 budget=ApiBudget(tmp_path/'fake_cost.json',policy=GPT54_POLICY,limit='.20',max_requests=2,input_token_bound=INPUT_BOUND,max_output_tokens=OUTPUT_BOUND)
 a=FrozenAssemblyAdapter(client,budget,tmp_path/'api',trace,observation=observation(composer))
 with pytest.raises(BudgetBlocked,match='budget'):a._request(**request_first())
 assert budget.snapshot()['requests']==[]
