"""Offline budget/transport evidence using dummy responses, never live credentials."""
from decimal import Decimal
import json
from types import SimpleNamespace

import pytest

from core.agent.api_budget import (ApiBudget, BudgetBlocked, MODEL, MAX_OUTPUT_TOKENS,
                                   reservation, cost)
from core.agent.credentials import ModelRequestError
from core.agent.live_model import BudgetedOpenAIAdapter
from core.agent.trace import ExecutionTrace, read_trace


def usage(incoming=1000, cached=200, outgoing=500, reasoning=400):
    return {'input_tokens': incoming, 'input_tokens_details': {'cached_tokens': cached},
            'output_tokens': outgoing, 'output_tokens_details': {'reasoning_tokens': reasoning},
            'total_tokens': incoming + outgoing}


def settle(budget, index, counts=None):
    budget.settle(index, counts or usage(), response_id='mock-response',
                  returned_model=MODEL + '-mock-snapshot', service_tier='default')


def test_full_context_reservation_and_cached_reasoning_cost(tmp_path):
    assert reservation() == Decimal('0.336864')
    assert cost(1000, 200, 500) == Decimal('0.002865')
    budget = ApiBudget(tmp_path / 'ledger.json')
    index = budget.begin()
    assert Decimal(budget.snapshot()['accounted_cost_usd']) == reservation()
    settle(budget, index)
    saved = budget.snapshot()
    assert saved['accounted_cost_usd'] == saved['measured_cost_usd'] == '0.002865'
    assert saved['totals'] == {'input_tokens': 1000, 'cached_input_tokens': 200,
                              'output_tokens': 500, 'reasoning_tokens': 400}


def test_cumulative_limit_blocks_next_request_and_preserves_ledger(tmp_path):
    budget = ApiBudget(tmp_path / 'ledger.json')
    settle(budget, budget.begin(), usage(390000, 0, 8192, 7000))
    before = budget.snapshot()
    with pytest.raises(BudgetBlocked, match='exceed'):
        budget.begin()
    assert budget.snapshot() == before
    assert Decimal(before['accounted_cost_usd']) <= Decimal('0.50')


def test_pending_or_failed_usage_never_releases_reservation(tmp_path):
    budget = ApiBudget(tmp_path / 'ledger.json')
    index = budget.begin()
    with pytest.raises(BudgetBlocked, match='unresolved'):
        budget.begin()
    budget.fail(index, http_status=429)
    assert Decimal(budget.snapshot()['accounted_cost_usd']) == reservation()
    assert budget.snapshot()['requests'][0]['http_status'] == 429
    with pytest.raises(BudgetBlocked):
        budget.begin()
    with pytest.raises(FileExistsError):
        ApiBudget(budget.path)


@pytest.mark.parametrize('bad_usage', [None, {}, usage(cached=1001), usage(reasoning=501),
                                      usage(outgoing=MAX_OUTPUT_TOKENS + 1), usage(incoming=True)])
def test_missing_or_invalid_usage_fails_closed(tmp_path, bad_usage):
    budget = ApiBudget(tmp_path / 'ledger.json')
    index = budget.begin()
    with pytest.raises(BudgetBlocked):
        budget.settle(index, bad_usage, response_id='mock', returned_model=MODEL, service_tier='default')
    assert Decimal(budget.snapshot()['accounted_cost_usd']) == reservation()


class DummyClient:
    max_retries = 0

    def __init__(self, *, failure=None, status='completed', returned_model=MODEL):
        self.requests = []
        self.responses = SimpleNamespace(create=self.create)
        self.failure, self.status, self.returned_model = failure, status, returned_model

    def create(self, **request):
        self.requests.append(request)
        if self.failure:
            raise self.failure
        data = {'id': 'mock-response', 'model': self.returned_model, 'service_tier': 'default',
                'status': self.status, 'usage': usage(),
                'output': [{'type': 'function_call', 'call_id': 'mock-call', 'name': 'read_project',
                            'arguments': '{"path":"robot/controller.py"}'}]}
        return SimpleNamespace(id=data['id'], model_dump=lambda **kwargs: data, output=data['output'])


def adapter(tmp_path, client):
    budget = ApiBudget(tmp_path / 'ledger.json')
    trace = ExecutionTrace(tmp_path / 'trace', model_mode='explicitly_mocked_transport')
    model = BudgetedOpenAIAdapter(client, budget, tmp_path / 'api', trace)
    return model, budget, trace


def test_fixed_model_medium_reasoning_output_cap_and_exact_response_saved(tmp_path):
    client = DummyClient()
    model, budget, trace = adapter(tmp_path, client)
    turn = model.complete(({'role': 'user', 'content': 'dummy test'},), ())
    assert turn.tool_calls[0].name == 'read_project'
    request = client.requests[0]
    assert request['model'] == MODEL and request['reasoning'] == {'effort': 'medium'}
    assert request['max_output_tokens'] == 8192 and request['service_tier'] == 'default'
    assert request['store'] is True and request['parallel_tool_calls'] is False
    assert json.loads((tmp_path / 'api/request_000.json').read_text()) == request
    raw = json.loads((tmp_path / 'api/response_000.json').read_text())
    assert raw['output'] == list(turn.provider_items)
    assert raw['usage'] == budget.snapshot()['requests'][0]['usage']
    assert read_trace(trace.path)[-1]['event'] == 'api_usage_recorded'


def test_failed_request_not_retried_and_provider_key_echo_not_saved(tmp_path):
    secret = 'dummy-secret-that-must-not-be-logged'
    failure = RuntimeError('Incorrect key: ' + secret)
    client = DummyClient(failure=failure)
    model, budget, trace = adapter(tmp_path, client)
    for _ in range(2):
        with pytest.raises(ModelRequestError):
            model.complete((), ())
    assert len(client.requests) == 1
    assert Decimal(budget.snapshot()['accounted_cost_usd']) == reservation()
    assert secret not in json.dumps(budget.snapshot()) + trace.path.read_text()


def test_known_api_failure_code_preserved_without_provider_message(tmp_path):
    failure = RuntimeError('provider message containing dummy-sensitive-text')
    failure.code = 'insufficient_quota'
    failure.status_code = 429
    model, budget, trace = adapter(tmp_path, DummyClient(failure=failure))
    with pytest.raises(ModelRequestError):
        model.complete((), ())
    entry = budget.snapshot()['requests'][0]
    assert entry['http_status'] == 429 and 'insufficient_quota' in entry['reason']
    assert 'dummy-sensitive-text' not in json.dumps(budget.snapshot()) + trace.path.read_text()


@pytest.mark.parametrize('model_name', ['gpt-5.4', 'gpt-5.5', 'gpt-6-astra'])
def test_other_models_blocked_before_network(tmp_path, model_name):
    client = DummyClient()
    model, budget, trace = adapter(tmp_path, client)
    model.model = model_name
    with pytest.raises(ModelRequestError):
        model.complete((), ())
    assert client.requests == [] and budget.snapshot()['requests'] == []


@pytest.mark.parametrize('status,returned_model', [('incomplete', MODEL), ('completed', 'gpt-5.4')])
def test_incomplete_response_or_wrong_model_preserved_then_stopped(tmp_path, status, returned_model):
    client = DummyClient(status=status, returned_model=returned_model)
    model, budget, trace = adapter(tmp_path, client)
    with pytest.raises(ModelRequestError):
        model.complete((), ())
    assert (tmp_path / 'api/response_000.json').is_file()
    with pytest.raises(BudgetBlocked):
        budget.begin()


def test_client_retry_configuration_is_rejected(tmp_path):
    client = DummyClient()
    client.max_retries = 1
    with pytest.raises(ValueError, match='retries'):
        adapter(tmp_path, client)
