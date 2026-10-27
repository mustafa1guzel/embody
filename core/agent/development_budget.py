"""Persistent project accounting over immutable prior request ledgers.

Import leaf ledgers only: combined reports are views and must not be charged twice.
Unknown historical charges retain their recorded full reservations.
"""
from decimal import Decimal
import json
from pathlib import Path

from core.agent.api_budget import ApiBudget, BudgetBlocked, cost
from core.simulation import sha256, write_json

OVERALL_LIMIT = Decimal('30')
WARNING_THRESHOLD = Decimal('1.50')


def historical_accounting(paths):
    sessions, response_ids = [], set()
    for path in sorted(map(Path, paths)):
        data = json.loads(path.read_text())
        # Unique server response IDs prevent accidental leaf/aggregate duplication.
        ids = {r['response_id'] for r in data['requests'] if r.get('response_id')}
        if ids & response_ids:
            raise BudgetBlocked('Historical ledgers contain duplicate server responses')
        response_ids.update(ids)
        measured = sum((Decimal(r.get('actual_cost_usd', '0')) for r in data['requests']), Decimal(0))
        accounted = sum((Decimal(r.get('actual_cost_usd', r['reserved_usd'])) for r in data['requests']), Decimal(0))
        if (measured != Decimal(data['measured_cost_usd'])
                or accounted != Decimal(data['accounted_cost_usd'])):
            raise BudgetBlocked('Historical request accounting does not reconcile')
        sessions.append({'path': str(path), 'sha256': sha256(path), 'ledger': data})
    return {'sessions': sessions,
            'measured_cost_usd': str(sum((Decimal(s['ledger']['measured_cost_usd']) for s in sessions), Decimal(0))),
            'accounted_cost_usd': str(sum((Decimal(s['ledger']['accounted_cost_usd']) for s in sessions), Decimal(0)))}


class DevelopmentBudget(ApiBudget):
    """One authorized session, with an independently persisted cumulative view."""
    def __init__(self, path, *, cumulative_path, historical_paths, **kwargs):
        self.history = historical_accounting(historical_paths)
        self.cumulative_path = Path(cumulative_path)
        if self.cumulative_path.exists():
            raise FileExistsError('Refusing to replace a cumulative experiment ledger')
        self.warning_events = []
        super().__init__(path, **kwargs)
        self.save_cumulative()

    def save_cumulative(self):
        current = self.snapshot()
        totals = {key: current['totals'][key] + sum(s['ledger']['totals'][key]
                  for s in self.history['sessions']) for key in current['totals']}
        data = {'overall_limit_usd': str(OVERALL_LIMIT), 'experiment_limit_usd': str(self.limit),
                'warning_threshold_usd': str(WARNING_THRESHOLD), 'warning_events': self.warning_events,
                'historical': self.history, 'current_ledger_path': str(self.path), 'current': current,
                'measured_cost_usd': str(Decimal(self.history['measured_cost_usd']) + Decimal(current['measured_cost_usd'])),
                'accounted_cost_usd': str(Decimal(self.history['accounted_cost_usd']) + Decimal(current['accounted_cost_usd'])),
                'totals': totals, 'unknown_historical_charges_released': False}
        temporary = self.cumulative_path.with_suffix('.tmp')
        write_json(temporary, data)
        temporary.replace(self.cumulative_path)

    def begin(self, request=None):
        projected = Decimal(self.history['accounted_cost_usd']) + Decimal(self.snapshot()['accounted_cost_usd']) + cost(
            self.input_token_bound, 0, self.max_output_tokens, policy=self.policy)
        if projected > OVERALL_LIMIT:
            raise BudgetBlocked('Next reservation exceeds overall project budget')
        index = super().begin(request)
        # No HTTP dispatch occurs until both reservation ledgers are durable.
        current = self.snapshot()
        if Decimal(current['accounted_cost_usd']) >= WARNING_THRESHOLD and not self.warning_events:
            self.warning_events.append({'request_index': index, 'kind': 'conservative_experiment_exposure',
                                        'accounted_cost_usd': current['accounted_cost_usd']})
            print('API BUDGET WARNING: conservative experiment exposure reached $1.50', flush=True)
        self.save_cumulative()
        return index

    def settle(self, *args, **kwargs):
        super().settle(*args, **kwargs)
        self.save_cumulative()

    def fail(self, *args, **kwargs):
        super().fail(*args, **kwargs)
        self.save_cumulative()
