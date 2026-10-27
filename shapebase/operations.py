"""Review-only typed shape operations; atomic execution on a project copy."""
import copy
from world.schema import obj,ID,num
from world.objects import primitive
from .model import CREATE_INPUT,HOLE,FRAME,FEATURE_ID,FAMILIES,PARAMETERS,create_shape,validate_shape,validate_project_shapes,dimensions,physical,frame_positions,rotate_z

def action(name,fields):return obj({'kind':{'type':'string','enum':[name]},**fields})
TARGET={'target':ID}
SCHEMAS=[
 action('create_parametric_part',{'part':CREATE_INPUT}),
 action('update_shape_parameter',{**TARGET,'parameter':{'enum':sorted({k for p in PARAMETERS.values() for k in p})},'value':num(0,1)}),
 action('add_mounting_hole',{**TARGET,'hole':HOLE}),
 action('update_mounting_hole',{**TARGET,'hole':HOLE}),
 action('set_attachment_frame',{**TARGET,'frame':FRAME,'mounted_body_id':{'anyOf':[ID,{'type':'null'}]}}),
 action('attach_part_to_joint',{**TARGET,'joint_body_id':ID,'frame_id':FEATURE_ID}),
]
MOBILITY_SCHEMAS=[action('attach_part_to_mount',{**TARGET,'mount_body_id':ID,'frame_id':FEATURE_ID})]
NAMES={s['properties']['kind']['enum'][0] for s in SCHEMAS+MOBILITY_SCHEMAS}

def synchronize(project):
 """Regenerate declared proxy and explicit frame constraints, never infer joints."""
 objects={o['id']:o for o in project['world']['objects']}
 for s in project.get('shape_specs',[]):
  validate_shape(s);o=objects.get(s['body_id'])
  if o is None:raise ValueError('Parametric proxy body absent')
  frames={f['id']:f for f in frame_positions(s)}
  if s['joint_attachment']:
   a=s['joint_attachment'];j=objects.get(a['joint_body_id'])
   if not j or j['id']!=s['parent_body_id'] or not j['joint'] or j['joint']['kind']!='revolute' or j['joint']['axis']!=[0,0,1]:raise ValueError('Attach only to the existing parent revolute +Z joint')
   s['position_m']=[-v for v in rotate_z(frames[a['frame_id']]['position_m'],s['rotation_rad'][2])]
  a=s.get('frame_attachment')
  if a:
   mount=objects.get(a['mount_body_id'])
   if not mount or mount['id']!=s['parent_body_id'] or mount['joint'] or mount['actuator']:raise ValueError('Fixed attachment requires an actual fixed parent mount')
   s['position_m']=[-v for v in rotate_z(frames[a['frame_id']]['position_m'],s['rotation_rad'][2])]
  o.update(geometry='cylinder' if s['family'] in ('shaft','axle','wheel') else 'box',dimensions_m=dimensions(s),position_m=copy.deepcopy(s['position_m']),rotation_rad=copy.deepcopy(s['rotation_rad']),mass_kg=s['physical']['mass_kg'],parent=s['parent_body_id'])
  for m in s['mounted_bodies']:
   child=objects.get(m['body_id']);frame=frames[m['frame_id']]
   if not child or child['parent']!=s['body_id']:raise ValueError('Mount requires an existing child of the correct part body')
   child['position_m']=copy.deepcopy(frame['position_m']);child['rotation_rad']=copy.deepcopy(frame['rotation_rad'])
 validate_project_shapes(project)

def execute(project,operation):
 k=operation['kind'];parts=project.setdefault('shape_specs',[])
 if project.get('creation'):raise ValueError('SHAPEBASE v0.1 uses independent projects, not frozen generated-device bindings')
 if k=='create_parametric_part':
  s=create_shape(operation['part'],project['id'])
  if any(p['id']==s['id'] or p['body_id']==s['body_id'] for p in parts) or any(o['id']==s['body_id'] for o in project['world']['objects']):raise ValueError('Shape or proxy identity already exists')
  parent=next((o for o in project['world']['objects'] if o['id']==s['parent_body_id']),None)
  if s['parent_body_id'] is not None and parent is None:raise ValueError('Shape parent body absent')
  moving=parent and parent['kind'] in ('dynamic','link')
  if (moving and s['physical']['mass_kg']<.001) or (not moving and s['physical']['mass_kg']!=0):raise ValueError('Explicit mass must match moving attachment or static mounting; no implicit joint creation')
  o=primitive('rigid_link' if moving else 'anchor',s['body_id']);o.update(name=s['family'].replace('_',' ').title(),parent=s['parent_body_id'],joint=None,actuator=None)
  parts.append(s);project['world']['objects'].append(o)
 else:
  s=next((p for p in parts if p['id']==operation['target']),None)
  if s is None:raise ValueError('Shape target absent')
  if k=='update_shape_parameter':
   if operation['parameter'] not in PARAMETERS[s['family']]:raise ValueError('Unsupported family parameter')
   s['parameters'][operation['parameter']]=operation['value']
  elif k in ('add_mounting_hole','update_mounting_hole'):
   hole=copy.deepcopy(operation['hole']);index=next((i for i,h in enumerate(s['mounting_holes']) if h['id']==hole['id']),None)
   if k=='add_mounting_hole':
    if index is not None:raise ValueError('Mounting hole identity already exists')
    s['mounting_holes'].append(hole);s['attachment_frames'].append({'id':hole['id'],'source':'hole','hole_id':hole['id'],'rotation_rad':[0,0,0]})
   else:
    if index is None:raise ValueError('Mounting hole target absent')
    s['mounting_holes'][index]=hole
  elif k=='set_attachment_frame':
   frame=copy.deepcopy(operation['frame']);index=next((i for i,f in enumerate(s['attachment_frames']) if f['id']==frame['id']),None)
   if index is None:s['attachment_frames'].append(frame)
   else:s['attachment_frames'][index]=frame
   if operation['mounted_body_id'] is not None:
    s['mounted_bodies']=[m for m in s['mounted_bodies'] if m['body_id']!=operation['mounted_body_id']]+[{'body_id':operation['mounted_body_id'],'frame_id':frame['id']}]
  elif k=='attach_part_to_joint':
   if s.get('frame_attachment'):raise ValueError('Fixed and joint attachments cannot conflict')
   s['joint_attachment']={'joint_body_id':operation['joint_body_id'],'frame_id':operation['frame_id']}
  elif k=='attach_part_to_mount':
   from .mobility import PARAMETERS as MOBILITY
   if s['family'] not in MOBILITY or s['joint_attachment']:raise ValueError('Fixed mount attachment requires an unattached mobility part')
   s['frame_attachment']={'mount_body_id':operation['mount_body_id'],'frame_id':operation['frame_id']}
  else:raise ValueError('Unsupported shape operation')
  s['geometry_revision']+=1
 s['physical']=physical(s,s['physical']['mass_kg'])
 project['world']['revision']+=1
