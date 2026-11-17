"""Actual public saved evidence + explicit offline transport and injected clocks.

These tests never call a provider or MuJoCo forward/stepping function.
"""
import copy,json,time,os
from decimal import Decimal
from pathlib import Path
import pytest
from ide_api.agent_deadline import SharedDeadline
from ide_api.engineering_agent_live import EngineeringAgentLive,body_for
from ide_api.product_alpha import ProductAlpha
from core.agent.trace import read_trace
from tests.test_engineering_agent_live import live,OfflineClient,response,function,message,answer
from tests.test_engineering_agent import agent
from tests.test_native_results import saved,recorded

@pytest.fixture(autouse=True)
def no_real_engine(monkeypatch):
 import mujoco
 def forbidden(*args,**kwargs):raise AssertionError('Reliability unit test forbids real engine calls')
 for n in ('mj_forward','mj_step','mj_step1','mj_step2'):monkeypatch.setattr(mujoco,n,forbidden)

def test_selected_public_inspection_does_not_build_scene_or_scan_native_catalog(agent,monkeypatch):
 a,c=agent
 def forbidden(*args,**kwargs):raise AssertionError('Unnecessary scene/catalog access')
 monkeypatch.setattr('ide_api.product_alpha.scene',forbidden);monkeypatch.setattr(a.product.native,'discover',forbidden)
 ctx=a.context(c);v=a.dispatch(c,ctx['context_sha256'],'inspect_result',{})
 assert v['data']['evidence']['metrics']['minimum_clearance_m']==pytest.approx(.003)
 assert v['data']['evidence']['verdict']=='FAIL' and not v['data']['evidence']['source_current']
 # Consumer mutation cannot poison the validated immutable cache.
 v['data']['evidence']['metrics']['minimum_clearance_m']=100
 assert a.context(c)['result']['metrics']['minimum_clearance_m']==pytest.approx(.003)

def test_public_cache_rechecks_bytes_even_when_size_and_mtime_are_preserved(agent,tmp_path):
 a,c=agent;source=a.product.evidence_root;copy_root=tmp_path/'public';copy_root.mkdir()
 from ide_api.product_alpha import PACKAGES
 for name in PACKAGES:(copy_root/name).write_bytes((source/name).read_bytes())
 a.product.evidence_root=copy_root;assert a.context(c)['result']['verdict']=='FAIL'
 p=copy_root/'initial-evidence.json';stat=p.stat();raw=p.read_bytes();p.write_bytes(b'['+raw[1:]);os.utime(p,ns=(stat.st_atime_ns,stat.st_mtime_ns))
 with pytest.raises(ValueError,match='Pinned public'):a.context(c)

def test_public_context_cannot_probe_a_private_locator_before_validation(agent,monkeypatch):
 a,c=agent
 monkeypatch.setattr(a.product.native,'load',lambda *args:pytest.fail('Native read before public ID validation'))
 with pytest.raises(ValueError,match='Public context'):a.context({**c,'result_id':'native_'+'a'*32+'_'+'b'*64})

def test_continuation_timeout_keeps_real_tool_evidence_and_unknown_reservation(live):
 s,key,d,a=live;c=OfflineClient([response(0,[function()]),TimeoutError('PRIVATE_EXCEPTION_MUST_NOT_ESCAPE')]);v=s.execute(key,a,offline_client=c)
 assert v['status']=='PROVIDER_TIMEOUT_USAGE_UNKNOWN' and len(c.calls)==2
 assert len(v['state']['events'])==1 and v['state']['events'][0]['output']['data']['evidence']['verdict']=='FAIL'
 assert v['state']['final_answer_status']=='NOT_COMPLETED' and v['state']['accounting_status']=='UNRESOLVED_RESERVATION_RETAINED'
 assert not v['state'].get('explanation') and v['state']['retry_allowed'] is False
 assert Decimal(v['state']['usage']['accounted_cost_usd'])>Decimal(v['state']['usage']['measured_cost_usd'])
 assert 'PRIVATE_EXCEPTION_MUST_NOT_ESCAPE' not in json.dumps(v)
 assert c.calls[1]['previous_response_id']=='resp_offline_0' and c.calls[1]['tool_choice']=='none'
 rows=read_trace(s._folder(key)/'trace.jsonl');names=[r['event'] for r in rows]
 for name in ('provider_dispatch_started','provider_response_received','provider_usage_settled','tool_started','tool_completed','continuation_ready','provider_transport_failed','turn_terminal'):assert name in names
 calls=[r['payload'] for r in rows if r['event']=='provider_dispatch_started'];assert len(calls)==2
 assert len({r['public_correlation_id'] for r in calls})==2
 for i,r in enumerate(calls):
  assert c.calls[i]['extra_headers']=={'X-Client-Request-Id':r['public_correlation_id']}
  assert r['public_correlation_id'] not in (key,d['context_sha256']) and r['clock']['remaining_seconds']>0
 with pytest.raises(ValueError,match='Consumed'):s.execute(key,a,offline_client=c)
 assert len(c.calls)==2

def test_final_answer_and_evidence_bound_continuation_succeed_offline(live):
 s,key,d,a=live;c=OfflineClient([response(0,[function()]),response(1,[message(answer(d))])]);v=s.execute(key,a,offline_client=c)
 assert v['status']=='COMPLETED' and v['state']['accounting_status']=='REPORTED_USAGE_SETTLED_NOT_INVOICE'
 assert v['state']['origin']=='OFFLINE_TRANSPORT_FIXTURE_NOT_AI' and c.calls[1]['tool_choice']=='none'
 assert len(c.calls)==2 and len(v['state']['events'])==1

class FakeClocks:
 def __init__(self):self.mono=10.;self.wall=time.time()
 def advance(self,n):self.mono+=n;self.wall+=n

def install_clocks(monkeypatch,clock):
 original=SharedDeadline.start.__func__
 def start(cls,seconds,expiry):return original(cls,seconds,expiry,monotonic=lambda:clock.mono,wall=lambda:clock.wall)
 monkeypatch.setattr(SharedDeadline,'start',classmethod(start))

def test_http_timeout_is_clamped_to_remaining_shared_budget(live,monkeypatch):
 s,key,d,a=live;clock=FakeClocks();install_clocks(monkeypatch,clock);original=s._check;advance={'pending':False}
 def check(*args):
  original(*args)
  if advance['pending']:clock.advance(175);advance['pending']=False
 monkeypatch.setattr(s,'_check',check)
 def first(body):advance['pending']=True;return response(0,[function()])
 c=OfflineClient([first,response(1,[message(answer(d))])]);v=s.execute(key,a,offline_client=c)
 assert v['status']=='COMPLETED' and len(c.calls)==2
 assert c.calls[0]['timeout']==30 and c.calls[1]['timeout']==pytest.approx(5)

def test_clock_jump_after_first_usage_stops_before_another_dispatch(live,monkeypatch):
 s,key,d,a=live;clock=FakeClocks();install_clocks(monkeypatch,clock)
 def first(body):clock.wall+=333;return response(0,[function()])
 c=OfflineClient([first]);v=s.execute(key,a,offline_client=c)
 assert v['status']=='CLOCK_DISCONTINUITY_OUTCOME_MAY_BE_UNKNOWN' and len(c.calls)==1
 assert v['state']['usage']['requests'][0]['state']=='SETTLED' and not v['state'].get('explanation')

def test_tool_timeout_is_separate_and_does_not_start_continuation(live,monkeypatch):
 s,key,d,a=live;clock=FakeClocks();install_clocks(monkeypatch,clock);dispatch=s.agent.dispatch
 def slow(*args,**kwargs):
  value=dispatch(*args,**kwargs);clock.advance(21);return value
 monkeypatch.setattr(s.agent,'dispatch',slow);c=OfflineClient([response(0,[function()])]);v=s.execute(key,a,offline_client=c)
 assert v['status']=='TIMEOUT_NO_RETRY' and len(c.calls)==1 and v['state']['usage']['requests'][0]['state']=='SETTLED'

def test_worker_stop_recovers_persisted_tool_evidence_and_accounting(live):
 s,key,d,a=live;c=OfflineClient([response(0,[function()]),TimeoutError('offline timeout')]);s.execute(key,a,offline_client=c);f=s._folder(key)
 (f/'result.json').unlink() # disposable interruption fixture, never historical evidence
 from ide_api.rail_sweeps import write_once
 write_once(f/'worker_stop.json',{'status':'DEADLINE_STOPPED_USAGE_MAY_BE_UNKNOWN','no_retry':True},2048)
 v=s.read(key);assert v['state']['events'][0]['name']=='inspect_result' and v['state']['accounting_status']=='UNRESOLVED_RESERVATION_RETAINED'
 (f/'api_cost_ledger.json').write_text('{') # intentionally unreadable disposable fixture
 v=s.read(key);assert v['state']['usage'] is None and v['state']['accounting_status']=='UNRESOLVED_LEDGER_UNREADABLE'
 assert len(v['state']['events'])==1 and not v['state'].get('explanation')

def test_invalid_saved_tool_is_not_relabelled_as_successful_evidence(live):
 s,key,d,a=live;c=OfflineClient([response(0,[function()]),TimeoutError('offline')]);s.execute(key,a,offline_client=c);f=s._folder(key);v=json.loads((f/'tool_001.json').read_text());v['output']['data']['evidence']['id']='not-the-selected-result';(f/'tool_001.json').write_text(json.dumps(v))
 value=s.read(key);assert not value['state']['events'] and value['state']['saved_tool_evidence_status']=='UNAVAILABLE_OR_INVALID' and value['status']!='COMPLETED'

def test_real_execution_requires_server_owned_shared_stamp(live):
 s,key,d,a=live
 with pytest.raises((ValueError,OSError)):s.execute(key,a)
 assert not (s._folder(key)/'consumed.json').exists()


def test_cancellation_after_valid_tool_prevents_continuation_but_preserves_evidence(live,monkeypatch):
 s,key,d,a=live;dispatch=s.agent.dispatch
 def cancel_after_tool(*args,**kwargs):
  value=dispatch(*args,**kwargs);s.cancel(key);return value
 monkeypatch.setattr(s.agent,'dispatch',cancel_after_tool)
 client=OfflineClient([response(0,[function()])]);v=s.execute(key,a,offline_client=client)
 assert v['status']=='CANCELLED_WITH_POSSIBLE_USAGE' and len(client.calls)==1
 assert v['state']['usage']['requests'][0]['state']=='SETTLED' and not v['state'].get('explanation')

def test_existing_policy_reservation_is_independently_bounded(live):
 from core.agent.api_budget import cost,GPT54_POLICY
 from ide_api.engineering_agent_live import policy_for
 s,key,d,a=live;p=d['policy']
 assert p['max_requests']==2 and p['max_tool_calls']==1 and p['maximum_total_tokens']==2*(p['input_token_bound']+p['max_output_tokens'])
 assert max(d['serialized_bounds'])<=p['input_token_bound']
 assert cost(p['input_token_bound'],0,p['max_output_tokens'],policy=GPT54_POLICY)*2==Decimal('0.28672')<=Decimal(p['hard_cap_usd'])
 assert policy_for('inspect','bounded_rover_ramp_v1')['maximum_tool_output_bytes']==10000
