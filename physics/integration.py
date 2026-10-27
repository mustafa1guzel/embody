"""Additive deterministic context/diagnostics adapter; schemas and permissions unchanged."""
import copy
from .contracts import digest
from .extraction import extract_contract
from .guard import assess_task


class PhysicsToolsAdapter:
    def __init__(self, tools):
        self.tools = tools

    def __getattr__(self, name):
        return getattr(self.tools, name)

    def dispatch(self, name, arguments):
        original = self.tools.dispatch(name, arguments)
        if not original.get('ok') or name not in ('get_robot_context', 'get_world_context', 'inspect_failure'):
            return original
        result = copy.deepcopy(original)
        value = result['result']
        try:
            if name == 'inspect_failure':
                evidence = value['evidence']
                context = evidence['physical_context']
                # Match authoritative context identity, not an invented scenario label.
                choices = [extract_contract(s, evidence['controller']['source_sha256']) for s in ('A', 'B', 'C')]
                c = next(c for c in choices if c.context_sha256 == digest(context))
                model_hash = evidence['effective_mjcf_sha256']
            else:
                c = extract_contract(arguments['scenario_id'])
                model_hash = value['effective_mjcf_sha256']
            if model_hash != c.model_sha256:
                raise ValueError('Tool/model identity mismatch')
            supplement = {'task_assessment': assess_task(c), 'contract_sha256': c.identity,
                          'authority': 'analytical model only; no VM or apply authorization'}
            if name == 'inspect_failure' and evidence.get('braking_initiation'):
                onset = evidence['braking_initiation']
                supplement['measured_onset_assessment'] = assess_task(c, velocity_mps=onset['velocity'],
                    clearance_m=onset['wall_clearance'], remaining_time_s=c.deadline_s-onset['time'],
                    contact_present=onset['wall_collision'])
            value['physics_analysis'] = supplement
        except (ValueError, KeyError, TypeError, StopIteration, OSError) as exc:
            value['physics_analysis'] = {'status': 'UNKNOWN', 'explanation': 'Analytical supplement unavailable: '+str(exc)[:200]}
        self.tools.trace.append('physics_analysis', {'tool': name, 'analysis': value['physics_analysis']})
        return result
