"""Product composition over existing projects, verified readers and planning contracts.

No integration, approval, apply, provider, arbitrary path or source execution API.
"""
import copy,hashlib,inspect,math
from pathlib import Path
from uuid import uuid4
import mujoco
import numpy as np
from core.simulation import ROOT
from ide_api import rail_sweeps as rail
from ide_api.research.artifacts import ArtifactStore,finite_json
from ide_api.research.store import Research
from ide_api.research import sampling,physical_math,analysis
from workspace.data import bounded_read

PACKAGES={'initial-evidence.json':'5635ab67a4d45e472aa169514ed031c56490908eceba5616c786a6552246ce9b','refinement-evidence.json':'84066bc129de61f72e1261ca2d97312d939d4c74ea4933e4a284016678d098c0'}

def diagnosis(record):
 if not record or not record.get('verified'):return {'status':'INSUFFICIENT_EVIDENCE','issues':[],'reason':'Verified saved measurements are required; missing data is not physical FAIL.'}
 if record.get('status')!='MEASURED':return {'status':'EXECUTION_OR_DATA_UNAVAILABLE','issues':[],'reason':'No measured physical classification available.'}
 m,p,c=record['metrics'],record['parameters'],record['criteria'];issues=[]
 checks=[('clearance','Minimum clearance',m.get('minimum_clearance_m'),c['minimumClearance'],'m','minimum'),('speed','Final speed',m.get('final_speed_mps'),c['maximumFinalSpeed'],'m/s','strict_maximum'),('contacts','Wall contact episodes',m.get('wall_contact_episodes'),c['maximumContactEpisodes'],'episodes','maximum'),('force','Peak actuator force',m.get('maximum_actuator_force_n'),p['force_n'],'N','maximum'),('settling','Sampled settling',m.get('sampled_settling_time_s'),c['maximumSettlingTime'],'s','maximum')]
 for key,title,value,required,unit,kind in checks:
  valid=type(value) in (int,float) and math.isfinite(value)
  failed=valid and (value<required-1e-12 if kind=='minimum' else value>=required if kind=='strict_maximum' else value>required+1e-12)
  issues.append({'id':key,'title':title,'status':'UNAVAILABLE' if not valid else 'FAIL' if failed else 'PASS','measured':value if valid else None,'required':required,'unit':unit,'relation':'>=' if kind=='minimum' else '<' if kind=='strict_maximum' else '<=','deficit':None if not valid else max(0,required-value if kind=='minimum' else value-required),'observation':'Saved simulator samples, independently re-read.','interpretation':'The carriage stopped without contact but did not retain the required clearance.' if key=='clearance' and failed and m.get('wall_contact_samples')==0 and m.get('final_speed_mps')==0 else 'Compare this recorded quantity with its own frozen requirement.','hypothesis':'Ideal braking distance increases with mass and with speed squared, and decreases with force. The ideal model is not a measured root-cause proof.','action':'Prepare a supported numerical change; new verification remains required.'})
 return {'status':'MEASURED_REQUIREMENT_FAILURE' if any(x['status']=='FAIL' for x in issues) else 'INSUFFICIENT_EVIDENCE' if any(x['status']=='UNAVAILABLE' for x in issues) else 'REQUIREMENTS_PASS','issues':issues,'authorship':'DETERMINISTIC_PHYSICAL_ANALYSIS_NOT_LIVE_AI'}

def scene(result):
 """Compiled saved geometry at recorded state; mj_forward is kinematics, not stepping."""
 model=mujoco.MjModel.from_xml_string(result['model_xml']);data=mujoco.MjData(model);first=result['samples'][0]
 if model.nq!=1 or model.njnt!=1 or model.jnt_type[0]!=mujoco.mjtJoint.mjJNT_SLIDE:raise ValueError('Unsupported recorded kinematics')
 data.qpos[0]=first['position'];data.qvel[0]=first['velocity'];mujoco.mj_forward(model,data)
 geoms=[]
 for i in range(model.ngeom):
  body=int(model.geom_bodyid[i]);ancestor=body;moving=False
  while ancestor:
   moving=moving or model.body_jntnum[ancestor]>0;ancestor=int(model.body_parentid[ancestor])
  quat=np.empty(4);mujoco.mju_mat2Quat(quat,data.geom_xmat[i])
  geoms.append({'id':f'geom:{i}','name':mujoco.mj_id2name(model,mujoco.mjtObj.mjOBJ_GEOM,i),'kind':'geom','body':body,'type':int(model.geom_type[i]),'size':model.geom_size[i].tolist(),'position':data.geom_xpos[i].tolist(),'quaternion_wxyz':quat.tolist(),'rgba':model.geom_rgba[i].tolist(),'moving':bool(moving)})
 return {'bodies':[{'id':f'body:{i}','name':mujoco.mj_id2name(model,mujoco.mjtObj.mjOBJ_BODY,i),'kind':'body','mass_kg':float(model.body_mass[i]),'parent':int(model.body_parentid[i])} for i in range(model.nbody)],'geoms':geoms,'joints':[{'id':'joint:0','name':'Carriage slide','kind':'joint','axis':model.jnt_axis[0].tolist()}],'actuators':[{'id':'actuator:0','name':rail.CONTROLLER,'kind':'actuator','force_range_n':model.actuator_forcerange[0].tolist()}],'slide_axis_world':data.xaxis[0].tolist(),'reference_position':first['position'],'transform_check':'Saved XML compiled; recorded initial qpos forwarded, no native integration.'}

class ProductAlpha:
 def __init__(self,designer,root=None,evidence_root=None):
  self.research=Research(designer,Path(root) if root else ROOT/'.runtime/product_alpha/projects');self.evidence_root=Path(evidence_root) if evidence_root else ROOT/'examples/adaptive-rail-study';self._cached=None
 def records(self):
  contents=[bounded_read(self.evidence_root,n) for n in PACKAGES]
  if any(hashlib.sha256(raw).hexdigest()!=h for raw,h in zip(contents,PACKAGES.values())):raise ValueError('Pinned public demonstration bytes changed; evidence withheld')
  if self._cached is None:
   records=[];results={}
   for raw in contents:
    checked=ArtifactStore.verify_package(finite_json(raw,18*1024*1024));summary=finite_json(checked['decoded']['summary.json']);req=finite_json(checked['decoded']['original_request.json'])
    for r in summary['records']:
     native=finite_json(checked['decoded']['cases/'+r['id']+'/native.json']);r={**r,'criteria':req['criteria'],'replay_status':native['replay']['status']};records.append(r);results[r['id']]=native
   self._cached=(records,results)
  records,results=self._cached;current=rail.source_identity()
  return [{**r,'source_current':r['source_sha256']==current} for r in records],results
 def catalog(self):
  records,_=self.records();current=rail.catalog()
  return {'version':'0.7 Product Alpha','catalog':current,'examples':[{'id':'adaptive-rail','title':'Rail braking · measured adaptive study','model':'Single-axis carriage','capability':'Saved native playback, physical debugger and bounded numerical planning','native_execution':'PREPARATION_ONLY_SEPARATE_APPROVAL_REQUIRED','origin':'GENUINE_SAVED_NATIVE_PUBLISHER_ORIGIN_EXTERNAL_INTEGRITY_VERIFIED'}],'records':[{k:v for k,v in r.items() if k not in ('samples',)} for r in records],'projects':self.listing(),'controller':{'id':rail.CONTROLLER,'file':'ide_api/rail_sweeps.py','content':inspect.getsource(rail.reference_controller),'sha256':hashlib.sha256(inspect.getsource(rail.reference_controller).encode()).hexdigest(),'editable':False,'execution':'REGISTERED_TRUSTED_REFERENCE_ONLY'},'evidence_status':'PUBLISHER_RECORDED_NATIVE; external integrity/readback verified, no imported local attestation','adaptive_history':self.history(),'bounds':rail.BOUNDS,'provider':'UNAVAILABLE_NO_PAID_CALLS','model_limitations':rail.LIMITATIONS}
 def case(self,key):
  records,results=self.records()
  if key not in results:raise ValueError('Unknown saved result identity')
  record=next(r for r in records if r['id']==key);result=results[key]
  return {'record':record,'result':result,'scene':scene(result),'diagnosis':diagnosis(record),'source_compatible_with_current':record['source_sha256']==rail.source_identity(),'verification_scope':'Saved exact input only. This result does not verify a new project or draft.'}
 def config(self,p):
  return {'experiment_id':rail.EXPERIMENT,'controller_id':rail.CONTROLLER,'objective':'Prepare and verify supported rail behavior','type':'adaptive_1d','axes':[{'parameter':'gap_m','minimum':.35,'maximum':2.2}],'fixed_parameters':rail.parameters(p),'criteria':copy.deepcopy(rail.DEFAULT_CRITERIA),'strategy':'uniform','count':1,'seed':1,'minimum_spacing':.001,'proposal_budget':8,'hypothesis_ids':[]}
 def new(self,title):
  if not isinstance(title,str) or not title.strip() or len(title)>80:raise ValueError('Project name must be 1–80 characters')
  p=self.research.new(title.strip(),'Inspect and prepare a bounded rail engineering configuration',rail.EXPERIMENT)
  p=self.research.campaign(p['project']['id'],p['sha256'],self.config({'mass_kg':2.,'speed_mps':.4,'force_n':4.,'gap_m':1.77}))
  return self.project(p['project']['id'])
 def project(self,key):
  p=self.research.read(key);campaign=p['project']['campaigns'][-1] if p['project']['campaigns'] else None
  return {**p,'configuration':campaign['config']['fixed_parameters'] if campaign else None,'revision':len(p['project']['events']),'verification':'NOT_VERIFIED','kind':'PERSISTED_TYPED_RAIL_PLAN_NOT_APPLIED_ROBOT_HEAD'}
 def listing(self):
  return [{**r,'updated_at':self.research.read(r['id'])['project']['updated_at'],'verification':'NOT_VERIFIED'} for r in self.research.listing()]
 def save(self,key,expected,p):
  self.research.campaign(key,expected,self.config(p));return self.project(key)
 def prepare(self,p):
  request=rail.validate({'experiment_id':rail.EXPERIMENT,'controller_id':rail.CONTROLLER,'source_sha256':rail.source_identity(),'cases':[p],'criteria':rail.DEFAULT_CRITERIA,'nonce':uuid4().hex,'confirmation':rail.CONFIRMATION})
  return {'request':request,'status':'AWAITING_SEPARATE_EXPLICIT_APPROVAL','execution_authorized':False,'native_steps':0,'primary_steps':600,'fresh_replay_steps':600,'maximum_steps':1200,'preview':physical_math.predictions(p,rail.DEFAULT_CRITERIA),'limits':rail.POLICY}
 def compare(self,a,b):
  if a==b:raise ValueError('Select two distinct compatible saved results')
  records,_=self.records();ra=next((r for r in records if r['id']==a),None);rb=next((r for r in records if r['id']==b),None)
  if not ra or not rb or ra['compatibility']!=rb['compatibility']:raise ValueError('Only exact compatible saved source/controller/criteria/simulation cohorts compare')
  return {'status':'COMPATIBLE_SAVED_RESULTS','baseline':a,'candidate':b,'changed_parameters':{k:{'before':ra['parameters'][k],'after':rb['parameters'][k]} for k in rail.BOUNDS if ra['parameters'][k]!=rb['parameters'][k]},'minimum_clearance_delta_m':rb['metrics']['minimum_clearance_m']-ra['metrics']['minimum_clearance_m'],'verdicts':[ra['verdict'],rb['verdict']],'meaning':'Physical parameter comparison, not controller-code repair or verification of your draft.'}
 def history(self):
  records,_=self.records();initial=records[:3];cfg=self.config(initial[0]['parameters']);cfg.update(axes=[{'parameter':'gap_m','minimum':min(r['parameters']['gap_m'] for r in records),'maximum':max(r['parameters']['gap_m'] for r in records)}],resolution_target=.005)
  before=analysis.boundaries(initial,['gap_m'])['intervals'];after=analysis.boundaries(records,['gap_m'])['intervals']
  chosen=sampling.adaptive(cfg,initial,[r['parameters'] for r in initial],1)
  return {'initial_intervals':before,'updated_intervals':after,'initial_selection':chosen,'measured_followup':[r['id'] for r in records[3:] if any(p['parameters']==r['parameters'] for p in chosen['points'])],'next_selection':sampling.adaptive(cfg,records,[r['parameters'] for r in records],1),'meaning':'Recorded comparison and deterministic measured guidance; not current project verification or live AI.'}
 def investigate(self,minimum,maximum,budget):
  minimum=rail.number(minimum,.35,2.2);maximum=rail.number(maximum,.35,2.2)
  if minimum>=maximum or type(budget) is not int or not 1<=budget<=8:raise ValueError('Ordered valid range and integer budget 1–8 required')
  records,_=self.records();cfg=self.config(records[0]['parameters']);cfg.update(axes=[{'parameter':'gap_m','minimum':minimum,'maximum':maximum}],resolution_target=min(.005,maximum-minimum))
  return {**sampling.adaptive(cfg,records,[r['parameters'] for r in records],budget),'execution_authorized':False,'native_steps':0}
