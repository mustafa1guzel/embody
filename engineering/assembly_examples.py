"""Independently authored deterministic examples; never a model tool or answer key."""
import math
from .assembly_plan import GOAL
from shapebase.mobility import frame_rotation

def rover_plan(*,length=.18,width=.12,wheel_diameter=.06,label='compact'):
 """Raw typed data with explicit masses, not Phase18D recipe import/repair."""
 prefix='example_'+label+'_';root=prefix+'root';chassis=prefix+'chassis';steps=[]
 thickness=.012;wheel_thickness=.018;hub=.004;axle_length=width+wheel_thickness+hub+.014
 def part(pid,family,parent,parameters,mass):
  return {'kind':'create_parametric_part','part':{'id':pid,'body_id':pid+'_body','family':family,'parameters':parameters,'parent_body_id':parent,'position_m':[0,0,0],'rotation_rad':[0,0,0],'mass_kg':mass,'mounting_holes':[]}}
 def step(ops,purpose):
  sid='batch_'+str(len(steps));steps.append({'id':sid,'depends_on':[steps[-1]['id']] if steps else [],'purpose':purpose,'operations':ops})
 def intermediary(bid,parent,hinge=False):
  return [{'kind':'create_object','primitive':'revolute' if hinge else 'rigid_link','id':bid,'parent':parent},{'kind':'set_geometry','target':bid,'dimensions_m':[.006,.006,.006]},{'kind':'set_mass','target':bid,'mass_kg':.002},{'kind':'create_joint','target':bid,'joint':{'kind':'revolute','axis':[0,0,1],'range':[-math.pi,math.pi],'initial_position':0,'initial_velocity':0,'damping':.001} if hinge else None}]
 def register(owner,family,frame,child):return {'kind':'set_attachment_frame','target':owner,'frame':{'id':frame,'source':frame,'hole_id':None,'rotation_rad':frame_rotation({'family':family},frame)},'mounted_body_id':child}
 step([{'kind':'create_free_root','id':root,'mass_kg':.01,'position_m':[0,0,wheel_diameter/2+thickness/2+.001],'dimensions_m':[.006,.006,.006]},part(chassis,'chassis',root,{'length_m':length,'width_m':width,'thickness_m':thickness,'corner_radius_m':.008},.15)],'New explicitly dimensioned, low-mass root and chassis')
 axles={};wheels={};plates={}
 for end in ('front','rear'):
  axle=prefix+end+'_axle';mount=prefix+end+'_mount';axles[end]=axle
  step(intermediary(mount,chassis+'_body')+[register(chassis,'chassis',end+'_axle',mount),part(axle,'axle',mount,{'diameter_m':.008,'length_m':axle_length},.012),{'kind':'attach_part_to_mount','target':axle,'mount_body_id':mount,'frame_id':'origin'}],end+' axle with declared chassis-owned mount')
  for side in ('left','right'):
   role=end+'_'+side;wheel=prefix+role+'_wheel';joint=prefix+role+'_hinge';wheels[role]={'part_id':wheel,'joint_body_id':joint}
   ops=intermediary(joint,axle+'_body',True)+[register(axle,'axle','axle_'+side,joint)]
   if end=='rear':ops.append({'kind':'set_actuator','target':joint,'actuator':{'limit':.02,'command':.0015,'unit':'N*m'}})
   ops.extend([part(wheel,'wheel',joint,{'outer_diameter_m':wheel_diameter,'thickness_m':wheel_thickness,'axle_hole_diameter_m':.009,'hub_thickness_m':hub},.02),{'kind':'attach_part_to_joint','target':wheel,'joint_body_id':joint,'frame_id':'axle'}]);step(ops,role+' wheel with explicit small hinge body')
 for side in ('left','right'):
  mount=prefix+side+'_plate_mount';pid=prefix+side+'_motor_plate';plates[side]=pid
  step(intermediary(mount,chassis+'_body')+[register(chassis,'chassis','rear_'+side+'_mount',mount),part(pid,'motor_mount',mount,{'length_m':.035,'width_m':.025,'thickness_m':.006,'corner_radius_m':.003},.006),{'kind':'attach_part_to_mount','target':pid,'mount_body_id':mount,'frame_id':'bottom'}],side+' rear mounting plate')
 return {'schema_version':1,'goal':GOAL,'roles':{'root_body_id':root,'chassis_part_id':chassis,'front_axle_part_id':axles['front'],'rear_axle_part_id':axles['rear'],'wheels':wheels,'motor_mount_parts':plates},'assumptions':['DEVELOPER_AUTHORED_DETERMINISTIC_EXAMPLE; not live AI and not a correction of either historical plan.','Masses, box helper dimensions and constant torques are explicit developer inputs, not calibrated hardware.'], 'limitations':['Solid collision proxies; no steering, suspension, continuous wheel rotation or tire/bearing/material fidelity.','Native finite-scope replay is not real-world safety or autonomous locomotion.'],'explanation':'Independent raw typed construction with canonical owner/child mounts and explicit mass allocation. No hidden macro is exposed to a model.','steps':steps}
