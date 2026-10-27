"""One explicitly authorized, budget-capped real EMBODY debugging session."""
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path

from core.agent.api_budget import ApiBudget, MODEL, REASONING_EFFORT, cost
from core.agent.credentials import create_openai_client
from core.agent.live_model import BudgetedOpenAIAdapter
from core.agent.orchestration import AgentOrchestrator
from core.agent.tools import AgentTools, CONTRACTS
from core.agent.trace import ExecutionTrace, read_trace
from core.agent.vm_backend import AppleVMBackend, runtime_command, file_hash
from core.day2 import file_inventory
from core.simulation import ROOT, write_json

REQUEST = 'Investigate why my robot collides with the wall. Read the real controller, inspect BODYBASE and WORLDBASE, run physical simulations, determine the cause, and generate a source-code repair that works across different robot and environment configurations.'
INPUT_ALLOWANCE = 32768
OUTPUT_ALLOWANCE = 3072
MAX_REQUESTS = 12
MAX_TOOL_CALLS = 20
MAX_PATCH_ATTEMPTS = 2
SESSION_INSTRUCTIONS = '''Session limits: 12 model requests, 20 tool calls, two patch attempts, $0.50 cumulative API cost. Choose your own tools and investigation order. Generate your own diagnosis and source modification from the actual evidence. Keep responses concise. A valid propose_patch result automatically includes deterministic independent verification of that actual candidate across A/B/C; redundant candidate simulation calls are unnecessary. If the first proposal fails, you may submit one evidence-driven revision. Stop revising once a candidate is physically verified. Never change the original controller or physics/safety configuration. Tool names, scenario IDs and controller variants must be obtained from the actual tool interface; do not invent run IDs. No fallback model or API retry is permitted.'''


class ExperimentAdapter(BudgetedOpenAIAdapter):
    def _request(self, **request):
        request['instructions'] = request.get('instructions', '') + '\n\n' + SESSION_INSTRUCTIONS
        return super()._request(**request)


class ExperimentTools(AgentTools):
    """Same six interfaces, with an experiment-only proposal attempt ceiling."""
    patch_attempts = 0
    last_candidate_id = None

    def dispatch(self, name, arguments):
        if name == 'propose_patch':
            if self.patch_attempts >= MAX_PATCH_ATTEMPTS:
                self.trace.append('patch_attempt_blocked', {'reason': 'Two patch attempts exhausted'})
                raise RuntimeError('Two patch attempts exhausted; no third proposal allowed')
            if self.last_candidate_id:
                previous = self.verifier.output / f'{self.last_candidate_id}.json'
                if previous.exists():
                    result = json.loads(previous.read_text())
                    if result.get('verification_execution') == 'BLOCKED':
                        raise RuntimeError('Candidate isolation is blocked; stop the experiment')
                    if result.get('physical_safety_status') == 'PASS':
                        raise RuntimeError('A verified repair already exists; no revision allowed')
            self.patch_attempts += 1
        result = super().dispatch(name, arguments)
        if name == 'propose_patch' and result['ok']:
            self.last_candidate_id = result['result'].get('candidate_id')
        return result


def run_session(output):
    output = Path(output)
    history = file_inventory(ROOT / 'artifacts')
    output.mkdir(parents=True, exist_ok=False)
    trace = ExecutionTrace(output / 'execution_trace.jsonl', model_mode='openai_responses')
    budget = ApiBudget(output / 'api_cost_ledger.json', input_token_bound=INPUT_ALLOWANCE,
                       max_output_tokens=OUTPUT_ALLOWANCE, max_requests=MAX_REQUESTS)
    policy = {'model':MODEL, 'reasoning_effort':REASONING_EFFORT,
              'input_allowance_tokens':INPUT_ALLOWANCE,'output_allowance_tokens':OUTPUT_ALLOWANCE,
              'max_model_requests':MAX_REQUESTS,'max_tool_calls':MAX_TOOL_CALLS,
              'max_patch_attempts':MAX_PATCH_ATTEMPTS,
              'maximum_per_request_reservation_usd':str(cost(INPUT_ALLOWANCE,0,OUTPUT_ALLOWANCE)),
              'sum_of_12_maximum_reservations_usd':str(cost(INPUT_ALLOWANCE,0,OUTPUT_ALLOWANCE)*MAX_REQUESTS),
              'reserved_upfront':False,'task':REQUEST,'session_instructions':SESSION_INSTRUCTIONS}
    if cost(INPUT_ALLOWANCE,0,OUTPUT_ALLOWANCE)*MAX_REQUESTS >= Decimal('.50'):
        raise ValueError('Combined planned reservations do not fit the budget')
    write_json(output / 'experiment_policy.json', policy)
    protected = {str(p.relative_to(ROOT)): file_hash(p) for directory in ('robot', 'configs', 'tests')
                 for p in (ROOT / directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    backend = AppleVMBackend()
    model = None
    report = {'session_status': 'BLOCKED', 'model': MODEL, 'reasoning_effort': REASONING_EFFORT,
              'budget_limit_usd': '0.50', 'fallback_enabled': False, 'automatic_retries': 0,
              'repair_verified': False, 'candidate_verifications': []}
    try:
        proof = backend.preflight()
        write_json(output / 'containment_snapshot.json', proof)
        client = create_openai_client().with_options(timeout=90.0, max_retries=0)
        model = ExperimentAdapter(client, budget, output / 'api', trace, parallel_tool_calls=True)
        tools = ExperimentTools(output, trace, backend=backend)
        write_json(output / 'tool_contracts.json', list(tools.schemas))
        report.update(AgentOrchestrator(model, tools, trace, max_turns=MAX_REQUESTS, max_tool_calls=MAX_TOOL_CALLS).run(REQUEST))
        report['patch_attempts'] = tools.patch_attempts
        rows = read_trace(trace.path)
        successful = {r['payload']['name'] for r in rows if r['event'] == 'tool_completed'
                      and r['payload']['output']['ok']}
        report['six_tools_used_successfully'] = successful == set(CONTRACTS)
        report['successful_tools'] = sorted(successful)
        blocked = any(v.get('verification_execution') == 'BLOCKED' for v in report['candidate_verifications'])
        report['session_status'] = ('BLOCKED' if blocked else
                                   ('PASS' if report['orchestration_status'] == 'COMPLETED'
                                    and report['six_tools_used_successfully'] and report['repair_verified'] else 'FAIL'))
    except Exception as exc:
        # No raw SDK exception or credential object is included in the report.
        report['failure_type'] = type(exc).__name__
        report['reason'] = 'Preflight or session failed; see the bounded trace and budget ledger'
    finally:
        if model is not None:
            model.close()
        report['api_budget'] = budget.snapshot()
        report['original_sources_tests_preserved'] = all(file_hash(ROOT / p) == h for p, h in protected.items())
        report['all_historical_artifacts_preserved'] = all((ROOT/'artifacts'/p).is_file() and file_hash(ROOT/'artifacts'/p)==h for p,h in history.items())
        try:
            report['no_candidate_vms_remain'] = json.loads(runtime_command(backend.config, ['list', '--all', '--format', 'json'])) == []
        except Exception:
            report['no_candidate_vms_remain'] = False
        if (not report['original_sources_tests_preserved'] or not report['all_historical_artifacts_preserved']
                or (not report['no_candidate_vms_remain'] and report['session_status'] != 'BLOCKED')):
            report['session_status'] = 'FAIL'
        write_json(output / 'session_result.json', report)
    return report


def main():
    output = ROOT / 'artifacts/live_experiment' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    report = run_session(output)
    print(json.dumps({'session_status': report['session_status'], 'model': MODEL,
                      'reasoning_effort': REASONING_EFFORT,
                      'repair_verified': report['repair_verified'],
                      'api_requests': len(report['api_budget']['requests']),
                      'measured_cost_usd': report['api_budget']['measured_cost_usd'],
                      'accounted_cost_usd': report['api_budget']['accounted_cost_usd'],
                      'artifacts': str(output)}, indent=2), flush=True)
    return 0 if report['session_status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
