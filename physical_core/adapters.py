"""Robot-specific registered geometry/observations only. No agent or task verifier."""
from dataclasses import replace
import math
import mujoco,numpy as np
from ide_api import rail_sweeps as rail,rover_reference as rover
from core.simulation import DEFAULT_MODEL_PATH,compile_context_model
from world.compiler import compile_world,initial_state
from world.simulation import poses

COMMON={'time_s':'s','dt_s':'s','actuator_peak':'N','unexpected_contacts':'1'}
class Rail:
 family='rail';steps=600
 parameter_bounds={k:v for k,v in rail.BOUNDS.items() if k!='speed_mps'}
 environment_bounds={'wall_half_width_m':(.1,1.),'initial_speed_mps':(0.,1.2)}
 defaults={'parameters':{'mass_kg':4.,'force_n':4.,'gap_m':1.44},'environment':{'wall_half_width_m':.5,'initial_speed_mps':1.2},'constants':{'margin_m':{'value':.1,'unit':'m'}}}
 units={**COMMON,'clearance_m':'m','velocity_mps':'m/s','speed_mps':'m/s','mass_kg':'kg','force_limit_n':'N','stopping_distance_m':'m','wall_contacts':'1'}
 def build(self,d):
  p={**d['parameters'],'speed_mps':d['environment']['initial_speed_mps']};body,w=rail.contexts(p);w=replace(w,wall_half_size_m=(w.wall_half_size_m[0],d['environment']['wall_half_width_m'],w.wall_half_size_m[2]));m,xml=compile_context_model(DEFAULT_MODEL_PATH,body,w);data=mujoco.MjData(m);data.qvel[0]=p['speed_mps'];mujoco.mj_forward(m,data)
  return m,data,xml,{'p':p,'wall':m.geom('wall').id,'bumper':m.geom('front_bumper').id,'actuators':{'force_n':m.actuator('x_motor').id},'view':{'kind':'rail'}}
 def actuators(self,d):return {'force_n':{'unit':'N','limit':d['parameters']['force_n']}}
 def observe(self,m,data,c,d):
  p=c['p'];s=rail.snapshot(m,data);pairs=[set(v['geom_ids']) for v in s['contacts']]
  return {'clearance_m':s['wall_clearance'],'velocity_mps':s['velocity'],'speed_mps':abs(s['velocity']),'mass_kg':float(m.body('carriage').mass[0]),'force_limit_n':p['force_n'],'stopping_distance_m':p['mass_kg']*s['velocity']**2/(2*p['force_n']),'wall_contacts':float(sum(c['wall'] in p for p in pairs)),'unexpected_contacts':float(sum(v!={c['wall'],c['bumper']} for v in pairs))}
 def mandatory(self,d):
  return [('clearance','clearance_m','min','>=',.05,'m',None),('no_wall_contact','wall_contacts','max','<=',0.,'1',None),('stopped','speed_mps','final','<',.03,'m/s',None),('settled','speed_mps','settling_time','<=',3.,'s',.03)]
 def extra(self,d):return []
 def view(self,m,data,c,d):
  from ide_api.product_alpha import scene
  s=rail.snapshot(m,data);return {**c['view'],'scene':scene({'model_xml':c['xml'],'samples':[s]}),'sample':s}

class DifferentialRover:
 family='differential_rover';steps=200
 parameter_bounds={k:b for k,b in rover.BOUNDS.items() if k not in ('angle_deg','friction','target_m')}
 environment_bounds={'angle_deg':(0.,12.),'friction':(.7,2.),'initial_speed_mps':(-.03,.03),'initial_heading_rad':(-.12,.12)}
 defaults={'parameters':{'chassis_mass_kg':.15,'length_m':.18,'width_m':.12,'wheel_radius_m':.03,'torque_nm':.012},'environment':{'angle_deg':5.,'friction':.9,'initial_speed_mps':0.,'initial_heading_rad':0.},'constants':{'target_m':{'value':.04,'unit':'m'},'position_gain':{'value':3.,'unit':'N/m'},'speed_gain':{'value':.8,'unit':'N*s/m'}}}
 units={**COMMON,'actuator_peak':'N*m','progress_m':'m','forward_speed_mps':'m/s','speed_mps':'m/s','upright':'1','wheel_contacts':'1','joint_range_violation':'1','axis_left':'1','axis_right':'1','radius_m':'m','gravity_force_n':'N','yaw_rad':'rad','lateral_m':'m'}
 def build(self,d):
  p={**d['parameters'],'angle_deg':d['environment']['angle_deg'],'friction':d['environment']['friction'],'target_m':d['task']['constants']['target_m']['value']};p=rover.parameters(p);project,roles,proof=rover.construction(p)
  root=next(o for o in project['world']['objects'] if o['id']==roles['root_body_id']);root['rotation_rad'][2]=d['environment']['initial_heading_rad']
  m,xml,contract=compile_world(project['world']);data=initial_state(m,project['world']);tangent,normal=rover.frame(p);data.qvel[:3]=d['environment']['initial_speed_mps']*tangent;mujoco.mj_forward(m,data);origin=data.xpos[m.body(roles['root_body_id']).id].copy()
  motors={name:m.actuator('motor_'+roles['wheels'][wheel]['joint_body_id']).id for name,wheel in [('left_nm','rear_left'),('right_nm','rear_right')]}
  wheels={m.geom('geom_'+v['part_id']+'_body').id for v in roles['wheels'].values()};surfaces={m.geom('geom_test_ramp').id,m.geom('geom_floor').id}
  return m,data,xml,{'p':p,'roles':roles,'world':project['world'],'origin':origin,'tangent':tangent,'normal':normal,'actuators':motors,'wheels':wheels,'surfaces':surfaces,'proof':proof,'view':{'kind':'world','world':project['world']}}
 def actuators(self,d):return {n:{'unit':'N*m','limit':d['parameters']['torque_nm']} for n in ('left_nm','right_nm')}
 def observe(self,m,data,c,d):
  roles=c['roles'];root=m.body(roles['root_body_id']).id;v=np.zeros(6);mujoco.mj_objectVelocity(m,data,mujoco.mjtObj.mjOBJ_BODY,root,v,0);delta=data.xpos[root]-c['origin'];contacts=[{int(x.geom1),int(x.geom2)} for x in data.contact];wheels=set();unexpected=0
  for pair in contacts:
   if len(pair&c['wheels'])==1 and len(pair&c['surfaces'])==1:wheels|=pair&c['wheels']
   else:unexpected+=1
  r=data.xmat[root].reshape(3,3);axes={}
  for key,name in [('axis_left','left_nm'),('axis_right','right_nm')]:
   aid=c['actuators'][name];jid=int(m.actuator_trnid[aid,0]);axes[key]=float(np.cross(data.xaxis[jid],c['normal'])@c['tangent'])
  joint_bad=any(m.jnt_limited[i] and not m.jnt_range[i,0]-1e-6<=data.qpos[m.jnt_qposadr[i]]<=m.jnt_range[i,1]+1e-6 for i in range(m.njnt))
  return {'progress_m':float(delta@c['tangent']),'forward_speed_mps':float(v[3:]@c['tangent']),'speed_mps':float(np.linalg.norm(v[3:])),'upright':float(r[2,2]),'wheel_contacts':float(len(wheels)),'unexpected_contacts':float(unexpected),'joint_range_violation':float(joint_bad),'radius_m':c['p']['wheel_radius_m'],'gravity_force_n':float(-m.body_mass.sum()*(m.opt.gravity@c['tangent'])),'yaw_rad':float(math.atan2(r[1,0],r[0,0])),'lateral_m':float(delta[1]),**axes}
 def mandatory(self,d):return [('upright','upright','min','>=',math.cos(math.pi/4),'1',None),('wheel_contact','wheel_contacts','max','>=',4.,'1',None),('joint_limits','joint_range_violation','max','<=',0.,'1',None)]
 def extra(self,d):return [('forward_progress','progress_m','final','>=',.005,'m',None),('target_accuracy','abs(target_m - progress_m)','final','<=',.035,'m',None),('stopped','speed_mps','final','<',.10,'m/s',None)]
 def view(self,m,data,c,d):return {**c['view'],'sample':{'poses':poses(m,data,c['world'])}}

REGISTRY={x.family:x for x in (Rail(),DifferentialRover())}
def adapter(family):
 if not isinstance(family,str) or family not in REGISTRY:raise ValueError('Unsupported physical family; no adapter/import fallback')
 return REGISTRY[family]
