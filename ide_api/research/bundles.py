"""Existing verified readers -> durable immutable copies; external imports never attest."""
import copy,hashlib,subprocess,shutil
from pathlib import Path
from core.simulation import ROOT
from ide_api import rail_sweeps as rail
from . import evidence,readback
from .artifacts import ArtifactStore,canonical,finite_json,LIMITS


def repo_base():
 desktop=Path('/Applications/GitHub Desktop.app/Contents/Resources/app/git/bin/git');git=str(desktop) if desktop.is_file() else shutil.which('git')
 if not git:raise ValueError('Working local Git required for provenance')
 value=subprocess.check_output([git,'rev-parse','HEAD'],cwd=ROOT,text=True,timeout=10).strip()
 if len(value)!=40:raise ValueError('Invalid repository base identity')
 return value

def source_manifest():
 paths=[*Path(__file__).parent.glob('*.py'),ROOT/'ide_api/rail_sweeps.py',ROOT/'ide_api/server.py',*[(ROOT/'tools'/n) for n in ('non_native_guards.py','release_checks.py','research_release_verify.py','research_native_preflight.py')],*(ROOT/'tests').glob('test_research*.py'),ROOT/'tests/test_evidence_bundles.py',ROOT/'frontend/src/ResearchWorkspace.tsx',ROOT/'frontend/src/ResearchEvidence.tsx',*(ROOT/'frontend/src/research').glob('*.ts*'),ROOT/'frontend/src/styles/research.css']
 return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}

class EvidenceBundles:
 def __init__(self,designer,root=None):self.designer=designer;self.store=ArtifactStore(root if root is not None else ROOT/'.runtime/evidence_store')
 def capture(self,kind,key,case_ids,project_id=None,campaign_id=None,research_manifest=None,report=None):
  if kind not in ('native','recorded'):raise ValueError('Capture only existing registered readers; no arbitrary source/file')
  summary=evidence.load(self.designer,kind,key);records=[r for r in summary['records'] if r['verified']]
  if not isinstance(case_ids,list) or not 1<=len(case_ids)<=9 or len(set(case_ids))!=len(case_ids) or any(c not in [r['id'] for r in records] for c in case_ids):raise ValueError('Select1–9verified case identities')
  chosen=[r for r in records if r['id'] in case_ids];artifacts=[];requirements=[];receipts=[]
  def put(name,value,provenance='ORIGINAL_MEASURED_EVIDENCE',raw=False):
   data=value if raw else canonical(value);artifacts.append((name,data,provenance,'application/json'));return name
  for record in chosen:
   cid=record['id'];prefix='cases/'+cid+'/';req={'case_id':cid,'kind':kind}
   if kind=='native':
    result=self.designer.rail.case(key,cid);readback.native_replay(result);receipt=readback.compare(record,result['samples']);req['primary']=put(prefix+'native.json',result);req['independent']=req['primary']
   else:
    from workspace.data import default_recording
    rec=default_recording();sel=record['recorded_selection'];t=rec.trajectory(sel['scenario'],sel['variant']);receipt=readback.compare(record,t['samples'])
    req['primary']=put(prefix+'telemetry.json',rec.read(t['telemetry_reference']),raw=True)
    ref=rec.reference(t['summary']['artifact_references']['independent_safety_trace.json']);req['independent']=put(prefix+'independent.json',rec.read(ref),raw=True)
    req['model']=put(prefix+'model.json',{'xml':t['xml'],'model_sha256':record['model_sha256']})
   requirements.append(req);receipts.append(receipt)
  complete_selection=len(chosen)==len(records)
  included=chosen+[r for r in summary['records'] if not r['verified']] if complete_selection else chosen
  counts={k:0 for k in summary['counts']};counts.update(planned=summary['counts']['planned'] if complete_selection else len(chosen),measured=len(chosen),physical_pass=sum(r['verdict']=='PASS' for r in chosen),physical_fail=sum(r['verdict']=='FAIL' for r in chosen))
  if complete_selection:
   for k in ('execution_error','cancelled','unexecuted','running'):counts[k]=summary['counts'][k]
  snapshot={**summary,'records':included,'counts':counts,'request':summary['request'] if complete_selection else None,'facts':[f for f in summary['facts'] if f['case_id'] in case_ids]}
  if summary['request'] is not None:put('original_request.json',summary['request'])
  # Original full request and unmeasured rows remain distinct; chosen snapshot is an explicit subset.
  put('summary.json',snapshot,'DERIVED_MEASUREMENT_SUMMARY');put('readback.json',{'format':'EMBODY_SAVED_READBACK_V1','cases':receipts,'native_steps':0},'DERIVED_MEASUREMENT_SUMMARY');put('requirements.json',requirements,'DERIVED_MEASUREMENT_SUMMARY')
  if research_manifest is not None:put('research_manifest.json',research_manifest,'USER_AUTHORED_RESEARCH')
  if report is not None:put('report.json',report,'DERIVED_MEASUREMENT_SUMMARY')
  metadata={'base_commit':repo_base(),'source_identity':chosen[0]['source_sha256'],'source_manifest':source_manifest(),'project_id':project_id,'campaign_id':campaign_id,'experiment_id':rail.EXPERIMENT if kind=='native' else 'pinned_rail_recording_v1','controller_ids':sorted({r['controller_id'] for r in chosen}),'evidence_kind':kind,'evidence_id':key,'limitations':['Capture copies actual reader-verified bytes; derived summaries never replace original trajectories.','Subset selection does not claim unselected or unexecuted cases measured.','Fresh replay shares MuJoCo; no new dynamics or universal safety proof.']}
  m=self.store.finalize(metadata,artifacts,trusted=True);return self.inspect(m['id'])
 def _readback(self,m,artifact=None):
  get=artifact or (lambda name:self.store.artifact(m,name))
  summary=finite_json(get('summary.json'));requirements=finite_json(get('requirements.json'));receipts=[]
  if len(requirements)!=len([r for r in summary['records'] if r['verified']]) or {r['id'] for r in summary['records'] if r['verified']}!={r['case_id'] for r in requirements}:raise ValueError('Case/trajectory requirements differ')
  for req in requirements:
   record=next(r for r in summary['records'] if r['id']==req['case_id'])
   if record.get('compatibility',{}).get('measurements')!=readback.DEFINITION:raise ValueError('Unsupported measurement definition')
   primary=finite_json(get(req['primary']))
   independent=finite_json(get(req['independent']))
   if req['kind']=='native':
    if rail.digest(primary)!=record['result_sha256'] or primary['source_sha256']!=record['source_sha256'] or hashlib.sha256(primary['model_xml'].encode()).hexdigest()!=record['model_sha256']:raise ValueError('Native source/model/result identities differ')
    readback.native_replay(primary);samples=primary['samples']
   elif req['kind']=='recorded':
    if hashlib.sha256(get(req['primary'])).hexdigest()!=record['trajectory_sha256']:raise ValueError('Pinned telemetry bytes differ')
    model=finite_json(get(req['model']))
    if hashlib.sha256(model['xml'].encode()).hexdigest()!=record['model_sha256'] or independent.get('verification_execution')!='PASS' or independent.get('effective_context_matches') is not True or primary['metadata']['controller']['source_sha256']!=record['compatibility']['controller']:raise ValueError('Required historical model/independent/controller verification missing')
    samples=primary['samples']
   else:raise ValueError('Unsupported measurement definition')
   receipts.append(readback.compare(record,samples))
  return summary,receipts
 def inspect(self,key,external=False):
  out=self.store.verify(key,self.designer.context()['catalog']['source_sha256'],external)
  if out.get('verified_local'):
   try:
    summary,checked=self._readback(out['manifest']);out.update(case_count=len(checked),case_ids=[r['id'] for r in summary['records'] if r['verified']],readback='PASS',readback_cases=checked,availability=out['availability'])
   except (ValueError,OSError,KeyError,TypeError):out.update(verified_local=False,availability='INTEGRITY_FAILED',readback='FAIL',errors=out['errors']+['Required trajectory/replay/source/measurement readback failed'])
  return out
 def summary(self,key):
  verified=self.inspect(key)
  if not verified.get('verified_local'):raise ValueError('Evidence bundle unavailable/unverified: '+verified['availability'])
  summary,_=self._readback(verified['manifest']);summary=copy.deepcopy(summary);summary.update(kind='bundle',id=key,bundle_availability=verified['availability'])
  for record in summary['records']:record['source_current']=record['source_sha256']==self.designer.context()['catalog']['source_sha256'] and record['provenance_kind']=='GENUINE_SAVED_NATIVE'
  summary['summary_sha256']=rail.digest({k:v for k,v in summary.items() if k!='summary_sha256'});return summary
 def catalog(self):
  local=[self.inspect(p.stem) for p in sorted(self.store.root.glob('bundles/*.json'))];external=[self.inspect(p.stem,True) for p in sorted(self.store.root.glob('external/*.json'))]
  return {'limits':LIMITS,'bundles':local,'external':external,'historical_missing':[{'id':'v04_private_three_case_demo','availability':'MISSING','provenance':'HISTORICAL_REPORTED_RESULT','reason':'Known private temporary raw directory is unavailable; prior screenshots/report are not raw measurement evidence.'}],'limitations':['Ignored local storage is persistent, not backup protection.','Imports verify bytes/math only; no local reader attestation or execution authority.']}
 def completeness(self,view):
  findings=view['findings'];rows=[]
  for ref in view['campaign']['evidence']:
   if ref['kind']=='bundle':status=self.inspect(ref['id']);rows.append({'reference':ref['id'],'availability':status['availability'],'cases':status.get('case_count',0),'errors':status['errors']})
   else:
    error=next((e for e in view['evidence_errors'] if e['reference']==ref['id']),None);s=next((s for s in view['summaries'] if s['id']==ref['id']),None)
    rows.append({'reference':ref['id'],'availability':'MISSING_OR_CHANGED' if error else 'VERIFIED_HISTORICAL' if s and ref['kind']=='recorded' else 'VERIFIED_AVAILABLE','cases':s['counts']['measured'] if s else 0,'errors':[error['error']] if error else []})
  return {'referenced_cases_currently_known':len(view['records']),'available_verified_cases':sum(r['verified'] for r in view['records']),'historical_or_source_incompatible_cases':sum(r['verified'] and not r['source_current'] for r in view['records']),'missing_or_changed_references':len(view['evidence_errors']),'unknown_missing_case_count':bool(view['evidence_errors']),'complete_findings':sum(f['status']=='VERIFIED' for f in findings),'incomplete_findings':sum(f['status']!='VERIFIED' for f in findings),'references':rows,'manifests_available':True,'meaning':'Missing-reference case cardinality is unknown, never silently treated as zero measured failures.'}


def package_readback(manifest,decoded):
 """Recompute saved arithmetic with no local trust promotion or integration."""
 holder=EvidenceBundles(None)
 _,receipts=holder._readback(manifest,lambda name:decoded[name])
 return {'status':'SAVED_ARITHMETIC_MATCH_EXTERNAL_UNVERIFIED','cases':len(receipts),'native_steps':0}
