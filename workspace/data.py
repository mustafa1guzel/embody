"""Bounded, hash-checked read models. No model client or candidate import/exec path."""
from __future__ import annotations
import difflib
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import stat

import mujoco

from core.agent.patching import TARGET, read_project_file
from core.day3 import load_scenarios
from core.simulation import ROOT, DEFAULT_MODEL_PATH, compile_context_model, collision_surfaces

MAX_FILE_BYTES = 12_000_000
LABELS = {'original': 'Original · collision', 'attempt_1': 'Proposal 1 · safety rejected',
          'attempt_2': 'Proposal 2 · verified'}
SCENARIOS = ('A', 'B', 'C')


class EvidenceError(ValueError):
    """Missing, corrupt, out-of-bound or internally inconsistent review evidence."""


def decode_json(raw):
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise EvidenceError('Duplicate JSON field in evidence')
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(EvidenceError('Nonfinite JSON evidence')))
    except (ValueError, UnicodeError) as exc:
        raise EvidenceError('Evidence JSON is invalid') from exc


def bounded_read(root, relative):
    """Walk with O_NOFOLLOW; neither references nor symlink swaps expose other files."""
    if (not isinstance(relative, str) or not relative or '\\' in relative or '\x00' in relative
            or PurePosixPath(relative).is_absolute() or any(p in ('', '.', '..') for p in relative.split('/'))):
        raise EvidenceError('Evidence path must be a safe indexed relative path')
    fd = None
    try:
        fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        parts = relative.split('/')
        for index, name in enumerate(parts):
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
            if index < len(parts)-1:
                flags |= os.O_DIRECTORY
            next_fd = os.open(name, flags, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_FILE_BYTES:
            raise EvidenceError('Evidence must be a bounded regular file')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(MAX_FILE_BYTES+1)
        if len(raw) > MAX_FILE_BYTES:
            raise EvidenceError('Evidence exceeds the size limit')
        return raw
    except OSError as exc:
        raise EvidenceError('Evidence is missing or a symlink was rejected') from exc
    finally:
        if fd is not None:
            os.close(fd)


class Recording:
    def __init__(self, root, inventory_sha256):
        self.root = Path(root).absolute()
        raw = bounded_read(self.root, 'final_evidence_inventory.json')
        if hashlib.sha256(raw).hexdigest() != inventory_sha256:
            raise EvidenceError('Recorded evidence inventory hash mismatch')
        self.inventory_sha256 = inventory_sha256
        self.inventory = decode_json(raw)
        if not isinstance(self.inventory, dict):
            raise EvidenceError('Invalid evidence inventory')

    def read(self, relative):
        if relative not in self.inventory:
            raise EvidenceError('File is not in the recorded evidence inventory')
        raw = bounded_read(self.root, relative)
        if hashlib.sha256(raw).hexdigest() != self.inventory[relative]:
            raise EvidenceError('Recorded evidence file hash mismatch: '+relative)
        return raw

    def json(self, relative):
        return decode_json(self.read(relative))

    def reference(self, reference):
        path = Path(reference)
        if path.is_absolute():
            try:
                return path.relative_to(self.root).as_posix()
            except ValueError as exc:
                raise EvidenceError('Evidence reference escaped this recording') from exc
        # Legacy baseline summaries use paths relative to their session.
        relative = path.as_posix()
        if relative in self.inventory:
            return relative
        return 'session/'+relative

    def original(self):
        current = read_project_file(ROOT, TARGET)
        expected = self.json('model_proposals/attempt_2/validation.json')['original_sha256']
        if current['sha256'] != expected:
            raise EvidenceError('Current controller differs from the recorded original; review is blocked')
        return current

    def proposal(self, name):
        if name not in ('attempt_1', 'attempt_2'):
            raise EvidenceError('Unknown recorded proposal')
        base = 'model_proposals/'+name+'/'
        source = self.read(base+'controller.py').decode('utf-8')
        validation = self.json(base+'validation.json')
        verification = self.json(base+'verification.json')
        original = self.original()
        digest = hashlib.sha256(source.encode()).hexdigest()
        diff = ''.join(difflib.unified_diff(original['content'].splitlines(True),source.splitlines(True),
                                           fromfile=TARGET,tofile='candidate/'+TARGET))
        if (digest != validation['proposed_sha256'] or digest != verification['source_sha256']
                or validation['candidate_id'] != verification['candidate_id']
                or diff != validation['unified_diff'] or diff != self.read(base+'proposal.diff').decode()):
            raise EvidenceError('Proposal source, diff or verification identity is inconsistent')
        return {'source':source,'diff':diff,'validation':validation,'verification':verification,
                'provenance':self.json(base+'provenance.json')}

    def summary(self, scenario, variant):
        if scenario not in SCENARIOS or variant not in LABELS:
            raise EvidenceError('Unknown scenario or controller review selection')
        if variant == 'original':
            result = self.json('baseline_physics_measurements.json')[scenario]
        else:
            result = self.proposal(variant)['verification']['scenario_results'][scenario]
        if result['scenario_id'] != scenario:
            raise EvidenceError('Recorded scenario identity mismatch')
        return result

    def trajectory(self, scenario, variant):
        summary = self.summary(scenario, variant)
        refs = summary['artifact_references']
        telemetry = self.json(self.reference(refs['telemetry.json']))
        independent = self.json(self.reference(refs['independent_safety_trace.json']))
        xml = self.read(self.reference(refs['effective_model.xml'])).decode()
        metadata, samples = telemetry['metadata'], telemetry['samples']
        if (metadata['controller']['source_sha256'] != summary['controller_sha256']
                or hashlib.sha256(xml.encode()).hexdigest() != metadata['effective_mjcf_sha256']):
            raise EvidenceError('Recorded controller or physical model identity mismatch')
        fields = ('time','position','velocity','wall_clearance','generalized_actuator_force')
        if not samples or any(any(type(s.get(k)) not in (int,float) or not math.isfinite(s[k])
                                  for k in fields) for s in samples):
            raise EvidenceError('Recorded telemetry contains invalid measurements')
        if any(b['time'] <= a['time'] for a,b in zip(samples,samples[1:])):
            raise EvidenceError('Recorded telemetry time is not increasing')
        return {'summary':summary,'samples':samples,'metadata':metadata,'independent':independent,'xml':xml,
                'telemetry_reference':self.reference(refs['telemetry.json'])}

    def tool_trace(self):
        events = [decode_json(row) for row in self.read('session/execution_trace.jsonl').splitlines() if row]
        calls = []
        for row in events:
            payload = row['payload']
            if row['event']=='tool_requested':
                calls.append({'name':payload['name'],'arguments':payload['arguments']})
            elif row['event']=='tool_completed':
                if not calls or calls[-1]['name'] != payload['name']:
                    raise EvidenceError('Recorded tool trace order mismatch')
                calls[-1]['output']=payload['output']
            elif row['event']=='candidate_verification' and calls and calls[-1]['name']=='propose_patch':
                calls[-1]['verification_feedback']=payload
        return calls


def settings():
    return decode_json((Path(__file__).parent/'recording.json').read_bytes())


def default_recording():
    config = settings()
    return Recording(ROOT/config['root'], config['inventory_sha256'])


def physical_context(scenario, recorded):
    if scenario not in SCENARIOS:
        raise EvidenceError('Unknown physical scenario')
    body, world = load_scenarios()[scenario]
    model, xml = compile_context_model(DEFAULT_MODEL_PATH,body,world)
    data = mujoco.MjData(model)
    data.qpos[0],data.qvel[0] = world.initial_position_x_m, world.initial_velocity_ms
    mujoco.mj_forward(model,data)
    if (hashlib.sha256(xml.encode()).hexdigest() != recorded['metadata']['effective_mjcf_sha256']):
        raise EvidenceError('Current physical context differs from the recorded compiled model')
    return {'robot_id':body.robot_id,'mass_kg':float(model.body('carriage').mass[0]),
            'braking_force_n':float(model.actuator_forcerange[0,1]),'initial_velocity_ms':float(data.qvel[0]),
            'wall_center_x_m':float(data.geom_xpos[model.geom('wall').id,0]),
            'wall_half_size_m':model.geom('wall').size.tolist(),'joint_axis':model.jnt_axis[0].tolist(),
            'minimum_clearance_m':world.minimum_clearance_m,'max_final_speed_ms':world.max_final_speed_ms,
            'duration_s':world.simulation_duration_s,'timestep_s':world.simulation_timestep_s,
            'completion_deadline_s':world.completion_deadline_s,**collision_surfaces(model,data)}


def chart_rows(trajectories):
    return [{'time':row['time'],'controller':LABELS[key],
             'clearance':row['wall_clearance'],'velocity':row['velocity'],
             'force':row['generalized_actuator_force'],'wall_contact':row['wall_collision']}
            for key,trajectory in trajectories.items() for row in trajectory['samples']]


def native_frame(scenario, variant, step):
    config = settings()
    if not config['native_index_sha256']:
        raise EvidenceError('Native replay has not been generated')
    root = ROOT/config['native_replay_root']
    raw = bounded_read(root,'index.json')
    if hashlib.sha256(raw).hexdigest() != config['native_index_sha256']:
        raise EvidenceError('Native replay index hash mismatch')
    index = decode_json(raw)
    if index['recording_inventory_sha256'] != config['inventory_sha256'] or index['status']!='COMPLETE':
        raise EvidenceError('Native replay does not match the recorded experiment')
    try:
        frame = next(f for f in index['scenarios'][scenario][variant] if f['step']==step)
    except (KeyError,StopIteration) as exc:
        raise EvidenceError('Requested recorded native frame is unavailable') from exc
    pixels = bounded_read(root,frame['path'])
    if hashlib.sha256(pixels).hexdigest() != frame['sha256']:
        raise EvidenceError('Native frame hash mismatch')
    return pixels, frame
