"""Offline checks for the user's experiment bounds, never a scripted repair."""
from decimal import Decimal
import json
from types import SimpleNamespace

import pytest

from core.agent.api_budget import ApiBudget, BudgetBlocked, cost
from core.agent.models import MockModelAdapter, ModelTurn, ToolCall
from core.agent.orchestration import AgentOrchestrator
from core.agent.trace import ExecutionTrace
from core.live_experiment import (ExperimentAdapter, ExperimentTools, INPUT_ALLOWANCE,
                                  OUTPUT_ALLOWANCE, MAX_REQUESTS, MAX_TOOL_CALLS,
                                  MAX_PATCH_ATTEMPTS, REQUEST)


def test_exact_user_task_and_combined_planned_allowances():
    assert REQUEST == 'Investigate why my robot collides with the wall. Read the real controller, inspect BODYBASE and WORLDBASE, run physical simulations, determine the cause, and generate a source-code repair that works across different robot and environment configurations.'
    assert (MAX_REQUESTS, MAX_TOOL_CALLS, MAX_PATCH_ATTEMPTS) == (12, 20, 2)
    assert cost(INPUT_ALLOWANCE, 0, OUTPUT_ALLOWANCE) == Decimal('.038400')
    assert cost(INPUT_ALLOWANCE, 0, OUTPUT_ALLOWANCE)*MAX_REQUESTS == Decimal('.460800')


def test_two_proposal_attempts_rejected_without_executing_or_writing_source(tmp_path):
    trace = ExecutionTrace(tmp_path/'trace', model_mode='explicit_mock')
    tools = ExperimentTools(tmp_path/'tools', trace)
    arguments = {'target_path': 'tests/forbidden.py', 'expected_original_sha256': '0'*64,
                 'proposed_source': '# invalid target fixture only', 'explanation': 'No candidate execution'}
    tools.dispatch('propose_patch', arguments)
    tools.dispatch('propose_patch', arguments)
    with pytest.raises(RuntimeError, match='exhausted'):
        tools.dispatch('propose_patch', arguments)
    assert tools.patch_attempts == 2
    assert not list((tmp_path/'tools').rglob('controller.py'))


@pytest.mark.parametrize('status', ['PASS','BLOCKED'])
def test_revision_not_allowed_after_success_or_isolation_block(tmp_path, status):
    tools = ExperimentTools(tmp_path/'tools', ExecutionTrace(tmp_path/'trace', model_mode='explicit_mock'))
    tools.last_candidate_id = 'candidate_dummy'
    tools.verifier.output.mkdir(parents=True)
    (tools.verifier.output/'candidate_dummy.json').write_text(json.dumps({
        'verification_execution':status,'physical_safety_status':'PASS' if status=='PASS' else 'NOT_EVALUATED'}))
    with pytest.raises(RuntimeError):
        tools.dispatch('propose_patch', {})
    assert tools.patch_attempts == 0


def test_budget_twelve_request_hard_limit_with_finite_allowances(tmp_path):
    budget = ApiBudget(tmp_path/'ledger.json', input_token_bound=INPUT_ALLOWANCE,
                       max_output_tokens=OUTPUT_ALLOWANCE,max_requests=MAX_REQUESTS)
    request = {'input':[{'role':'user','content':'small fixture'}],'tools':[]}
    for _ in range(12):
        index = budget.begin(request)
        budget.settle(index, {'input_tokens':100,'input_tokens_details':{'cached_tokens':0},
                             'output_tokens':100,'output_tokens_details':{'reasoning_tokens':10},
                             'total_tokens':200},response_id='mock',returned_model='gpt-5.4-mini',service_tier='default')
    with pytest.raises(BudgetBlocked,match='count'):
        budget.begin(request)
    assert len(budget.snapshot()['requests']) == 12


def test_twenty_tool_call_limit_stops_before_twenty_first_dispatch(tmp_path):
    class Tools:
        schemas=()
        calls=0
        def dispatch(self,name,arguments):
            self.calls += 1
            return {'ok':True,'result':{}}
    tools=Tools()
    model=MockModelAdapter([ModelTurn(tool_calls=tuple(ToolCall(str(i),'get_robot_context',{}) for i in range(20))),
                            ModelTurn(tool_calls=(ToolCall('21','get_robot_context',{}),))])
    result=AgentOrchestrator(model,tools,ExecutionTrace(tmp_path/'trace',model_mode='explicit_mock'),
                             max_turns=12,max_tool_calls=20).run('Fixture only')
    assert result['orchestration_status']=='ERROR' and tools.calls==20


def test_model_selects_tool_order_and_parallel_calls_are_not_forced(tmp_path):
    requests=[]
    def create(**request):
        requests.append(request)
        raw={'id':'resp_mock','status':'completed','model':'gpt-5.4-mini','service_tier':'default',
             'usage':{'input_tokens':100,'input_tokens_details':{'cached_tokens':0},'output_tokens':10,
                      'output_tokens_details':{'reasoning_tokens':0},'total_tokens':110},'output':[]}
        return SimpleNamespace(id=raw['id'],output=[],model_dump=lambda **kwargs:raw)
    client=SimpleNamespace(max_retries=0,responses=SimpleNamespace(create=create))
    budget=ApiBudget(tmp_path/'ledger.json',input_token_bound=INPUT_ALLOWANCE,
                     max_output_tokens=OUTPUT_ALLOWANCE,max_requests=12)
    model=ExperimentAdapter(client,budget,tmp_path/'api',ExecutionTrace(tmp_path/'trace',model_mode='explicit_mock'),
                            parallel_tool_calls=True)
    model.complete(({'role':'system','content':'Original instructions'},{'role':'user','content':REQUEST}),())
    assert requests[0]['parallel_tool_calls'] is True
    assert 'tool_choice' not in requests[0]
    assert requests[0]['input'] == [{'role':'user','content':REQUEST}]
