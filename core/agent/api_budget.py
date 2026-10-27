"""Single-experiment, persisted USD reservations and measured token accounting."""
from contextlib import contextmanager
from datetime import datetime, timezone
from dataclasses import dataclass
from decimal import Decimal
import fcntl
import json
from pathlib import Path
import re

MODEL = 'gpt-5.4-mini'
REASONING_EFFORT = 'medium'
LIMIT = Decimal('0.50')
INPUT_RATE = Decimal('0.75')
CACHED_RATE = Decimal('0.075')
OUTPUT_RATE = Decimal('4.50')
CONTEXT_LIMIT = 400_000
MAX_OUTPUT_TOKENS = 8192
PRICING_SOURCE = 'https://developers.openai.com/api/docs/models/gpt-5.4-mini'


@dataclass(frozen=True)
class ModelBudgetPolicy:
    model: str
    reasoning_effort: str
    input_rate: Decimal
    cached_rate: Decimal
    output_rate: Decimal
    maximum_limit: Decimal
    context_limit: int
    output_limit: int
    pricing_source: str


# Selection is explicit. Legacy defaults remain unchanged; there is no fallback.
MINI_POLICY = ModelBudgetPolicy(MODEL, REASONING_EFFORT, INPUT_RATE, CACHED_RATE, OUTPUT_RATE,
                               LIMIT, CONTEXT_LIMIT, MAX_OUTPUT_TOKENS, PRICING_SOURCE)
GPT54_POLICY = ModelBudgetPolicy('gpt-5.4', 'low', Decimal('2.50'), Decimal('0.25'), Decimal('15'),
                                Decimal('2.50'), 272_000, 25_000,
                                'https://developers.openai.com/api/docs/models/gpt-5.4')


class BudgetBlocked(RuntimeError):
    pass


def cost(input_tokens, cached_tokens, output_tokens, *, policy=MINI_POLICY):
    # output_tokens already includes reasoning tokens. Never add them twice.
    return ((input_tokens - cached_tokens) * policy.input_rate + cached_tokens * policy.cached_rate
            + output_tokens * policy.output_rate) / Decimal(1_000_000)


def reservation():
    # Reserve the entire published context window as uncached input, plus the
    # output cap. This deliberately overestimates even hidden/framing tokens;
    # it requires neither a tokenizer download nor a speculative token estimate.
    return cost(CONTEXT_LIMIT, 0, MAX_OUTPUT_TOKENS)


class ApiBudget:
    def __init__(self, path, *, limit=LIMIT, input_token_bound=CONTEXT_LIMIT,
                 max_output_tokens=MAX_OUTPUT_TOKENS, max_requests=None, policy=MINI_POLICY):
        if policy not in (MINI_POLICY, GPT54_POLICY):
            raise ValueError('Unapproved model budget policy')
        self.policy = policy
        self.limit = Decimal(limit)
        self.input_token_bound = input_token_bound
        self.max_output_tokens = max_output_tokens
        self.max_requests = max_requests
        if (not Decimal('0') < self.limit <= policy.maximum_limit or type(input_token_bound) is not int
                or not 1 <= input_token_bound <= policy.context_limit or type(max_output_tokens) is not int
                or not 16 <= max_output_tokens <= policy.output_limit
                or (max_requests is not None and (type(max_requests) is not int or max_requests < 1))):
            raise ValueError('Invalid API budget limits')
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open('x') as stream:
            json.dump({'model': policy.model, 'reasoning_effort': policy.reasoning_effort,
                       'limit_usd': str(self.limit), 'pricing_source': policy.pricing_source,
                       'rates_usd_per_million': {'input': str(policy.input_rate), 'cached_input': str(policy.cached_rate),
                                                'output_including_reasoning': str(policy.output_rate)},
                       'input_reservation_tokens': input_token_bound, 'max_output_tokens': max_output_tokens,
                       'max_requests': max_requests,
                       'reservation_method': ('Entire model context as uncached input plus capped output'
                                              if input_token_bound == policy.context_limit else
                                              'Bounded text payload bytes + 4096 framing allowance + prior reported chain tokens'),
                       'requests': [], 'accounted_cost_usd': '0', 'measured_cost_usd': '0',
                       'totals': {'input_tokens': 0, 'cached_input_tokens': 0,
                                  'output_tokens': 0, 'reasoning_tokens': 0}}, stream, indent=2)

    @contextmanager
    def _update(self):
        with self.path.with_suffix('.lock').open('a+b') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            data = json.loads(self.path.read_text())
            yield data
            temporary = self.path.with_suffix('.tmp')
            temporary.write_text(json.dumps(data, indent=2) + '\n')
            temporary.replace(self.path)

    def begin(self, request=None):
        with self._update() as data:
            if any(r['state'] != 'SETTLED' for r in data['requests']):
                raise BudgetBlocked('A failed or unresolved API request prevents further requests')
            if self.max_requests is not None and len(data['requests']) >= self.max_requests:
                raise BudgetBlocked('Maximum API request count reached')
            if self.input_token_bound < self.policy.context_limit:
                if request is None:
                    raise BudgetBlocked('Bounded budget requires the request payload')
                if (not isinstance(request.get('input'), list)
                        or any(i.get('type') not in (None, 'function_call_output')
                               or not isinstance(i.get('output') if i.get('type') == 'function_call_output'
                                                 else i.get('content'), str) for i in request['input'])
                        or any(t.get('type') != 'function' for t in request.get('tools', []))):
                    raise BudgetBlocked('Small-budget probe accepts text and local function outputs only')
                # Narrow text-only probe: byte-level token upper estimate plus
                # generous template framing and the reported prior chain size.
                previous = data['requests'][-1]['usage']['total_tokens'] if data['requests'] else 0
                bound = len(json.dumps(request, ensure_ascii=True, allow_nan=False).encode()) + 4096 + previous
                if bound > self.input_token_bound:
                    raise BudgetBlocked('Text request exceeds the input reservation envelope')
            reserved = cost(self.input_token_bound, 0, self.max_output_tokens, policy=self.policy)
            projected = Decimal(data['accounted_cost_usd']) + reserved
            if projected >= self.limit:
                raise BudgetBlocked('Next request maximum would exceed the experiment budget')
            index = len(data['requests'])
            data['requests'].append({'index': index, 'state': 'PENDING', 'model': self.policy.model,
                                     'reasoning_effort': self.policy.reasoning_effort,
                                     'started_utc': datetime.now(timezone.utc).isoformat(),
                                     'reserved_usd': str(reserved),
                                     'projected_cumulative_max_usd': str(projected)})
            data['accounted_cost_usd'] = str(projected)
        return index

    def fail(self, index, *, http_status=None, reason='API request failed; provider details suppressed',
             unbilled=False):
        with self._update() as data:
            entry = data['requests'][index]
            if unbilled and entry['state'] == 'PENDING':
                data['accounted_cost_usd'] = str(Decimal(data['accounted_cost_usd']) - Decimal(entry['reserved_usd']))
                entry['actual_cost_usd'] = '0'
            entry.update(state='REJECTED_UNBILLED' if unbilled else
                         ('FAILED_WITH_USAGE' if entry['state'] == 'SETTLED' else 'FAILED_USAGE_UNKNOWN'),
                         http_status=http_status, reason=reason)
            # Retain the whole reservation. A timeout/crash may still be billed.

    def settle(self, index, usage, *, response_id, returned_model, service_tier):
        def integer(value):
            if type(value) is not int or value < 0:
                raise BudgetBlocked('API usage is missing or invalid')
            return value
        try:
            incoming = integer(usage['input_tokens'])
            cached = integer(usage['input_tokens_details']['cached_tokens'])
            outgoing = integer(usage['output_tokens'])
            reasoning = integer(usage['output_tokens_details']['reasoning_tokens'])
            total = integer(usage['total_tokens'])
            if (cached > incoming or reasoning > outgoing or total != incoming + outgoing
                    or incoming > self.input_token_bound or outgoing > self.max_output_tokens
                    or not isinstance(returned_model, str)
                    or not (returned_model == self.policy.model or returned_model.startswith(self.policy.model + '-'))
                    or (self.policy == GPT54_POLICY and returned_model != self.policy.model
                        and not re.fullmatch(r'gpt-5\.4-\d{4}-\d{2}-\d{2}', returned_model))
                    or service_tier != 'default'):
                raise BudgetBlocked('API usage or returned model/tier differs from the approved bounds')
        except (KeyError, TypeError):
            raise BudgetBlocked('API usage is missing or invalid') from None
        actual = cost(incoming, cached, outgoing, policy=self.policy)
        with self._update() as data:
            entry = data['requests'][index]
            if entry['state'] != 'PENDING' or actual > Decimal(entry['reserved_usd']):
                raise BudgetBlocked('Invalid API budget settlement')
            entry.update(state='SETTLED', actual_cost_usd=str(actual), usage=usage,
                         response_id=response_id, returned_model=returned_model, service_tier=service_tier)
            data['accounted_cost_usd'] = str(Decimal(data['accounted_cost_usd'])
                                                - Decimal(entry['reserved_usd']) + actual)
            data['measured_cost_usd'] = str(Decimal(data['measured_cost_usd']) + actual)
            for name, value in zip(data['totals'], (incoming, cached, outgoing, reasoning)):
                data['totals'][name] += value

    def snapshot(self):
        return json.loads(self.path.read_text())
