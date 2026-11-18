"""One source-bound native rollout/replay/verifier for all registered adapters."""
import hashlib,math,time
from pathlib import Path
import mujoco,numpy as np
from core.simulation import ROOT
from ide_api import rail_sweeps as rail,rover_reference
from physical_core import adapters,contracts,language

def sources():
 names={str(p.relative_to(ROOT)) for p in (ROOT/'physical_core').glob('*.py')}
 names.add('examples/physical-engineering/controller_examples.json');names|=set(rover_reference.source_manifest());return {n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in sorted(names)}
def identity():return rail.digest({'files':sources(),'engine':mujoco.__version__,'numpy':np.__version__})
def build(d):
 a=adapters.adapter(d['family']);m,data,xml,c=a.build(d);c['xml']=xml
 if set(c['actuators'])!=set(contracts.contract(d)['actuators']) or set(c['actuators'].values())!=set(range(m.nu)) or abs(m.opt.timestep-.005)>1e-15:raise ValueError('Compiled actuator/time interface mismatch')
 for name,v in contracts.contract(d)['actuators'].items():
  aid=c['actuators'][name]
  if m.actuator_gear[aid,0]!=1 or not np.allclose(m.actuator_ctrlrange[aid],[-v['limit'],v['limit']],rtol=0,atol=1e-12) or not np.allclose(m.actuator_forcerange[aid],[-v['limit'],v['limit']],rtol=0,atol=1e-12):raise ValueError('Compiled force/torque envelope mismatch')
 return a,m,data,xml,c

def observe(a,m,data,c,d):
 values={**a.observe(m,data,c,d),'time_s':float(data.time),'dt_s':.005,'actuator_peak':float(max(abs(v) for v in data.actuator_force)),**{k:v['value'] for k,v in d['task']['constants'].items()}}
 if set(values)!=set(contracts.contract(d)['measurements']) or any(type(v) not in (float,int) or not math.isfinite(v) for v in values.values()):raise ValueError('Invalid/unknown native observation')
 return values

def sample(a,m,data,c,d,requested):return {'time_s':float(data.time),'qpos':data.qpos.tolist(),'qvel':data.qvel.tolist(),'control':data.ctrl.tolist(),'actuator_force':data.actuator_force.tolist(),'generalized_force':data.qfrc_actuator.tolist(),'contacts':[[int(v.geom1),int(v.geom2)] for v in data.contact],'observations':observe(a,m,data,c,d),'requested_actions':requested}

def execute(request,folder,cancel):
 d=contracts.validate(request['definition']);contract=contracts.contract(d);compiled=language.compile_source(request['compiled']['source'],contract)
 if compiled!=request['compiled'] or identity()!=request['implementation_sha256']:raise ValueError('Source/contract implementation changed')
 deadline=time.monotonic()+60
 def rollout(label):
  a,m,data,xml,c=build(d);out=[]
  try:
   for i in range(a.steps+1):
    if cancel.is_set():raise rail.Cancelled('Explicit generalized native cancellation')
    if time.monotonic()>=deadline:raise rail.Deadline('Generalized native60s deadline')
    mujoco.mj_forward(m,data);state=observe(a,m,data,c,d);requested={k:language.evaluate(v,state) for k,v in compiled['artifact']['actions'].items()}
    for name,value in requested.items():
     if type(value) not in (int,float) or not math.isfinite(value):raise ValueError('Invalid controller action')
     lim=contract['actuators'][name]['limit'];data.ctrl[c['actuators'][name]]=min(lim,max(-lim,value))
    mujoco.mj_forward(m,data);out.append(sample(a,m,data,c,d,requested))
    if i<a.steps:mujoco.mj_step(m,data)
   if any(v.number for v in data.warning):raise ValueError('Native warning')
  except Exception as e:
   rail.write_once(folder/(label+'_incomplete.json'),{'status':'INCOMPLETE_NO_PHYSICAL_VERDICT','samples':out,'error':type(e).__name__},8000000);raise
  rail.write_once(folder/(label+'_samples.json'),{'samples':out,'model_sha256':hashlib.sha256(xml.encode()).hexdigest()},8000000)
  return out,xml
 primary,xml=rollout('primary');fresh,xml2=rollout('fresh')
 if xml!=xml2:raise ValueError('Fresh model differs')
 if any(not np.allclose(p[k],f[k],rtol=0,atol=1e-9) for p,f in zip(primary,fresh) for k in ('qpos','qvel','control','actuator_force','generalized_force')) or any(p['contacts']!=f['contacts'] for p,f in zip(primary,fresh)):raise ValueError('Fresh replay mismatch')
 metrics,checks=contracts.evaluate_requirements(d,primary)
 result={'format':'GENERAL_PHYSICAL_RESULT_V1','request':request,'model_xml':xml,'model_sha256':hashlib.sha256(xml.encode()).hexdigest(),'samples':primary,'trajectory_sha256':rail.digest(primary),'replay':{'status':'PASS','samples':fresh,'trajectory_sha256':rail.digest(fresh),'primary_steps':len(primary)-1,'fresh_steps':len(fresh)-1},'metrics':metrics,'checks':checks,'verdict':'PASS' if all(checks.values()) else 'FAIL'}
 verify(result)
 if identity()!=request['implementation_sha256']:raise ValueError('Implementation changed during native run')
 return result

def audit_expression(n,s):
 # Separate expression implementation for independent action/quantity read-back.
 op=n['op']
 if op=='constant':return n['value']
 if op=='input':return s[n['name']]
 if op=='if':return audit_expression(n['a'] if audit_expression(n['condition'],s) else n['b'],s)
 if op=='and':return all(audit_expression(v,s) for v in n['args'])
 if op=='or':return any(audit_expression(v,s) for v in n['args'])
 x=audit_expression(n['a'],s)
 if op=='neg':return -x
 if op=='abs':return abs(x)
 y=audit_expression(n['b'],s)
 if op=='add':return x+y
 if op=='sub':return x-y
 if op=='mul':return x*y
 if op=='div':return x/y
 if op=='lt':return x<y
 if op=='le':return x<=y
 if op=='gt':return x>y
 if op=='ge':return x>=y
 raise ValueError('Unsupported audited expression')

def verify(v):
 rail.exact(v,['format','request','model_xml','model_sha256','samples','trajectory_sha256','replay','metrics','checks','verdict']);r=v['request'];d=contracts.validate(r['definition']);contract=contracts.contract(d);compiled=language.compile_source(r['compiled']['source'],contract)
 if v['format']!='GENERAL_PHYSICAL_RESULT_V1' or compiled!=r['compiled'] or identity()!=r['implementation_sha256']:raise ValueError('Contract/source/artifact/implementation mismatch')
 a,m,data,xml,c=build(d)
 if xml!=v['model_xml'] or hashlib.sha256(xml.encode()).hexdigest()!=v['model_sha256']:raise ValueError('Registered model mismatch')
 initialq=data.qpos.copy();initialv=data.qvel.copy();rp=v['replay'];rail.exact(rp,['status','samples','trajectory_sha256','primary_steps','fresh_steps'])
 for samples,h in [(v['samples'],v['trajectory_sha256']),(rp['samples'],rp['trajectory_sha256'])]:
  if len(samples)!=a.steps+1 or rail.digest(samples)!=h:raise ValueError('Complete hashed trajectory required')
  if not np.allclose(initialq,samples[0]['qpos'],rtol=0,atol=1e-12) or not np.allclose(initialv,samples[0]['qvel'],rtol=0,atol=1e-12):raise ValueError('Initial condition mismatch')
  for i,s in enumerate(samples):
   rail.exact(s,['time_s','qpos','qvel','control','actuator_force','generalized_force','contacts','observations','requested_actions'])
   if any(len(s[k])!=n or any(type(x) not in (int,float) or not math.isfinite(x) for x in s[k]) for k,n in [('qpos',m.nq),('qvel',m.nv),('control',m.nu),('actuator_force',m.nu),('generalized_force',m.nv)]) or abs(s['time_s']-i*.005)>1e-10:raise ValueError('Finite native state/vector/time mismatch')
   for jid,kind in enumerate(m.jnt_type):
    if kind in (mujoco.mjtJoint.mjJNT_FREE,mujoco.mjtJoint.mjJNT_BALL):
     start=int(m.jnt_qposadr[jid])+(3 if kind==mujoco.mjtJoint.mjJNT_FREE else 0)
     if abs(np.linalg.norm(s['qpos'][start:start+4])-1)>1e-9:raise ValueError('Nonunit native quaternion')
   data.qpos[:]=s['qpos'];data.qvel[:]=s['qvel'];data.ctrl[:]=s['control'];data.time=s['time_s'];mujoco.mj_forward(m,data);state=observe(a,m,data,c,d)
   if not isinstance(s['observations'],dict) or any(type(v) not in (int,float) or not math.isfinite(v) for v in s['observations'].values()):raise ValueError('Strict finite observations required')
   if set(state)!=set(s['observations']) or any(abs(state[k]-s['observations'][k])>1e-10 for k in state):raise ValueError('Independent native observation mismatch')
   requested={k:audit_expression(tree,state) for k,tree in compiled['artifact']['actions'].items()}
   if not isinstance(s['requested_actions'],dict) or any(type(v) not in (int,float) or not math.isfinite(v) for v in s['requested_actions'].values()):raise ValueError('Strict finite requested actions required')
   if requested!=s['requested_actions']:raise ValueError('Independent executed source mismatch')
   for name,value in requested.items():
    aid=c['actuators'][name];lim=contract['actuators'][name]['limit'];expected=min(lim,max(-lim,value));jid=int(m.actuator_trnid[aid,0]);dof=int(m.jnt_dofadr[jid])
    if abs(expected-s['control'][aid])>1e-12 or abs(data.actuator_force[aid]-s['actuator_force'][aid])>1e-10 or abs(data.qfrc_actuator[dof]-s['generalized_force'][dof])>1e-10 or abs(data.actuator_force[aid]-data.qfrc_actuator[dof])>1e-10:raise ValueError('Independent actuator force/torque mismatch')
   if not np.allclose(data.qfrc_actuator,s['generalized_force'],rtol=0,atol=1e-10) or not np.allclose(data.actuator_force,s['actuator_force'],rtol=0,atol=1e-10):raise ValueError('Complete force vector mismatch')
   if [[int(x.geom1),int(x.geom2)] for x in data.contact]!=s['contacts']:raise ValueError('Independent native contact mismatch')
 if rp['status']!='PASS' or rp['primary_steps']!=a.steps or rp['fresh_steps']!=a.steps or any(not np.allclose(p[k],f[k],rtol=0,atol=1e-9) for p,f in zip(v['samples'],rp['samples']) for k in ('qpos','qvel','control','actuator_force','generalized_force')) or any(p['contacts']!=f['contacts'] for p,f in zip(v['samples'],rp['samples'])):raise ValueError('Replay contract mismatch')
 metrics,checks=contracts.evaluate_requirements(d,v['samples'])
 if metrics!=v['metrics'] or checks!=v['checks'] or v['verdict']!=('PASS' if all(checks.values()) else 'FAIL'):raise ValueError('Independent project requirement verdict mismatch')
 return {'verified':True,'metrics':metrics,'checks':checks,'verdict':v['verdict'],'source_sha256':compiled['source_sha256'],'artifact_sha256':compiled['artifact_sha256'],'contract_sha256':rail.digest(contract),'model_sha256':v['model_sha256'],'trajectory_sha256':v['trajectory_sha256'],'fresh_replay':'PASS'}

def display(v,index=0):
 d=v['request']['definition'];a,m,data,xml,c=build(d);s=v['samples'][index];data.qpos[:]=s['qpos'];data.qvel[:]=s['qvel'];data.ctrl[:]=s['control'];data.time=s['time_s'];mujoco.mj_forward(m,data);return a.view(m,data,c,d)
