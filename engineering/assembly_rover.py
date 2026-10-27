"""Fixed host structural predicates and native observations; model cannot edit them."""
import math
import numpy as np
import mujoco
from .assembly_plan import PlanError
from world.compiler import compile_world,initial_state
from physics.contracts import digest

CRITERIA={'duration_s':1,'dt_s':.005,'native_steps_primary':200,'native_steps_replay':200,
 'force_tolerance':1e-12,'axis_tolerance':1e-10,'max_total_mass_kg':2.,'max_chassis_length_m':.6,'max_chassis_width_m':.4,
 'max_motor_authority_nm':.08,'max_motor_command_nm':.02,'min_abs_motor_command_nm':.0005,
 'movement_threshold_m':.005,'minimum_upright_z_dot':math.cos(math.pi/4),
 'contacts':'Wheel-floor pairs allowed and expected; any other contact is a measured failure.',
 'meaning':'Finite proxy experiment, not robust locomotion or hardware safety. Poor movement/tipping/slip observations remain saved.'}


def structural(project,roles):
 shapes={s['id']:s for s in project.get('shape_specs',[])};objects={o['id']:o for o in project['world']['objects']}
 expected=[roles[k] for k in ('chassis_part_id','front_axle_part_id','rear_axle_part_id')]+[v['part_id'] for v in roles['wheels'].values()]+list(roles['motor_mount_parts'].values())
 if len(set(expected))!=9 or set(shapes)!=set(expected):raise PlanError('Exactly nine distinct role-bound rover ShapeSpecs required')
 def shape(key,family):
  s=shapes[key]
  if s['family']!=family:raise PlanError('Wrong supported family for role '+key)
  return s
 chassis=shape(roles['chassis_part_id'],'chassis');root=objects.get(roles['root_body_id'])
 if not root or not root['joint'] or root['joint']['kind']!='free' or chassis['parent_body_id']!=root['id']:raise PlanError('Chassis must be attached to an actual free root')
 if sum(o['joint'] is not None and o['joint']['kind']=='free' for o in objects.values())!=1:raise PlanError('Exactly one free rover root required')
 if chassis['parameters']['length_m']>CRITERIA['max_chassis_length_m'] or chassis['parameters']['width_m']>CRITERIA['max_chassis_width_m'] or sum(o['mass_kg'] for o in objects.values())>CRITERIA['max_total_mass_kg']:raise PlanError('Desktop size/mass envelope exceeded')
 if project['world']['environment']['duration_s']!=1 or project['world']['environment']['gravity_m_s2']!=[0,0,-9.81]:raise PlanError('Frozen native environment must be 1s, dt .005, gravity -9.81 Z')
 floor=[o for o in objects.values() if o['geometry']=='plane']
 if len(floor)!=1 or floor[0]['id']!='floor' or floor[0]['position_m']!=[0,0,0] or floor[0]['rotation_rad']!=[0,0,0]:raise PlanError('Original ground plane must be preserved')
 helpers={root['id'],floor[0]['id']}
 def registered(owner,mount_id,source):
  mount=objects.get(mount_id);frame=next((f for f in owner['attachment_frames'] if f['source']==source and f['id']==source),None)
  if not mount or mount['parent']!=owner['body_id'] or frame is None or {'body_id':mount_id,'frame_id':source} not in owner['mounted_bodies']:raise PlanError('Missing correct declared connection '+source)
  helpers.add(mount['id']);return mount
 axles={}
 for which in ('front','rear'):
  axle=shape(roles[which+'_axle_part_id'],'axle');anchor=registered(chassis,axle['parent_body_id'],which+'_axle')
  if axle.get('frame_attachment')!={'mount_body_id':anchor['id'],'frame_id':'origin'}:raise PlanError('Axle must anchor to its registered chassis mount at origin')
  axles[which]=axle
 expected_motors=[];expected_joints=[];wheel_bodies=[]
 for placement,r in roles['wheels'].items():
  which,side=placement.split('_');s=shape(r['part_id'],'wheel');joint=registered(axles[which],r['joint_body_id'],'axle_'+side)
  if s['parent_body_id']!=joint['id'] or s['joint_attachment']!={'joint_body_id':joint['id'],'frame_id':'axle'}:raise PlanError('Wheel must use actual registered axle hinge and named coaxial datum')
  if not joint['joint'] or joint['joint']['kind']!='revolute' or joint['joint']['axis']!=[0,0,1]:raise PlanError('Four genuine local +Z wheel hinges required')
  expected_joints.append(joint['id']);wheel_bodies.append(s['body_id']);a=joint['actuator']
  if which=='rear':
   if not a or a['unit']!='N*m' or not CRITERIA['min_abs_motor_command_nm']<=abs(a['command'])<=CRITERIA['max_motor_command_nm'] or a['limit']>CRITERIA['max_motor_authority_nm']:raise PlanError('Rear bounded nonzero motor declaration outside scope')
   expected_motors.append(joint['id'])
  elif a:raise PlanError('Front wheels must be passive in this experiment')
 for side,pid in roles['motor_mount_parts'].items():
  s=shape(pid,'motor_mount');mount=registered(chassis,s['parent_body_id'],'rear_'+side+'_mount')
  if not s.get('frame_attachment') or s['frame_attachment']['mount_body_id']!=mount['id']:raise PlanError('Motor plate needs registered rear fixed mounting')
 if {o['id'] for o in objects.values() if o['joint'] and o['joint']['kind']!='free'}!=set(expected_joints) or {o['id'] for o in objects.values() if o['actuator']}!=set(expected_motors):raise PlanError('Unexpected joint or actuator outside rover roles')
 if set(objects)!=helpers|{s['body_id'] for s in shapes.values()}:raise PlanError('Unrequested body outside explicit rover roles')
 m,xml,proof=compile_world(project['world']);d=initial_state(m,project['world']);mujoco.mj_forward(m,d)
 chassis_z=d.geom_xmat[m.geom('geom_'+chassis['body_id']).id].reshape(3,3)[:,2];chassis_y=d.geom_xmat[m.geom('geom_'+chassis['body_id']).id].reshape(3,3)[:,1]
 if abs(np.dot(chassis_z,[0,0,1])-1)>1e-10:raise PlanError('Initial chassis must be level')
 for b in wheel_bodies:
  axis=d.geom_xmat[m.geom('geom_'+b).id].reshape(3,3)[:,2]
  if abs(abs(float(np.dot(axis,chassis_y)))-1)>1e-10:raise PlanError('Native wheel axes not horizontal/coaxial with chassis')
 return {'status':'STRUCTURAL_NATIVE_COMPILE_PASS','compiled':proof,'wheel_bodies':wheel_bodies,'floor_body':floor[0]['id'],'root_body':root['id'],'chassis_body':chassis['body_id'],'native_dof':int(m.nv),'native_actuators':int(m.nu),'criteria':CRITERIA}


def measured(result,proof):
 """Fresh forward checks on saved states, not another integration/replay."""
 m=mujoco.MjModel.from_xml_string(result['model_xml']);d=mujoco.MjData(m)
 for o in result['world']['objects']:
  if o['actuator']:d.ctrl[m.actuator('motor_'+o['id']).id]=o['actuator']['command']
 wheel_geoms={'geom_'+b for b in proof['wheel_bodies']};allowed={'geom_'+proof['floor_body']};telemetry=[];unexpected=[];ground=0;forces=True;upright=1.
 for index,s in enumerate(result['samples']):
  d.qpos[:]=s['qpos'];d.qvel[:]=s['qvel'];mujoco.mj_forward(m,d)
  np.testing.assert_allclose(d.qfrc_actuator,s['generalized_force'],atol=1e-12,rtol=0)
  if d.ncon!=s['contacts']:raise ValueError('Independent contact count mismatch')
  pairs=[]
  for c in d.contact:
   a,b=m.geom(int(c.geom1)).name,m.geom(int(c.geom2)).name;pair=sorted((a,b));pairs.append(pair)
   if (a in wheel_geoms and b in allowed) or (b in wheel_geoms and a in allowed):ground+=1
   else:unexpected.append({'sample':index,'time_s':s['time_s'],'geoms':pair})
  for o in result['world']['objects']:
   if o['actuator']:
    a=m.actuator('motor_'+o['id']);forces=forces and abs(float(d.actuator_force[a.id]))<=o['actuator']['limit']+1e-12
  z=d.geom_xmat[m.geom('geom_'+proof['chassis_body']).id].reshape(3,3)[:,2];upright=min(upright,float(z[2]));telemetry.append({'sample':index,'time_s':s['time_s'],'pairs':pairs})
 poses=lambda s:next(p['position_m'] for p in s['poses'] if p['id']==proof['root_body'])
 displacement=float(np.linalg.norm(np.array(poses(result['samples'][-1]))[:2]-np.array(poses(result['samples'][0]))[:2]))
 checks={'finite_native_states':all(np.isfinite(s['qpos']+s['qvel']).all() for s in result['samples']),'bounded_actuator_forces':bool(forces),'ground_contacts_measured':ground>0,'no_unexpected_contacts':not unexpected,'upright_throughout':upright>=CRITERIA['minimum_upright_z_dot'],'measurable_horizontal_movement':displacement>=CRITERIA['movement_threshold_m'],'fresh_replay':result['independent_verification']['status']=='PASS'}
 return {'status':'MEASURED_ROVER_PROXY_PASS' if all(checks.values()) else 'MEASURED_ROVER_REQUIREMENT_FAILURE','checks':checks,'horizontal_displacement_m':displacement,'minimum_chassis_up_z_dot':upright,'wheel_ground_contact_events':ground,'unexpected_contacts':unexpected,'contact_telemetry':telemetry,'contact_telemetry_sha256':digest(telemetry),'extra_integration_steps':0,'limitations':'Single bounded constant-control proxy test; no steering, continuous wheel rotation, robust locomotion, detailed tire model or hardware safety. Movement alone does not prove no slip.'}
