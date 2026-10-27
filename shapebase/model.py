"""ShapeSpec v1: SI data, stable feature IDs and explicitly limited physics."""
import copy,math,json
from jsonschema import Draft202012Validator
from world.schema import obj,ID,num,vec
from physics.contracts import digest

LEGACY_FAMILIES=('rounded_link','drilled_plate','motor_bracket','shaft','structural_support')
from .mobility import PARAMETERS as MOBILITY_PARAMETERS,SOURCES,ALL_SOURCES,datum,frame_rotation,validate_parameters,validate_wheel_support
FAMILIES=LEGACY_FAMILIES+tuple(MOBILITY_PARAMETERS)
PARAMETERS={
 'rounded_link':{'length_m':num(.03,1),'width_m':num(.01,.3),'thickness_m':num(.005,.1),'end_radius_m':num(.001,.15)},
 'drilled_plate':{'length_m':num(.02,1),'width_m':num(.01,.5),'thickness_m':num(.005,.1),'corner_radius_m':num(.001,.15)},
 'motor_bracket':{'length_m':num(.03,1),'width_m':num(.02,.5),'thickness_m':num(.005,.05),'height_m':num(.02,.5)},
 'shaft':{'diameter_m':num(.005,.3),'length_m':num(.01,1)},
 'structural_support':{'length_m':num(.01,1),'width_m':num(.01,.5),'height_m':num(.01,1)},
}
PARAMETERS.update(MOBILITY_PARAMETERS)
FEATURE_ID={'type':'string','pattern':'^[A-Za-z][A-Za-z0-9_]{0,23}$','maxLength':24}
HOLE=obj({'id':FEATURE_ID,'diameter_m':num(.002,.05),'u':num(-.49,.49),'v':num(-.49,.49)})
FRAME=obj({'id':FEATURE_ID,'source':{'enum':['origin','hole','top','bottom',*ALL_SOURCES]},'hole_id':{'anyOf':[FEATURE_ID,{'type':'null'}]},'rotation_rad':vec(-math.pi,math.pi)})
JOINT_ATTACHMENT=obj({'joint_body_id':ID,'frame_id':FEATURE_ID})
MOUNTED_BODY=obj({'body_id':ID,'frame_id':FEATURE_ID})
STRINGS={'type':'array','items':{'type':'string'},'maxItems':8}
PHYSICAL=obj({'representation':{'enum':['ENVELOPE_BOX','SOLID_BOX','SOLID_CYLINDER']},'accuracy':{'enum':['APPROXIMATE','EXACT_SUPPORTED_PRIMITIVE']},'mass_kg':num(0,100),'mass_source':{'const':'EXPLICIT_USER_VALUE_KG'},'density_source':{'const':'UNKNOWN_NOT_INFERRED'},'inertia_source':{'const':'MUJOCO_UNIFORM_COLLISION_PROXY'},'included_features':STRINGS,'omitted_features':STRINGS})
VISUAL=obj({'generator':{'const':'SHAPEBASE_FACETED_V1'},'arc_segments_per_quadrant':{'const':8},'cad_solid_status':{'const':'NOT_BREP_NO_STEP_EXPORT'}})
COMMON={'schema_version':{'const':1},'id':ID,'body_id':ID,'assembly_id':ID,'geometry_revision':{'type':'integer','minimum':0,'maximum':999999},'units':{'const':'SI'},'parent_body_id':{'anyOf':[ID,{'type':'null'}]},'position_m':vec(-10,10),'rotation_rad':vec(-math.pi,math.pi),'mounting_holes':{'type':'array','items':HOLE,'maxItems':8},'attachment_frames':{'type':'array','items':FRAME,'minItems':1,'maxItems':12},'joint_attachment':{'anyOf':[JOINT_ATTACHMENT,{'type':'null'}]},'mounted_bodies':{'type':'array','items':MOUNTED_BODY,'maxItems':8},'visual':VISUAL,'physical':PHYSICAL}
SHAPE_SPEC={'oneOf':[obj({**COMMON,'family':{'const':family},'parameters':obj(fields)}) for family,fields in PARAMETERS.items()]}
FRAME_ATTACHMENT=obj({'mount_body_id':ID,'frame_id':FEATURE_ID})
for variant in SHAPE_SPEC['oneOf']:
 if variant['properties']['family']['const'] in MOBILITY_PARAMETERS:variant['properties']['frame_attachment']=FRAME_ATTACHMENT
 if variant['properties']['family']['const']=='chassis':
  variant['properties']['attachment_frames']=copy.deepcopy(COMMON['attachment_frames']);variant['properties']['attachment_frames']['maxItems']=20
CREATE_INPUT={'anyOf':[obj({'id':ID,'body_id':ID,'family':{'const':family},'parameters':obj(fields),'parent_body_id':{'anyOf':[ID,{'type':'null'}]},'position_m':vec(-10,10),'rotation_rad':vec(-math.pi,math.pi),'mass_kg':num(0,100),'mounting_holes':{'type':'array','items':HOLE,'maxItems':8}}) for family,fields in PARAMETERS.items()]}
MIN_WALL_M=.001

def dimensions(s):
 p=s['parameters'];f=s['family']
 if f in ('shaft','axle'):return [p['diameter_m'],p['diameter_m'],p['length_m']]
 if f=='wheel':return [p['outer_diameter_m'],p['outer_diameter_m'],p['thickness_m']+p['hub_thickness_m']]
 return [p['length_m'],p['width_m'],p['height_m'] if f in ('motor_bracket','structural_support') else p['thickness_m']]

def hole_center(s,h):
 x,y,z=dimensions(s)
 return [h['u']*x,h['v']*y,(-z/2+s['parameters']['thickness_m']/2) if s['family']=='motor_bracket' else 0.]

def physical(s,mass):
 f=s['family'];exact=f in ('shaft','axle','structural_support')
 if f=='wheel':return {'representation':'SOLID_CYLINDER','accuracy':'APPROXIMATE','mass_kg':mass,'mass_source':'EXPLICIT_USER_VALUE_KG','density_source':'UNKNOWN_NOT_INFERRED','inertia_source':'MUJOCO_UNIFORM_COLLISION_PROXY','included_features':['Nominal outer cylinder envelope including hub depth','Explicit mass with uniform proxy inertia'],'omitted_features':['Axle through-bore; proxy is solid across opening','Tire/hub profile, tread, compliance and bearing fit','Actual material distribution and manufacturing detail']}
 return {'representation':'SOLID_CYLINDER' if f in ('shaft','axle') else 'SOLID_BOX' if f=='structural_support' else 'ENVELOPE_BOX','accuracy':'EXACT_SUPPORTED_PRIMITIVE' if exact else 'APPROXIMATE','mass_kg':mass,'mass_source':'EXPLICIT_USER_VALUE_KG','density_source':'UNKNOWN_NOT_INFERRED','inertia_source':'MUJOCO_UNIFORM_COLLISION_PROXY','included_features':['Nominal solid cylinder and local pose' if f in ('shaft','axle') else 'Nominal box extents and local pose','Explicit mass with uniform proxy inertia'],'omitted_features':[] if exact else (['Empty L-section volume'] if f=='motor_bracket' else [] if f=='drone_arm' else ['Rounded outer corners'])+['Mounting through-holes; proxy is solid across openings','Actual material distribution and manufacturing detail']}

def frame_positions(s):
 holes={h['id']:h for h in s['mounting_holes']};z=dimensions(s)[2];result=[]
 for frame in s['attachment_frames']:
  source=frame['source'];position=hole_center(s,holes[frame['hole_id']]) if source=='hole' else [0.,0.,z/2 if source=='top' else -z/2 if source=='bottom' else 0.] if source in ('origin','top','bottom') else datum(s,source)
  result.append({'id':frame['id'],'position_m':position,'rotation_rad':frame['rotation_rad'],'source':source,'hole_id':frame['hole_id']})
 return result

def rotate_z(v,angle):
 c=math.cos(angle);s=math.sin(angle);return [c*v[0]-s*v[1],s*v[0]+c*v[1],v[2]]

def validate_shape(s):
 json.dumps(s,allow_nan=False)
 if not Draft202012Validator(SHAPE_SPEC).is_valid(s):raise ValueError('Invalid exact ShapeSpec schema')
 if type(s['schema_version']) is not int or type(s['geometry_revision']) is not int:raise ValueError('Exact integer shape revision required')
 if s['rotation_rad'][:2]!=[0,0]:raise ValueError('SHAPEBASE supports local Z orientation only')
 p=s['parameters'];f=s['family'];x,y,z=dimensions(s)
 validate_parameters(s)
 radius=p.get('end_radius_m',p.get('corner_radius_m',0))
 if f=='rounded_link' and x<y:raise ValueError('Link length must be at least width')
 if radius>min(x,y)/2:raise ValueError('End/corner radius exceeds supported boundary')
 if f=='motor_bracket' and (p['height_m']<=2*p['thickness_m'] or p['width_m']<=3*p['thickness_m']):raise ValueError('Bracket needs clearance beyond flange/base thickness')
 if f in ('shaft','structural_support') and s['mounting_holes']:raise ValueError('Holes unsupported for solid shaft/support')
 if f=='rounded_link' and len(s['mounting_holes'])<2:raise ValueError('Rounded link requires at least two mounting holes')
 ids=set()
 for h in s['mounting_holes']:
  if h['id'] in ids or h['id'] in ('origin','top','bottom',*ALL_SOURCES):raise ValueError('Duplicate/reserved mounting hole identity')
  ids.add(h['id']);cx,cy,_=hole_center(s,h);r=h['diameter_m']/2
  qx=abs(cx)-(x/2-radius);qy=abs(cy)-(y/2-radius)
  sd=math.hypot(max(qx,0),max(qy,0))+min(max(qx,qy),0)-radius
  if sd+r+MIN_WALL_M>1e-12:raise ValueError('Mounting hole outside part boundary or minimum wall')
  if f=='motor_bracket' and cy-r<-y/2+p['thickness_m']+MIN_WALL_M:raise ValueError('Hole intersects bracket upright')
 for i,a in enumerate(s['mounting_holes']):
  for b in s['mounting_holes'][i+1:]:
   ca=hole_center(s,a);cb=hole_center(s,b)
   if math.dist(ca,cb)<(a['diameter_m']+b['diameter_m'])/2+MIN_WALL_M-1e-12:raise ValueError('Overlapping mounting holes or insufficient wall')
 frames={a['id']:a for a in s['attachment_frames']}
 if len(frames)!=len(s['attachment_frames']):raise ValueError('Duplicate attachment frame identity')
 for source in SOURCES.get(f,()):
  if source not in frames or frames[source]!={'id':source,'source':source,'hole_id':None,'rotation_rad':frame_rotation(s,source)}:raise ValueError('Required stable mobility datum altered or missing')
 for a in frames.values():
  if a['source'] in ALL_SOURCES and a['source'] not in SOURCES.get(f,()):raise ValueError('Datum unsupported for this part family')
  expected_rotation=frame_rotation(s,a['source']) if a['source'] in ALL_SOURCES else None
  if (expected_rotation is not None and a['rotation_rad']!=expected_rotation) or (expected_rotation is None and a['rotation_rad'][:2]!=[0,0]) or (a['source']=='hole')!=(a['hole_id'] is not None) or a['hole_id'] is not None and a['hole_id'] not in ids:raise ValueError('Invalid attachment source/orientation')
 if s.get('frame_attachment') and (s['joint_attachment'] or s['frame_attachment']['frame_id'] not in frames):raise ValueError('Conflicting or missing fixed mounting frame')
 if s['joint_attachment'] and s['joint_attachment']['frame_id'] not in frames:raise ValueError('Joint attachment frame absent')
 if len({m['body_id'] for m in s['mounted_bodies']})!=len(s['mounted_bodies']) or any(m['frame_id'] not in frames for m in s['mounted_bodies']):raise ValueError('Invalid mounted body references')
 if s['physical']!=physical(s,s['physical']['mass_kg']):raise ValueError('Physical representation claims differ from supported geometry')
 return copy.deepcopy(s)

def create_shape(data,assembly_id):
 json.dumps(data,allow_nan=False)
 if not Draft202012Validator(CREATE_INPUT).is_valid(data):raise ValueError('Invalid create_parametric_part input')
 d=copy.deepcopy(data);mass=d.pop('mass_kg')
 s={**d,'assembly_id':assembly_id,'schema_version':1,'geometry_revision':0,'units':'SI','attachment_frames':[{'id':'origin','source':'origin','hole_id':None,'rotation_rad':[0,0,0]},*[{'id':h['id'],'source':'hole','hole_id':h['id'],'rotation_rad':[0,0,0]} for h in d['mounting_holes']]],'joint_attachment':None,'mounted_bodies':[],'visual':{'generator':'SHAPEBASE_FACETED_V1','arc_segments_per_quadrant':8,'cad_solid_status':'NOT_BREP_NO_STEP_EXPORT'}}
 if s['family'] in MOBILITY_PARAMETERS:
  for source in ('top','bottom'):s['attachment_frames'].append({'id':source,'source':source,'hole_id':None,'rotation_rad':[0,0,0]})
 for source in SOURCES.get(s['family'],()):s['attachment_frames'].append({'id':source,'source':source,'hole_id':None,'rotation_rad':frame_rotation(s,source)})
 s['physical']=physical(s,mass);return validate_shape(s)

def validate_project_shapes(project):
 shapes=project.get('shape_specs',[])
 if not isinstance(shapes,list) or len(shapes)>12:raise ValueError('At most twelve ShapeSpecs per project')
 objects={o['id']:o for o in project['world']['objects']};ids=set();bodies=set();mounted=set()
 for s in shapes:
  validate_shape(s)
  if s['id'] in ids or s['body_id'] in bodies or s['assembly_id']!=project['id']:raise ValueError('Duplicate or wrong assembly shape identity')
  ids.add(s['id']);bodies.add(s['body_id']);o=objects.get(s['body_id'])
  expected_geometry='cylinder' if s['family'] in ('shaft','axle','wheel') else 'box'
  if not o or o['parent']!=s['parent_body_id'] or o['geometry']!=expected_geometry or o['dimensions_m']!=dimensions(s) or o['position_m']!=s['position_m'] or o['rotation_rad']!=s['rotation_rad'] or o['mass_kg']!=s['physical']['mass_kg'] or o['joint'] or o['actuator']:raise ValueError('ShapeSpec differs from authoritative collision proxy')
  if o['contact']!={'enabled':True,'friction':[.7,.005,.0001]}:raise ValueError('Shape collision policy is fixed, not decorative')
  frames={f['id']:f for f in frame_positions(s)}
  a=s['joint_attachment']
  if a:
   j=objects.get(a['joint_body_id']);frame=frames[a['frame_id']]
   if not j or j['id']!=o['parent'] or not j['joint'] or j['joint']['kind']!='revolute' or j['joint']['axis']!=[0,0,1]:raise ValueError('Attachment requires actual parent revolute +Z joint body')
   expected=[-v for v in rotate_z(frame['position_m'],s['rotation_rad'][2])]
   if any(abs(v-w)>1e-12 for v,w in zip(expected,s['position_m'])):raise ValueError('Part attachment does not meet joint origin')
  a=s.get('frame_attachment')
  if a:
   mount=objects.get(a['mount_body_id']);frame=frames[a['frame_id']]
   if not mount or mount['id']!=o['parent'] or mount['joint'] or mount['actuator']:raise ValueError('Fixed attachment requires actual fixed parent mount body')
   if frame['rotation_rad']!=[0,0,0]:raise ValueError('Fixed part alignment requires an unrotated local datum')
   expected=[-v for v in rotate_z(frame['position_m'],s['rotation_rad'][2])]
   if any(abs(v-w)>1e-12 for v,w in zip(expected,s['position_m'])):raise ValueError('Part frame misses fixed mount origin')
  validate_wheel_support(s,objects,shapes)
  for m in s['mounted_bodies']:
   target=objects.get(m['body_id']);frame=frames[m['frame_id']]
   if m['body_id'] in mounted or not target or target['parent']!=s['body_id'] or target['position_m']!=frame['position_m'] or target['rotation_rad']!=frame['rotation_rad']:raise ValueError('Broken, duplicate or mismatched mounted body frame')
   if m['body_id'] in bodies or any(other['body_id']==m['body_id'] for other in shapes):raise ValueError('Use an explicit existing joint/mount body between parametric parts')
   mounted.add(m['body_id'])
 return shapes
