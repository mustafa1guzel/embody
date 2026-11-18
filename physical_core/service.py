"""ONE project/source/tool/review/job workflow; dispatch only for native adapters."""
import copy,difflib,hashlib,os,shutil,threading
from uuid import uuid4
from jsonschema import validate as schema_validate
from engineering.store import Store
from ide_api import rail_sweeps as rail
from physical_core import adapters,contracts,language,engine
APPLY='APPLY REVIEWED PHYSICAL PROJECT SOURCE'
RUN='RUN THIS EXACT PHYSICAL PROJECT AND FRESH REPLAY'
TOOLS={
 'inspect_system':{'type':'object','properties':{},'required':[],'additionalProperties':False},
 'validate_source':{'type':'object','properties':{'source':{'type':'string','maxLength':8192},'definition':{'type':'object'}},'required':['source','definition'],'additionalProperties':False},
 'propose_change':{'type':'object','properties':{'source':{'type':'string','maxLength':8192},'definition':{'type':'object'},'intent':{'type':'string','minLength':1,'maxLength':1000}},'required':['source','definition','intent'],'additionalProperties':False},
 'inspect_result':{'type':'object','properties':{'nonce':{'type':'string','pattern':'^[a-f0-9]{32}$'}},'required':['nonce'],'additionalProperties':False}}

class PhysicalEngineering:
 def __init__(self,workbench):self.w=workbench;self.controls={};self.started=set();self.lock=threading.RLock()
 def path(self,*names):return self.w._path('physical_core',*names)
 def _id(self,key,n=32):
  from ide_api.workbench import exact_id
  return exact_id(key,n)
 def examples(self):
  from core.simulation import ROOT
  return rail.read_json(ROOT/'examples/physical-engineering','controller_examples.json')['examples']
 def catalog(self):
  projects=[];root=self.path('projects')
  if root.exists():
   for p in root.iterdir():
    self._id(p.name);v=self.read(p.name);projects.append({'id':p.name,'title':v['definition']['title'],'family':v['definition']['family'],'revision':v['revision'],'stale':v['stale']})
  return {'format':'PHYSICAL_ENGINEERING_CATALOG_V1','families':[{'id':k,'definition':contracts.template(k),'initial_source':self.examples()[k]['initial_source'],'contract':contracts.contract(contracts.template(k))} for k,a in adapters.REGISTRY.items()],'projects':projects,'tool_schemas':self.schemas(),'apply_confirmation':APPLY,'run_confirmation':RUN,'provider':'OFFLINE_EXPLICIT_SOURCE_PLAN_NOT_GPT'}
 def schemas(self):return [{'type':'function','name':k,'description':'Shared project-bound '+k+'. No implicit source application, physics execution, files or provider access.','strict':True,'parameters':v} for k,v in TOOLS.items()]
 def _save(self,key,revision,d,compiled,origin):
  folder=self.path('projects',key);folder.mkdir(parents=True,exist_ok=True);s={'format':'GENERAL_PROJECT_SOURCE_SNAPSHOT_V1','project_id':key,'revision':revision,'definition':d,'definition_sha256':rail.digest(d),'compiled':compiled,'implementation_sha256':engine.identity(),'origin':origin};h=Store(folder/'snapshots').put(s);p=folder/(uuid4().hex+'.tmp');rail.write_once(p,{'sha256':h},1024);os.replace(p,folder/'head.json');return h
 def create(self,definition,source):
  d=contracts.validate(definition);compiled=language.compile_source(source,contracts.contract(d));engine.build(d)
  with self.w.transaction():
   root=self.path('projects');root.mkdir(parents=True,exist_ok=True)
   if len(list(root.iterdir()))>=16:raise ValueError('Physical project quota16; no automatic deletion')
   key=uuid4().hex;self._save(key,0,d,compiled,'HUMAN_CREATED_DEVELOPER_INITIAL_SOURCE')
  return self.read(key)
 def snapshot(self,key,h):
  folder=self.path('projects',self._id(key),'snapshots')
  if not folder.is_dir():raise ValueError('Unknown physical project')
  value=Store(folder).get(self._id(h,64));rail.exact(value,['format','project_id','revision','definition','definition_sha256','compiled','implementation_sha256','origin'])
  d=contracts.validate(value['definition'])
  if value['format']!='GENERAL_PROJECT_SOURCE_SNAPSHOT_V1' or value['project_id']!=key or type(value['revision']) is not int or not 0<=value['revision']<10000 or value['definition_sha256']!=rail.digest(d) or value['compiled']!=language.compile_source(value['compiled']['source'],contracts.contract(d)):raise ValueError('Project/source snapshot mismatch')
  return value
 def read(self,key):
  folder=self.path('projects',self._id(key));pointer=rail.read_json(folder,'head.json');rail.exact(pointer,['sha256']);v=self.snapshot(key,pointer['sha256']);return {**v,'sha256':pointer['sha256'],'stale':v['implementation_sha256']!=engine.identity(),'contract':contracts.contract(v['definition']),'runs':self.runs(key)}
 def bound(self,key,expected):
  p=self.read(key)
  if p['sha256']!=self._id(expected,64) or p['stale']:raise ValueError('Stale project/source/implementation; inspect the exact current head')
  return p
 def tool(self,key,expected,name,args):
  p=self.bound(key,expected)
  if name not in TOOLS:raise ValueError('Unsupported shared engineering tool; no apply, execute, shell or provider tool')
  schema_validate(args,TOOLS[name])
  if name=='inspect_system':v={'project':p,'tool_schemas':self.schemas(),'source_bound_head':expected,'canonical_requirement_ids':[r['id'] for r in p['definition']['requirements']]}
  elif name=='validate_source':
   d=contracts.validate(args['definition']);v=language.compile_source(args['source'],contracts.contract(d))
  elif name=='propose_change':v=self.propose(key,expected,args['definition'],args['source'],args['intent'])
  else:
   r=self.run(key,args['nonce']);v={k:r[k] for k in ('association','state','same_head','verified')}
   if r['verified']:v['evidence']=r['record']
  return {'name':name,'arguments':copy.deepcopy(args),'project_id':key,'expected_head':expected,'origin':'OFFLINE_EXPLICIT_SOURCE_PLAN_NOT_GPT','data':v}
 def propose(self,key,expected,definition,source,intent):
  if not isinstance(intent,str) or not 1<=len(intent)<=1000 or any(ord(c)<32 for c in intent):raise ValueError('Bounded explicit engineering intent required')
  with self.w.transaction():
   p=self.bound(key,expected);d=contracts.validate(definition)
   if d['family']!=p['definition']['family']:raise ValueError('Changing robot family requires a new project')
   compiled=language.compile_source(source,contracts.contract(d));engine.build(d)
   if compiled==p['compiled'] and d==p['definition']:raise ValueError('No change to review')
   proposal={'project_id':key,'before_head':expected,'before_revision':p['revision'],'before_source_sha256':p['compiled']['source_sha256'],'after_source_sha256':compiled['source_sha256'],'after_artifact_sha256':compiled['artifact_sha256'],'definition':d,'compiled':compiled,'implementation_sha256':engine.identity(),'intent':intent,'review_nonce':uuid4().hex,'source_diff':''.join(difflib.unified_diff(p['compiled']['source'].splitlines(True),source.splitlines(True),fromfile='saved/controller.physical',tofile='proposed/controller.physical')),'definition_diff':''.join(difflib.unified_diff((rail.canonical(p['definition']).decode()+'\n').splitlines(True),(rail.canonical(d).decode()+'\n').splitlines(True),fromfile='saved/system.json',tofile='proposed/system.json')),'status':'VALIDATED_UNAPPLIED_NOT_PHYSICALLY_VERIFIED'}
   store=Store(self.path('reviews'))
   if len(list(store.root.glob('*.json')))>=128:raise ValueError('Review quota128; no deletion')
   return {'review_id':store.put(proposal),**proposal}
 def decide(self,key,expected,review_id,decision,confirmation):
  if decision not in ('APPLY','REJECT') or confirmation!=APPLY:raise PermissionError('Separate exact human approval required')
  with self.w.transaction():
   p=self.bound(key,expected);r=Store(self.path('reviews')).get(self._id(review_id,64))
   if (r['project_id'],r['before_head'],r['before_revision'],r['implementation_sha256'])!=(key,expected,p['revision'],engine.identity()) or r['before_source_sha256']!=p['compiled']['source_sha256']:raise ValueError('Stale or foreign review')
   d=contracts.validate(r['definition']);compiled=language.compile_source(r['compiled']['source'],contracts.contract(d))
   if compiled!=r['compiled'] or d['family']!=p['definition']['family']:raise ValueError('Review source/contract mismatch')
   folder=self.path('decisions',review_id)
   if folder.exists():raise ValueError('Review already decided/interrupted; no retry')
   folder.mkdir(parents=True);rail.write_once(folder/'intent.json',{'decision':decision,'before':expected},4096)
   h=self._save(key,p['revision']+1,d,compiled,'EXPLICIT_HUMAN_REVIEW') if decision=='APPLY' else expected
   rail.write_once(folder/'done.json',{'decision':decision,'before_head':expected,'after_head':h,'before_source_sha256':p['compiled']['source_sha256'],'approved_source_sha256':compiled['source_sha256'] if decision=='APPLY' else p['compiled']['source_sha256']},4096)
  return self.read(key)
 def restore(self,key,expected,snapshot):
  p=self.snapshot(key,snapshot);return self.propose(key,expected,p['definition'],p['compiled']['source'],'Explicit restore through a new review')
 def history(self,key):
  folder=self.path('projects',self._id(key),'snapshots');return sorted([{'sha256':f.stem,'revision':v['revision'],'source_sha256':v['compiled']['source_sha256']} for f in folder.glob('*.json') for v in [self.snapshot(key,f.stem)]],key=lambda x:x['revision'])
 def agent_task(self,key,expected,task,source,definition):
  inspected=self.tool(key,expected,'inspect_system',{});validated=self.tool(key,expected,'validate_source',{'source':source,'definition':definition});proposed=self.tool(key,expected,'propose_change',{'source':source,'definition':definition,'intent':task})
  return {'origin':'OFFLINE_EXPLICIT_SOURCE_PLAN_NOT_GPT','task':task,'tool_calls':[inspected,validated,proposed],'proposal':proposed['data'],'model_requests':0,'note':'The proposed source is supplied explicitly, not inferred by a model or a robot-specific agent.'}
 def _state(self,folder,value):
  p=folder/(uuid4().hex+'.tmp');rail.write_once(p,value,8192);os.replace(p,folder/'state.json')
 def state(self,nonce):
  s=rail.read_json(self.path('runs',self._id(nonce)),'state.json')
  with self.lock:
   if s['status'] in ('QUEUED','RUNNING') and nonce not in self.controls:return {**s,'status':'INTERRUPTED_NO_RETRY'}
  return s
 def runs(self,key):
  out=[];root=self.path('runs')
  if root.exists():
   for f in root.iterdir():
    self._id(f.name);r=rail.read_json(self.path('runs',f.name),'request.json')
    if r['project_id']==key:out.append({'nonce':f.name,'revision':r['revision'],**self.state(f.name)})
  return out
 def start(self,key,expected,nonce,confirmation,submit):
  if confirmation!=RUN:raise PermissionError('Explicit exact-source native authorization required')
  self._id(nonce)
  with self.w.transaction():
   p=self.bound(key,expected);r={'format':'GENERAL_NATIVE_REQUEST_V1','project_id':key,'head_sha256':expected,'revision':p['revision'],'definition':p['definition'],'compiled':p['compiled'],'implementation_sha256':engine.identity(),'nonce':nonce};root=self.path('runs');folder=self.path('runs',nonce)
   if folder.exists():
    if rail.read_json(folder,'request.json')!=r:raise ValueError('Consumed run identity belongs to another project/source')
    return {'nonce':nonce,'reused':True,'state':self.state(nonce)}
   if len(rail.canonical(r))>65536:raise ValueError('Exact native request exceeds64KiB; no admission')
   if shutil.disk_usage(self.w.root).free<32*1024*1024:raise ValueError('At least32MiB free storage required; no native run admitted')
   root.mkdir(parents=True,exist_ok=True)
   if len(list(root.iterdir()))>=16:raise ValueError('Native retention limit16')
   folder.mkdir();rail.write_once(folder/'request.json',r,65536);self._state(folder,{'status':'QUEUED','verdict':None})
   with self.lock:self.controls[nonce]=threading.Event()
   def perform():
    with self.lock:
     if nonce in self.started or nonce not in self.controls:raise ValueError('Execution already consumed')
     self.started.add(nonce);cancel=self.controls[nonce]
    try:
     if cancel.is_set():raise rail.Cancelled('Cancelled before stepping')
     self._state(folder,{'status':'RUNNING','verdict':None});result=engine.execute(r,folder,cancel);rail.write_once(folder/'result.json',result,8000000);self._state(folder,{'status':'COMPLETED','verdict':result['verdict'],'result_sha256':rail.digest(result)})
    except rail.Cancelled:self._state(folder,{'status':'CANCELLED','verdict':None})
    except Exception as e:self._state(folder,{'status':'EXECUTION_ERROR','verdict':None,'error':type(e).__name__+': '+str(e)[:180]})
    finally:
     with self.lock:self.controls.pop(nonce,None)
   try:job=submit(perform)
   except Exception:
    self._state(folder,{'status':'ADMISSION_FAILED_NO_RETRY','verdict':None})
    with self.lock:self.controls.pop(nonce,None)
    raise
   return {'nonce':nonce,'reused':False,'job':job}
 def cancel(self,key,nonce):
  r=rail.read_json(self.path('runs',self._id(nonce)),'request.json')
  if r['project_id']!=key:raise ValueError('Foreign run')
  with self.lock:
   if nonce in self.controls:self.controls[nonce].set()
  return self.state(nonce)
 def run(self,key,nonce):
  p=self.read(key);folder=self.path('runs',self._id(nonce));r=rail.read_json(folder,'request.json');rail.exact(r,['format','project_id','head_sha256','revision','definition','compiled','implementation_sha256','nonce'])
  if r['project_id']!=key or r['nonce']!=nonce or r['format']!='GENERAL_NATIVE_REQUEST_V1':raise ValueError('Foreign native request')
  old=self.snapshot(key,r['head_sha256'])
  if r['definition']!=old['definition'] or r['compiled']!=old['compiled'] or r['revision']!=old['revision'] or r['implementation_sha256']!=old['implementation_sha256']:raise ValueError('Immutable project/source/requirement binding mismatch')
  state=self.state(nonce);out={'association':r,'state':state,'same_head':p['sha256']==r['head_sha256'],'verified':False}
  if state['status']=='COMPLETED':
   v=rail.read_json(folder,'result.json')
   if v['request']!=r or state['result_sha256']!=rail.digest(v):raise ValueError('Result/request hash mismatch')
   record=engine.verify(v)
   if record['verdict']!=state['verdict']:raise ValueError('State verdict mismatch')
   out.update(verified=True,record=record)
  return out
 def view(self,key,nonce=None,index=0):
  if nonce:
   r=self.run(key,nonce)
   if not r['verified']:raise ValueError('No complete native evidence')
   v=rail.read_json(self.path('runs',nonce),'result.json')
   if type(index) is not int or not 0<=index<len(v['samples']):raise ValueError('Sample index outside saved trajectory')
   return {**engine.display(v,index),'time_s':v['samples'][index]['time_s'],'sample_count':len(v['samples']),'origin':'ACTUAL_SAVED_NATIVE_STATE','same_head':r['same_head']}
  p=self.read(key);a,m,data,xml,c=engine.build(p['definition']);return {**a.view(m,data,c,p['definition']),'origin':'COMPILED_INITIAL_STATE_NOT_SIMULATION'}
 def explain(self,key,nonce):
  r=self.run(key,nonce)
  if not r['verified']:raise ValueError('Measured evidence required')
  rec=r['record'];answer={'requirements':[{'id':k,'passed':v} for k,v in rec['checks'].items()],'observations':[{'id':k,'measured':v} for k,v in rec['metrics'].items()],'interpretation':'Recorded physical '+rec['verdict']+'. Failed project IDs: '+', '.join(k for k,v in rec['checks'].items() if not v)}
  validate_answer(answer,rec)
  return {'origin':'OFFLINE_DETERMINISTIC_NOT_GPT','same_head':r['same_head'],'answer':answer,'source_sha256':rec['source_sha256'],'artifact_sha256':rec['artifact_sha256']}
 def report(self,key,nonce):
  r=self.run(key,nonce)
  if not r['verified']:raise ValueError('Complete native/replay evidence required')
  body={'format':'GENERAL_PHYSICAL_REPORT_V1','association':r['association'],'same_head':r['same_head'],'record':r['record'],'provenance':'LOCAL_NATIVE_NOT_GPT_NOT_REMOTE_ATTESTATION','limits':{'primary_steps':adapters.adapter(r['association']['definition']['family']).steps,'fresh_steps':adapters.adapter(r['association']['definition']['family']).steps,'dt_s':.005},'limitations':['Registered rigid proxies only; not universal robotics or hardware safety.','Source and compiled artifact hashes are different mapped identities.']};return {**body,'report_sha256':rail.digest(body)}

def validate_answer(answer,record):
 rail.exact(answer,['requirements','observations','interpretation'])
 ids=[r['id'] for r in answer['requirements']];obs=[r['id'] for r in answer['observations']]
 if set(ids)!=set(record['checks']) or len(ids)!=len(set(ids)) or set(obs)!=set(record['metrics']) or len(obs)!=len(set(obs)):raise ValueError('Complete unique canonical project requirement references required')
 for r in answer['requirements']:
  rail.exact(r,['id','passed'])
  if type(r['passed']) is not bool or r['passed']!=record['checks'][r['id']]:raise ValueError('Requirement outcome mismatch')
 for r in answer['observations']:
  rail.exact(r,['id','measured'])
  if r['measured']!=record['metrics'][r['id']] or type(r['measured']) is bool:raise ValueError('Numerical evidence mismatch')
 expected='Recorded physical '+record['verdict']+'. Failed project IDs: '+', '.join(k for k,v in record['checks'].items() if not v)
 if answer['interpretation']!=expected:raise ValueError('Deterministic prose differs from measured verdict')
