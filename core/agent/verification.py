"""Deterministic verification, kept separate from the six model-facing tools."""
from __future__ import annotations
from pathlib import Path
from uuid import uuid4

from core.day2 import diagnose_and_save
from core.simulation import run_simulation, sha256, write_json
from robot.controller import faulty_braking_controller


class CandidateVerifier:
    def __init__(self, store, scenarios, output: Path, trace, *, backend=None, family=None):
        self.store, self.scenarios, self.output, self.trace = store, scenarios, Path(output), trace
        self.backend = backend
        self.family = family
        self.runs = {}

    def verify(self, candidate_id):
        candidate = self.store.get(candidate_id)
        if self.backend is not None:
            from core.agent.vm_backend import IsolationBlocked
            from core.agent.candidate_execution import execute_candidate
            executor = self.family.executor if self.family is not None else execute_candidate
            try:
                self.backend.preflight()
                if self.family is not None:
                    from core.agent.vm_backend import AppleVMBackend
                    from core.robots.qualification import require_qualification
                    if type(self.backend) is not AppleVMBackend:
                        raise IsolationBlocked('Only qualified AppleVMBackend supports arm execution')
                    require_qualification(self.backend,self.family)
            except IsolationBlocked as exc:
                reason = str(exc)
            else:
                scenarios = {}
                try:
                    for name in self.scenarios:
                        measured, records = executor(candidate, self.scenarios, self.backend,
                                                               self.output.parent / 'simulations', names=[name])
                        scenarios.update(measured)
                        self.runs.update(records)
                    verified = all(r['independent_verification'] == 'PASS' or
                                   (r.get('task_rejection_verified') is True and r.get('analytical_guard',{}).get('status')=='PROVEN_INFEASIBLE')
                                   for r in scenarios.values())
                    dynamic = [r for r in scenarios.values() if r.get('simulation_execution') != 'NOT_RUN']
                    result = {'candidate_id': candidate_id, 'source_sha256': candidate['proposed_sha256'],
                              'verification_execution': 'PASS' if verified else 'FAIL',
                              'physical_safety_status': ('PASS' if all(r['physical_safety_status']=='PASS' for r in dynamic) else 'FAIL') if verified and dynamic else 'NOT_EVALUATED',
                              'candidate_code_executed': True, 'scenario_results': scenarios}
                except Exception as exc:
                    # No safety claim is made from partial or failed execution.
                    result = {'candidate_id': candidate_id, 'source_sha256': candidate['proposed_sha256'],
                              'verification_execution': 'FAIL', 'physical_safety_status': 'NOT_EVALUATED',
                              'candidate_code_executed': True if scenarios else None, 'execution_attempted': True,
                              'reason': type(exc).__name__ + ': ' + str(exc)[:512],
                              'scenario_results': {name: scenarios.get(name, {'simulation_execution':'NOT_VERIFIED','physical_safety_status':'NOT_EVALUATED'}) for name in self.scenarios}}
                write_json(self.output / f'{candidate_id}.json', result)
                self.trace.append('candidate_verification', result)
                return result
        else:
            reason = 'No audited candidate isolation backend is configured. Syntax validation and a temporary directory are not a security sandbox.'
        # There is deliberately no exec/import/subprocess path for candidate code.
        # An audited OS isolation backend is not configured for this prototype.
        result = {'candidate_id': candidate_id, 'source_sha256': candidate['proposed_sha256'],
                  'verification_execution': 'BLOCKED', 'physical_safety_status': 'NOT_EVALUATED',
                  'reason': reason,
                  'candidate_code_executed': False,
                  'scenario_results': {name: {'simulation_execution': 'NOT_RUN', 'physical_safety_status': 'NOT_EVALUATED'}
                                       for name in self.scenarios}}
        write_json(self.output / f'{candidate_id}.json', result)
        self.trace.append('candidate_verification', result)
        return result

    def verify_trusted_existing(self, tools):
        """Real A/B/C reference executions; never presented as candidate evidence."""
        results = {name: tools.run_simulation(name, 'faulty') for name in self.scenarios}
        result = {'kind': 'trusted_existing_controller_reference',
                  'verification_execution': 'PASS' if all(r['independent_verification'] == 'PASS' for r in results.values()) else 'FAIL',
                  'candidate_code_executed': False, 'scenarios': results}
        write_json(self.output / 'trusted_existing_reference.json', result)
        self.trace.append('trusted_reference_verification', result)
        return result


def execute_trusted(scenario_id, controller_variant, scenarios, output: Path, expected_source_hash: str, *, save_render=False):
    if controller_variant != 'faulty':
        raise ValueError('Only the pinned existing faulty controller is trusted for in-process execution')
    if sha256(Path(__file__).resolve().parents[2] / 'robot/controller.py') != expected_source_hash:
        raise ValueError('Trusted controller source changed; restart the session')
    body, world = scenarios[scenario_id]
    run_id = 'simulation_' + uuid4().hex
    directory = Path(output) / run_id
    run = run_simulation(bodybase=body, worldbase=world, controller=faulty_braking_controller,
                         save_render=save_render, artifacts_dir=directory)
    diagnostics = diagnose_and_save(run)
    # Tool summaries intentionally expose observations, not a scripted diagnosis.
    onset, contact = diagnostics['braking_initiation'], diagnostics['first_wall_contact']
    summary = {'simulation_run_id': run_id, 'scenario_id': scenario_id, 'controller_variant': controller_variant,
               'controller_sha256': run['metadata']['controller']['source_sha256'],
               'simulation_execution': diagnostics['physics_simulation'],
               'physical_safety_status': diagnostics['safety_acceptance']['status'],
               'braking_onset': onset, 'first_wall_contact': contact,
               'contact_velocity_ms': contact['velocity'] if contact else None,
               'minimum_clearance_m': diagnostics['minimum_observed_clearance_m'],
               'final_speed_ms': abs(diagnostics['final_state']['velocity']),
               'applied_force_n': {'minimum': min(s['generalized_actuator_force'] for s in run['telemetry']),
                                   'maximum': max(s['generalized_actuator_force'] for s in run['telemetry'])},
               'independent_verification': diagnostics['independent_safety_verification']['verification_execution'],
               'safety_acceptance': diagnostics['safety_acceptance'],
               'artifact_references': {name: str(Path('simulations') / run_id / name)
                                       for name in ('telemetry.json','diagnostics.json','independent_safety_trace.json','effective_model.xml','manifest.json')}}
    write_json(directory / 'tool_summary.json', summary)
    inventory = {p.name: sha256(p) for p in directory.iterdir() if p.is_file()}
    return summary, {'directory': directory, 'inventory': inventory}
