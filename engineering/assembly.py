"""Atomic aggregate review over existing typed engineering preview/commit paths."""
from pathlib import Path
import os,time,json
from uuid import uuid4
from physics.contracts import digest
from robustness.contracts import file_hash,write_once
from workspace.data import bounded_read,decode_json
from .store import Store
from .project import identity,validate
from .assembly_plan import GOAL,PLAN,construct,PlanError,semantic_preflight
from .assembly_rover import structural,measured

ROOT=Path(__file__).resolve().parents[1]

def sources():
 paths=[*(ROOT/'shapebase').glob('*.py'),*(ROOT/'world').glob('*.py'),*(ROOT/'engineering').glob('*.py'),ROOT/'ide_api/engineering.py',ROOT/'requirements.txt']
 return {str(p.relative_to(ROOT)):file_hash(p) for p in sorted(paths)}


class AssemblyComposer:
 def __init__(self,service):
  self.service=service;self.root=service.root
  self.proposals=Store(self.root/'assembly_proposals');self.failures=Store(self.root/'assembly_failures');self.evidence=Store(self.root/'assembly_evidence')
 def session(self):
  p=self.root/'assembly_session.json'
  return decode_json(bounded_read(self.root,p.name)) if p.exists() else {'status':'NO_SESSION','review_only':False,'task':GOAL}
 def bootstrap(self):
  p=self.service.current();session=self.session();review=None
  pointer=self.root/'assembly_live_review.json'
  if pointer.exists():
   record=Store(self.root/'assembly_reviews').get(decode_json(bounded_read(self.root,pointer.name))['sha256'])
   q=self.load(record['proposal_id']) if record.get('proposal_id') else None
   if q:self.reconstruct(q)
   native=self.evidence.get(record['native_ref']) if record.get('native_ref') else None
   if native and (not q or native['proposal_id']!=record['proposal_id'] or native['proposed_project_sha256']!=q['resulting_project_sha256']):raise PlanError('Review/native identity mismatch')
   review={**record,'proposal':q,'native':native}
  from .assembly_semantics import contract
  return {'status':'ASSEMBLY_REVIEW_READY' if review else session.get('status','NO_SESSION'),'task':session.get('task',GOAL),'head':p,'head_sha256':identity(p),'schema':PLAN,'review':review,'semantic_contract':contract(p),'rejections':self.rejections(p),'application_allowed':not session.get('review_only',False),'limits':{'batches':12,'actions_per_batch':16,'total_actions':96,'parts':12},'ai_status':'PENDING_APPROVAL' if not review else review['origin']}
 def rejections(self,p):
  """Original content-addressed failures + explicitly labelled current analysis."""
  result=[]
  for path in sorted(self.failures.root.glob('*.json'))[:8]:
   old=self.failures.get(path.stem)
   if old.get('base_project_sha256')!=identity(p) or old.get('base_revision')!=p['revision']:continue
   try:analysis=semantic_preflight(p,old['plan'])
   except ValueError as exc:analysis={'status':'SCHEMA_OR_DAG_REJECTED','diagnostics':[],'error':str(exc)[:500]}
   from .assembly_validation import assess
   result.append({'failure_id':path.stem,'original':old,'current_analysis':analysis,'engineering_assessment':assess(self.service,p,old['plan']),'analysis_label':'Current read-only semantic analysis; historical error and model plan unchanged. This is not a repaired proposal.'})
  return result
 def assess(self,sha,revision,plan):
  from .assembly_validation import assess
  with self.service.transaction():return assess(self.service,self.service._precondition(sha,revision),plan)
 def propose(self,sha,revision,plan,*,origin='LOCAL_TYPED_PLAN_REVIEW',deadline=None,action_budget=96):
  with self.service.transaction():
   before=self.service._precondition(sha,revision)
   try:
    if before['revision']!=0 or before.get('creation') or before.get('shape_specs') or len(before['world']['objects'])!=1 or before['world']['objects'][0]['id']!='floor':raise PlanError('Assembly v0.1 requires an actual independent empty project')
    candidate,trace=construct(self.service,before,plan,deadline=deadline,action_budget=action_budget)
    if next(o for o in candidate['world']['objects'] if o['id']=='floor')!=before['world']['objects'][0]:raise PlanError('Original ground data changed')
    proof=structural(candidate,plan['roles'])
   except (ValueError,TypeError,KeyError) as exc:
    self.failures.put({'status':'REJECTED_NO_HEAD_CHANGE','base_project_sha256':sha,'base_revision':revision,'plan':plan,'error':{'type':type(exc).__name__,'message':str(exc)[:500],'diagnostics':getattr(exc,'diagnostics',[])},'origin':origin})
    raise
   record={'schema_version':1,'status':'PROPOSED_NOT_APPLIED','base_project_sha256':sha,'base_revision':revision,'resulting_project_sha256':identity(candidate),'resulting_revision':candidate['revision'],'proposed_project':candidate,'assembly_plan':plan,'construction':trace,'structural':proof,'source_sha256':sources(),'origin':origin,'action_authorship':'All plan action arguments supplied by plan author. Backend only schedules, validates and derives existing datums/proxies/revisions/native representations.','model_application_authority':False,'controller_installation':'NONE'}
   key=self.proposals.put(record);return {**record,'proposal_id':key}
 def load(self,key):return {**self.proposals.get(key),'proposal_id':key}
 def reconstruct(self,q,*,before=None):
  if q['source_sha256']!=sources():raise PlanError('Assembly source identity changed; prepare a fresh review')
  before=self.service.current() if before is None else before
  if identity(before)!=q['base_project_sha256'] or before['revision']!=q['base_revision']:raise PlanError('Stale assembly base revision/hash')
  after,trace=construct(self.service,before,q['assembly_plan'])
  proof=structural(after,q['assembly_plan']['roles'])
  if after!=q['proposed_project'] or identity(after)!=q['resulting_project_sha256'] or digest(trace)!=digest(q['construction']) or digest(proof)!=digest(q['structural']):raise PlanError('Assembly candidate or validation tampered')
  return after,proof
 def decide(self,sha,revision,key,decision,confirmation):
  with self.service.transaction():
   before=self.service._precondition(sha,revision);q=self.load(key)
   if q['base_project_sha256']!=sha or q['base_revision']!=revision:raise PlanError('Stale assembly proposal')
   if decision not in ('apply','reject') or confirmation!=('APPLY REVIEWED ASSEMBLY' if decision=='apply' else 'REJECT ASSEMBLY'):raise PlanError('Separate explicit assembly confirmation required')
   if decision=='apply' and self.session().get('review_only',False):raise PlanError('This experiment is review-only; application is not authorized')
   if decision=='apply':candidate,_=self.reconstruct(q,before=before)
   terminal=self.root/'assembly_decisions'/key;Store(terminal.parent)
   event={'decision':decision,'proposal_id':key,'base_project_sha256':sha,'resulting_project_sha256':q['resulting_project_sha256']}
   fd=os.open(terminal,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
   with os.fdopen(fd,'w') as f:json.dump(event,f)
   authorization=self.service.events.put(event)
   project=self.service._commit(candidate,authorization=authorization) if decision=='apply' else before
   return {'decision':'APPLIED_DATA_ONLY' if decision=='apply' else 'REJECTED','project':project,'model_requests':0,'simulation_run':False}
 def preview_native(self,sha,revision,key):
  with self.service.transaction():
   before=self.service._precondition(sha,revision);q=self.load(key);candidate,proof=self.reconstruct(q,before=before)
   reservations=self.root/'assembly_preview_reservations';Store(reservations)
   # Exactly one native preview per exact aggregate, consumed on any failure.
   if self.session().get('review_only',False):
    fd=os.open(self.root/'assembly_preview_session.reservation',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600);os.close(fd)
   fd=os.open(reservations/key,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600);os.close(fd)
  out=self.root/'assembly_native'/('run_'+uuid4().hex)
  from world.simulation import run
  try:result=run(candidate['world'],out) # Real primary + fresh replay, 200+200 steps.
  except Exception as exc:
   out.mkdir(parents=True,exist_ok=True)
   write_once(out/'failure.json',{'status':'NATIVE_EXECUTION_FAILED','proposal_id':key,'input_project_sha256':identity(candidate),'structural':proof,'error':{'type':type(exc).__name__,'message':str(exc)[:500]},'partial_telemetry_available':(out/'result.json').exists(),'reservation_consumed':True,'note':'No synthetic or replacement trajectory; original simulator may stop before saving states.'})
   raise
  physical=measured(result,proof)
  head_after=identity(self.service.current());unchanged=head_after==q['base_project_sha256']
  native={'status':physical['status'] if unchanged else 'STALE_DURING_PREVIEW','proposal_id':key,'proposed_project_sha256':identity(candidate),'structural':proof,'observations':physical,'result':result,'evidence_path':str(out),'head_sha256_after':head_after,'head_unchanged':unchanged,'application_status':'PROPOSED_NOT_APPLIED' if unchanged else 'HEAD_CHANGED_AFTER_PROPOSAL','new_model_requests':0,'vm_launches':0}
  write_once(out/'assembly_verification.json',native);ref=self.evidence.put(native)
  return {**native,'evidence_ref':ref}
 def publish(self,record):
  key=Store(self.root/'assembly_reviews').put(record);write_once(self.root/'assembly_live_review.json',{'sha256':key});return key
