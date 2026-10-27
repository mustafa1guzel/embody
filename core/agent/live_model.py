"""Explicit model budget policies and stored Responses; no fallback or retry path."""
import hashlib
import json
from pathlib import Path

from core.agent.api_budget import MODEL, REASONING_EFFORT, MAX_OUTPUT_TOKENS, BudgetBlocked
from core.agent.models import OpenAIResponsesAdapter
from core.agent.api_diagnostics import sanitized_error


class BudgetedOpenAIAdapter(OpenAIResponsesAdapter):
    def __init__(self, client, budget, output, trace, *, parallel_tool_calls=False):
        if client.max_retries != 0:
            raise ValueError('Live experiment requires automatic retries disabled')
        super().__init__(client, budget.policy.model, continuation='server')
        self.budget, self.output, self.trace = budget, Path(output), trace
        self.parallel_tool_calls = parallel_tool_calls
        self.output.mkdir(parents=True, exist_ok=True)

    def _request(self, **request):
        policy = self.budget.policy
        if request['model'] != policy.model or self.model != policy.model:
            raise BudgetBlocked('Only the explicitly approved primary model is enabled')
        request.update(reasoning={'effort': policy.reasoning_effort}, max_output_tokens=self.budget.max_output_tokens,
                       service_tier='default', store=True, parallel_tool_calls=self.parallel_tool_calls)
        index = self.budget.begin(request)
        # Persist exactly the request payload before dispatch; never headers/client.
        path = self.output / f'request_{index:03d}.json'
        with path.open('x') as stream:
            json.dump(request, stream, indent=2, allow_nan=False)
        self.trace.append('api_request_reserved', {'index': index, 'model': policy.model,
                          'reasoning_effort': policy.reasoning_effort,
                          'request_path': str(path),
                          'request_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                          'accounted_cost_usd': self.budget.snapshot()['accounted_cost_usd']})
        try:
            response = self.client.responses.create(**request)
        except Exception as exc:
            diagnostic = sanitized_error(exc, request, api_key=getattr(self.client, 'api_key', None))
            with (self.output / f'error_{index:03d}.json').open('x') as stream:
                json.dump(diagnostic, stream, indent=2)
            status, code = diagnostic['http_status'], diagnostic['error_code']
            # Explicit validation/auth/model rejections did not reach generation.
            # Timeouts, 429s and server errors retain their full reservation.
            unbilled = status in (400, 401, 403, 404, 422)
            reason = 'API request failed; provider details suppressed'
            if code is not None:
                reason = 'API request failed: ' + code
            self.budget.fail(index, http_status=status, reason=reason, unbilled=unbilled)
            self.trace.append('api_request_failed', {'index': index, 'http_status': status,
                                                     'error_code': code,
                                                     'diagnostic': diagnostic,
                                                     'usage': 'REJECTED_UNBILLED' if unbilled else 'UNKNOWN; full reservation retained'})
            raise BudgetBlocked('Live request failed; no retry or fallback is permitted') from None
        raw = response.model_dump(mode='json')
        with (self.output / f'response_{index:03d}.json').open('x') as stream:
            json.dump(raw, stream, indent=2, allow_nan=False)
        try:
            self.budget.settle(index, raw.get('usage'), response_id=raw.get('id'),
                               returned_model=raw.get('model'), service_tier=raw.get('service_tier'))
        except BudgetBlocked:
            self.budget.fail(index, reason='Response usage/model/tier validation failed')
            raise
        self.trace.append('api_usage_recorded', {'index': index, 'usage': raw['usage'],
                          'cumulative_cost_usd': self.budget.snapshot()['measured_cost_usd']})
        if raw.get('status') != 'completed':
            # Preserve incomplete output and measured usage, then stop the session.
            self.budget.fail(index, reason='Model response was not completed; no retry permitted')
            raise BudgetBlocked('Model response was incomplete or failed; evidence preserved')
        return response
