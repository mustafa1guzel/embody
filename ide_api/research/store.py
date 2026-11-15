"""Bounded research state. Mutations cannot grant model/native authority."""
import copy,json,threading
from pathlib import Path
from datetime import datetime,timezone
from uuid import uuid4
from core.simulation import ROOT
from workspace.data import bounded_read,decode_json
from ide_api import rail_sweeps as rail
from . import contracts as c,sampling,analysis,evidence,registry,graph

def now():return datetime.now(timezone.utc).isoformat()
def uid():return uuid4().hex

class Research:
 def __init__(self,designer,root=None):self.designer=designer;self.root=Path(root) if root else ROOT/'.runtime/research';self.lock=threading.RLock()
 def context(self):
  ctx=self.designer.context();descriptors=registry.descriptors(ctx)
  code={p.name:__import__('hashlib').sha256(p.read_bytes()).hexdigest() for p in sorted(Path(__file__).parent.glob('*.py'))}
  return {'context_sha256':rail.digest({'designer':ctx['context_sha256'],'descriptors':descriptors,'research_sources':code}),'designer_context_sha256':ctx['context_sha256'],'catalog':ctx['catalog'],'descriptors':descriptors,'controllers':registry.controllers(ctx),'limits':c.LIMITS,'model':ctx['model'],'campaign_schema':c.CONFIG,'hypothesis_schema':c.HYPOTHESIS}
 def _folder(self,key):return self.root/rail.identifier(key)
 def _read(self,key):
  folder=self._folder(key);pointer=decode_json(bounded_read(folder,'head.json'));rail.exact(pointer,['sha256'])
  digest=pointer['sha256']
  if not isinstance(digest,str) or len(digest)!=64 or any(x not in '0123456789abcdef' for x in digest):raise ValueError('Research head identity invalid')
  p=decode_json(bounded_read(folder,digest+'.json'))
  if rail.digest(p)!=digest:raise ValueError('Research snapshot integrity differs')
  return c.validate_project(p,self.context()['catalog'])
 def _save(self,p):
  c.validate_project(p,self.context()['catalog']);folder=self._folder(p['id']);folder.mkdir(parents=True,exist_ok=True);h=rail.digest(p);path=folder/(h+'.json')
  if not path.exists():rail.write_once(path,p,c.LIMITS['bytes'])
  tmp=folder/(uid()+'.tmp');rail.write_once(tmp,{'sha256':h},1024);tmp.replace(folder/'head.json')
 def read(self,key):
  p=self._read(key);return {'project':p,'sha256':rail.digest(p),'stale':p['context_sha256']!=self.context()['context_sha256']}
 def listing(self):
  values=[]
  if self.root.exists():
   for p in sorted(self.root.iterdir()):
    if not p.is_dir() or len(p.name)!=32:continue
    try:v=self.read(p.name);values.append({'id':p.name,'title':v['project']['title'],'status':v['project']['status'],'stale':v['stale']})
    except (ValueError,OSError,KeyError):values.append({'id':p.name,'title':'Unreadable saved project','status':'CORRUPT','stale':True})
  return values
 def _event(self,p,kind,subject):
  if len(p['events'])>=c.LIMITS['events']:raise ValueError('Research timeline quota reached; export/archive before creating another project')
  p['events'].append({'id':uid(),'at':now(),'kind':kind,'subject':subject});p['updated_at']=now()
 def new(self,title,question,experiment_id):
  c.text(title);c.text(question)
  if experiment_id not in [d['id'] for d in self.context()['descriptors']]:raise ValueError('Unknown registered experiment descriptor')
  with self.lock:
   if len(self.listing())>=c.LIMITS['projects']:raise ValueError('Research project retention limit reached; no automatic deletion')
   p={'version':1,'id':uid(),'title':title,'question':question,'description':'Independent research project; no robot head mutation.','experiment_id':experiment_id,'context_sha256':self.context()['context_sha256'],'status':'ACTIVE','created_at':now(),'updated_at':now(),'hypotheses':[],'campaigns':[],'findings':[],'open_questions':[],'events':[]};self._event(p,'QUESTION_CREATED',p['id']);self._save(p)
   return self.read(p['id'])
 def _edit(self,key,expected,fn,*,allow_stale=False):
  with self.lock:
   value=self.read(key);p=value['project']
   if value['sha256']!=expected:raise ValueError('Research head changed; reload before editing')
   if p['status']=='ARCHIVED':raise ValueError('Archived project is read-only')
   if value['stale'] and not allow_stale:raise ValueError('Stale research context; preserve/export and create a new current project')
   fn(p);self._save(p);return self.read(key)
 def hypothesis(self,key,expected,content,hypothesis_id=None):
  c.validate(c.HYPOTHESIS,content)
  def edit(p):
   h=next((h for h in p['hypotheses'] if h['id']==hypothesis_id),None)
   if hypothesis_id and not h:raise ValueError('Unknown hypothesis')
   if h:h['content']=copy.deepcopy(content)
   else:
    if len(p['hypotheses'])>=16:raise ValueError('Hypothesis quota reached')
    h={'id':uid(),'content':copy.deepcopy(content),'status':'PROPOSED'};p['hypotheses'].append(h)
   self._event(p,'HYPOTHESIS_EDITED' if hypothesis_id else 'HYPOTHESIS_ADDED',h['id'])
  return self._edit(key,expected,edit)
 def note(self,key,expected,question):
  c.text(question)
  def edit(p):
   if len(p['open_questions'])>=16:raise ValueError('Open-question quota reached')
   p['open_questions'].append(question);self._event(p,'OPEN_QUESTION_ADDED',p['id'])
  return self._edit(key,expected,edit)
 def campaign(self,key,expected,config):
  c.config(config,self.context()['catalog'])
  def edit(p):
   if p['experiment_id']!=rail.EXPERIMENT:raise ValueError('Selected descriptor has no Research planning/native integration')
   if len(p['campaigns'])>=12:raise ValueError('Campaign quota reached')
   cid=uid();p['campaigns'].append({'id':cid,'config':copy.deepcopy(config),'context_sha256':self.context()['context_sha256'],'status':'DRAFT','batches':[],'evidence':[],'created_at':now()});self._event(p,'CAMPAIGN_CREATED',cid)
   for h in p['hypotheses']:
    if h['id'] in config['hypothesis_ids']:h['status']='UNDER_INVESTIGATION'
  return self._edit(key,expected,edit)
 def _campaign(self,p,key):
  value=next((v for v in p['campaigns'] if v['id']==key),None)
  if value is None:raise ValueError('Unknown campaign identity')
  return value
 def _active(self,v):
  if v['status'] in ('ARCHIVED','CANCELLED','COMPLETED'):raise ValueError('Campaign is closed; create an independent follow-up campaign')
 def propose(self,key,expected,campaign_id,method,selected=None):
  def edit(p):
   v=self._campaign(p,campaign_id);self._active(v);cfg=v['config'];previous=[x for b in v['batches'] for x in b['cases']];remaining=cfg['proposal_budget']-len({rail.digest(x) for x in previous})
   if method=='initial':result=sampling.initial(cfg)
   elif method=='adaptive':result=sampling.adaptive(cfg,self._records(v)[0],previous,remaining)
   elif method=='reproduce':
    records=self._records(v)[0];record=next((x for x in records if x['id']==selected and x['verified']),None)
    if record is None:raise ValueError('Verified saved case required for reproducibility proposal')
    c.point_allowed(record['parameters'],cfg)
    result={'points':[{'parameters':record['parameters'],'reason':'Explicit reproducibility proposal; old source retained, new source needs separate execution approval'}],'algorithm':'reproducibility_v1'}
   else:raise ValueError('Unknown proposal strategy')
   if not result['points']:raise ValueError(result['termination'])
   points=result['points']
   if selected is not None and method!='reproduce':
    if not isinstance(selected,list) or not selected or len(set(selected))!=len(selected) or any(type(i) is not int or not 0<=i<len(points) for i in selected):raise ValueError('Select valid unique proposed candidate indices')
    points=[points[i] for i in selected]
   if len({rail.digest(x['parameters']) for x in points}|{rail.digest(x) for x in previous})>cfg['proposal_budget']:raise ValueError('Campaign proposal budget exhausted')
   b={'cases':[c.point_allowed(x['parameters'],cfg) for x in points],'rationales':[x['reason'] for x in points],'strategy':result['algorithm'],'context_sha256':self.context()['context_sha256'],'parent_summary_sha256':rail.digest(self._records(v)[0]) if method!='initial' else None,'status':'AWAITING_REVIEW'};b['id']=c.batch_id(b)
   if any(x['id']==b['id'] for x in v['batches']):raise ValueError('Exact proposal already exists; no duplicate or implicit retry')
   v['batches'].append(b);v['status']='AWAITING_REVIEW';self._event(p,'PROPOSAL_VALIDATED',b['id'])
  return self._edit(key,expected,edit)
 def review(self,key,expected,campaign_id,batch_id,decision):
  def edit(p):
   v=self._campaign(p,campaign_id);self._active(v);b=next((b for b in v['batches'] if b['id']==batch_id),None)
   if not b or b['context_sha256']!=self.context()['context_sha256'] or decision not in ('accept','reject'):raise ValueError('Current exact batch and explicit review required')
   b['status']='REVIEWED' if decision=='accept' else 'REJECTED';v['status']='REVIEWED' if decision=='accept' else 'AWAITING_REVIEW';self._event(p,'PLAN_REVIEWED' if decision=='accept' else 'PLAN_REJECTED',batch_id)
  return self._edit(key,expected,edit)
 def transfer(self,key,campaign_id,batch_id):
  read=self.read(key);p=read['project'];v=self._campaign(p,campaign_id);self._active(v)
  b=next((b for b in v['batches'] if b['id']==batch_id),None)
  if read['stale'] or not b or b['status'] not in ('REVIEWED','TRANSFERRED') or b['context_sha256']!=self.context()['context_sha256']:raise ValueError('Exact current reviewed research batch required')
  return {'project_id':key,'campaign_id':campaign_id,'batch_id':batch_id,'cases':b['cases'],'rationales':b['rationales'],'criteria':v['config']['criteria'],'catalog':self.context()['catalog'],'context_sha256':b['context_sha256'],'execution_authorized':False,'origin':'DETERMINISTIC_RESEARCH_PROPOSAL_NOT_AI'}
 def mark_transfer(self,key,expected,campaign_id,batch_id):
  self.transfer(key,campaign_id,batch_id)
  def edit(p):
   v=self._campaign(p,campaign_id);next(b for b in v['batches'] if b['id']==batch_id)['status']='TRANSFERRED';v['status']='TRANSFERRED';self._event(p,'TRANSFERRED_NOT_EXECUTED',batch_id)
  self._edit(key,expected,edit);return self.transfer(key,campaign_id,batch_id)
 def _records(self,v):
  records={};summaries=[];errors=[]
  for ref in v['evidence']:
   try:
    s=evidence.load(self.designer,ref['kind'],ref['id'])
    if s['summary_sha256']!=ref['summary_sha256']:raise ValueError('Evidence summary changed; relink authentic current state')
    summaries.append(s)
    for r in s['records']:records[r['id']]=r
   except (ValueError,OSError,KeyError) as exc:errors.append({'reference':ref['id'],'status':'UNVERIFIED','error':type(exc).__name__})
  return list(records.values()),summaries,errors
 def link(self,key,expected,campaign_id,kind,evidence_id):
  s=evidence.load(self.designer,kind,evidence_id)
  def edit(p):
   v=self._campaign(p,campaign_id);self._active(v);batch=next((b for b in v['batches'] if b['status'] in ('REVIEWED','TRANSFERRED') and s['request'] and b['cases']==s['request']['cases'] and s['request']['experiment_id']==rail.EXPERIMENT and s['request']['controller_id']==rail.CONTROLLER and v['config']['criteria']==s['request']['criteria'] and s['request']['source_sha256']==self.context()['catalog']['source_sha256']),None)
   ref={'kind':kind,'id':evidence_id,'summary_sha256':s['summary_sha256'],'association':'MATCHING_REVIEWED_BATCH' if batch else 'EXTERNAL_REFERENCE','batch_id':batch['id'] if batch else None}
   v['evidence']=[r for r in v['evidence'] if (r['kind'],r['id'])!=(kind,evidence_id)]+[ref]
   if batch:v['status']='MEASURED' if s['counts']['measured']==len(batch['cases']) else 'PARTIAL'
   self._event(p,'EVIDENCE_VERIFIED_EXTERNAL' if not batch else 'MATCHING_SAVED_RESULTS_VERIFIED',s['summary_sha256'])
  return self._edit(key,expected,edit)
 def finding(self,key,expected,campaign_id,summary_sha256,fact_id):
  def edit(p):
   v=self._campaign(p,campaign_id);summaries=self._records(v)[1];s=next((s for s in summaries if s['summary_sha256']==summary_sha256),None)
   if not s or not any(f['id']==fact_id and f['value'] is not None for f in s['facts']):raise ValueError('Finding must cite an exact nonmissing verified numerical fact')
   if len(p['findings'])>=32:raise ValueError('Finding quota reached')
   f={'id':uid(),'campaign_id':campaign_id,'summary_sha256':summary_sha256,'fact_id':fact_id};p['findings'].append(f);self._event(p,'FINDING_CREATED',f['id'])
  return self._edit(key,expected,edit)
 def transition(self,key,expected,campaign_id,state):
  def edit(p):
   if campaign_id is None:
    if state!='ARCHIVED':raise ValueError('Only explicit archive is supported; no deletion')
    p['status']='ARCHIVED'
   else:
    v=self._campaign(p,campaign_id);self._active(v)
    if state=='COMPLETED':
     records,summaries,errors=self._records(v);matching=[r for r in v['evidence'] if r['association']=='MATCHING_REVIEWED_BATCH'];measured={r['id'] for r in records if r['verified']}
     covered={r['batch_id'] for r in matching};required={b['id'] for b in v['batches'] if b['status']!='REJECTED'}
     if errors or not required or not required<=covered or any(s['counts']['measured']!=s['counts']['planned'] for s in summaries if any(ref['summary_sha256']==s['summary_sha256'] for ref in matching)):raise ValueError('Completion needs all nonrejected batches independently measured; external evidence is insufficient')
    elif state not in ('ARCHIVED','CANCELLED'):raise ValueError('No editable measured/approval state')
    v['status']=state
   self._event(p,'ARCHIVED_OR_STOPPED' if state!='COMPLETED' else 'CAMPAIGN_COMPLETED',campaign_id or key)
  return self._edit(key,expected,edit,allow_stale=True)
 def view(self,key,campaign_id):
  read=self.read(key);p=read['project'];v=self._campaign(p,campaign_id);records,summaries,errors=self._records(v);findings=[]
  for f in p['findings']:
   if f['campaign_id']!=campaign_id:continue
   fact=next((x for s in summaries if s['summary_sha256']==f['summary_sha256'] for x in s['facts'] if x['id']==f['fact_id']),None)
   findings.append({**f,'status':'VERIFIED' if fact else 'UNVERIFIED','fact':fact})
  valid=[r for r in records if r['verified']];cfg=v['config'];previous=[p for b in v['batches'] for p in b['cases']];remaining=cfg['proposal_budget']-len({rail.digest(p) for p in previous})
  budgets={'proposed':len({rail.digest(x) for x in previous}),'reviewed':sum(len(b['cases']) for b in v['batches'] if b['status'] in ('REVIEWED','TRANSFERRED')),'submitted':sum(s['counts']['planned'] for s in summaries if any(ref['summary_sha256']==s['summary_sha256'] and ref['association']=='MATCHING_REVIEWED_BATCH' for ref in v['evidence'])),'measured_reference_cases':len(valid),'physical_fail':sum(r['verdict']=='FAIL' for r in valid),'execution_errors':sum(s['counts']['execution_error'] for s in summaries),'cancelled':sum(s['counts']['cancelled'] for s in summaries),'remaining_proposal_capacity':remaining,'authorized_execution_capacity':0,'meaning':'Proposal capacity is not native authorization. External reference measurements do not count as campaign execution.'}
  return {**read,'campaign':v,'budgets':budgets,'records':records,'summaries':[{k:v for k,v in s.items() if k not in ('records','request')} for s in summaries],'evidence_errors':errors,'boundary':analysis.boundaries(records,[a['parameter'] for a in cfg['axes']]),'sensitivity':{'analytical':analysis.analytical(cfg['fixed_parameters']),'measured':{r['id']:analysis.finite_differences(records,r['id']) for r in valid}},'benchmark':analysis.pareto(records),'adaptive':sampling.adaptive(cfg,[r for r in records if r['controller_id']==cfg['controller_id']],previous,remaining),'findings':findings,'graph':graph.build(p,v,summaries,findings),'completion_verified':v['status']=='COMPLETED' and not errors}
