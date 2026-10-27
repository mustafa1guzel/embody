"""Immutable canonical definitions and write-once evidence, no model transport."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from physics.contracts import canonical,digest
from core.simulation import ROOT
from workspace.data import bounded_read,decode_json,EvidenceError


def file_hash(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_once(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x') as f:f.write(json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n')


def implementation_identity():
    paths=[]
    for folder in ('robustness','core','physics'):
        paths.extend((ROOT/folder).rglob('*.py'))
    paths.extend((ROOT/'configs').glob('*.json'))
    paths.extend(ROOT/p for p in ('robot/controller.py','robot/arm_controller.py','robot/rail_carriage.xml','robot/planar_arm.xml','workspace/recording.json','workspace/arm_recording.json'))
    return {p.relative_to(ROOT).as_posix():file_hash(p) for p in sorted(paths)}


@dataclass(frozen=True)
class Experiment:
    serialized:str

    def __post_init__(self):
        d=decode_json(self.serialized.encode())
        if d.get('schema_version')!=1 or d.get('families')!=['rail','arm'] or d.get('api_calls_allowed')!=0:
            raise ValueError('Unsupported experiment definition')
        if len(d['matrix'])!=80 or len({r['id'] for r in d['matrix']})!=80:raise ValueError('Exactly 80 uniquely identified scenarios required')
        if canonical(d)!=self.serialized:raise ValueError('Contract must be canonical')

    @property
    def data(self):return json.loads(self.serialized)
    @property
    def identity(self):return digest(self.data)

    def assert_current(self):
        if self.data['implementation']!=implementation_identity():raise EvidenceError('Benchmark implementation/source/configuration is stale')

    @classmethod
    def load(cls,folder):
        d=decode_json(bounded_read(folder,'experiment.json'));e=cls(canonical(d['definition']))
        if e.identity!=d['sha256']:raise EvidenceError('Experiment hash mismatch')
        e.assert_current();return e


def frozen_sources():
    from workspace.data import default_recording
    from workspace.arm_data import default_arm_recording
    r=default_recording();a=default_arm_recording()
    result={}
    for family,proposal,inventory in [('rail',r.proposal('attempt_2'),r.inventory_sha256),('arm',a.proposal('attempt_1'),a.identity)]:
        v=proposal['validation'];source=proposal['source']
        if (v['validation_status']!='VALID' or proposal['verification']['physical_safety_status']!='PASS'
                or hashlib.sha256(source.encode()).hexdigest()!=v['proposed_sha256']):raise EvidenceError('Historical repair identity/verification mismatch')
        path='robot/controller.py' if family=='rail' else 'robot/arm_controller.py'
        if file_hash(ROOT/path)!=v['original_sha256']:raise EvidenceError('Original source drift')
        result[family]={'baseline':{'path':path,'sha256':v['original_sha256'],'origin':'trusted_developer_original'},
                        'repair':{'source':source,'sha256':v['proposed_sha256'],'recording_sha256':inventory,
                                  'provenance':proposal['provenance'],'origin':'genuine_historical_gpt_proposal'}}
    return result
