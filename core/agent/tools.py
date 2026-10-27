"""Six real, bounded application tools. No model-selected filesystem or Python execution."""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path
from types import MappingProxyType

import mujoco

from core.context_validation import json_values
from core.day3 import load_scenarios, measure_force_probes
from core.simulation import ROOT, DEFAULT_MODEL_PATH, compile_context_model, collision_surfaces, sha256, write_json
from core.agent.patching import CandidateStore, READ_ALLOWLIST, TARGET, MAX_SOURCE_BYTES, read_project_file, source_policy, violation
from core.agent.verification import CandidateVerifier, execute_trusted

CONTRACTS = {
    'read_project': ('Read exact allowlisted source and its SHA-256.', ('path',)),
    'get_robot_context': ('Read scenario BODYBASE and measured effective MuJoCo parameters.', ('scenario_id',)),
    'get_world_context': ('Read scenario WORLDBASE, actual collision surfaces and task criteria.', ('scenario_id',)),
    'run_simulation': ('Run the allowlisted existing controller, or request an explicitly validated candidate. Store full real telemetry separately.', ('scenario_id','controller_variant')),
    'inspect_failure': ('Read measured diagnostic evidence from a registered simulation run.', ('simulation_run_id',)),
    'propose_patch': ('Validate a controller-only source proposal and produce its diff without overwriting or executing the original.',
                      ('target_path','expected_original_sha256','proposed_source','explanation')),
}


class AgentTools:
    def __init__(self, output: Path, trace, *, save_render=False, backend=None, family='rail'):
        from core.robots.registry import get_family
        self.family = get_family(family)
        self.target = self.family.target if self.family else TARGET
        self.read_allowlist = self.family.read_allowlist if self.family else READ_ALLOWLIST
        self.output, self.trace, self.save_render = Path(output), trace, save_render
        self.output.mkdir(parents=True, exist_ok=True)
        self.scenarios = MappingProxyType(self.family.scenarios if self.family else load_scenarios())
        self._pinned = {path: read_project_file(ROOT, path,self.read_allowlist)['sha256'] for path in self.read_allowlist}
        self.candidates = CandidateStore(ROOT, self.output / 'candidates',target=self.target)
        self.verifier = CandidateVerifier(self.candidates, self.scenarios, self.output / 'verifications', trace, backend=backend,family=self.family)
        self._runs = {}
        self._handlers = MappingProxyType({name: getattr(self, name) for name in CONTRACTS})

    @property
    def schemas(self):
        # Expose existing authorization metadata so the model need not guess
        # paths or identifiers. Dispatch still enforces the same boundaries.
        choices = {'path': sorted(self.read_allowlist), 'target_path': [self.target],
                   'scenario_id': sorted(self.scenarios),
                   'controller_variant': ['faulty', *sorted(self.candidates.records)]}
        runs = sorted(set(self._runs) | set(self.verifier.runs))
        if runs:
            choices['simulation_run_id'] = runs
        schemas = tuple({'type': 'function', 'name': name, 'description': description, 'strict': True,
                      'parameters': {'type': 'object', 'properties': {field: {'type':'string',
                                      **({'enum': choices[field]} if field in choices else {})} for field in fields},
                                     'required': list(fields), 'additionalProperties': False}}
                     for name, (description, fields) in CONTRACTS.items())
        patch = next(s for s in schemas if s['name'] == 'propose_patch')
        patch['parameters']['properties']['proposed_source']['description'] = json.dumps(
            source_policy(read_project_file(ROOT, self.target,self.read_allowlist)['content'],self.target), sort_keys=True)
        patch['description'] += ' Read the structured proposed_source policy before writing: exactly one top-level controller function; no additional top-level helpers. A rejection returns rule IDs and source locations.'
        return schemas

    def _check_pinned(self):
        for path, expected in self._pinned.items():
            if read_project_file(ROOT, path,self.read_allowlist)['sha256'] != expected:
                raise ValueError('Project configuration/source changed during the session; restart it')

    def dispatch(self, name, arguments):
        self.trace.append('tool_requested', {'name': name, 'arguments': arguments})
        try:
            if name not in self._handlers:
                raise ValueError('Unknown tool name')
            fields = CONTRACTS[name][1]
            if not isinstance(arguments, dict) or set(arguments) != set(fields):
                raise ValueError('Tool arguments must contain exactly the declared fields')
            if any(not isinstance(v, str) or not v.strip() for v in arguments.values()):
                raise ValueError('All tool arguments must be nonempty strings')
            if any(len(v.encode()) > MAX_SOURCE_BYTES for v in arguments.values()):
                raise ValueError('Tool argument exceeds the size limit')
            self._check_pinned()
            value = self._handlers[name](**copy.deepcopy(arguments))
            result = {'ok': True, 'result': value}
        except (ValueError, OSError, KeyError, TypeError, RuntimeError) as exc:
            result = {'ok': False, 'error': {'type': type(exc).__name__, 'message': str(exc)}}
            if name == 'propose_patch' and isinstance(arguments, dict) and arguments.get('target_path') != self.target:
                result['error'].update(violations=[violation('patch_target')],
                                       revision_request='Use only the authorized relative controller target. No file was modified.')
        self.trace.append('tool_completed', {'name': name, 'output': result})
        return result

    def read_project(self, path):
        return read_project_file(ROOT, path,self.read_allowlist)

    def _context(self, scenario_id):
        if self.family:return self.family.context(scenario_id)
        if scenario_id not in self.scenarios:
            raise ValueError('Unknown scenario_id; available scenarios are A, B, C')
        body, world = self.scenarios[scenario_id]
        model, xml = compile_context_model(DEFAULT_MODEL_PATH, body, world)
        data = mujoco.MjData(model)
        data.qpos[0], data.qvel[0] = world.initial_position_x_m, world.initial_velocity_ms
        mujoco.mj_forward(model, data)
        context = {'scenario_id': scenario_id, 'bodybase': json_values(body.context), 'worldbase': json_values(world.context),
                   'effective_mujoco': {'carriage_mass_kg': float(model.body('carriage').mass[0]),
                                        'actuator_gear': float(model.actuator_gear[0,0]),
                                        'ctrlrange': model.actuator_ctrlrange[0].tolist(),
                                        'generalized_force_limit_n': float(model.actuator_forcerange[0,1]),
                                        'joint_type': int(model.jnt_type[0]), 'joint_axis': model.jnt_axis[0].tolist(),
                                        'carriage_half_size_m': model.geom('carriage_box').size.tolist(),
                                        'bumper_half_size_m': model.geom('front_bumper').size.tolist(),
                                        'wall_center_m': data.geom_xpos[model.geom('wall').id].tolist(),
                                        'wall_half_size_m': model.geom('wall').size.tolist(),
                                        'initial_position_m': float(data.qpos[0]), 'initial_velocity_ms': float(data.qvel[0]),
                                        'timestep_s': float(model.opt.timestep), **collision_surfaces(model,data)},
                   'effective_mjcf_sha256': hashlib.sha256(xml.encode()).hexdigest(),
                   'force_probes': measure_force_probes(xml, world.initial_position_x_m)}
        directory = self.output / 'contexts'
        directory.mkdir(exist_ok=True)
        (directory / f'{scenario_id}.xml').write_text(xml)
        write_json(directory / f'{scenario_id}.json', context)
        return context

    def get_robot_context(self, scenario_id):
        c = self._context(scenario_id)
        if self.family:return c
        return {k: c[k] for k in ('scenario_id','bodybase','effective_mujoco','effective_mjcf_sha256','force_probes')}

    def get_world_context(self, scenario_id):
        c = self._context(scenario_id)
        if self.family:return c
        return {k: c[k] for k in ('scenario_id','worldbase','effective_mujoco','effective_mjcf_sha256')}

    def run_simulation(self, scenario_id, controller_variant):
        if scenario_id not in self.scenarios:
            raise ValueError('Unknown scenario_id')
        self._check_pinned()
        if controller_variant != 'faulty':
            # Syntax validation does not grant execution permission.
            blocked = self.verifier.verify(controller_variant)
            if blocked['verification_execution'] == 'PASS':
                self._runs.update(self.verifier.runs)
                return blocked['scenario_results'][scenario_id]
            return {'simulation_execution': 'BLOCKED' if blocked['verification_execution']=='BLOCKED' else 'FAIL', 'physical_safety_status': 'NOT_EVALUATED',
                    'candidate_verification': blocked}
        if self.family:
            summary,record=self.family.trusted(scenario_id,self.output/'simulations')
            if record is not None:self._runs[summary['simulation_run_id']]=record
            return summary
        summary, record = execute_trusted(scenario_id, controller_variant, self.scenarios,
                                          self.output / 'simulations', self._pinned[TARGET], save_render=self.save_render)
        self._runs[summary['simulation_run_id']] = record
        write_json(self.output / 'simulation_index.json', {key: {'artifacts': str(Path('simulations') / key), 'sha256': value['inventory']}
                                                           for key,value in self._runs.items()})
        return summary

    def inspect_failure(self, simulation_run_id):
        self._runs.update(self.verifier.runs)
        if simulation_run_id not in self._runs:
            raise ValueError('Only simulation IDs registered in this session may be inspected')
        record = self._runs[simulation_run_id]
        if self.family:
            return {'simulation_run_id':simulation_run_id,'evidence':self.family.diagnostic(record),
                    'artifact_references':{n:str(record['directory']/n) for n in record['inventory']}}
        if any(sha256(record['directory'] / name) != digest for name,digest in record['inventory'].items()):
            raise ValueError('Simulation artifact integrity mismatch')
        d = json.loads((record['directory'] / 'diagnostics.json').read_text())
        fields = ('physical_context','robot_physical_parameters','controller','analytical_prediction',
                  'prediction_at_measured_braking_onset','actual_available_braking_distance_m',
                  'braking_initiation','first_wall_contact','minimum_observed_clearance_m','final_state',
                  'safety_acceptance','independent_safety_verification','effective_mjcf_sha256')
        return {'simulation_run_id': simulation_run_id, 'evidence': {key:d[key] for key in fields},
                'artifact_references': {name:str(Path('simulations')/simulation_run_id/name) for name in record['inventory']}}

    def propose_patch(self, target_path, expected_original_sha256, proposed_source, explanation):
        return self.candidates.propose(target_path=target_path, expected_original_sha256=expected_original_sha256,
                                        proposed_source=proposed_source, explanation=explanation)
