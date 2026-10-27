"""One authorized two-turn API probe. No patch tool or candidate execution."""
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path

from core.agent.api_budget import ApiBudget, MODEL
from core.agent.credentials import create_openai_client
from core.agent.live_model import BudgetedOpenAIAdapter
from core.agent.tools import AgentTools
from core.agent.trace import ExecutionTrace

ROOT = Path(__file__).resolve().parents[1]


class ProbeAdapter(BudgetedOpenAIAdapter):
    def _request(self, **request):
        # This is a protocol probe, not an autonomous debugging experiment.
        request['tool_choice'] = ({'type': 'function', 'name': 'get_robot_context'}
                                  if self._previous_response_id is None else 'none')
        return super()._request(**request)


def run_probe(output, *, client=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    mode = 'injected_test_client' if client is not None else 'openai_responses_continuation_probe'
    trace = ExecutionTrace(output / 'execution_trace.jsonl', model_mode=mode)
    budget = ApiBudget(output / 'api_cost_ledger.json', limit=Decimal('0.05'),
                       input_token_bound=16384, max_output_tokens=2048, max_requests=2)
    model = None
    result = {'status': 'FAIL', 'model': MODEL, 'reasoning_effort': 'medium',
              'transport_mode': mode,
              'full_debugging_experiment': 'NOT_RUN', 'candidate_patch_generated': False,
              'candidate_execution': 'NOT_RUN', 'tool_selection': 'forced protocol probe',
              'continuation_strategy': 'previous_response_id; stored responses; instructions resent',
              'automatic_retries': 0, 'fallback_enabled': False}
    try:
        client = client or create_openai_client().with_options(timeout=90.0, max_retries=0)
        model = ProbeAdapter(client, budget, output / 'api', trace)
        tools = AgentTools(output / 'tools', trace)
        schemas = tuple(s for s in tools.schemas if s['name'] == 'get_robot_context')
        messages = [{'role': 'system', 'content': 'This is a two-turn tool protocol test. Read context only; do not propose or modify code.'},
                    {'role': 'user', 'content': 'Call get_robot_context for scenario A. After its result, reply only: Context received.'}]
        turn = model.complete(tuple(messages), schemas)
        trace.append('model_completed', asdict(turn))
        if (len(turn.tool_calls) != 1 or turn.tool_calls[0].name != 'get_robot_context'
                or turn.tool_calls[0].arguments != {'scenario_id': 'A'}):
            raise ValueError('Expected exactly the requested context call; no retry permitted')
        call = turn.tool_calls[0]
        measured = tools.dispatch(call.name, call.arguments)
        if not measured['ok']:
            raise ValueError('Real context tool failed')
        messages.extend([{'role': 'assistant', 'content': turn.text, 'provider_items': list(turn.provider_items),
                          'tool_calls': [asdict(call)]},
                         {'role': 'tool', 'tool_call_id': call.call_id, 'name': call.name,
                          'content': json.dumps(measured, allow_nan=False)}])
        final = model.complete(tuple(messages), schemas)
        trace.append('model_completed', asdict(final))
        if final.tool_calls or not final.text.strip():
            raise ValueError('Expected a final text acknowledgement; no third request permitted')
        result.update(status='PASS', final_model_text=final.text, exact_call_id=call.call_id,
                      measured_carriage_mass_kg=measured['result']['effective_mujoco']['carriage_mass_kg'])
    except Exception as exc:
        result['failure_type'] = type(exc).__name__
        result['diagnostic_artifacts'] = [str(p.relative_to(output)) for p in (output / 'api').glob('error_*.json')]
    finally:
        if model is not None:
            model.close()
        result['api_budget'] = budget.snapshot()
        trace.append('probe_finished', result)
        with (output / 'probe_result.json').open('x') as stream:
            json.dump(result, stream, indent=2)
    return result


def main():
    output = ROOT / 'artifacts/day4b2_continuation' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    result = run_probe(output)
    print(json.dumps({'status': result['status'], 'requests': len(result['api_budget']['requests']),
                      'measured_cost_usd': result['api_budget']['measured_cost_usd'],
                      'accounted_cost_usd': result['api_budget']['accounted_cost_usd'],
                      'artifacts': str(output)}, indent=2), flush=True)
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
