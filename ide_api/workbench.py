"""Local rail workbench: compose existing typed projects, tools and native verifier.

No provider/credential/VM route; source documents are bounded JSON declarations,
never executable Python. All storage belongs to this separate local workspace.
"""
import copy,difflib,fcntl,hashlib,json,os,re,threading,time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4
from engineering.store import Store
from core.simulation import ROOT
from ide_api import rail_sweeps as rail,robot_import
from ide_api.toolkit import Toolkit
from ide_api.native_results import NativeResults,locator
from ide_api.product_alpha import ProductAlpha,scene,diagnosis
from ide_api.experiment_designer import ExperimentDesigner
from ide_api.engineering_agent import EngineeringAgent
from ide_api.engineering_agent_live import EngineeringAgentLive
from ide_api.research.artifacts import ArtifactStore
from ide_api.research.physical_math import predictions

SAVE='SAVE REVIEWED ROBOT CONFIGURATION'
RUN='RUN ONE LOCAL TRUSTED RAIL VERIFICATION'
CRITERIA=rail.DEFAULT_CRITERIA

def bounded_title(v):
 if not isinstance(v,str) or not 1<=len(v.strip())<=80 or any(ord(c)<32 for c in v):raise ValueError('Project title must contain 1–80 printable characters')
 return v.strip()

def exact_id(value,length=32):
 if not isinstance(value,str) or not re.fullmatch('[a-f0-9]{'+str(length)+'}',value):raise ValueError('Exact local identity required; paths are not accepted')
 return value

def pretty(d):return json.dumps(d,indent=2,allow_nan=False)+'\n'

def explanation_text(ev):
 return 'Recorded physical '+ev['verdict']+'. Replay PASS means the measured outcome reproduced. '+('Failed requirements: '+', '.join(k for k,v in ev['checks'].items() if not v) if ev['verdict']=='FAIL' else 'All saved finite-scope checks passed.')

def validate_explanation(answer,ev):
 EngineeringAgentLive.validate_answer(answer,{ev['id']:ev},[])
 ids=[r['check'] for r in answer['requirements']]
 required={k for k in ev['checks'] if k.startswith('selected_')}
 if not required or not required<=set(ids) or len(ids)!=len(set(ids)):raise ValueError('Complete unique canonical requirement references required')
 if answer['interpretation']!=explanation_text(ev):raise ValueError('Deterministic interpretation must match the saved physical verdict')

class Workbench:
 def __init__(self,root=None):
  self.root=Path(root).absolute() if root else ROOT/'.runtime/local_workbench'
  if any(p.is_symlink() for p in (self.root,*self.root.parents)):raise ValueError('Symlink workbench refused')
  self.guard=threading.RLock();self.rail=rail.RailSweeps(self.root/'native')
  native=NativeResults(self.rail,ArtifactStore(self.root/'evidence'))
  self.toolkit=Toolkit(self.root/'projects',native=native)
  designer=ExperimentDesigner(self.rail,self.root/'designer')
  product=ProductAlpha(designer,self.root/'research');product.native=native
  self.agent=EngineeringAgent(product,self.toolkit,self.root/'assistant')
 @property
 def controllers(self):
  with self.guard:
   if not hasattr(self,'_controllers'):
    from ide_api.controller_engineering import ControllerEngineering
    self._controllers=ControllerEngineering(self)
   return self._controllers
 def _safe(self):
  if any(p.is_symlink() for p in (self.root,*self.root.parents)):raise ValueError('Unsafe local workspace')
 def _path(self,*parts):
  p=self.root.joinpath(*parts)
  if any(x.is_symlink() for x in (p,*p.parents)):raise ValueError('Symlink workspace path refused')
  return p
 @contextmanager
 def transaction(self):
  with self.guard:
   self._safe();self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
   fd=os.open(self._path('admission.lock'),os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
   with os.fdopen(fd,'a+b') as stream:
    fcntl.flock(stream,fcntl.LOCK_EX);yield
 def _store(self,name):
  self._safe();return Store(self._path(name))
 def binding(self):
  return rail.digest({'native':rail.source_identity(),'files':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in ('ide_api/workbench.py','ide_api/toolkit.py','ide_api/robot_import.py','ide_api/engineering_agent.py')}})
 def _project(self,key,expected=None):
  self._safe();p=self.toolkit.read(exact_id(key))
  if p['declaration']['model_id']!='rail_carriage':raise ValueError('This local workflow supports the registered rail model only')
  if p['stale']:raise ValueError('Native source changed; preserve this project and create a new reviewed project')
  if expected is not None and p['sha256']!=exact_id(expected,64):raise ValueError('Stale project head; reload before reviewing or running')
  return p
 def catalog(self):
  return {'version':'1.0.0-rc1','projects':self.toolkit.listing(),'fields':rail.BOUNDS,'units':rail.UNITS,'requirements':CRITERIA,'scope':'LOCAL_TRUSTED_RAIL_ONLY','controller_id':rail.CONTROLLER,'provider':'OFFLINE_DETERMINISTIC_TOOLS_NO_MODEL_REQUESTS','limits':{'cases_per_run':1,'primary_steps':600,'fresh_replay_steps':600,'wall_seconds':60,'retained_runs':16},'save_confirmation':SAVE,'run_confirmation':RUN}
 def create(self,title):
  d={'format':robot_import.FORMAT,'title':bounded_title(title),'model_id':'rail_carriage','controller_id':rail.CONTROLLER,'parameters':{'mass_kg':4.,'speed_mps':1.2,'force_n':2.,'gap_m':1.44},'requirements':copy.deepcopy(CRITERIA)}
  with self.transaction():p=self.toolkit.create(d)
  return self.read(p['id'])
 def read(self,key):
  p=self._project(key);return {**p,'source':pretty(p['declaration']),'design':self.toolkit.design(p['declaration']),'runs':self.runs(key),'reviews':self.reviews(key),'controller':__import__('inspect').getsource(rail.reference_controller),'provider':'OFFLINE_DETERMINISTIC_NOT_AI','controller_source':self.controllers.read(key)}
 def _declaration(self,source,p):
  if not isinstance(source,str) or len(source.encode())>16384:raise ValueError('robot.json must be bounded UTF-8 JSON (maximum16KiB)')
  d=robot_import.validate(source)
  if d['model_id']!='rail_carriage' or d['controller_id']!=rail.CONTROLLER:raise ValueError('Registered rail model/controller cannot change')
  if d['requirements']!=CRITERIA:raise ValueError('Keep the original fixed verification requirements; no threshold relaxation')
  return d
 def review(self,key,expected,source,*,origin='HUMAN_AUTHORED_JSON',tool=None):
  with self.transaction():
   p=self._project(key,expected);d=self._declaration(source,p)
   if d==p['declaration']:raise ValueError('No configuration change to review')
   design=self.toolkit.design(d) # Existing compiler verifies actual typed geometry; no stepping.
   # Every explicit review needs its own decision identity, even after an identical discard.
   value={'format':'LOCAL_RAIL_REVIEW_V1','review_nonce':uuid4().hex,'project_id':key,'base_sha256':expected,'base_revision':p['revision'],'before':p['declaration'],'after':d,'source_binding':self.binding(),'origin':origin,'tool_proposal':tool,'diff':''.join(difflib.unified_diff(pretty(p['declaration']).splitlines(True),pretty(d).splitlines(True),fromfile='saved/robot.json',tofile='proposed/robot.json')),'verification':'COMPILED_NOT_PHYSICALLY_VERIFIED','applied':False}
   store=self._store('reviews')
   if len(list(store.root.glob('*.json')))>=128:raise ValueError('Review retention limit; no automatic deletion')
   review_id=store.put(value);return {'review_id':review_id,**value,'design':design}
 def _review(self,key):return self._store('reviews').get(exact_id(key,64))
 def _decision(self,key):
  folder=self.root/'decisions'/exact_id(key,64)
  if any(p.is_symlink() for p in (folder,*folder.parents)):raise ValueError('Symlink decision refused')
  if (folder/'done.json').exists():return rail.read_json(folder,'done.json')
  if (folder/'intent.json').exists():return {'decision':'INTERRUPTED_REVIEW_NO_RETRY'}
  return {'decision':'PROPOSED_NOT_APPLIED'}
 def decide(self,key,expected,review_id,decision,confirmation):
  if decision not in ('SAVE','DISCARD'):raise ValueError('Review decision must be SAVE or DISCARD')
  if confirmation!=SAVE:raise PermissionError('Separate explicit human configuration-save confirmation required')
  with self.transaction():
   p=self._project(key,expected);r=self._review(review_id)
   if r['project_id']!=key or r['base_sha256']!=expected or r['base_revision']!=p['revision'] or r['source_binding']!=self.binding():raise ValueError('Review is stale or belongs to different source/project')
   if self._decision(review_id)['decision']!='PROPOSED_NOT_APPLIED':raise ValueError('Review already decided/interrupted; do not repeat it')
   d=self._declaration(pretty(r['after']),p);self.toolkit.design(d)
   folder=self.root/'decisions'/review_id;folder.mkdir(parents=True)
   rail.write_once(folder/'intent.json',{'decision':decision,'base':expected},4096)
   saved=self.toolkit.save(key,expected,d) if decision=='SAVE' else p
   rail.write_once(folder/'done.json',{'decision':decision,'project_id':key,'sha256':saved['sha256'],'revision':saved['revision'],'decided_unix':time.time()},4096)
   return self.read(key)
 def restore(self,key,expected,review_id):
  r=self._review(review_id)
  if r['project_id']!=key or self._decision(review_id)['decision']!='SAVE':raise ValueError('Only a saved review of this project can be restored')
  return self.review(key,expected,pretty(r['before']))
 def reviews(self,key):
  exact_id(key);rows=[];root=self.root/'reviews'
  if not root.exists():return []
  for p in sorted(root.glob('*.json'))[:128]:
   r=self._review(p.stem)
   if r['project_id']==key:rows.append({'review_id':p.stem,'origin':r['origin'],'base_revision':r['base_revision'],**self._decision(p.stem)})
  return rows
 def _run_binding(self,key,nonce):
  self._path('native',exact_id(nonce));value=rail.read_json(self._path('runs'),nonce+'.json')
  rail.exact(value,['project_id','project_sha256','project_revision','parameters','requirements','native_source'])
  if value['project_id']!=exact_id(key):raise ValueError('Run belongs to another project')
  snapshot=Store(self._path('projects',key,'snapshots')).get(exact_id(value['project_sha256'],64))
  if type(value['project_revision']) is not int or value['project_revision']!=snapshot['revision'] or value['parameters']!=snapshot['declaration']['parameters'] or value['requirements']!=snapshot['declaration']['requirements'] or value['native_source']!=snapshot['source_sha256']:raise ValueError('Run association differs from the immutable project revision')
  native=self._path('native',nonce)
  if native.exists():
   request=rail.read_json(native,'request.json')
   if request['cases']!=[value['parameters']] or request['criteria']!=value['requirements'] or request['source_sha256']!=value['native_source']:raise ValueError('Run association differs from admitted native request')
  return value
 def start(self,key,expected,nonce,confirmation,submit):
  if self.controllers.read(key):raise ValueError('This project selects DSL source; use exact approved-source execution, not the numerical reference controller')
  if confirmation!=RUN:raise PermissionError('Explicit one-case local native verification confirmation required')
  exact_id(nonce)
  with self.transaction():
   p=self._project(key,expected);d=p['declaration'];root=self._path('runs');self._path('native',nonce);root.mkdir(parents=True,exist_ok=True)
   association={'project_id':key,'project_sha256':expected,'project_revision':p['revision'],'parameters':d['parameters'],'requirements':d['requirements'],'native_source':rail.source_identity()}
   path=root/(nonce+'.json')
   if path.exists():
    if not self._path('native',nonce).exists():raise ValueError('Interrupted run admission; preserve it and use a separately requested new run')
    if self._run_binding(key,nonce)!=association:raise ValueError('Consumed run identity belongs to another head')
   else:
    if len(list(root.glob('*.json')))>=16:raise ValueError('Local run retention limit; no automatic deletion')
    rail.write_once(path,association,8192)
   req={'experiment_id':rail.EXPERIMENT,'controller_id':rail.CONTROLLER,'source_sha256':association['native_source'],'cases':[d['parameters']],'criteria':d['requirements'],'nonce':nonce,'confirmation':rail.CONFIRMATION}
   return self.rail.start(req,submit)
 def runs(self,key):
  exact_id(key);out=[];root=self._path('runs')
  if not root.exists():return []
  for path in sorted(root.glob('*.json')):
   value=rail.read_json(root,path.name)
   if value['project_id']!=key:continue
   try:s=self.rail.read(path.stem);out.append({'nonce':path.stem,'revision':value['project_revision'],'status':s['status'],'verdict':s['cases'][0].get('verdict') if s['cases'] else None,'parameters':value['parameters']})
   except FileNotFoundError:out.append({'nonce':path.stem,'revision':value['project_revision'],'status':'INTERRUPTED_BEFORE_ADMISSION','verdict':None,'parameters':value['parameters']})
  return sorted(out,key=lambda r:(r['revision'],r['nonce']),reverse=True)
 def run(self,key,nonce):
  association=self._run_binding(key,nonce);s=self.rail.read(nonce);p=self._project(key)
  out={'state':s,'association':association,'same_head':p['sha256']==association['project_sha256'],'verified':False}
  if s['status']=='COMPLETED' and len(s['cases'])==1 and s['cases'][0]['execution_status']=='MEASURED':
   record,result=self.toolkit.native.load(locator(nonce,s['cases'][0]['case_id']))
   out.update(verified=True,record=record,scene=scene(result),samples=result['samples'],diagnosis=diagnosis(record))
  return out
 def cancel(self,key,nonce):self._run_binding(key,nonce);return self.rail.cancel(nonce)
 def context(self,key,nonce):
  r=self.run(key,nonce)
  if not r['verified']:raise ValueError('Complete native/replay/independent evidence required before explanation')
  record=r['record'];c={'kind':'native_study','project_id':None,'project_sha256':None,'model_id':'rail_carriage','parameters':record['parameters'],'requirements':record['criteria'],'result_id':record['id'],'selection':None}
  return r,c,self.agent.context(c)
 def explain(self,key,nonce,question):
  from ide_api.engineering_agent_live import clean_task
  clean_task(question);r,c,ctx=self.context(key,nonce);tool=self.agent.dispatch(c,ctx['context_sha256'],'inspect_result',{})
  ev=tool['data']['evidence']
  if ev!=self.agent._summary(r['record']) or tool['context_sha256']!=ctx['context_sha256']:raise ValueError('Tool output does not match independently read evidence/context')
  ids=[k for k in ev['checks'] if k.startswith('selected_')]
  answer={'observations':[{'result_id':ev['id'],'metric':k,'value':ev['metrics'][k]} for k in ('minimum_clearance_m','final_speed_mps','wall_contact_episodes','maximum_actuator_force_n','sampled_settling_time_s') if ev['metrics'].get(k) is not None], 'requirements':[{'result_id':ev['id'],'check':k,'passed':ev['checks'][k]} for k in ids], 'interpretation':explanation_text(ev),'hypotheses':[],'proposed_action':'Review a bounded numerical controller-authority change; no code or project is automatically applied.','verification_required':'A new native run and fresh replay are required after any configuration change.','proposal_id':None}
  validate_explanation(answer,ev)
  return {'origin':'DETERMINISTIC_TOOLS_NOT_GPT','question':question,'tool_calls':[{'name':'inspect_result','arguments':{},'output':tool}],'answer':answer,'diagnosis':tool['data']['analysis'],'same_head':r['same_head'],'model_requests':0,'cost_usd':'0'}
 def suggest(self,key,expected,nonce):
  p=self._project(key,expected);r,c,ctx=self.context(key,nonce)
  if not r['same_head']:raise ValueError('Saved evidence belongs to an earlier head; verify the current configuration first')
  if r['record']['verdict']!='FAIL':raise ValueError('No physical failure to investigate')
  params=p['declaration']['parameters'];candidate=None
  for step in range(21,61):
   force=step/10
   if force<=params['force_n']:continue
   pred=predictions({**params,'force_n':force},CRITERIA)
   if pred['discrete']['predicted_remaining_gap_m']>=CRITERIA['minimumClearance']+1e-6 and pred['discrete']['predicted_final_speed_mps']<CRITERIA['maximumFinalSpeed']:
    candidate=force;break
  if candidate is None:raise ValueError('No bounded authority-only prediction found; no repair or PASS fabricated')
  proposal=self.agent.dispatch(c,ctx['context_sha256'],'propose_parameters',{'changes':{'force_n':candidate},'rationale':'Deterministic bounded search of the existing ideal discrete braking prediction; candidate is not physically verified.'})
  after={**p['declaration'],'parameters':{**params,'force_n':candidate}}
  return self.review(key,expected,pretty(after),origin='DETERMINISTIC_ANALYTICAL_NOT_AI',tool=proposal)
 def report(self,key,nonce):
  r=self.run(key,nonce)
  if not r['verified']:raise ValueError('No complete measured evidence to export')
  rec=r['record'];body={'format':'EMBODY_LOCAL_VERIFICATION_REPORT_V1','origin':'LOCAL_TRUSTED_MUJOCO_NOT_AI','project':r['association'],'same_head':r['same_head'],'result':{k:rec[k] for k in ('id','controller_id','parameters','criteria','metrics','checks','verdict','source_sha256','trajectory_sha256','result_sha256','replay_status','independent_verification')},'limits':{'physical_cases':1,'primary_steps':600,'fresh_replay_steps':600},'limitations':['Finite rigid rail proxy only; no real-world safety certification.','JSON edits change registered numeric settings, not arbitrary controller source.','Source, replay and physical verdict are distinct.']};return {**body,'report_sha256':rail.digest(body)}
