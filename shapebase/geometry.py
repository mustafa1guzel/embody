"""Deterministic faceted 2.5D profiles, true hole contours, no CAD solid claim."""
import math,hashlib,copy
from pathlib import Path
from physics.contracts import digest
from .model import validate_shape,dimensions,hole_center,frame_positions,PARAMETERS,SHAPE_SPEC,MIN_WALL_M

def outline(length,width,radius=0):
 if radius==0:return [[-length/2,-width/2],[length/2,-width/2],[length/2,width/2],[-length/2,width/2]]
 points=[]
 for cx,cy,start in [(length/2-radius,width/2-radius,0),(-length/2+radius,width/2-radius,math.pi/2),(-length/2+radius,-width/2+radius,math.pi),(length/2-radius,-width/2+radius,3*math.pi/2)]:
  for i in range(9):
   a=start+i*math.pi/16;p=[round(cx+radius*math.cos(a),12),round(cy+radius*math.sin(a),12)]
   if not points or p!=points[-1]:points.append(p)
 if points[-1]==points[0]:points.pop()
 return points

def generate(spec):
 s=validate_shape(spec);p=s['parameters'];x,y,z=dimensions(s);f=s['family'];sections=[]
 holes=[{'id':h['id'],'center_m':hole_center(s,h),'radius_m':h['diameter_m']/2} for h in s['mounting_holes']]
 if f=='wheel':
  from .mobility import hub_radius
  bore=p['axle_hole_diameter_m']/2;hub=hub_radius(p)
  circle=lambda r:[[round(r*math.cos(i*math.tau/32),12),round(r*math.sin(i*math.tau/32),12)] for i in range(32)]
  holes=[{'id':'axle_hole','center_m':[0.,0.,0.],'radius_m':bore}]
  sections=[{'id':'tire','outline_m':circle(x/2),'holes':[{'id':'hub_void','center_m':[0.,0.,0.],'radius_m':hub}],'position_m':[0,0,-p['thickness_m']/2],'depth_m':p['thickness_m']},{'id':'hub','outline_m':circle(hub),'holes':holes,'position_m':[0,0,-z/2],'depth_m':z}]
 elif f not in ('shaft','axle'):
  radius=p.get('end_radius_m',p.get('corner_radius_m',0));depth=p['thickness_m'] if f=='motor_bracket' else z
  sections.append({'id':'main','outline_m':outline(x,y,radius),'holes':holes,'position_m':[0,0,-z/2],'depth_m':depth})
  if f=='motor_bracket':sections.append({'id':'upright','outline_m':outline(x,p['thickness_m']),'holes':[],'position_m':[0,-y/2+p['thickness_m']/2,-z/2+p['thickness_m']],'depth_m':z-p['thickness_m']})
 return {'shape_id':s['id'],'body_id':s['body_id'],'geometry_revision':s['geometry_revision'],'shape_sha256':digest(s),'representation':'FACETED_PARAMETRIC_EXTRUSIONS' if f not in ('shaft','axle') else 'FACETED_SOLID_CYLINDER','dimensions_m':[x,y,z],'sections':sections,'cylinder':{'radius_m':x/2,'length_m':z,'radial_segments':32} if f in ('shaft','axle') else None,'holes':holes,'attachment_frames':frame_positions(s),'physical':s['physical'],'limitations':['No BREP, CAD booleans, STEP export or fabrication proof.','Collision proxy is separate; through-holes/rounding are omitted for envelope parts.']}

def library(project):
 specs=project.get('shape_specs',[])
 return {'schema_version':1,'families':list(PARAMETERS),'parameter_constraints':copy.deepcopy(PARAMETERS),'minimum_wall_m':MIN_WALL_M,'shape_spec_schema':copy.deepcopy(SHAPE_SPEC),'parts':[{'spec':s,'geometry':generate(s)} for s in specs],'source_sha256':{str(p.relative_to(Path(__file__).resolve().parents[1])):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path(__file__).parent.glob('*.py'))},'ai_status':'DETERMINISTIC_LOCAL; no model request or genuine AI design claim','physical_scope':'Native primitive proxy only; explicit mass, uniform proxy inertia, no inferred material density','mobility_scope':'Toy rover / fixed quad-frame concepts only. No suspension, steering geometry, tire compliance, propeller aerodynamics, thrust, flight control, vehicle shell or certified safety. Wheel hinges are bounded +/- pi; chassis battery/controller datums are not electrical bindings.'}
