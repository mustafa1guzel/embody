"""Explicit disposable two-joint sample using actual engineering transactions."""
from engineering.project import new_project,identity
from ide_api.engineering import EngineeringService

def part_input(identifier,body,parent,*,length=.3):
 return {'id':identifier,'body_id':body,'family':'rounded_link','parameters':{'length_m':length,'width_m':.06,'thickness_m':.015,'end_radius_m':.03},'parent_body_id':parent,'position_m':[0,0,0],'rotation_rad':[0,0,0],'mass_kg':.15,'mounting_holes':[{'id':'mount_a','diameter_m':.012,'u':-.32,'v':0},{'id':'mount_b','diameter_m':.012,'u':.32,'v':0}]}

def create_disposable_arm(root):
 """Caller explicitly requests a new store; an existing head is never reused."""
 from pathlib import Path
 root=Path(root)
 if (root/'head.json').exists():raise ValueError('Disposable example requires a new project store')
 p=new_project();p['world']['id']='shapebase_arm_v1';p['world']['environment']['duration_s']=1.
 service=EngineeringService(root,initial_project=p);receipts=[]
 def review(ops,description):
  base=service.current();proposal=service.propose(identity(base),base['revision'],ops,description,origin='EXPLICIT_LOCAL_USER_REVIEW')
  assert service.current()==base
  result=service.decide(identity(base),base['revision'],proposal['proposal_id'],'apply','APPLY REVIEWED ENGINEERING CHANGE');receipts.append({'proposal':proposal,'decision':result['decision']});return result['project']
 def joint(body,parent,position,angle):
  return [{'kind':'create_object','primitive':'motor','id':body,'parent':parent},{'kind':'move_object','target':body,'position_m':position},{'kind':'set_shape','target':body,'geometry':'cylinder'},{'kind':'set_geometry','target':body,'dimensions_m':[.04,.04,.04]},{'kind':'set_mass','target':body,'mass_kg':.05},{'kind':'create_joint','target':body,'joint':{'kind':'revolute','axis':[0,0,1],'range':[-2.5,2.5],'initial_position':angle,'initial_velocity':.2,'damping':.02}},{'kind':'set_actuator','target':body,'actuator':{'limit':.5,'command':.015,'unit':'N*m'}}]
 review([{'kind':'create_object','primitive':'anchor','id':'arm_base','parent':None},{'kind':'move_object','target':'arm_base','position_m':[0,0,.075]},{'kind':'set_geometry','target':'arm_base','dimensions_m':[.1,.1,.15]},*joint('shoulder','arm_base',[0,0,.1],0)],'Explicit disposable arm base and actual shoulder joint')
 review([{'kind':'create_parametric_part','part':part_input('shape_link_one','link_one','shoulder')},{'kind':'attach_part_to_joint','target':'shape_link_one','joint_body_id':'shoulder','frame_id':'mount_a'}],'First parametric link with two true display mounting holes; declared solid collision proxy')
 review(joint('elbow','link_one',[.096,0,0],.45),'Explicit existing elbow mechanics, separate from part geometry')
 frame={'id':'mount_b','source':'hole','hole_id':'mount_b','rotation_rad':[0,0,0]}
 review([{'kind':'set_attachment_frame','target':'shape_link_one','frame':frame,'mounted_body_id':'elbow'},{'kind':'create_parametric_part','part':part_input('shape_link_two','link_two','elbow',length=.28)},{'kind':'attach_part_to_joint','target':'shape_link_two','joint_body_id':'elbow','frame_id':'mount_a'}],'Explicit distal-frame/elbow relationship and second parametric link')
 return service,receipts
