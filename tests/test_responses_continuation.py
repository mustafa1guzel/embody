"""Deterministic SDK-wire regression tests; only developer-authored fake responses."""
from dataclasses import asdict
from decimal import Decimal
import json

import pytest

openai = pytest.importorskip('openai')
import httpx2 as httpx
from pydantic import TypeAdapter
from openai.types.responses.response_create_params import ResponseCreateParamsNonStreaming

from core.agent.api_budget import ApiBudget, BudgetBlocked
from core.agent.credentials import ModelRequestError, _disable_transport_logging
from core.agent.live_model import BudgetedOpenAIAdapter
from core.agent.models import OpenAIResponsesAdapter
from core.agent.orchestration import AgentOrchestrator
from core.agent.tools import AgentTools
from core.agent.trace import ExecutionTrace


def response(index, calls):
    return {'id': f'resp_mock_{index}', 'object': 'response', 'created_at': 1792738000,
            'status': 'completed', 'model': 'gpt-5.4-mini', 'service_tier': 'default',
            'output': ([{'type': 'reasoning', 'id': 'rs_mock', 'summary': [],
                         'encrypted_content': 'mock-opaque-reasoning', 'status': None}] + calls if index == 0 else
                       [{'type': 'message', 'id': 'msg_mock', 'role': 'assistant', 'status': 'completed',
                         'content': [{'type': 'output_text', 'text': 'Tool evidence received.', 'annotations': []}]}]),
            'usage': {'input_tokens': 200, 'input_tokens_details': {'cached_tokens': 0},
                      'output_tokens': 50, 'output_tokens_details': {'reasoning_tokens': 30},
                      'total_tokens': 250}}


def function_call(call_id='call_exact_from_model', name='get_robot_context'):
    return {'id': 'fc_mock_' + call_id, 'type': 'function_call', 'call_id': call_id,
            'name': name, 'arguments': '{"scenario_id":"A"}', 'status': 'completed',
            'async': None, 'caller': None, 'namespace': None}


def fixture(tmp_path, *, calls=None, second_error=None):
    calls = [function_call()] if calls is None else calls
    wire = []

    def serve(request):
        data = json.loads(request.content)
        # Validate the actual SDK-serialized HTTP body, not just our Python dict.
        TypeAdapter(ResponseCreateParamsNonStreaming).validate_python(data, strict=True, extra='forbid')
        wire.append(data)
        index = len(wire) - 1
        if index == 1 and second_error:
            return httpx.Response(second_error[0], json={'error': second_error[1]},
                                  headers={'x-request-id': 'req_mock_validation'})
        return httpx.Response(200, json=response(index, calls))

    _disable_transport_logging()
    client = openai.OpenAI(api_key='sk-dummy-never-real-secret-123456789', max_retries=0,
                           http_client=httpx.Client(transport=httpx.MockTransport(serve)))
    budget = ApiBudget(tmp_path / 'ledger.json', limit=Decimal('0.05'), input_token_bound=16384,
                       max_output_tokens=2048, max_requests=2)
    trace = ExecutionTrace(tmp_path / 'trace', model_mode='explicit_mock_http_transport')
    model = BudgetedOpenAIAdapter(client, budget, tmp_path / 'api', trace)
    tools = AgentTools(tmp_path / 'tools', trace)
    return model, tools, budget, wire, trace


@pytest.mark.parametrize('multiple', [False, True])
def test_two_turn_real_tool_dispatch_valid_wire_and_reasoning_retention(tmp_path, multiple):
    calls = [function_call()]
    if multiple:
        calls.append(function_call('call_second_exact', 'get_world_context'))
    model, tools, budget, wire, trace = fixture(tmp_path, calls=calls)
    result = AgentOrchestrator(model, tools, trace, max_turns=2).run('Read physical context only.')
    assert result['orchestration_status'] == 'COMPLETED'
    assert len(wire) == 2
    first, second = wire
    assert 'previous_response_id' not in first
    assert second['previous_response_id'] == 'resp_mock_0'
    assert second['instructions'] == first['instructions'] and first['instructions']
    assert first['store'] is True and second['store'] is True
    assert 'conversation' not in first and 'conversation' not in second
    assert all(i['type'] == 'function_call_output' for i in second['input'])
    assert [i['call_id'] for i in second['input']] == [i['call_id'] for i in calls]
    assert all(set(i) == {'type', 'call_id', 'output'} and isinstance(i['output'], str) for i in second['input'])
    measured = json.loads(second['input'][0]['output'])
    assert measured['ok'] and measured['result']['effective_mujoco']['carriage_mass_kg'] > 0
    assert (tmp_path / 'tools/contexts/A.xml').exists()  # Real compiled MuJoCo context.
    assert 'mock-opaque-reasoning' in (tmp_path / 'api/response_000.json').read_text()
    assert 'mock-opaque-reasoning' not in json.dumps(second)  # Retained server-side.
    assert len(budget.snapshot()['requests']) == 2 and Decimal(budget.snapshot()['accounted_cost_usd']) < Decimal('.05')
    with pytest.raises(BudgetBlocked):
        budget.begin(second)
    model.close()


@pytest.mark.parametrize('bad_id', ['', None, 'invented_call_id'])
def test_missing_or_unknown_call_id_rejected_before_request(tmp_path, bad_id):
    model, tools, budget, wire, trace = fixture(tmp_path)
    messages = [{'role': 'system', 'content': 'instructions'}, {'role': 'user', 'content': 'context'}]
    turn = model.complete(tuple(messages), tools.schemas)
    messages.extend([{'role': 'assistant', 'provider_items': list(turn.provider_items)},
                     {'role': 'tool', 'tool_call_id': bad_id, 'content': '{}'}])
    with pytest.raises(ValueError, match='call_id'):
        model.complete(tuple(messages), tools.schemas)
    assert len(wire) == len(budget.snapshot()['requests']) == 1
    model.close()


@pytest.mark.parametrize('bad_output', [{'not': 'serialized'}, object(), b'bytes', float('nan')])
def test_invalid_tool_output_serialization_rejected_locally(tmp_path, bad_output):
    model, tools, budget, wire, trace = fixture(tmp_path)
    messages = [{'role': 'user', 'content': 'context'}]
    turn = model.complete(tuple(messages), tools.schemas)
    messages.extend([{'role': 'assistant', 'provider_items': list(turn.provider_items)},
                     {'role': 'tool', 'tool_call_id': turn.tool_calls[0].call_id, 'content': bad_output}])
    with pytest.raises(ValueError, match='serialized'):
        model.complete(tuple(messages), tools.schemas)
    assert len(wire) == len(budget.snapshot()['requests']) == 1
    model.close()


def test_missing_model_call_id_never_invented(tmp_path):
    call = function_call()
    del call['call_id']
    model, tools, budget, wire, trace = fixture(tmp_path, calls=[call])
    with pytest.raises(ValueError, match='missing call_id'):
        model.complete(({'role': 'user', 'content': 'context'},), tools.schemas)
    assert len(wire) == 1
    model.close()


def test_validation_error_diagnostics_and_reservation_cleanup(tmp_path, monkeypatch):
    private = 'private-environment-value-never-log'
    monkeypatch.setenv('PRIVATE_TEST_TOKEN', private)
    message = "Unknown parameter: 'input[3].async_'. " + private + ' sk-dummy-never-real-secret-123456789'
    model, tools, budget, wire, trace = fixture(tmp_path, second_error=(400, {
        'type': 'invalid_request_error', 'code': 'unknown_parameter',
        'param': 'input[3].async_', 'message': message}))
    result = AgentOrchestrator(model, tools, trace, max_turns=2).run('Read context only')
    assert result['orchestration_status'] == 'ERROR' and len(wire) == 2
    diagnostic = json.loads((tmp_path / 'api/error_001.json').read_text())
    assert diagnostic['http_status'] == 400 and diagnostic['error_type'] == 'invalid_request_error'
    assert diagnostic['error_code'] == 'unknown_parameter' and diagnostic['parameter'] == 'input[3].async_'
    assert diagnostic['request_id'] == 'req_mock_validation'
    assert "Unknown parameter: 'input[3].async_'." in diagnostic['message']
    assert private not in json.dumps(diagnostic) and 'sk-dummy' not in json.dumps(diagnostic)
    assert 'authorization' not in json.dumps(diagnostic).lower()
    assert 'output' not in diagnostic['payload_structure']['input'][0]
    ledger = budget.snapshot()
    assert ledger['requests'][1]['state'] == 'REJECTED_UNBILLED'
    assert ledger['accounted_cost_usd'] == ledger['measured_cost_usd']
    with pytest.raises(BudgetBlocked):
        budget.begin(wire[1])
    model.close()


def test_transport_failure_retains_unknown_reservation(tmp_path):
    budget = ApiBudget(tmp_path / 'ledger.json', limit=Decimal('.05'), input_token_bound=16384,
                       max_output_tokens=2048, max_requests=2)
    index = budget.begin({'input': [{'role': 'user', 'content': 'small probe'}]})
    budget.fail(index)
    assert budget.snapshot()['requests'][0]['state'] == 'FAILED_USAGE_UNKNOWN'
    assert Decimal(budget.snapshot()['accounted_cost_usd']) == Decimal('.021504')


def test_manual_mode_normalizes_saved_sdk_output_without_server_chain():
    from core.agent.models import _replay_item
    bad = function_call()
    bad['async_'] = bad.pop('async')
    replay = _replay_item(bad)
    assert 'async_' not in replay and all(v is not None for v in replay.values())
    assert replay['call_id'] == bad['call_id'] and replay['arguments'] == bad['arguments']
    reasoning = _replay_item({'type': 'reasoning', 'id': 'rs', 'summary': [],
                               'encrypted_content': 'opaque', 'status': None, 'content': []})
    assert reasoning == {'type': 'reasoning', 'id': 'rs', 'summary': [], 'encrypted_content': 'opaque'}


def test_payload_envelope_blocks_large_request_before_paid_dispatch(tmp_path):
    budget = ApiBudget(tmp_path / 'ledger.json', limit=Decimal('.05'), input_token_bound=16384,
                       max_output_tokens=2048, max_requests=2)
    with pytest.raises(BudgetBlocked, match='envelope'):
        budget.begin({'input': [{'role': 'user', 'content': 'x' * 20_000}]})
    assert budget.snapshot()['requests'] == []


@pytest.mark.parametrize('fail_second', [False, True])
def test_minimal_probe_runner_uses_only_two_requests_and_context_tool(tmp_path, fail_second):
    from tools.continuation_probe import run_probe
    wire = []

    def serve(request):
        data = json.loads(request.content)
        TypeAdapter(ResponseCreateParamsNonStreaming).validate_python(data, strict=True, extra='forbid')
        wire.append(data)
        index = len(wire) - 1
        assert len(data['tools']) == 1 and data['tools'][0]['name'] == 'get_robot_context'
        if index == 0:
            assert data['tool_choice'] == {'type': 'function', 'name': 'get_robot_context'}
        else:
            assert data['tool_choice'] == 'none' and data['previous_response_id'] == 'resp_mock_0'
            if fail_second:
                return httpx.Response(400, json={'error': {'type': 'invalid_request_error',
                                      'message': "Invalid value at 'input[0].call_id'.", 'param': 'input[0].call_id'}},
                                      headers={'x-request-id': 'req_mock_probe'})
        return httpx.Response(200, json=response(index, [function_call()]))

    _disable_transport_logging()
    client = openai.OpenAI(api_key='dummy-probe', max_retries=0,
                           http_client=httpx.Client(transport=httpx.MockTransport(serve)))
    result = run_probe(tmp_path / 'probe', client=client)
    assert result['status'] == ('FAIL' if fail_second else 'PASS')
    assert result['transport_mode'] == 'injected_test_client'
    assert len(wire) == len(result['api_budget']['requests']) == 2
    assert Decimal(result['api_budget']['accounted_cost_usd']) < Decimal('.05')
    assert result['candidate_patch_generated'] is False and result['candidate_execution'] == 'NOT_RUN'
    assert not list((tmp_path / 'probe').rglob('candidate_*.py'))
    assert client.is_closed
