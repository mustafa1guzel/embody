"""Frozen inspect/propose experiment over the existing SHAPEBASE transaction engine.

No network at import/preflight time; no mutation/apply or source-execution tool.
"""
import copy
import json
import time
from decimal import Decimal
from pathlib import Path
from importlib.metadata import version

from jsonschema import Draft202012Validator
from core.agent.api_budget import GPT54_POLICY, BudgetBlocked, cost
from core.agent.live_model import BudgetedOpenAIAdapter
from core.agent.models import OpenAIResponsesAdapter
from core.agent.orchestration import SYSTEM_INSTRUCTIONS
from engineering.agent import EngineeringTools, PARAMETERS
from engineering.project import identity
from physics.contracts import canonical, digest
from robustness.contracts import file_hash
from shapebase.geometry import library, generate
from shapebase.operations import SCHEMAS as SHAPE_OPERATIONS
from workspace.data import decode_json
from world.compiler import compile_world, initial_state

GOAL = 'Make the first robotic arm link 40% longer. Keep both mounting holes proportional to the link and preserve the elbow connection.'
ENDPOINT = 'https://api.openai.com/v1/responses'
INPUT_BOUND = 41472
OUTPUT_BOUND = 3072
MAX_REQUESTS = 2
CAP = '0.30'


def compact_schema(schema):
    """Factor identical schema subtrees; no field or accepted value changes."""
    from collections import Counter
    counts, nodes = Counter(), {}
    def collect(x):
        if isinstance(x, dict):
            key = canonical(x)
            if len(key) >= 80 and any(k in x for k in ('type', 'anyOf', 'enum', 'const')):
                counts[key] += 1; nodes[key] = x
            for v in x.values(): collect(v)
        elif isinstance(x, list):
            for v in x: collect(v)
    collect(schema)
    names = {key: 'D' + str(i) for i, key in enumerate(sorted(k for k, n in counts.items() if n > 1))}
    def factor(x, own=None):
        if isinstance(x, dict):
            key = canonical(x)
            if key in names and key != own: return {'$ref': '#/$defs/' + names[key]}
            return {k: factor(v) for k, v in x.items()}
        if isinstance(x, list): return [factor(v) for v in x]
        return x
    result = factor(schema)
    result['$defs'] = {names[k]: factor(nodes[k], k) for k in names}
    return result


def schemas():
    parameters = copy.deepcopy(PARAMETERS)
    parameters['properties']['operations'] = {'type': 'array', 'minItems': 1, 'maxItems': 16,
                                             'items': {'anyOf': copy.deepcopy(SHAPE_OPERATIONS)}}
    def explicit_types(x):
        if isinstance(x, list): return [explicit_types(v) for v in x]
        if not isinstance(x, dict): return x
        x = {k: explicit_types(v) for k, v in x.items()}
        if 'const' in x:
            x['enum'] = [x.pop('const')]
        if 'enum' in x and 'type' not in x:
            if not all(isinstance(v, str) for v in x['enum']):
                raise ValueError('Only existing string constants/enums need wire normalization')
            x['type'] = 'string'
        return x
    parameters = compact_schema(explicit_types(parameters))
    return [
        {'type': 'function', 'name': 'inspect_engineering', 'strict': True,
         'description': 'Inspect actual authoritative project identities, ShapeSpecs, mounting frames, joint/child relationships and native proxy limits before designing. Arguments must be {}. No execution.', 'parameters': {'type': 'object', 'properties': {}, 'required': [], 'additionalProperties': False}},
        {'type': 'function', 'name': 'propose_engineering_change', 'strict': True,
         'description': 'Propose exact typed SHAPEBASE actions against the inspected hash/revision. All fields are required; use null only where explicitly permitted. Operations use kind, never op. SI dimensions; hole u/v are fractions of full length/width. Existing normalized holes and declared attachment frames regenerate when dimensions change. No inferred joints. Return explanation of physical consequences and unsupported capabilities. Review only: cannot apply, simulate, execute source or install anything.',
         'parameters': parameters}]


def task_context():
    # No desired final dimensions or prewritten operations enter model context.
    return {'user_request': GOAL, 'scope': 'Independent two-joint World Builder arm, not a generated device contract.',
            'instructions': 'First inspect actual state with inspect_engineering. Then select supported operations and supply your own arguments in propose_engineering_change. At most two model turns, one tool per turn. Explain inertia, mass, actuator/load and collision-proxy limitations. Do not claim simulation, application, manufacturing or hardware safety. Preserve existing identities, mounting-hole proportions, joint/child relationships and other design inputs. No final answer plan has been provided.',
            'supported_families': ['rounded_link', 'drilled_plate', 'motor_bracket', 'shaft', 'structural_support'],
            'unsupported': ['BREP CAD/STEP', 'material/density inference', 'through-hole contact physics', 'manufacturing fit', 'hardware safety', 'arbitrary source/controller execution', 'automatic application']}


def inspection(service):
    raw = service.inspect_context()  # Same existing engineering inspect path.
    p = service.current()
    return {'identities': raw['identities'], 'project_id': p['id'], 'revision': p['revision'],
            'shape_specs': copy.deepcopy(p['shape_specs']),
            'world_objects': [{k: copy.deepcopy(v) for k, v in o.items() if k not in ('name', 'visual')} for o in p['world']['objects']],
            'environment': copy.deepcopy(p['world']['environment']),
            'physical_scope': 'Explicit entered masses; uniform native solid-envelope inertia. Display holes/rounding are omitted from collision and inertia. Constant bounded trusted world motors; no electrical/controller execution.',
            'permissions': {'review_only': True, 'apply': False, 'simulation_tool': False}}


def normalize(request):
    wire = copy.deepcopy(request)
    wire.update(reasoning={'effort': 'low'}, max_output_tokens=OUTPUT_BOUND,
                service_tier='default', store=True, parallel_tool_calls=False, tool_choice='auto')
    return wire


def first_request():
    return normalize(OpenAIResponsesAdapter(None, 'gpt-5.4', continuation='server')._build_request(
        ({'role': 'system', 'content': SYSTEM_INSTRUCTIONS}, {'role': 'user', 'content': canonical(task_context())}), schemas()))


def second_request(observation, response_id, call_id):
    body = first_request()
    body['input'] = [{'type': 'function_call_output', 'call_id': call_id,
                      'output': json.dumps({'ok': True, 'result': observation}, allow_nan=False)}]
    body['previous_response_id'] = response_id
    return body


class ShapeExperimentTools:
    """Restricted facade; all accepted mutations still use EngineeringTools."""
    def __init__(self, service, trace):
        self.service, self.trace = service, trace
        self.delegate = EngineeringTools(service, trace)
        self.stage, self.result = 0, None
        self.observation = inspection(service)
        self.before = copy.deepcopy(service.current())

    @property
    def schemas(self):
        return schemas()

    def dispatch(self, name, arguments):
        expected = ('inspect_engineering', 'propose_engineering_change')
        try:
            if self.stage >= 2 or name != expected[self.stage]:
                raise ValueError('Inspect once before proposing once; no retry, alias or apply tool')
            schema = next(s for s in schemas() if s['name'] == name)
            Draft202012Validator(schema['parameters']).validate(arguments)
            if self.service.current() != self.before:
                raise ValueError('Authoritative project changed since frozen inspection')
            if name == 'inspect_engineering':
                raw = self.delegate.dispatch(name, arguments)
                if not raw['ok'] or inspection(self.service) != self.observation:
                    raise ValueError('Actual inspection changed')
                result = {'ok': True, 'result': copy.deepcopy(self.observation)}
            else:
                result = self.delegate.dispatch(name, arguments)
                self.result = result
            self.stage += 1
        except Exception as exc:
            self.stage = 2  # Failure consumes this protocol; never retry.
            result = {'ok': False, 'error': {'type': type(exc).__name__, 'message': str(exc)[:300]}}
        self.trace.append('shape_experiment_tool_completed', {'name': name, 'output': result})
        return result


def validate_task(service, proposal):
    """Host-only independent task/identity/geometry/native checks, no rollout/apply.

    Required length is calculated here, never transmitted as an answer.
    """
    import mujoco
    import numpy as np
    from engineering.changes import validate_changeset
    before = service.current()
    validate_changeset({k: v for k, v in proposal.items() if k != "proposal_id"})
    if (proposal['base_project_sha256'] != identity(before) or proposal['base_revision'] != before['revision']
            or proposal['approval_status'] != 'PROPOSED_NOT_APPLIED'):
        raise ValueError('Stale or applied proposal')
    after, checks = service.preview(before, proposal['operations'])
    if after != proposal['proposed_project'] or identity(after) != proposal['resulting_project_sha256'] or digest(checks) != digest(proposal['validation']):
        raise ValueError('Independent proposal reconstruction differs')
    old = next(s for s in before['shape_specs'] if s['id'] == 'shape_link_one')
    new = next(s for s in after['shape_specs'] if s['id'] == old['id'])
    expected = float(Decimal(str(old['parameters']['length_m'])) * Decimal('1.40'))
    np.testing.assert_allclose(new['parameters']['length_m'], expected, rtol=0, atol=1e-12)
    # Every other design input must remain unchanged. Placement/revision changes
    # are derived by the existing engine, never accepted as unrelated model edits.
    normalized = copy.deepcopy(new)
    normalized['parameters']['length_m'] = old['parameters']['length_m']
    for key in ('geometry_revision', 'position_m'):
        normalized[key] = copy.deepcopy(old[key])
    if normalized != old:
        raise ValueError('Unrequested part, hole, frame, mass or interface modification')
    old_other = [s for s in before['shape_specs'] if s['id'] != old['id']]
    if [s for s in after['shape_specs'] if s['id'] != old['id']] != old_other:
        raise ValueError('Unrequested second part modification')
    expected_project = copy.deepcopy(before)
    expected_project.update(revision=after['revision'], shape_specs=after['shape_specs'], world=after['world'])
    if expected_project != after:
        raise ValueError('Nonmechanical project data changed')
    a = {o['id']: o for o in before['world']['objects']}
    b = {o['id']: o for o in after['world']['objects']}
    if set(a) != set(b):
        raise ValueError('Body identities changed')
    for name in a:
        allowed = {'position_m', 'dimensions_m'} if name == old['body_id'] else {'position_m', 'rotation_rad'} if name == 'elbow' else set()
        if {k: v for k, v in a[name].items() if k not in allowed} != {k: v for k, v in b[name].items() if k not in allowed}:
            raise ValueError('Unrequested mechanics or actuator change')
    if before['world']['environment'] != after['world']['environment']:
        raise ValueError('Verification environment changed')
    go, gn = generate(old), generate(new)
    for ho, hn in zip(go['holes'], gn['holes'], strict=True):
        assert ho['id'] == hn['id']
        np.testing.assert_allclose(hn['center_m'], [ho['center_m'][0] * 1.4, *ho['center_m'][1:]], rtol=0, atol=1e-12)
    frames = {f['id']: f for f in gn['attachment_frames']}
    np.testing.assert_allclose(b['elbow']['position_m'], frames['mount_b']['position_m'], atol=1e-12, rtol=0)
    m0, _, c0 = compile_world(before['world'])
    m1, _, c1 = compile_world(after['world'])
    d0, d1 = initial_state(m0, before['world']), initial_state(m1, after['world'])
    mujoco.mj_forward(m0, d0); mujoco.mj_forward(m1, d1)
    np.testing.assert_allclose(d0.xanchor[m0.joint('joint_shoulder').id], d1.xanchor[m1.joint('joint_shoulder').id], atol=1e-12, rtol=0)
    np.testing.assert_allclose(m1.body('link_one').mass, m0.body('link_one').mass, atol=1e-12, rtol=0)
    assert max(m1.body('link_one').inertia) > max(m0.body('link_one').inertia)
    assert digest(library(after)) == digest(proposal['validation']['shapes'])
    return {'status': 'TYPED_TASK_GEOMETRY_NATIVE_COMPILE_PASS', 'base_sha256': identity(before),
            'proposed_sha256': identity(after), 'original_geometry': go, 'proposed_geometry': gn,
            'original_compiled': c0, 'proposed_compiled': c1,
            'head_unchanged': service.current() == before,
            'limitations': 'Proxy compilation/force/inertia checks, not hardware safety or closed-loop device control.'}


def versions():
    return {n: version(n) for n in ('openai', 'mujoco', 'numpy', 'jsonschema')}


def preflight(root, manifest, approval, service):
    """Fail closed before credentials, client creation or any network operation."""
    d = manifest['definition']
    if approval != manifest['sha256'] or digest(d) != approval:
        raise ValueError('Fresh explicit approval of this exact Phase18C manifest required')
    if not 0 <= time.time() - d['frozen_unix'] <= 86400:
        raise ValueError('Frozen approval scope expired or clock precedes freeze')
    expected = {'model': 'gpt-5.4', 'reasoning_effort': 'low', 'endpoint': ENDPOINT, 'max_requests': MAX_REQUESTS,
                'input_token_bound': INPUT_BOUND, 'max_output_tokens': OUTPUT_BOUND, 'hard_cap_usd': CAP,
                'execution_window_seconds': 600, 'max_native_previews': 1, 'native_steps_total': 400,
                'vm_launches': 0, 'automatic_application': False, 'retries': 0}
    if any(d.get(k) != v for k, v in expected.items()) or d['versions'] != versions():
        raise ValueError('Frozen execution scope/version differs')
    if str(cost(INPUT_BOUND, 0, OUTPUT_BOUND, policy=GPT54_POLICY) * 2) != d['worst_case_reservation_usd']:
        raise ValueError('Pricing reservation changed')
    for name, sha in d['source_sha256'].items():
        if file_hash(Path(root) / name) != sha:
            raise ValueError('Frozen source or requirement identity changed: ' + name)
    for name, sha in d['input_files_sha256'].items():
        if file_hash(Path(root) / name) != sha:
            raise ValueError('Frozen local input changed: ' + name)
    if identity(service.current()) != d['project_sha256'] or service.current()['revision'] != d['project_revision']:
        raise ValueError('Authoritative disposable head changed')
    observation = inspection(service)
    if digest(observation) != d['inspection_sha256'] or digest(first_request()) != d['first_request_sha256']:
        raise ValueError('Actual tool context or schemas changed')
    second = second_request(observation, 'R' * 128, 'C' * 128)
    first_bound = len(json.dumps(first_request(), ensure_ascii=True).encode()) + 4096
    second_bound = len(json.dumps(second, ensure_ascii=True).encode()) + 4096 + first_bound + OUTPUT_BOUND
    if first_bound != d['first_serialized_bound'] or second_bound != d['second_serialized_chain_bound'] or max(first_bound, second_bound) > INPUT_BOUND:
        raise ValueError('Serialized request/continuation bounds differ or exceed reservation')
    return observation


class FrozenShapeAdapter(BudgetedOpenAIAdapter):
    def __init__(self, *args, observation, **kwargs):
        super().__init__(*args, **kwargs)
        self.observation, self.completed = copy.deepcopy(observation), []

    def _request(self, **request):
        wire = normalize(request)
        n = len(self.completed)
        expected = first_request() if n == 0 else second_request(self.observation, *self.completed[0]) if n == 1 else None
        if expected is None or wire != expected:
            raise BudgetBlocked('Actual request differs from frozen protocol; no dispatch')
        response = super()._request(**wire)
        raw = response.model_dump(mode='json')
        calls = [c for c in raw['output'] if c['type'] == 'function_call']
        name = ('inspect_engineering', 'propose_engineering_change')[n]
        if len(calls) != 1 or calls[0]['name'] != name:
            raise BudgetBlocked('Actual model did not select the required supported tool; no retry')
        c = calls[0]
        args = decode_json(c['arguments'].encode())
        Draft202012Validator(next(t for t in schemas() if t['name'] == name)['parameters']).validate(args)
        for value in (raw.get('id'), c.get('call_id')):
            if not isinstance(value, str) or not 1 <= len(value) <= 128 or not value.isascii() or not all(x.isalnum() or x in '_-' for x in value):
                raise BudgetBlocked('Provider continuation identity exceeds frozen bound')
        self.completed.append((raw['id'], c['call_id']))
        return response
