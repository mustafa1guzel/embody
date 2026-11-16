"""Serial, finite offline release verification with durable immutable receipts."""
import argparse,json,os,re,subprocess,sys
from pathlib import Path
from uuid import uuid4
from datetime import datetime,timezone
from importlib.metadata import version
ROOT=Path(__file__).resolve().parents[1]
BACKEND=['tests/test_research_algorithms.py','tests/test_research_workflow.py','tests/test_research_http.py','tests/test_evidence_bundles.py','tests/test_research_benchmarks.py','tests/test_research_release.py','tests/test_experiment_designer.py','tests/test_rail_sweeps.py','tests/test_ide_api.py::test_host_origin_csrf_and_bounded_strict_json','tests/test_ide_api.py::test_bootstrap_does_not_load_credentials_run_physics_or_call_model','tests/test_ide_api.py::test_one_expensive_job_at_a_time']
FRONTEND=['ResearchWorkspace','ResearchEvidence','AIExperimentDesigner','TrustedSweepPanel','parameterSweep','ParameterSweepLab','physicsRegression','PhysicsRegressionExplorer','App','PhysicsPanel','UnifiedWorkspace','playback']

def parse_counts(raw,kind):
 counts={k:None for k in ('pass','fail','skip','deselected','errors')}
 text=re.sub(r'\x1b\[[0-9;]*m','',raw)
 if kind=='backend':
  for key,word in [('pass','passed'),('fail','failed'),('skip','skipped'),('deselected','deselected'),('errors','error')]:
   found=re.findall(r'(\d+) '+word+r's?\b',text);counts[key]=int(found[-1]) if found else 0
  if not re.search(r'\b\d+ passed\b',text):counts['pass']=None
 elif kind=='frontend':
  line=next((s for s in reversed(text.splitlines()) if re.search(r'^\s*Tests\s',s)),None)
  if line:
   for key,word in [('pass','passed'),('fail','failed'),('skip','skipped')]:
    m=re.search(r'(\d+) '+word,line);counts[key]=int(m[1]) if m else 0
   counts['deselected']=0;counts['errors']=0
 return counts

def run(args):
 sys.path.insert(0,str(ROOT))
 from ide_api.research.artifacts import ArtifactStore,RECEIPT,byte_hash,canonical,now
 from ide_api.research.bundles import source_manifest,repo_base
 from ide_api.research.contracts import data_digest
 root=ROOT/'.runtime/evidence_store';store=ArtifactStore(root);run_id=uuid4().hex;folder=ROOT/'.runtime/release_verification'/run_id;folder.mkdir(parents=True,exist_ok=False)
 source=source_manifest();identity=data_digest(source);base=repo_base();node=args.npm
 stages=[('backend',[sys.executable,'-B','-m','pytest','-ra','-p','no:cacheprovider','-p','tools.non_native_guards',*BACKEND],ROOT),('frontend',[node,'test','--','--configLoader','runner','--no-cache','--maxWorkers','1',*['src/'+n+'.test.'+('ts' if n in ('parameterSweep','physicsRegression','playback') else 'tsx') for n in FRONTEND]],ROOT/'frontend'),('typecheck',[node,'run','typecheck'],ROOT/'frontend'),('build',[node,'run','build','--','--configLoader','runner'],ROOT/'frontend'),('static',[sys.executable,'-B','-m','tools.release_checks',*(['--original-root',args.original_root,'--original-inventory',args.original_inventory] if args.original_root else [])],ROOT)]
 receipts=[];ok=True
 for stage,command,cwd in stages:
  started=now();env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','EMBODY_VERIFICATION_GUARD_OUTPUT':str(folder/'guards.json')}
  try:
   result=subprocess.run(command,cwd=cwd,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=900);raw=result.stdout;code=result.returncode;status='PASS' if code==0 else 'FAIL'
  except subprocess.TimeoutExpired as exc:raw=(exc.stdout or b'')+b'\nVerification timed out; no automatic retry.\n';code=124;status='TIMEOUT'
  completed=now()
  if len(raw)>2*1024*1024:raise ValueError('Release output exceeds retained log bound; not silently truncated')
  with (folder/(stage+'.txt')).open('xb') as f:f.write(raw)
  guards=json.loads((folder/'guards.json').read_text())['counters'] if (folder/'guards.json').exists() else None
  if stage=='backend' and (guards is None or any(guards.values())):status='FAIL'
  if source_manifest()!=source:status='FAIL';raw_notice='Source identity drifted during verification'
  receipt={'format':RECEIPT,'id':uuid4().hex,'command':command,'started_utc':started,'completed_utc':completed,'source_identity':identity,'base_commit':base,'versions':{'python':sys.version.split()[0],**{p:version(p) for p in ('mujoco','numpy','jsonschema','pytest')}},'exit_status':code,'counts':parse_counts(raw.decode(errors='replace'),stage),'stage':stage,'status':status,'guard_counters':guards,'limits':{'timeout_seconds':900,'retained_log_bytes':2*1024*1024,'execution':'serial fixed offline stage allowlist'},'limitations':['No native/provider/VM integration is allowed. Frontend/build execute installed local developer tools only.','Receipts contain exact operator paths; raw logs are private, not exported automatically.'],'log_sha256':byte_hash(raw)}
  store.receipt(receipt,raw)
  with (folder/(stage+'_receipt.json')).open('x') as f:json.dump(receipt,f,indent=2)
  receipts.append(receipt);print(stage+': '+status+' '+str(receipt['counts']),flush=True)
  if status!='PASS':ok=False;break
 final={'format':'EMBODY_SERIAL_RELEASE_VERIFICATION_V1','id':run_id,'status':'PASS' if ok and len(receipts)==len(stages) else 'FAIL_OR_INCOMPLETE','source_identity':identity,'source_manifest':source,'base_commit':base,'receipts':[r['id'] for r in receipts],'completed_stages':[r['stage'] for r in receipts],'skipped_stages':[stage for stage,_,_ in stages[len(receipts):]],'no_retries':True,'native_qualification':'NOT_RUN','paid_provider':'NOT_RUN'}
 with (folder/'verification.json').open('x') as f:json.dump(final,f,indent=2)
 print(str(folder),flush=True);return 0 if final['status']=='PASS' else 1

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--npm',default='npm');parser.add_argument('--original-root');parser.add_argument('--original-inventory');args=parser.parse_args()
 if bool(args.original_root)!=bool(args.original_inventory):parser.error('Provide both existing original root and historical inventory, or neither')
 raise SystemExit(run(args))
