"""Prepare/check exact current-source model scopes. NO execute/approval action.

Fresh explicit user approval of each digest is required before the trusted local
operator may use existing Server.job / RailSweeps.start. Hash possession is not
consent. This tool cannot reserve a nonce, simulate, retry or refresh authority.
"""
import argparse,hashlib,json
from datetime import datetime,timezone,timedelta
from importlib.metadata import version
from pathlib import Path
from uuid import uuid4
from core.simulation import ROOT
from ide_api import rail_sweeps as rail,native_models as models,rover_reference as rover
from ide_api.research.bundles import repo_base
from ide_api.research.artifacts import ArtifactStore,finite_json
FORMAT='EMBODY_MULTI_MODEL_CURRENT_SOURCE_QUALIFICATION_V1'

def sources():
    names=set(rover.source_manifest())|{'tools/model_qualification.py','ide_api/toolkit.py','ide_api/robot_import.py',
         'ide_api/product_alpha.py','frontend/package.json','frontend/package-lock.json',
         'frontend/src/ProductAlpha.tsx','frontend/src/ModelWorkspace.tsx','frontend/src/styles/productAlpha.css'}
    # Rendering/controller inspection is bound as well; only source/data, never private runtime.
    names|={str(p.relative_to(ROOT)) for p in (ROOT/'frontend/src').rglob('*') if p.suffix in ('.ts','.tsx','.css')}
    return {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in sorted(names)}

def cases(model_id):
    if model_id==models.RAIL:return [{'mass_kg':4.,'speed_mps':1.2,'force_n':2.,'gap_m':g} for g in (1.44,1.49)]
    if model_id==models.ROVER:return [{**rover.DEFAULTS,'angle_deg':0.},{**rover.DEFAULTS,'angle_deg':10.,'chassis_mass_kg':.6,'torque_nm':.003}]
    raise ValueError('Unknown qualification model')

def prepare(model_id):
    module=models.for_model(model_id);request=module.validate({'experiment_id':module.EXPERIMENT,'controller_id':module.CONTROLLER,'source_sha256':module.source_identity(),'cases':cases(model_id),'criteria':module.DEFAULT_CRITERIA,'nonce':uuid4().hex,'confirmation':module.CONFIRMATION})
    now=datetime.now(timezone.utc);n=len(request['cases']);primary=module.POLICY['primary_steps_per_case'];fresh=module.POLICY['replay_steps_per_case']
    definition={'format':FORMAT,'status':'PROPOSED_NOT_AUTHORIZED_NOT_EXECUTED','model_id':model_id,'created_utc':now.isoformat(),'expires_utc':(now+timedelta(hours=48)).isoformat(),'base_commit':repo_base(),'source_manifest':sources(),'installed_versions':{p:version(p) for p in ('mujoco','numpy','jsonschema')},'descriptor':models.descriptor(model_id),'request':request,
      'limits':{'new_physical_cases':n,'native_rollouts':2*n,'primary_steps_per_case':primary,'fresh_replay_steps_per_case':fresh,'maximum_integration_steps':n*(primary+fresh),'exclusive_window_seconds':600,'native_cooperative_deadline_seconds':module.POLICY['wall_seconds'],'retries':0,'paid_calls':0,'api_usd':0,'vm_launches':0,'installs':0,'applications':0},
      'expected_artifacts':['Exact immutable request/nonce and actual approval message reference','Raw primary/fresh samples, compiled model XML and result/trajectory hashes','Original acceptance dictionary; retain physical FAIL or execution error honestly','Measured force/contact/pose data and independently recomputed saved measurements','Write-once raw result plus strictly verified portable export if valid; no origin attestation inferred from import'],
      'procedure':['Require fresh explicit user approval naming this exact canonical digest. Neither UI preparation, a CLI hash nor this manifest grants consent.','Recheck exact bytes, canonical/source/version/base/descriptor, expiry, unused nonce, retained-job capacity and original preservation; record approval separately.','Trusted local operator acquires existing global Server.job lock and invokes the same existing RailSweeps.start with the exact request once. No other service, arbitrary controller or source is permitted.','Serially execute only these cases plus each required fresh replay. Preserve cancellation, deadline, every failure, raw result and unknown/incomplete outcome. No retry.','Afterward use existing rail saved readback/package contracts or the versioned rover forward/contact/force/readback and package validator. Report actual counts, not expected outcomes.','Stop after this model-specific scope. A different model consent is a separate approval; do not chain, run refinement, apply a proposal or refresh an expired scope.'],
      'physical_outcomes':'UNKNOWN_NOT_PREDICTED_AS_MEASURED; nominal/challenging describe selection, not a predeclared PASS/FAIL',
      'prohibitions':['No paid model, VM, downloads/installations, controller/source changes during execution, arbitrary XML/source, engineering application, retry/fallback, historical mutation, next adaptive refinement or automatic publication.']}
    return {'definition':definition,'sha256':rail.digest(definition),'authorization':'NOT_GRANTED'}

def check(value):
    rail.exact(value,['definition','sha256','authorization']);d=value['definition']
    if value['sha256']!=rail.digest(d) or value['authorization']!='NOT_GRANTED' or d['format']!=FORMAT:raise ValueError('Exact proposed canonical identity required')
    if datetime.now(timezone.utc)>=datetime.fromisoformat(d['expires_utc']):raise ValueError('Expired freeze; fresh preparation/review/approval required')
    if d['base_commit']!=repo_base() or d['source_manifest']!=sources():raise ValueError('Frozen source/base identity differs')
    if d['installed_versions']!={p:version(p) for p in ('mujoco','numpy','jsonschema')}:raise ValueError('Installed dependency identity differs')
    if d['descriptor']!=json.loads(rail.canonical(models.descriptor(d['model_id']))):raise ValueError('Model/controller/criteria descriptor differs')
    module=models.for_model(d['model_id']);r=module.validate(d['request'])
    if r['cases']!=cases(d['model_id']) or r['criteria']!=module.DEFAULT_CRITERIA:raise ValueError('Exact physical qualification scope differs')
    expected={'new_physical_cases':2,'native_rollouts':4,'primary_steps_per_case':module.POLICY['primary_steps_per_case'],'fresh_replay_steps_per_case':module.POLICY['replay_steps_per_case'],'maximum_integration_steps':2*(module.POLICY['primary_steps_per_case']+module.POLICY['replay_steps_per_case']),'exclusive_window_seconds':600,'native_cooperative_deadline_seconds':module.POLICY['wall_seconds'],'retries':0,'paid_calls':0,'api_usd':0,'vm_launches':0,'installs':0,'applications':0}
    if d['limits']!=expected:raise ValueError('Frozen execution limits differ')
    folder=ROOT/'.runtime/rail_sweeps'
    if (folder/r['nonce']).exists():raise ValueError('Nonce already consumed or uncertain; no reuse')
    if folder.exists() and len(list(folder.iterdir()))>=rail.POLICY['retained_jobs']:raise ValueError('Shared retained-job quota reached; no pruning')
    return {'status':'IDENTITIES_VALID_NO_EXECUTION_AUTHORITY','approval':'MISSING_FRESH_EXPLICIT_USER_APPROVAL','source_count':len(d['source_manifest']),'limits':expected,'nonce_unused':True,'new_native_steps':0,'execution_authorized':False}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','check']);parser.add_argument('--model',choices=[models.RAIL,models.ROVER]);parser.add_argument('--manifest');args=parser.parse_args()
    if args.action=='prepare':
        if not args.model:parser.error('--model required')
        value=prepare(args.model);name='model_qualifications/'+value['definition']['request']['nonce']+'/consent.json';ArtifactStore(ROOT/'.runtime/evidence_store').write_once(name,rail.canonical(value),180000)
        result={'relative_path':'.runtime/evidence_store/'+name,'canonical_sha256':value['sha256'],'manifest_byte_sha256':hashlib.sha256(rail.canonical(value)).hexdigest(),'authorization':'NOT_GRANTED','new_native_steps':0}
    else:
        if not args.manifest:parser.error('--manifest required')
        path=(ROOT/args.manifest).absolute()
        if not path.is_relative_to(ROOT/'.runtime/evidence_store/model_qualifications') or path.is_symlink():raise ValueError('Use prepared local manifest')
        raw=path.read_bytes();result=check(finite_json(raw,180000));result['manifest_byte_sha256']=hashlib.sha256(raw).hexdigest()
    print(json.dumps(result,indent=2))
