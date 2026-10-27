"""Explicit disposable assembly setup; edits remain review-only, never auto-applied."""
from pathlib import Path
import math,copy
from engineering.project import new_project,identity
from ide_api.engineering import EngineeringService


def part(identifier,family,parameters,parent,*,mass=0,holes=()):
 return {'id':'shape_'+identifier,'body_id':identifier,'family':family,'parameters':copy.deepcopy(parameters),'parent_body_id':parent,'position_m':[0,0,0],'rotation_rad':[0,0,0],'mass_kg':mass,'mounting_holes':copy.deepcopy(list(holes))}


def create_example(root,kind):
 root=Path(root)
 if kind not in ('rover','drone') or (root/'head.json').exists() or (root/'construction_review/head.json').exists():raise ValueError('New disposable rover/drone store required')
 p=new_project();p['world']['id']='mobility_'+kind+'_v1';p['world']['environment']['duration_s']=1.
 review_service=EngineeringService(root/'construction_review',initial_project=p);receipts=[]
 authored=p
 def reviewed_setup(ops,description):
  nonlocal authored
  # Construct copies using the existing typed engine; never call decide/apply.
  # The separate empty construction-review head remains revision zero.
  candidate,checks=review_service.preview(authored,ops)
  receipts.append({'purpose':'EXPLICIT_DETERMINISTIC_COPY_CONSTRUCTION_NOT_MODEL_OUTPUT','description':description,'base_project_sha256':identity(authored),'base_revision':authored['revision'],'operations':ops,'resulting_project_sha256':identity(candidate),'resulting_revision':candidate['revision'],'validation':checks,'application':'NO_APPLY_CALL; copied construction state only'})
  authored=candidate
 def fixed(name,parent,moving):
  return [{'kind':'create_object','primitive':'rigid_link' if moving else 'anchor','id':name,'parent':parent},{'kind':'create_joint','target':name,'joint':None},{'kind':'move_object','target':name,'position_m':[0,0,0]},{'kind':'set_geometry','target':name,'dimensions_m':[.005,.005,.005]},*([{'kind':'set_mass','target':name,'mass_kg':.001}] if moving else [])]
 def mount(owner,source,name):
  from .mobility import frame_rotation
  family=next(s for s in authored['shape_specs'] if s['id']==owner)
  return {'kind':'set_attachment_frame','target':owner,'frame':{'id':source,'source':source,'hole_id':None,'rotation_rad':frame_rotation(family,source)},'mounted_body_id':name}
 def attach(name,parent,frame='origin'):
  return {'kind':'attach_part_to_mount','target':'shape_'+name,'mount_body_id':parent,'frame_id':frame}
 chassis={'length_m':.30 if kind=='rover' else .14,'width_m':.18 if kind=='rover' else .14,'thickness_m':.015 if kind=='rover' else .01,'corner_radius_m':.012}
 holes=[{'id':'fix_'+str(i),'diameter_m':.005,'u':u,'v':v} for i,(u,v) in enumerate([(-.3,-.3),(-.3,.3),(.3,-.3),(.3,.3)])]
 if kind=='rover':
  reviewed_setup([{'kind':'create_object','primitive':'dynamic_body','id':'rover_root','parent':None},{'kind':'move_object','target':'rover_root','position_m':[0,0,.12]},{'kind':'set_geometry','target':'rover_root','dimensions_m':[.01,.01,.01]},{'kind':'set_mass','target':'rover_root','mass_kg':.05},{'kind':'create_parametric_part','part':part('chassis','chassis',chassis,'rover_root',mass=.3,holes=holes)}],'Explicit independent free-root toy rover chassis; no controller/electrical binding')
  for axle in ('front','rear'):
   name=axle+'_axle';mount_name=name+'_mount'
   reviewed_setup([*fixed(mount_name,'chassis',True),mount('shape_chassis',name,mount_name),{'kind':'create_parametric_part','part':part(name,'axle',{'diameter_m':.008,'length_m':.24},mount_name,mass=.015)},attach(name,mount_name)],'Reviewed '+axle+' nominal solid axle and rotated chassis datum')
   for side,datum in [('left','axle_left'),('right','axle_right')]:
    wheel=axle+'_'+side+'_wheel';joint=wheel+'_joint'
    ops=[{'kind':'create_object','primitive':'motor' if axle=='rear' else 'revolute','id':joint,'parent':name},{'kind':'move_object','target':joint,'position_m':[0,0,0]},{'kind':'set_geometry','target':joint,'dimensions_m':[.005,.005,.005]},{'kind':'set_mass','target':joint,'mass_kg':.001},{'kind':'create_joint','target':joint,'joint':{'kind':'revolute','axis':[0,0,1],'range':[-math.pi,math.pi],'initial_position':0,'initial_velocity':0,'damping':.001}},mount('shape_'+name,datum,joint)]
    if axle=='rear':ops.append({'kind':'set_actuator','target':joint,'actuator':{'limit':.04,'command':.003,'unit':'N*m'}})
    ops.extend([{'kind':'create_parametric_part','part':part(wheel,'wheel',{'outer_diameter_m':.12,'thickness_m':.025,'axle_hole_diameter_m':.009,'hub_thickness_m':.004},joint,mass=.03)},{'kind':'attach_part_to_joint','target':'shape_'+wheel,'joint_body_id':joint,'frame_id':'axle'}])
    reviewed_setup(ops,'Reviewed '+wheel+'; actual local +Z hinge, nominal axle/bore clearance, solid wheel contact proxy')
  for side in ('left','right'):
   name='rear_'+side+'_motor_mount';anchor=name+'_datum'
   reviewed_setup([*fixed(anchor,'chassis',True),mount('shape_chassis','rear_'+side+'_mount',anchor),{'kind':'create_parametric_part','part':part(name,'motor_mount',{'length_m':.045,'width_m':.03,'thickness_m':.006,'corner_radius_m':.004},anchor,mass=.01,holes=[{'id':'bolt_a','diameter_m':.004,'u':-.25,'v':0},{'id':'bolt_b','diameter_m':.004,'u':.25,'v':0}])},attach(name,anchor,'bottom')],'Reviewed drive-motor mounting plate; motor hardware and powertrain not inferred')
  edit=[{'kind':'update_shape_parameter','target':'shape_front_left_wheel','parameter':'outer_diameter_m','value':.144}]
 else:
  reviewed_setup([{'kind':'create_object','primitive':'anchor','id':'frame_stand','parent':None},{'kind':'move_object','target':'frame_stand','position_m':[0,0,.25]},{'kind':'set_geometry','target':'frame_stand','dimensions_m':[.005,.005,.005]},{'kind':'create_parametric_part','part':part('center','chassis',chassis,'frame_stand',holes=holes)}],'Explicit fixed quad-frame concept: static geometry, no motors, thrust or flight dynamics')
  for direction in ('east','north','west','south'):
   arm='arm_'+direction;anchor=arm+'_root';pad='pad_'+direction;pad_mount=pad+'_mount'
   reviewed_setup([*fixed(anchor,'center',False),mount('shape_center','arm_'+direction,anchor),{'kind':'create_parametric_part','part':part(arm,'drone_arm',{'length_m':.20,'width_m':.025,'thickness_m':.008},anchor)},attach(arm,anchor,'root')],'Reviewed symmetric '+direction+' arm and explicit fixed root datum')
   reviewed_setup([*fixed(pad_mount,arm,False),mount('shape_'+arm,'motor_pad',pad_mount),{'kind':'create_parametric_part','part':part(pad,'motor_pad',{'length_m':.05,'width_m':.05,'thickness_m':.006,'corner_radius_m':.008},pad_mount,holes=[{'id':'motor_a','diameter_m':.004,'u':-.2,'v':0},{'id':'motor_b','diameter_m':.004,'u':.2,'v':0}])},attach(pad,pad_mount)],'Reviewed '+direction+' motor pad datum; no propeller/aerodynamic/actuator claim')
  edit=[{'kind':'update_shape_parameter','target':'shape_arm_'+d,'parameter':'length_m','value':.24} for d in ('east','north','west','south')]
 # Explicit creation of a new disposable authored document, not application to
 # an existing project. Parameter changes below are review proposals only.
 assert review_service.current()==p
 service=EngineeringService(root,initial_project=authored)
 before=service.current();proposal=service.propose(identity(before),before['revision'],edit,'EXPLICIT_DETERMINISTIC_MOBILITY_EDIT: review-only '+('20% larger front-left wheel; intentional single-wheel variation, entered masses unchanged' if kind=='rover' else '20% longer four symmetric arms; motor pads follow declared datums'),origin='EXPLICIT_LOCAL_USER_REVIEW')
 assert service.current()==before
 return service,{'kind':kind,'setup_receipts':receipts,'base':before,'edit_proposal':proposal,'application_status':'PROPOSED_NOT_APPLIED','construction_review_head_revision':review_service.current()['revision'],'setup_apply_calls':0,'model_requests':0,'vm_launches':0,'unsupported':['Suspension','Steering geometry','Detailed tire/bearing contact','Powertrain/MCU electrical execution','Propellers, aerodynamics, thrust and flight control','Certified mechanical safety','Vehicle body shell']}
