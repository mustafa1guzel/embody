"""One explicitly authorized GPT-5.4/low Day 4B.2 experiment. No controller template."""
import copy
import json
from pathlib import Path

from core.agent.api_budget import GPT54_POLICY
from core.agent.credentials import create_openai_client
from core.agent.development_budget import DevelopmentBudget
from core.agent.live_model import BudgetedOpenAIAdapter
from core.agent.orchestration import AgentOrchestrator
from core.agent.trace import ExecutionTrace, read_trace
from core.agent.vm_backend import AppleVMBackend, file_hash, runtime_command
from core.live_experiment import ExperimentTools
from core.simulation import ROOT, write_json

REQUEST = ('Investigate why my robot collides with the wall.\n'
           'Inspect the actual controller and physical context,\n'
           'run the experiments you need, identify the cause,\n'
           'and propose a controller repair that generalizes\n'
           'across different robot configurations.')
INSTRUCTIONS = '''This is one bounded physical-debugging session: at most 12 API requests, 30 tool calls, 2 patch proposals and $2.50 additional API spending. All six tools are available; choose your own investigation order and use only those needed. Read the actual controller and authoritative scenario context. Reuse evidence already obtained; avoid redundant source/context reads or duplicate baseline experiments. Tool outputs include measured results and artifact references, with full telemetry stored separately. Once the evidence supports a diagnosis, submit a concrete complete-source proposal using propose_patch rather than repeatedly analyzing the same observations. Read its actual structured source-policy metadata before writing code. Do not reveal or claim unavailable private reasoning; give a concise evidence-grounded diagnosis. A valid proposal automatically undergoes separate deterministic A/B/C verification of the actual candidate in a qualified VM; use that returned measured feedback. If the first proposal is invalid or unsafe, you may generate one evidence-driven revision. Stop after a verified repair or after two proposals. Do not manually change physics, safety criteria or the original controller. No model switch, reasoning-effort escalation or automatic API retry is allowed.'''
INPUT_ALLOWANCE = 131072
OUTPUT_ALLOWANCE = 25000


class StrongAdapter(BudgetedOpenAIAdapter):
    def _request(self, **request):
        request['instructions'] = request.get('instructions', '') + '\n\n' + INSTRUCTIONS
        return super()._request(**request)


class EvidenceTools(ExperimentTools):
    """Reuse measured context/baselines within this session, with integrity checks."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._contexts = {}
        self._baselines = {}

    def _context(self, scenario_id):
        self._check_pinned()
        if scenario_id not in self._contexts:
            self._contexts[scenario_id] = super()._context(scenario_id)
        return copy.deepcopy(self._contexts[scenario_id])

    def run_simulation(self, scenario_id, controller_variant):
        self._check_pinned()
        if controller_variant == 'faulty' and scenario_id in self._baselines:
            result = copy.deepcopy(self._baselines[scenario_id])
            record = self._runs[result['simulation_run_id']]
            if any(file_hash(record['directory']/name) != digest for name, digest in record['inventory'].items()):
                raise ValueError('Cached baseline artifact integrity mismatch')
            result['reused_existing_measurement'] = True
            self.trace.append('baseline_evidence_reused', {'simulation_run_id': result['simulation_run_id']})
            return result
        result = super().run_simulation(scenario_id, controller_variant)
        if controller_variant == 'faulty':
            self._baselines[scenario_id] = copy.deepcopy(result)
        return result


def run(output):
    output = Path(output)
    assert json.loads((output/'regression/exit_code.json').read_text())['exit_code'] == 0
    session = output/'session'
    prior = sorted((ROOT/'artifacts').rglob('api_cost_ledger.json'))
    session.mkdir(exist_ok=False)
    backend = AppleVMBackend()
    proof = backend.preflight()
    write_json(session/'containment_snapshot.json', proof)
    trace = ExecutionTrace(session/'execution_trace.jsonl', model_mode='openai_responses')
    budget = DevelopmentBudget(session/'api_cost_ledger.json', cumulative_path=output/'cumulative_api_ledger.json',
        historical_paths=prior, policy=GPT54_POLICY, limit='2.50', input_token_bound=INPUT_ALLOWANCE,
        max_output_tokens=OUTPUT_ALLOWANCE, max_requests=12)
    write_json(session/'experiment_policy.json', {'model':GPT54_POLICY.model, 'reasoning_effort':'low',
        'max_output_tokens':OUTPUT_ALLOWANCE, 'input_allowance':INPUT_ALLOWANCE, 'max_api_requests':12,
        'max_tool_calls':30, 'max_patch_attempts':2, 'experiment_cap_usd':'2.50',
        'project_cap_usd':'30', 'warning_usd':'1.50', 'task':REQUEST, 'instructions':INSTRUCTIONS,
        'automatic_retries':0, 'model_fallback':False, 'reasoning_escalation':False,
        'generation_probe':'None; first genuine session request verifies model access'})
    tools = EvidenceTools(session, trace, backend=backend)
    write_json(session/'tool_contracts.json', tools.schemas)
    model = StrongAdapter(create_openai_client().with_options(timeout=180.0,max_retries=0),
                          budget, session/'api', trace, parallel_tool_calls=True)
    try:
        report = AgentOrchestrator(model, tools, trace, max_turns=12, max_tool_calls=30).run(REQUEST)
    finally:
        model.close()
    report.update(patch_attempts=tools.patch_attempts, api_budget=budget.snapshot(),
        no_candidate_vms_remain=json.loads(runtime_command(backend.config,['list','--all','--format','json'])) == [])
    report['session_status'] = ('PASS' if report['orchestration_status']=='COMPLETED' and report['repair_verified']
                                and report['no_candidate_vms_remain'] else 'FAIL')
    write_json(session/'session_result.json',report)
    print(json.dumps({'session_status':report['session_status'],'repair_verified':report['repair_verified'],
        'requests':len(report['api_budget']['requests']), 'tool_calls':report['tool_calls'],
        'patch_attempts':tools.patch_attempts, 'new_measured_cost_usd':report['api_budget']['measured_cost_usd'],
        'cumulative_accounted_cost_usd':json.loads((output/'cumulative_api_ledger.json').read_text())['accounted_cost_usd']},indent=2),flush=True)
    return report
