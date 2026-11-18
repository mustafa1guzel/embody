"""Trusted DSL interpreter adapter + independent registered-model saved-state audit.

No arbitrary controller/XML/module is executed. Source is compiled to finite data;
all native dynamics use the existing rail model and original safety predicates.
"""
import hashlib,math,time
from pathlib import Path
import mujoco,numpy as np
from core.simulation import ROOT,DEFAULT_MODEL_PATH,compile_context_model,run_simulation
from core.diagnostics import evaluate_safety
from ide_api import rail_sweeps as rail,controller_language as language
from ide_api.product_alpha import scene

def identity():
 return rail.digest({'native':rail.source_identity(),'engine':mujoco.__version__,'files':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in ('ide_api/controller_language.py','ide_api/controller_native.py','ide_api/controller_engineering.py')}})

def control(artifact,p,cancel,deadline):
 def callback(model,data):
  if cancel.is_set():raise rail.Cancelled('Explicit DSL cancellation')
  if time.monotonic()>=deadline:raise rail.Deadline('DSL native deadline')
  sample=rail.snapshot(model,data);data.ctrl[0]=language.command(artifact,sample,p)
 return callback

def checks(samples,p,world,model):
 metrics,selected=rail.measure(samples,rail.DEFAULT_CRITERIA);original=evaluate_safety(samples,world,model.geom('wall').id)
 expected={model.geom('wall').id,model.geom('front_bumper').id}
 c={**{k:v=='PASS' for k,v in original['checks'].items()},**selected,'bounded_actuator_force':metrics['maximum_actuator_force_n']<=p['force_n']+1e-12,'no_unexpected_contacts':all(set(v['geom_ids'])==expected for s in samples for v in s['contacts']),'fresh_replay':True}
 return metrics,c

def execute(request,folder,cancel):
 p=rail.parameters(request['parameters']);compiled=language.compile_source(request['controller']['source'])
 if compiled!=request['controller'] or request['implementation_sha256']!=identity():raise ValueError('Controller/compiler identity differs before execution')
 body,world=rail.contexts(p);deadline=time.monotonic()+60
 callback=control(compiled['artifact'],p,cancel,deadline)
 primary=run_simulation(bodybase=body,worldbase=world,controller=callback,save_telemetry=False,save_render=False,artifacts_dir=folder/'primary')
 if primary['metadata']['actual_steps']!=600 or primary['metadata']['warnings']:raise ValueError('Primary native step or numerical warning failure')
 samples=[{k:s[k] for k in (*rail.FIELDS,'wall_collision','contacts')} for s in primary['telemetry']]
 # Strip detailed contact measurements to the existing finite native contract.
 for s in samples:s['contacts']=[{'geom_ids':v['geom_ids']} for v in s['contacts']]
 model,xml=compile_context_model(DEFAULT_MODEL_PATH,body,world);data=mujoco.MjData(model);data.qvel[0]=p['speed_mps'];replay=[]
 for i in range(601):
  mujoco.mj_forward(model,data);callback(model,data);mujoco.mj_forward(model,data);replay.append(rail.snapshot(model,data))
  if i<600:mujoco.mj_step(model,data)
 if any(w.number for w in data.warning):raise ValueError('Replay numerical warning')
 delta={k:max(abs(a[k]-b[k]) for a,b in zip(samples,replay)) for k in rail.FIELDS}
 if max(delta.values())>1e-9 or any(a['contacts']!=b['contacts'] for a,b in zip(samples,replay)):raise ValueError('Fresh controller replay mismatch')
 met,c=checks(samples,p,world,model)
 result={'format':'SOURCE_BOUND_RAIL_RESULT_V1','request':request,'controller_id':language.VERSION,'source_sha256':compiled['source_sha256'],'artifact_sha256':compiled['artifact_sha256'],'implementation_sha256':request['implementation_sha256'],'model_xml':xml,'model_sha256':hashlib.sha256(xml.encode()).hexdigest(),'samples':samples,'trajectory_sha256':rail.digest(samples),'replay':{'status':'PASS','primary_steps':600,'fresh_steps':600,'samples':replay,'trajectory_sha256':rail.digest(replay),'max_abs_differences':delta},'metrics':met,'checks':c,'verdict':'PASS' if all(c.values()) else 'FAIL','engine':mujoco.__version__}
 verify(result) # Independent native state/force/contact verification before persistence.
 if identity()!=request['implementation_sha256']:raise ValueError('Trusted implementation changed during execution')
 return result

def audit_expression(n,state):
 # Separate evaluator: verifies emitted control against the compiled data contract.
 op=n['op']
 if op=='literal':return n['value']
 if op=='input':return state[n['name']]
 if op=='and':return all(audit_expression(v,state) for v in n['args'])
 if op=='or':return any(audit_expression(v,state) for v in n['args'])
 x,y=audit_expression(n['a'],state),audit_expression(n['b'],state)
 if op=='add':return x+y
 if op=='sub':return x-y
 if op=='mul':return x*y
 if op=='lt':return x<y
 if op=='le':return x<=y
 if op=='gt':return x>y
 if op=='ge':return x>=y
 raise ValueError('Unknown audited artifact operation')

def verify(v):
 rail.exact(v,['format','request','controller_id','source_sha256','artifact_sha256','implementation_sha256','model_xml','model_sha256','samples','trajectory_sha256','replay','metrics','checks','verdict','engine'])
 r=v['request'];p=rail.parameters(r['parameters']);compiled=language.compile_source(r['controller']['source'])
 if v['format']!='SOURCE_BOUND_RAIL_RESULT_V1' or compiled!=r['controller'] or v['source_sha256']!=compiled['source_sha256'] or v['artifact_sha256']!=compiled['artifact_sha256'] or v['implementation_sha256']!=r['implementation_sha256'] or v['implementation_sha256']!=identity() or v['controller_id']!=language.VERSION or v['engine']!=mujoco.__version__:raise ValueError('Source/artifact/implementation contract mismatch')
 if r['requirements']!=rail.DEFAULT_CRITERIA:raise ValueError('Original fixed requirements required')
 body,world=rail.contexts(p);model,xml=compile_context_model(DEFAULT_MODEL_PATH,body,world);data=mujoco.MjData(model)
 if xml!=v['model_xml'] or hashlib.sha256(xml.encode()).hexdigest()!=v['model_sha256']:raise ValueError('Registered numeric model mismatch')
 if not math.isclose(model.body('carriage').mass[0],p['mass_kg'],abs_tol=1e-12) or not np.allclose(model.actuator_ctrlrange[0],[-p['force_n'],p['force_n']],atol=1e-12,rtol=0) or model.actuator_gear[0,0]!=1 or model.opt.timestep!=.005:raise ValueError('Compiled physical parameters mismatch')
 replay=v['replay'];rail.exact(replay,['status','primary_steps','fresh_steps','samples','trajectory_sha256','max_abs_differences'])
 for samples,h in [(v['samples'],v['trajectory_sha256']),(replay['samples'],replay['trajectory_sha256'])]:
  if len(samples)!=601 or rail.digest(samples)!=h:raise ValueError('Trajectory completeness/hash mismatch')
  for i,s in enumerate(samples):
   rail.exact(s,[*rail.FIELDS,'wall_collision','contacts'])
   if any(type(s[k]) not in (int,float) or not math.isfinite(s[k]) for k in rail.FIELDS) or abs(s['time']-i*.005)>1e-10:raise ValueError('Nonfinite or irregular saved state')
   state={'clearance_m':s['wall_clearance'],'stopping_distance_m':p['mass_kg']*s['velocity']**2/(2*p['force_n']),'speed_mps':abs(s['velocity']),'time_s':s['time'],'mass_kg':p['mass_kg'],'force_limit_n':p['force_n']}
   action=compiled['artifact']['then'] if audit_expression(compiled['artifact']['condition'],state) else compiled['artifact']['else']
   expected=max(-p['force_n'],min(p['force_n'],-p['mass_kg']*s['velocity']/.005)) if action=='brake' else 0.
   data.qpos[0]=s['position'];data.qvel[0]=s['velocity'];data.ctrl[0]=s['control'];mujoco.mj_forward(model,data);actual=rail.snapshot(model,data)
   if any(abs(a-b)>1e-10 for a,b in [(expected,s['control']),(actual['wall_clearance'],s['wall_clearance']),(actual['generalized_actuator_force'],s['generalized_actuator_force']),(actual['scalar_actuator_force'],s['scalar_actuator_force'])]) or actual['contacts']!=s['contacts'] or actual['wall_collision']!=s['wall_collision']:raise ValueError('Independent source/control/force/contact/geometry mismatch')
  if samples[0]['position']!=0 or samples[0]['velocity']!=p['speed_mps'] or abs(samples[0]['wall_clearance']-p['gap_m'])>1e-12:raise ValueError('Initial state mismatch')
 delta={k:max(abs(a[k]-b[k]) for a,b in zip(v['samples'],replay['samples'])) for k in rail.FIELDS}
 if replay['status']!='PASS' or replay['primary_steps']!=600 or replay['fresh_steps']!=600 or replay['max_abs_differences']!=delta or max(delta.values())>1e-9 or any(a['contacts']!=b['contacts'] for a,b in zip(v['samples'],replay['samples'])):raise ValueError('Replay comparison mismatch')
 met,c=checks(v['samples'],p,world,model)
 if met!=v['metrics'] or c!=v['checks'] or v['verdict']!=('PASS' if all(c.values()) else 'FAIL'):raise ValueError('Independent measured verdict mismatch')
 return {'verified':True,'record':{'id':'dsl_'+rail.digest(r),'controller_id':language.VERSION,'source_sha256':v['source_sha256'],'artifact_sha256':v['artifact_sha256'],'trajectory_sha256':v['trajectory_sha256'],'model_sha256':v['model_sha256'],'parameters':p,'criteria':r['requirements'],'metrics':met,'checks':c,'verdict':v['verdict'],'replay_status':'PASS','independent_verification':'INDEPENDENT_DSL_NATIVE_STATE_AUDIT_PASS'},'samples':v['samples'],'scene':scene(v)}
