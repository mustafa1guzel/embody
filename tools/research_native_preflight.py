"""Prepare/check exact local consent only. This command has no execution action."""
import argparse,hashlib,json
from datetime import datetime,timezone,timedelta
from pathlib import Path
from uuid import uuid4
from importlib.metadata import version
from core.simulation import ROOT
from ide_api import rail_sweeps as rail
from ide_api.research.bundles import source_manifest,repo_base
from ide_api.research.store import Research
from ide_api.research.artifacts import ArtifactStore,now,finite_json
from ide_api.experiment_designer import ExperimentDesigner

FORMAT='EMBODY_CURRENT_SOURCE_NATIVE_RESEARCH_CONSENT_V1'
OLD='46343bfe46c2d97fa265959511611f51f95ebef8683fab8daea6a09141840b2c'
def sources():
 names=set(source_manifest())|{'tools/research_native_preflight.py','ide_api/experiment_designer.py','core/simulation.py','core/bodybase.py','core/worldbase.py','core/diagnostics.py','core/context_validation.py','configs/bodybase.json','configs/worldbase.json','robot/rail_carriage.xml','requirements.txt','frontend/package.json','frontend/package-lock.json'}
 return {n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in sorted(names)}

def prepare():
 catalog=rail.catalog();nonce=uuid4().hex
 request=rail.validate({'experiment_id':rail.EXPERIMENT,'controller_id':rail.CONTROLLER,'source_sha256':catalog['source_sha256'],'cases':[{'mass_kg':4.,'speed_mps':1.2,'force_n':2.,'gap_m':g} for g in (1.44,1.49,1.54)],'criteria':catalog['defaults'],'nonce':nonce,'confirmation':rail.CONFIRMATION})
 research=Research(ExperimentDesigner(rail.RailSweeps()))
 definition={'format':FORMAT,'status':'PROPOSED_NOT_AUTHORIZED_NOT_EXECUTED','created_utc':now(),'expires_utc':(datetime.now(timezone.utc)+timedelta(hours=48)).isoformat(),'base_commit':repo_base(),'source_manifest':sources(),'catalog':catalog,'research_context_sha256':research.context()['context_sha256'],'requirements_sha256':hashlib.sha256((ROOT/'requirements.txt').read_bytes()).hexdigest(),'versions':{p:version(p) for p in ('mujoco','numpy','jsonschema')},'request':request,'limits':{'new_cases':3,'native_rollouts':6,'primary_steps_per_case':600,'fresh_replay_steps_per_case':600,'maximum_integration_steps':3600,'exclusive_window_seconds':600,'native_cooperative_deadline_seconds':rail.POLICY['wall_seconds'],'retries':0,'api_calls':0,'api_usd':0,'vm_launches':0,'installations':0,'applications':0},'outputs':{'raw_native_root':'.runtime/rail_sweeps','durable_evidence_root':'.runtime/evidence_store','campaign_root':'.runtime/research'},'analytical_predictions':[{'gap_m':g,'continuous_stop_distance_m':1.44,'continuous_remaining_gap_m':g-1.44,'provenance':'ANALYTICAL_PREDICTION_NOT_NATIVE'} for g in (1.44,1.49,1.54)],'campaign_planning_ceiling':{'total_cases':8,'total_rollouts':16,'maximum_steps':9600,'authorization':'NONE beyond the three initial cases; every additional exact measured-guided midpoint requires separate approval'},'procedure':['Require a new explicit user approval naming this exact canonical definition. Hash possession or CLI arguments are not consent.','Before dispatch, recheck manifest bytes, canonical definition, every frozen source, versions, current catalog, expiration and previously unused nonce; require the existing global expensive-job lock and retained-job capacity.','Record the actual explicit approval separately, with original message reference and approved window, before invoking the unchanged server job admission / RailSweeps.start with this exact request once. Do not retry an interrupted/uncertain admission.','Use only the registered trusted controller; run each approved case and required fresh replay serially through the unchanged native service. Stop at deadline/cancellation/failure; save every actual outcome.','After execution capture available actual raw records into durable bundles, independently read back trajectories/forces/contacts/replay, link only exact matching reviewed batch, preserve failures and honest missing data.','Stop after this initial sweep. A measured opposite-outcome interval may justify a midpoint proposal; that proposal is not execution approval. No transition is predeclared.'],'prohibited':['No paid model, VM, controller/source/XML changes, installation/download, automatic application, retry, fallback, unattended chain or historical evidence modification.'],'supersedes_unapproved_definition':OLD}
 value={'definition':definition,'sha256':rail.digest(definition),'authorization':'NOT_GRANTED'}
 path='native_preparations/'+nonce+'/consent.json';ArtifactStore(ROOT/'.runtime/evidence_store').write_once(path,rail.canonical(value),120000)
 return {'relative_path':'.runtime/evidence_store/'+path,'definition_sha256':value['sha256'],'manifest_byte_sha256':hashlib.sha256(rail.canonical(value)).hexdigest(),'new_native_steps':0,'authorization':'NOT_GRANTED'}

def check(value):
 rail.exact(value,['definition','sha256','authorization']);d=value['definition']
 if value['sha256']!=rail.digest(d) or d['format']!=FORMAT or value['authorization']!='NOT_GRANTED':raise ValueError('Exact proposed consent identity differs')
 if datetime.now(timezone.utc)>=datetime.fromisoformat(d['expires_utc']):raise ValueError('Consent freeze expired; fresh review needed')
 if d['source_manifest']!=sources() or d['base_commit']!=repo_base():raise ValueError('Frozen source/base identities differ')
 if d['versions']!={p:version(p) for p in ('mujoco','numpy','jsonschema')}:raise ValueError('Installed versions differ')
 if rail.digest(d['catalog'])!=rail.digest(rail.catalog()):raise ValueError('Native catalog differs')
 research=Research(ExperimentDesigner(rail.RailSweeps()))
 if d['research_context_sha256']!=research.context()['context_sha256']:raise ValueError('Research context differs')
 request=rail.validate(d['request'])
 if request['cases']!=[{'mass_kg':4.,'speed_mps':1.2,'force_n':2.,'gap_m':g} for g in (1.44,1.49,1.54)] or request['criteria']!=rail.DEFAULT_CRITERIA:raise ValueError('Exact initial numeric scope differs')
 if (ROOT/'.runtime/rail_sweeps'/request['nonce']).exists():raise ValueError('Nonce consumed or interrupted; no reuse')
 count=len(list((ROOT/'.runtime/rail_sweeps').iterdir())) if (ROOT/'.runtime/rail_sweeps').exists() else 0
 if count>=rail.POLICY['retained_jobs']:raise ValueError('Existing retained-job capacity exhausted; no pruning')
 return {'status':'IDENTITIES_VALID_NO_AUTHORITY','source_count':len(d['source_manifest']),'canonical_valid':True,'numeric_admission':'PASS_NO_EXECUTION','native_steps':0,'nonce_unused':True,'approval':'MISSING_EXPLICIT_USER_APPROVAL','execution_authorized':False,'limitations':['Global expensive-job lock must be acquired at future admission; this read-only preflight cannot reserve it.','This command cannot execute or grant approval.']}

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','check']);parser.add_argument('--manifest');args=parser.parse_args()
 if args.action=='prepare':result=prepare()
 else:
  if not args.manifest:parser.error('check requires --manifest')
  p=(ROOT/args.manifest).resolve()
  if not p.is_relative_to(ROOT/'.runtime/evidence_store/native_preparations'):raise ValueError('Use a local prepared consent reference')
  raw=p.read_bytes();result=check(finite_json(raw,120000));result['manifest_byte_sha256']=hashlib.sha256(raw).hexdigest()
 print(json.dumps(result,indent=2))
