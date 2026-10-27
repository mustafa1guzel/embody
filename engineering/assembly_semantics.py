"""Read-only identity/relationship preflight, never an action executor or repairer.

This symbolic inventory explains necessary conditions. Existing copied-state,
geometry, structural and native validators remain authoritative afterward.
"""
import copy
from shapebase.mobility import SOURCES, frame_rotation
from world.objects import primitive

SHAPE_OPS={'update_shape_parameter','add_mounting_hole','update_mounting_hole','set_attachment_frame','attach_part_to_joint','attach_part_to_mount'}
IDENTIFIERS={
 'part_id':'ShapeSpec.id, not ShapeSpec.body_id. Shape operations target this namespace.',
 'body_id':'World object id. A ShapeSpec owns exactly one proxy body_id; that proxy is not its part id.',
 'joint_body_id':'World body id whose joint is an existing revolute +Z joint. No separate user joint-id namespace: native joint_<body_id> names are compiler output, never tool arguments.',
 'frame_id':'Local to the TARGET ShapeSpec. The same frame id may exist on different parts. Parent owner frames are used in registration, not in child attach_part_to_*.',
}

def protected_frames(family):
 return [{'id':s,'source':s,'hole_id':None,'rotation_rad':frame_rotation({'family':family},s)} for s in SOURCES.get(family,())]

def contract(project):
 return {'identifier_namespaces':IDENTIFIERS,'operation_relationships':{
 'set_attachment_frame':{'target':'OWNER ShapeSpec part_id','frame':'Frame on that OWNER; protected mobility datums retain exact id/source/rotation','mounted_body_id':'nullable World child body_id; if supplied its parent MUST equal owner.body_id; never owner.body_id or another ShapeSpec proxy'},
 'attach_part_to_joint':{'target':'CHILD ShapeSpec part_id','joint_body_id':'actual parent World joint body_id','frame_id':'frame on the CHILD part (wheel: axle), NOT the parent axle endpoint frame'},
 'attach_part_to_mount':{'target':'CHILD ShapeSpec part_id','mount_body_id':'actual parent fixed World intermediary, joint=null and actuator=null','frame_id':'unrotated frame on the CHILD part (e.g. its own origin), NOT the chassis registration datum'}},
 'protected_datums':{f:protected_frames(f) for f in ('chassis','axle','wheel','motor_mount')},
 'frame_rules':'Built-in mobility frames are already generated. Register by setting the exact existing frame; do not rename or rotate it. Custom aliases do not replace required rover role datums. Null mounted_body_id creates/updates a local frame without registering a body.',
 'assembly_relationships':['Chassis part -> its proxy body -> fixed axle intermediary -> axle part proxy -> wheel hinge body -> wheel part proxy','Chassis part -> its proxy body -> fixed motor-plate intermediary -> motor_mount part proxy','The free root parents the chassis proxy, not the chassis mount intermediaries.'],
 'current_inventory':inventory(project),'preflight_scope':'Read-only symbolic namespace/reference/ownership check; PASS is not geometry, dynamics or safety proof. No ID translation or plan repair.'}

def inventory(project):
 return {'bodies':[{'body_id':o['id'],'parent_body_id':o['parent'],'joint':copy.deepcopy(o['joint']),'actuator_present':o['actuator'] is not None} for o in project['world']['objects']],
 'parts':[{'part_id':s['id'],'body_id':s['body_id'],'parent_body_id':s['parent_body_id'],'family':s['family'],'frames':copy.deepcopy(s['attachment_frames']),'protected_frame_ids':list(SOURCES.get(s['family'],())),'registered_children':copy.deepcopy(s['mounted_bodies']),'joint_attachment':copy.deepcopy(s['joint_attachment']),'fixed_attachment':copy.deepcopy(s.get('frame_attachment'))} for s in project.get('shape_specs',[])]}

def annotate_schema(schema):
 """Describe unchanged wire keys/types; no aliases or implicit coercion."""
 def visit(x):
  if isinstance(x,list):
   for v in x:visit(v)
  elif isinstance(x,dict):
   p=x.get('properties',{});kind=p.get('kind',{}).get('enum',[None])[0]
   if 'target' in p:p['target']={**p['target'],'description':IDENTIFIERS['part_id' if kind in SHAPE_OPS else 'body_id']}
   for key in p:
    if key.endswith('_part_id'):p[key]={**p[key],'description':IDENTIFIERS['part_id']}
    elif key.endswith('_body_id'):p[key]={**p[key],'description':IDENTIFIERS['joint_body_id' if key=='joint_body_id' else 'body_id']}
   for key,ns in [('part_id','part_id'),('body_id','body_id'),('parent_body_id','body_id'),('joint_body_id','joint_body_id'),('mount_body_id','body_id'),('mounted_body_id','body_id'),('frame_id','frame_id')]:
    if key in p:p[key]={**p[key],'description':IDENTIFIERS[ns]}
   if 'family' in p and 'body_id' in p:p['id']={**p['id'],'description':IDENTIFIERS['part_id']}
   if kind=='create_free_root':
    x['description']='Create one free World root with explicit mass, position and box dimensions. Uses existing valid free-joint defaults including unused range [-1,1]; no joint or parent argument accepted.'
    p['id']={**p['id'],'description':IDENTIFIERS['body_id']}
   if kind=='create_object':
    p['id']={**p['id'],'description':IDENTIFIERS['body_id']};p['parent']={**p['parent'],'description':'Actual World parent body_id, not a part ID. A mount registered by a ShapeSpec must parent to that owner.body_id.'}
   if 'source' in p and 'hole_id' in p:p['id']={**p['id'],'description':'Frame ID local to the owning ShapeSpec. Protected mobility datum ID must equal its canonical source; do not rename it.'}
   if 'motor_mount_parts' in p:
    for key,value in p['motor_mount_parts']['properties'].items():p['motor_mount_parts']['properties'][key]={**value,'description':IDENTIFIERS['part_id']}
   if kind in ('set_attachment_frame','attach_part_to_joint','attach_part_to_mount'):
    x['description']={'set_attachment_frame':'OWNER part target registers a World child of owner.body_id at an OWNER frame. Never invert target and mounted_body_id; protected datum identity/source/rotation remain exact.', 'attach_part_to_joint':'CHILD part target attaches its OWN frame to its actual parent +Z revolute World joint body. Wheel child frame is axle, not axle_left/right.', 'attach_part_to_mount':'CHILD part target attaches its OWN unrotated frame to its actual fixed parent World mount body. Parent registration is separate.'}[kind]
   for v in x.values():visit(v)
 visit(schema)
 return schema

def preflight(project,plan,order,ancestors):
 bodies={o['id']:copy.deepcopy(o) for o in project['world']['objects']};parts={s['id']:copy.deepcopy(s) for s in project.get('shape_specs',[])}
 origins={('body',k):None for k in bodies};origins.update({('part',k):None for k in parts});errors=[]
 steps={s['id']:s for s in plan['steps']};registrations={m['body_id']:(s['id'],m['frame_id']) for s in parts.values() for m in s['mounted_bodies']}
 def emit(code,message,field,actual,expected):
  errors.append({'code':code,'step_id':step,'operation_index':index,'field':field,'actual':copy.deepcopy(actual),'expected':expected,'message':message})
 def ref(ns,key,field):
  if (ns,key) not in origins:
   other='body' if ns=='part' else 'part';wrong=(other,key) in origins
   emit('WRONG_ID_NAMESPACE' if wrong else 'MISSING_REFERENCE',f'{field} requires an existing {ns} ID; {key!r} '+(f'is a {other} ID.' if wrong else 'does not exist yet.'),field,key,ns+'_id');return False
  origin=origins[(ns,key)]
  if origin is not None and origin!=step and origin not in ancestors[step]:emit('UNDECLARED_DEPENDENCY','Cross-batch reference requires an explicit transitive dependency.',field,key,origin)
  return True
 for step in order:
  for index,op in enumerate(steps[step]['operations']):
   k=op['kind']
   if k=='create_free_root':
    if ('body',op['id']) in origins:emit('DUPLICATE_ID','World body already exists.','id',op['id'],'unique body_id');continue
    b=primitive('dynamic_body',op['id']);b.update(mass_kg=op['mass_kg'],position_m=op['position_m'],dimensions_m=op['dimensions_m']);bodies[b['id']]=b;origins[('body',b['id'])]=step
   elif k=='create_object':
    if op['parent'] is not None:ref('body',op['parent'],'parent')
    if ('body',op['id']) in origins:emit('DUPLICATE_ID','World body already exists.','id',op['id'],'unique body_id');continue
    b=primitive(op['primitive'],op['id']);b['parent']=op['parent'];bodies[b['id']]=b;origins[('body',b['id'])]=step
   elif k=='create_parametric_part':
    p=copy.deepcopy(op['part']);pid=p['id'];bid=p['body_id']
    if p['parent_body_id'] is not None:ref('body',p['parent_body_id'],'part.parent_body_id')
    if ('part',pid) in origins or ('body',bid) in origins:emit('DUPLICATE_ID','Part or proxy body already exists.','part',pid,'unique part_id and body_id');continue
    p['attachment_frames']=[{'id':s,'source':s,'hole_id':None,'rotation_rad':[0,0,0]} for s in ('origin','top','bottom')]+[{'id':h['id'],'source':'hole','hole_id':h['id'],'rotation_rad':[0,0,0]} for h in p['mounting_holes']]+protected_frames(p['family'])
    p.update(joint_attachment=None,mounted_bodies=[]);parts[pid]=p;bodies[bid]={'id':bid,'parent':p['parent_body_id'],'joint':None,'actuator':None}
    origins[('part',pid)]=origins[('body',bid)]=step
   else:
    ns='part' if k in SHAPE_OPS else 'body';found=ref(ns,op['target'],'target')
    for key in ('mounted_body_id','mount_body_id','joint_body_id'):
     if op.get(key) is not None:ref('body',op[key],key)
    if k=='set_attachment_frame':
     f=op['frame'];family=next((fam for fam,src in SOURCES.items() if f['source'] in src),None)
     if family and f['rotation_rad']!=frame_rotation({'family':family},f['source']):emit('DATUM_ROTATION','Named mobility datum requires its canonical rotation.','frame.rotation_rad',f['rotation_rad'],frame_rotation({'family':family},f['source']))
     if op['mounted_body_id'] in {p['body_id'] for p in parts.values()}:emit('REGISTERED_PROXY_BODY','Register an explicit child intermediary, not a ShapeSpec proxy.','mounted_body_id',op['mounted_body_id'],'unowned child body_id')
    if not found:continue
    if ns=='body':
     if k=='create_joint':bodies[op['target']]['joint']=copy.deepcopy(op['joint'])
     if k=='set_actuator':bodies[op['target']]['actuator']=copy.deepcopy(op['actuator'])
     continue
    p=parts[op['target']];frames={f['id']:f for f in p['attachment_frames']}
    if k=='set_attachment_frame':
     f=op['frame'];protected={f['id']:f for f in protected_frames(p['family'])}
     if f['id'] in protected and f!=protected[f['id']]:emit('PROTECTED_DATUM','Protected datum id/source/rotation cannot be altered.','frame',f,protected[f['id']]);continue
     role_owners={plan['roles'][key] for key in ('chassis_part_id','front_axle_part_id','rear_axle_part_id')}
     if p['id'] in role_owners and op['mounted_body_id'] is not None and f['source'] in SOURCES.get(p['family'],()) and f['id']!=f['source']:emit('ROVER_DATUM_ALIAS','Assembly role registration uses the canonical datum ID; a custom alias cannot substitute for it.','frame.id',f['id'],f['source'])
     if f['source'] not in ('origin','top','bottom','hole',*SOURCES.get(p['family'],())):emit('UNSUPPORTED_DATUM','Frame source is unsupported by this owner family.','frame.source',f['source'],list(SOURCES.get(p['family'],())))
     child=bodies.get(op['mounted_body_id'])
     if child:
      if child['parent']!=p['body_id']:emit('MOUNT_PARENT','Registered child must be directly parented to owner.body_id.','mounted_body_id',child['parent'],p['body_id'])
      elif child['id'] in registrations and registrations[child['id']][0]!=p['id']:emit('DUPLICATE_MOUNT_OWNER','A body cannot be registered to two owning parts.','mounted_body_id',child['id'],'one owning part')
      else:registrations[child['id']]=(p['id'],f['id'])
     frames[f['id']]=copy.deepcopy(f);p['attachment_frames']=list(frames.values())
    elif k in ('attach_part_to_joint','attach_part_to_mount'):
     joint=k=='attach_part_to_joint';key='joint_body_id' if joint else 'mount_body_id';body=bodies.get(op[key]);fid=op['frame_id']
     if fid not in frames:emit('CHILD_FRAME_MISSING','Attachment frame_id belongs to the target child part, not its parent.','frame_id',fid,list(frames))
     elif not joint and frames[fid]['rotation_rad']!=[0,0,0]:emit('FIXED_FRAME_ROTATION','Fixed attachment requires an unrotated child-local frame.','frame_id',fid,'unrotated child frame')
     if body and p['parent_body_id']!=body['id']:emit('ATTACHMENT_PARENT','Attachment body must be the target part actual parent. ',key,body['id'],p['parent_body_id'])
     if body and joint and (not body['joint'] or body['joint']['kind']!='revolute' or body['joint']['axis']!=[0,0,1]):emit('JOINT_REQUIRED','joint_body_id must own an actual local +Z revolute joint.',key,body['id'],'parent revolute +Z joint body')
     if body and not joint and (body['joint'] or body['actuator']):emit('FIXED_MOUNT_REQUIRED','Fixed intermediary must have joint=null and actuator=null.',key,body['id'],'fixed parent body')
     if p['family']=='wheel' and fid!='axle':emit('WHEEL_LOCAL_DATUM','Wheel attachment uses its own coaxial axle datum.','frame_id',fid,'axle')
     if p.get('joint_attachment') and not joint or p.get('frame_attachment') and joint:emit('CONFLICTING_ATTACHMENT','A part cannot have both fixed and joint attachments.','target',p['id'],'one attachment type')
     p['joint_attachment' if joint else 'frame_attachment']={key:op[key],'frame_id':fid}
    elif k=='add_mounting_hole':
     h=op['hole'];p['attachment_frames'].append({'id':h['id'],'source':'hole','hole_id':h['id'],'rotation_rad':[0,0,0]})
 # Role constraints are independent observations; never invert/repair bad actions.
 step=None;index=None;r=plan['roles'];chassis=parts.get(r['chassis_part_id'])
 if chassis:
  for role in ('front_axle_part_id','rear_axle_part_id'):
   p=parts.get(r[role]);mount=bodies.get(p['parent_body_id']) if p else None
   if mount and mount['parent']!=chassis['body_id']:emit('ROLE_MOUNT_PARENT','Axle intermediary must be a direct child of the chassis proxy.','roles.'+role,mount['parent'],chassis['body_id'])
  for role,pid in r['motor_mount_parts'].items():
   p=parts.get(pid);mount=bodies.get(p['parent_body_id']) if p else None
   if mount and mount['parent']!=chassis['body_id']:emit('ROLE_MOUNT_PARENT','Motor-plate intermediary must be a direct child of the chassis proxy.','roles.motor_mount_parts.'+role,mount['parent'],chassis['body_id'])
 return {'status':'SEMANTIC_PREFLIGHT_FAIL' if errors else 'SEMANTIC_PREFLIGHT_PASS','diagnostics':errors,'errors':len(errors),'scope':'Necessary symbolic conditions only; existing typed/geometry/native validation still required. No actions applied or IDs translated.','new_native_steps':0}
