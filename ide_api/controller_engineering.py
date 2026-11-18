"""Source-aware tools/review/jobs composed over the existing local Workbench.

No tool applies source or starts execution. No provider/client/credential access.
"""
import copy,difflib,hashlib,os,threading
from uuid import uuid4
from jsonschema import validate as validate_schema
from engineering.store import Store
from ide_api import rail_sweeps as rail,controller_language as language,controller_native as native
from ide_api.workbench import exact_id,pretty,validate_explanation,explanation_text
APPLY='APPLY REVIEWED RAIL DSL SOURCE'
RUN='RUN APPROVED RAIL DSL SOURCE AND FRESH REPLAY'
SCHEMAS={
 'inspect_controller':{'type':'object','properties':{},'required':[],'additionalProperties':False},
 'validate_controller':{'type':'object','properties':{'source':{'type':'string','minLength':1,'maxLength':4096}},'required':['source'],'additionalProperties':False},
 'propose_source':{'type':'object','properties':{'source':{'type':'string','minLength':1,'maxLength':4096},'intent':{'type':'string','minLength':1,'maxLength':1000}},'required':['source','intent'],'additionalProperties':False},
 'inspect_controller_result':{'type':'object','properties':{'nonce':{'type':'string','pattern':'^[a-f0-9]{32}$'}},'required':['nonce'],'additionalProperties':False}}

class ControllerEngineering:
 def __init__(self,workbench):self.w=workbench;self.controls={};self.started=set();self.lock=threading.RLock()
 def folder(self,key):return self.w._path('controllers',exact_id(key))
 def create(self,title):
  from ide_api.workbench import bounded_title
  from ide_api import robot_import
  d={'format':robot_import.FORMAT,'title':bounded_title(title),'model_id':'rail_carriage','controller_id':rail.CONTROLLER,'parameters':{'mass_kg':4.,'speed_mps':1.2,'force_n':4.,'gap_m':1.44},'requirements':copy.deepcopy(rail.DEFAULT_CRITERIA)}
  with self.w.transaction():
   p=self.w.toolkit.create(d);folder=self.folder(p['id']);folder.mkdir(parents=True)
   self._save(p['id'],0,language.INITIAL,'DEVELOPER_AUTHORED_INITIAL_SOURCE')
  return self.w.read(p['id'])
 def _save(self,key,revision,source,origin):
  compiled=language.compile_source(source);snapshot={'format':'RAIL_CONTROLLER_SOURCE_V1','project_id':key,'revision':revision,'compiled':compiled,'implementation_sha256':native.identity(),'origin':origin}
  folder=self.folder(key);h=Store(folder/'snapshots').put(snapshot);temp=folder/(uuid4().hex+'.tmp');rail.write_once(temp,{'sha256':h},1024);os.replace(temp,folder/'head.json');return h
 def read(self,key):
  folder=self.folder(key)
  if not folder.exists():return None
  pointer=rail.read_json(folder,'head.json');rail.exact(pointer,['sha256']);v=Store(self.w._path('controllers',key,'snapshots')).get(exact_id(pointer['sha256'],64))
  rail.exact(v,['format','project_id','revision','compiled','implementation_sha256','origin'])
  if v['format']!='RAIL_CONTROLLER_SOURCE_V1' or v['project_id']!=key or type(v['revision']) is not int or not 0<=v['revision']<10000 or language.compile_source(v['compiled']['source'])!=v['compiled']:raise ValueError('Invalid source snapshot identity/contract')
  return {**v,'head_sha256':pointer['sha256'],'stale':v['implementation_sha256']!=native.identity(),'runs':self.runs(key)}
 def bound(self,key,expected,head):
  p=self.w._project(key,expected);s=self.read(key)
  if not s or s['head_sha256']!=exact_id(head,64) or s['stale']:raise ValueError('Stale source/compiler head; inspect exact current source')
  return p,s
 def tools(self):
  return [{'type':'function','name':n,'description':{'inspect_controller':'Read actual current source, immutable IDs, physical context, fixed requirements and tool contracts.','validate_controller':'Compile bounded DSL to data; validation is not physical PASS.','propose_source':'Review-only source proposal. Never applies source or starts physics. Source/head arguments are bound by the surrounding exact context.','inspect_controller_result':'Read independently verified saved native evidence with exact canonical requirement IDs.'}[n],'parameters':s,'strict':True} for n,s in SCHEMAS.items()]
 def tool(self,key,expected,head,name,args,origin='USER_SUPPLIED_TOOL_ARGUMENTS_NOT_LIVE_AI'):
  p,s=self.bound(key,expected,head)
  if name not in SCHEMAS:raise ValueError('Unsupported controller tool; no apply, shell, provider or run tool')
  validate_schema(args,SCHEMAS[name])
  if name=='inspect_controller':v={'project_id':key,'project_sha256':expected,'controller_head_sha256':head,'source_revision':s['revision'],'source':s['compiled'],'parameters':p['declaration']['parameters'],'requirements':p['declaration']['requirements'],'input_units':language.UNITS,'tool_contracts':self.tools(),'effective_controller_id':language.VERSION,'numeric_declaration_controller_id_is_reference_only':rail.CONTROLLER}
  elif name=='validate_controller':v=language.compile_source(args['source'])
  elif name=='propose_source':v=self.propose(key,expected,head,args['source'],args['intent'],origin)
  else:v=self.run(key,args['nonce'])
  return {'name':name,'arguments':copy.deepcopy(args),'project_id':key,'project_sha256':expected,'controller_head_sha256':head,'origin':origin,'data':v}
 def propose(self,key,expected,head,source,intent,origin):
  from ide_api.engineering_agent_live import clean_task
  clean_task(intent)
  with self.w.transaction():
   p,s=self.bound(key,expected,head);after=language.compile_source(source)
   if after['source_sha256']==s['compiled']['source_sha256']:raise ValueError('No source change to review')
   value={'format':'RAIL_SOURCE_REVIEW_V1','project_id':key,'project_sha256':expected,'before_head':head,'before_revision':s['revision'],'before':s['compiled'],'after':after,'implementation_sha256':native.identity(),'origin':origin,'intent':intent,'review_nonce':uuid4().hex,'diff':''.join(difflib.unified_diff(s['compiled']['source'].splitlines(True),source.splitlines(True),fromfile='saved/controller.rail',tofile='proposed/controller.rail')),'applied':False,'verification':'STATICALLY_VALIDATED_NOT_PHYSICALLY_VERIFIED'}
   store=Store(self.w._path('source_reviews'))
   if len(list(store.root.glob('*.json')))>=128:raise ValueError('Source review limit reached; no automatic deletion')
   return {'review_id':store.put(value),**value}
 def decide(self,key,expected,head,review_id,decision,confirmation):
  if confirmation!=APPLY or decision not in ('APPLY','REJECT'):raise PermissionError('Separate human source decision confirmation required')
  with self.w.transaction():
   p,s=self.bound(key,expected,head);r=Store(self.w._path('source_reviews')).get(exact_id(review_id,64))
   if (r['project_id'],r['project_sha256'],r['before_head'],r['before_revision'],r['implementation_sha256'])!=(key,expected,head,s['revision'],native.identity()) or r['before']!=s['compiled'] or language.compile_source(r['after']['source'])!=r['after']:raise ValueError('Stale or cross-project source proposal')
   folder=self.w._path('source_decisions',review_id)
   if folder.exists():raise ValueError('Source review already decided/interrupted; never retry automatically')
   folder.mkdir(parents=True);rail.write_once(folder/'intent.json',{'decision':decision,'before_head':head},4096)
   after=self._save(key,s['revision']+1,r['after']['source'],r['origin']) if decision=='APPLY' else head
   rail.write_once(folder/'done.json',{'decision':decision,'before_head':head,'after_head':after,'before_source_sha256':r['before']['source_sha256'],'approved_source_sha256':r['after']['source_sha256'] if decision=='APPLY' else r['before']['source_sha256']},4096)
  return self.w.read(key)
 def restore(self,key,expected,head,snapshot):
  old=Store(self.w._path('controllers',exact_id(key),'snapshots')).get(exact_id(snapshot,64))
  if old['project_id']!=key:raise ValueError('Foreign source revision')
  return self.propose(key,expected,head,old['compiled']['source'],'Explicit restore as a new source review','HUMAN_RESTORE_NOT_AI')
 def history(self,key):
  folder=self.w._path('controllers',exact_id(key),'snapshots')
  return sorted([{'head_sha256':p.stem,'revision':v['revision'],'source_sha256':v['compiled']['source_sha256']} for p in folder.glob('*.json') for v in [Store(folder).get(p.stem)] if v['project_id']==key],key=lambda x:x['revision'])
 def runs(self,key):
  root=self.w._path('source_runs');out=[]
  if root.exists():
   for f in sorted(root.iterdir()):
    if not f.is_dir():continue
    rail.identifier(f.name);request=rail.read_json(self.w._path('source_runs',f.name),'request.json')
    if request['project_id']==key:
     state=self.state(f.name);out.append({'nonce':f.name,'revision':request['source_revision'],'status':state['status'],'verdict':state.get('verdict')})
  return out
 def state(self,nonce):
  folder=self.w._path('source_runs',exact_id(nonce));v=rail.read_json(folder,'state.json')
  with self.lock:
   if v['status'] in ('QUEUED','RUNNING') and nonce not in self.controls:return {**v,'status':'INTERRUPTED_NO_RETRY'}
  return v
 def _state(self,folder,v):
  path=folder/(uuid4().hex+'.tmp');rail.write_once(path,v,8192);os.replace(path,folder/'state.json')
 def start(self,key,expected,head,nonce,confirmation,submit):
  if confirmation!=RUN:raise PermissionError('Explicit approved-source native run confirmation required')
  exact_id(nonce)
  with self.w.transaction():
   p,s=self.bound(key,expected,head);request={'format':'APPROVED_DSL_NATIVE_REQUEST_V1','project_id':key,'project_sha256':expected,'controller_head_sha256':head,'source_revision':s['revision'],'controller':s['compiled'],'parameters':p['declaration']['parameters'],'requirements':p['declaration']['requirements'],'implementation_sha256':native.identity(),'nonce':nonce}
   root=self.w._path('source_runs');root.mkdir(parents=True,exist_ok=True);folder=self.w._path('source_runs',nonce)
   if folder.exists():
    if rail.read_json(folder,'request.json')!=request:raise ValueError('Consumed source run belongs to other source/project')
    return {'nonce':nonce,'reused':True,'state':self.state(nonce)}
   if len(list(root.iterdir()))>=16:raise ValueError('Source run retention limit reached; no automatic deletion')
   folder.mkdir();rail.write_once(folder/'request.json',request,16384);self._state(folder,{'status':'QUEUED','verdict':None})
   with self.lock:self.controls[nonce]=threading.Event()
   def perform():
    with self.lock:
     if nonce in self.started:raise ValueError('Source run dispatch already consumed')
     self.started.add(nonce);event=self.controls.get(nonce)
    if event is None:raise ValueError('Consumed source execution cannot resume')
    try:
     if event.is_set():raise rail.Cancelled('Cancelled before dispatch')
     self._state(folder,{'status':'RUNNING','verdict':None});result=native.execute(request,folder,event);rail.write_once(folder/'result.json',result,2500000);self._state(folder,{'status':'COMPLETED','verdict':result['verdict'],'result_sha256':rail.digest(result)})
    except rail.Cancelled:self._state(folder,{'status':'CANCELLED','verdict':None})
    except Exception as e:self._state(folder,{'status':'EXECUTION_ERROR','verdict':None,'error':type(e).__name__+': '+str(e)[:180]})
    finally:
     with self.lock:self.controls.pop(nonce,None)
   try:job=submit(perform)
   except Exception:
    self._state(folder,{'status':'ADMISSION_FAILED_NO_RETRY','verdict':None})
    with self.lock:self.controls.pop(nonce,None)
    raise
   return {'nonce':nonce,'job':job,'reused':False}
 def cancel(self,key,nonce):
  folder=self.w._path('source_runs',exact_id(nonce));r=rail.read_json(folder,'request.json')
  if r['project_id']!=key:raise ValueError('Foreign controller run')
  with self.lock:
   event=self.controls.get(nonce)
   if event:event.set()
  return self.state(nonce)
 def run(self,key,nonce):
  p=self.w._project(key);s=self.read(key);folder=self.w._path('source_runs',exact_id(nonce));r=rail.read_json(folder,'request.json')
  rail.exact(r,['format','project_id','project_sha256','controller_head_sha256','source_revision','controller','parameters','requirements','implementation_sha256','nonce'])
  if r['project_id']!=key or r['nonce']!=nonce or r['format']!='APPROVED_DSL_NATIVE_REQUEST_V1':raise ValueError('Run belongs to another source/project')
  physical=Store(self.w._path('projects',key,'snapshots')).get(exact_id(r['project_sha256'],64));saved=Store(self.w._path('controllers',key,'snapshots')).get(exact_id(r['controller_head_sha256'],64))
  if physical['declaration']['parameters']!=r['parameters'] or physical['declaration']['requirements']!=r['requirements'] or saved['project_id']!=key or saved['revision']!=r['source_revision'] or saved['compiled']!=r['controller']:raise ValueError('Run differs from immutable physical/source snapshots')
  state=self.state(nonce);out={'state':state,'association':r,'same_head':bool(s and r['controller_head_sha256']==s['head_sha256'] and r['project_sha256']==p['sha256']),'verified':False}
  if state['status']=='COMPLETED':
   v=rail.read_json(folder,'result.json')
   if state['result_sha256']!=rail.digest(v) or v['request']!=r:raise ValueError('Controller result/request hash mismatch')
   out.update(native.verify(v))
   if state['verdict']!=out['record']['verdict']:raise ValueError('Saved status differs from measured verdict')
  return out
 def report(self,key,nonce):
  r=self.run(key,nonce)
  if not r['verified']:raise ValueError('No complete verified source evidence to export')
  body={'format':'SOURCE_BOUND_RAIL_REPORT_V1','origin':'LOCAL_DSL_NATIVE_NOT_GPT','association':r['association'],'same_head':r['same_head'],'result':r['record'],'samples_sha256':rail.digest(r['samples']),'limitations':['Bounded DSL, not arbitrary Python.','Finite rigid proxy, not hardware safety.','Source, artifact, and trusted interpreter hashes identify different layers.']}
  return {**body,'report_sha256':rail.digest(body)}
 def offline(self,key,expected,head,task,nonce):
  from ide_api.engineering_agent_live import clean_task
  clean_task(task);inspected=self.tool(key,expected,head,'inspect_controller',{})
  result=self.run(key,nonce)
  if not result['verified'] or not result['same_head'] or result['record']['verdict']!='FAIL':raise ValueError('Current source-bound physical failure required')
  proposed=self.tool(key,expected,head,'propose_source',{'source':language.REPAIR,'intent':task},'OFFLINE DETERMINISTIC ENGINEERING ASSISTANT')
  return {'origin':'OFFLINE DETERMINISTIC ENGINEERING ASSISTANT','tool_calls':[inspected,proposed],'proposal':proposed['data'],'rationale':'Fixed supported stopping-distance algorithm, not natural-language model reasoning. Buffer0.10 m and low-speed braking are developer assumptions; only a new native run can verify them.','model_requests':0}
 def explain(self,key,nonce):
  r=self.run(key,nonce)
  if not r['verified']:raise ValueError('Complete independent native evidence required')
  ev=r['record'];answer={'observations':[{'result_id':ev['id'],'metric':k,'value':ev['metrics'][k]} for k in ('minimum_clearance_m','final_speed_mps','wall_contact_episodes','maximum_actuator_force_n','sampled_settling_time_s') if ev['metrics'][k] is not None],'requirements':[{'result_id':ev['id'],'check':k,'passed':v} for k,v in ev['checks'].items() if k.startswith('selected_')],'interpretation':explanation_text(ev),'hypotheses':[],'proposed_action':'Review source; explicit approval and a new native run are required.','verification_required':'Fresh source-bound native replay.','proposal_id':None}
  validate_explanation(answer,ev)
  return {'origin':'OFFLINE DETERMINISTIC ENGINEERING ASSISTANT','source_sha256':ev['source_sha256'],'artifact_sha256':ev['artifact_sha256'],'same_head':r['same_head'],'answer':answer,'canonical_checks':ev['checks']}
