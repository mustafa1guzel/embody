"""Bounded mobility parameters/datums; no vehicle dynamics or material inference."""
import math
from world.schema import num

PARAMETERS={
 'wheel':{'outer_diameter_m':num(.03,.25),'thickness_m':num(.01,.08),'axle_hole_diameter_m':num(.002,.04),'hub_thickness_m':num(0,.02)},
 'axle':{'diameter_m':num(.005,.05),'length_m':num(.03,.6)},
 'chassis':{'length_m':num(.08,1),'width_m':num(.06,.6),'thickness_m':num(.005,.05),'corner_radius_m':num(.001,.1)},
 'motor_mount':{'length_m':num(.02,.3),'width_m':num(.02,.2),'thickness_m':num(.005,.03),'corner_radius_m':num(.001,.05)},
 'drone_arm':{'length_m':num(.05,.6),'width_m':num(.015,.08),'thickness_m':num(.005,.03)},
 'motor_pad':{'length_m':num(.02,.15),'width_m':num(.02,.15),'thickness_m':num(.005,.03),'corner_radius_m':num(.001,.05)},
}
# Datums are regenerated analytically. References are not inferred joints,
# certified mounting surfaces, bearings, electronics bindings or propellers.
SOURCES={'wheel':('axle',),'axle':('axle_left','axle_right'),
 'chassis':('front_axle','rear_axle','rear_left_mount','rear_right_mount','battery','controller','arm_east','arm_north','arm_west','arm_south'),
 'motor_mount':('motor_top',),'drone_arm':('root','motor_pad'),'motor_pad':('motor_top',)}
ALL_SOURCES=tuple(sorted({s for v in SOURCES.values() for s in v}))


def datum(s,source):
 p=s['parameters'];f=s['family']
 if source not in SOURCES.get(f,()):raise ValueError('Unsupported family mounting datum')
 if f=='wheel':return [0.,0.,0.]
 if f=='axle':return [0.,0.,p['length_m']/2*(-1 if source=='axle_left' else 1)]
 if f=='drone_arm':return [p['length_m']/2*(-1 if source=='root' else 1),0.,0.]
 if f in ('motor_mount','motor_pad'):return [0.,0.,p['thickness_m']/2]
 l,w,t=p['length_m'],p['width_m'],p['thickness_m']
 return {'front_axle':[l*.32,0.,-t/2],'rear_axle':[-l*.32,0.,-t/2],
 'rear_left_mount':[-l*.32,w*.3,t/2],'rear_right_mount':[-l*.32,-w*.3,t/2],
 'battery':[-l*.15,0.,t/2],'controller':[l*.15,0.,t/2],
 'arm_east':[l/2,0.,0.],'arm_north':[0.,w/2,0.],'arm_west':[-l/2,0.,0.],'arm_south':[0.,-w/2,0.]}[source]


def frame_rotation(s,source):
 if s['family']=='chassis':
  if source in ('front_axle','rear_axle'):return [math.pi/2,0.,0.]
  return [0.,0.,{'arm_north':math.pi/2,'arm_west':math.pi,'arm_south':-math.pi/2}.get(source,0.)]
 return [0.,0.,0.]


def hub_radius(p):
 return max((p['axle_hole_diameter_m']/2+.001)/math.cos(math.pi/32),p['outer_diameter_m']*.225)

def validate_parameters(s):
 p=s['parameters'];f=s['family']
 if f=='wheel':
  if p['outer_diameter_m']/2*math.cos(math.pi/32)-hub_radius(p)<.001-1e-12:raise ValueError('Wheel axle bore/hub/tire leaves insufficient faceted radial wall')
  if s['mounting_holes']:raise ValueError('Wheel bore uses axle_hole_diameter_m; arbitrary wheel holes unsupported')
 if f=='axle' and s['mounting_holes']:raise ValueError('Axle is a nominal solid cylinder; drilled axle holes unsupported')


def validate_wheel_support(s,objects,shapes):
 if s['family']!='wheel' or not (s['joint_attachment'] or s.get('frame_attachment')):return
 relation=s['joint_attachment'] or s.get('frame_attachment')
 if relation['frame_id']!='axle':raise ValueError('Wheel attachment must use its named coaxial axle datum')
 mount=objects.get(s['parent_body_id']);axle=next((p for p in shapes if p['body_id']==mount['parent'] and p['family']=='axle'),None) if mount else None
 if axle is None:raise ValueError('Declared wheel attachment requires a mount/joint directly on an actual axle ShapeSpec')
 reference=next((m for m in axle['mounted_bodies'] if m['body_id']==mount['id']),None)
 frames={f['id']:f for f in axle['attachment_frames']}
 if reference is None or frames[reference['frame_id']]['source'] not in ('axle_left','axle_right'):raise ValueError('Wheel support must reference an explicit axle end datum')
 clearance=s['parameters']['axle_hole_diameter_m']-axle['parameters']['diameter_m']
 if not .0002-1e-12<=clearance<=.004+1e-12:raise ValueError('Nominal axle/bore diametral clearance outside 0.0002..0.004 m; no fit certification')
