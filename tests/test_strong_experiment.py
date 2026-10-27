"""Offline authorization, accounting and evidence reuse; no real API calls."""
from decimal import Decimal
import json
from types import SimpleNamespace

import pytest

from core.agent.api_budget import ApiBudget, BudgetBlocked, GPT54_POLICY, cost
from core.agent.credentials import ModelRequestError
from core.agent.development_budget import DevelopmentBudget, historical_accounting
from core.agent.trace import ExecutionTrace, read_trace
from core.strong_experiment import EvidenceTools, StrongAdapter, REQUEST


def usage(incoming=1000, outgoing=100):
    return {'input_tokens':incoming,'input_tokens_details':{'cached_tokens':0},'output_tokens':outgoing,
            'output_tokens_details':{'reasoning_tokens':10},'total_tokens':incoming+outgoing}


def budget(path, **kwargs):
    return ApiBudget(path, policy=GPT54_POLICY, limit='2.50', input_token_bound=131072,
                     max_output_tokens=25000, max_requests=12, **kwargs)


def test_explicit_model_policy_and_bounded_conservative_reservation(tmp_path):
    b=budget(tmp_path/'ledger')
    request={'input':[{'role':'user','content':'Offline fixture'}]}
    b.begin(request)
    assert b.snapshot()['model']=='gpt-5.4' and b.snapshot()['reasoning_effort']=='low'
    assert cost(131072,0,25000,policy=GPT54_POLICY)==Decimal('0.702680')
    assert Decimal(b.snapshot()['accounted_cost_usd'])==Decimal('0.702680')
    with pytest.raises(BudgetBlocked): b.begin(request)
    assert cost(1000,200,500,policy=GPT54_POLICY)==Decimal('0.009550')


@pytest.mark.parametrize('wrong',['gpt-5.4-mini','gpt-5.4-pro','gpt-5.5','gpt-5.4-nano','gpt-5.4-unapproved'])
def test_wrong_returned_model_retains_full_reservation(tmp_path,wrong):
    b=budget(tmp_path/'ledger')
    i=b.begin({'input':[]})
    with pytest.raises(BudgetBlocked):
        b.settle(i,usage(),response_id='offline',returned_model=wrong,service_tier='default')
    assert b.snapshot()['requests'][0]['state']=='PENDING'
    assert Decimal(b.snapshot()['accounted_cost_usd'])==Decimal('0.702680')


def test_strong_transport_uses_existing_server_continuation_and_low_effort(tmp_path):
    requests=[]
    def create(**request):
        requests.append(request)
        output=([{'type':'function_call','name':'read_project','call_id':'real-shaped-offline-call',
                  'arguments':'{"path":"robot/controller.py"}'}] if len(requests)==1 else [])
        raw={'id':f'offline_response_{len(requests)}','model':'gpt-5.4-2026-03-05',
             'status':'completed','service_tier':'default','usage':usage(),'output':output}
        return SimpleNamespace(id=raw['id'],output=output,model_dump=lambda **_:raw)
    model=StrongAdapter(SimpleNamespace(max_retries=0,responses=SimpleNamespace(create=create)),
        budget(tmp_path/'ledger'),tmp_path/'api',ExecutionTrace(tmp_path/'trace',model_mode='explicit_mock'))
    messages=({'role':'system','content':'Developer test instructions'}, {'role':'user','content':REQUEST})
    turn=model.complete(messages,())
    model.complete((*messages,{'role':'tool','tool_call_id':turn.tool_calls[0].call_id,'content':'{"ok":true}'}),())
    assert requests[1]['previous_response_id']=='offline_response_1'
    assert requests[1]['input']==[{'type':'function_call_output','call_id':'real-shaped-offline-call','output':'{"ok":true}'}]
    for r in requests:
        assert r['reasoning']=={'effort':'low'} and r['max_output_tokens']==25000
        assert r['model']=='gpt-5.4' and r['store'] is True
        assert 'submit a concrete complete-source proposal' in r['instructions']
        assert 'stopping_distance' not in r['instructions']


def test_cumulative_reservation_uncertain_charges_and_warning(tmp_path):
    prior=ApiBudget(tmp_path/'prior.json')
    prior.begin();prior.fail(0,http_status=400)
    b=DevelopmentBudget(tmp_path/'new.json',cumulative_path=tmp_path/'cumulative.json',
        historical_paths=[prior.path],policy=GPT54_POLICY,limit='2.50',input_token_bound=131072,
        max_output_tokens=25000,max_requests=12)
    assert Decimal(b.history['accounted_cost_usd'])==Decimal('0.336864')
    first=b.begin({'input':[]})
    b.settle(first,usage(100000,25000),response_id='offline_unique',returned_model='gpt-5.4',service_tier='default')
    second=b.begin({'input':[]})
    b.settle(second,usage(100000,25000),response_id='offline_unique2',returned_model='gpt-5.4',service_tier='default')
    b.begin({'input':[]})
    c=json.loads((tmp_path/'cumulative.json').read_text())
    assert c['warning_events'] and c['warning_threshold_usd']=='1.50'
    assert Decimal(c['accounted_cost_usd'])==Decimal('2.289544')
    assert c['historical']['sessions'][0]['ledger']==prior.snapshot()
    b.fail(2,http_status=504)
    assert Decimal(json.loads((tmp_path/'cumulative.json').read_text())['accounted_cost_usd'])==Decimal('2.289544')
    with pytest.raises(BudgetBlocked):b.begin({'input':[]})


def test_historical_duplicate_response_rejected(tmp_path):
    b=ApiBudget(tmp_path/'prior.json');i=b.begin()
    b.settle(i,usage(),response_id='duplicate',returned_model='gpt-5.4-mini',service_tier='default')
    with pytest.raises(BudgetBlocked,match='duplicate'):
        historical_accounting([b.path,b.path])


def test_overall_cap_stops_before_new_request(tmp_path):
    b=DevelopmentBudget(tmp_path/'new.json',cumulative_path=tmp_path/'total.json',historical_paths=[],
                        policy=GPT54_POLICY,limit='2.50',input_token_bound=131072,max_output_tokens=25000)
    b.history['accounted_cost_usd']='29.5'
    with pytest.raises(BudgetBlocked,match='overall'):
        b.begin({'input':[]})
    assert b.snapshot()['requests']==[]


def test_context_and_baseline_reuse_preserves_real_evidence_and_detects_tampering(tmp_path):
    trace=ExecutionTrace(tmp_path/'trace',model_mode='offline_real_physics')
    tools=EvidenceTools(tmp_path/'tools',trace)
    a=tools.get_robot_context('A'); b=tools.get_world_context('A')
    assert a['effective_mujoco']==b['effective_mujoco'] and len(tools._contexts)==1
    first=tools.run_simulation('A','faulty'); second=tools.run_simulation('A','faulty')
    assert first['simulation_run_id']==second['simulation_run_id'] and second['reused_existing_measurement']
    assert len(tools._runs)==1 and read_trace(trace.path)[-1]['event']=='baseline_evidence_reused'
    folder=tools._runs[first['simulation_run_id']]['directory']
    (folder/'telemetry.json').write_text('{}')
    with pytest.raises(ValueError,match='integrity'):
        tools.run_simulation('A','faulty')


def test_experiment_cap_blocks_before_reservation_exceeds_250(tmp_path):
    b=budget(tmp_path/'ledger')
    for n in range(3):
        i=b.begin({'input':[]})
        b.settle(i,usage(100000,25000),response_id=f'offline_{n}',returned_model='gpt-5.4',service_tier='default')
    before=b.snapshot()
    with pytest.raises(BudgetBlocked,match='budget'):
        b.begin({'input':[]})
    assert b.snapshot()==before
