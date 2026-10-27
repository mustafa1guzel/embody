"""Whole-plan assessment without repair, dynamics or authoritative writes."""
import copy,math
from jsonschema import Draft202012Validator
from world.objects import primitive
from world.schema import JOINT,MOTOR
from shapebase.model import create_shape
from .assembly_rover import CRITERIA

def declaration_audit(before,plan,order):
 """Read-only declaration accounting; only EngineeringService builds projects.

Collect independent issues even when a different batch would fail first. This
does not infer corrected IDs or generate an executable corrected candidate.
"""
 bodies={o['id']:{'value':copy.deepcopy(o),'mass_source':'EXISTING_HEAD','location':(None,None)} for o in before['world']['objects']};parts={};issues=[]
 steps={s['id']:s for s in plan['steps']}
 def issue(code,message,field,actual,expected,location):
  issues.append({'code':code,'message':message,'field':field,'actual':copy.deepcopy(actual),'expected':expected,'step_id':location[0],'operation_index':location[1]})
 for step in order:
  for index,op in enumerate(steps[step]['operations']):
   k=op['kind'];loc=(step,index)
   if k in ('create_object','create_free_root'):
    o=primitive('dynamic_body' if k=='create_free_root' else op['primitive'],op['id'])
    if k=='create_free_root':o.update(mass_kg=op['mass_kg'],position_m=op['position_m'],dimensions_m=op['dimensions_m'])
    else:o['parent']=op['parent']
    bodies[o['id']]={'value':o,'mass_source':'EXPLICIT_PLAN_ARGUMENT' if k=='create_free_root' else 'EXISTING_PRIMITIVE_DEFAULT','location':loc,'joint_location':loc,'actuator_location':loc}
   elif k=='create_parametric_part':
    p=copy.deepcopy(op['part']);parts[p['id']]={'input':p,'location':loc}
    bodies[p['body_id']]={'value':{'id':p['body_id'],'mass_kg':p['mass_kg'],'parent':p['parent_body_id'],'joint':None,'actuator':None,'geometry':'cylinder' if p['family'] in ('axle','wheel') else 'box'},'mass_source':'EXPLICIT_PLAN_ARGUMENT','location':loc}
   elif k in ('set_mass','create_joint','set_actuator','set_geometry','set_shape','move_object','rotate_object') and op['target'] in bodies:
    key={'set_mass':'mass_kg','create_joint':'joint','set_actuator':'actuator','set_geometry':'dimensions_m','set_shape':'geometry','move_object':'position_m','rotate_object':'rotation_rad'}[k]
    b=bodies[op['target']];b['value'][key]=copy.deepcopy(op[key])
    if k=='set_mass':b['mass_source']='EXPLICIT_PLAN_ARGUMENT'
    if k=='create_joint':b['joint_location']=loc
    if k=='set_actuator':b['actuator_location']=loc
   elif k=='update_shape_parameter' and op['target'] in parts:parts[op['target']]['input']['parameters'][op['parameter']]=op['value']
   elif k in ('add_mounting_hole','update_mounting_hole') and op['target'] in parts:
    holes=parts[op['target']]['input']['mounting_holes'];h=copy.deepcopy(op['hole'])
    if k=='add_mounting_hole':holes.append(h)
    else:
     for n,old in enumerate(holes):
      if old['id']==h['id']:holes[n]=h;break
   # Validate every supplied joint immediately; do not normalize even a later
   # overwritten invalid declaration. Existing typed World checks remain final.
   if k=='create_joint' and op['joint']:
    j=op['joint']
    if not Draft202012Validator(JOINT).is_valid(j):issue('JOINT_SCHEMA','Invalid exact joint declaration.','joint',j,'World JOINT schema',loc);continue
    lo,hi=j['range']
    if lo>=hi or not lo<=j['initial_position']<=hi:issue('JOINT_RANGE','Joint range must be ordered and include the initial position.','joint.range',j['range'],'lower < upper; lower <= initial <= upper',loc)
    if abs(sum(x*x for x in j['axis'])-1)>1e-10:issue('JOINT_AXIS','Joint axis must be unit length.','joint.axis',j['axis'],'unit vector',loc)
    if j['kind']=='revolute' and (lo < -math.pi or hi > math.pi):issue('REVOLUTE_RANGE','Revolute limits cannot exceed exact +/-pi.','joint.range',j['range'],[-math.pi,math.pi],loc)
    if j['kind']=='prismatic' and (lo < -2 or hi > 2):issue('PRISMATIC_RANGE','Prismatic limits exceed supported travel.','joint.range',j['range'],[-2,2],loc)
    if j['kind']=='free' and (j['range']!=[-1,1] or j['initial_position']!=0 or j['initial_velocity']!=0 or j['damping']!=0):issue('FREE_ROOT_CONTRACT','Use create_free_root; legacy free joints require the exact existing unused range and zero scalar state.','joint',j,'range [-1,1], zero initial position/velocity/damping',loc)
 for pid,entry in parts.items():
  try:create_shape(entry['input'],before['id'])
  except (ValueError,KeyError,TypeError) as exc:issue('SHAPE_GEOMETRY',str(exc)[:250],'part',pid,'existing ShapeSpec geometry/clearance contract',entry['location'])
 allocation=[]
 for bid,entry in bodies.items():
  o=entry['value'];loc=entry['location'];mass=o['mass_kg'];allocation.append({'body_id':bid,'mass_kg':mass,'source':entry['mass_source'],'parent_body_id':o.get('parent')})
  a=o.get('actuator');j=o.get('joint')
  if a:
   if not Draft202012Validator(MOTOR).is_valid(a):issue('ACTUATOR_SCHEMA','Actuator does not match the exact MOTOR schema.','actuator',a,'World MOTOR schema',entry.get('actuator_location',loc))
   elif not j or j['kind']=='free' or abs(a['command'])>a['limit'] or a['unit']!=('N*m' if j['kind']=='revolute' else 'N'):issue('ACTUATOR_CONTRACT','Actuator requires a bounded scalar joint, matching unit and command within authority.','actuator',a,'valid scalar joint and abs(command)<=limit',entry.get('actuator_location',loc))
  if j and j['kind']=='free' and (o.get('parent') is not None or a):issue('FREE_ROOT_PARENT','Free joint is permitted only at an unactuated root.','parent',o.get('parent'),'null parent and actuator',loc)
  d=o.get('dimensions_m')
  if d and (o.get('geometry')=='sphere' and not d[0]==d[1]==d[2] or o.get('geometry') in ('cylinder','capsule') and d[0]!=d[1] or o.get('geometry')=='capsule' and d[2]<=d[0]):issue('WORLD_GEOMETRY','Primitive dimensions violate the existing World geometry contract.','dimensions_m',d,'supported nominal primitive dimensions',loc)
 total=math.fsum(e['mass_kg'] for e in allocation)
 if total>CRITERIA['max_total_mass_kg']:issue('TOTAL_MASS','Declared and default masses exceed the unchanged rover envelope.','total_mass_kg',total,CRITERIA['max_total_mass_kg'],(None,None))
 wheel_roles=plan['roles']['wheels']
 for role,r in wheel_roles.items():
  entry=bodies.get(r['joint_body_id']);a=entry['value'].get('actuator') if entry else None
  if role.startswith('rear') and (not a or a['limit']>CRITERIA['max_motor_authority_nm'] or not CRITERIA['min_abs_motor_command_nm']<=abs(a['command'])<=CRITERIA['max_motor_command_nm']):issue('ROVER_ACTUATOR','Rear actuator must satisfy fixed nonzero command/authority bounds.','roles.wheels.'+role,a,'fixed CRITERIA rear motor limits',(None,None))
  if role.startswith('front') and a:issue('FRONT_PASSIVE','Front wheel joints must remain passive.','roles.wheels.'+role,a,None,(None,None))
 return {'diagnostics':issues,'mass_allocation':allocation,'total_mass_kg':total,'mass_limit_kg':CRITERIA['max_total_mass_kg'],'scope':'Declaration/necessary-condition audit only; geometry/native compilation and measured dynamics are separate gates.'}

def assess(service,before,plan):
 from .assembly_plan import validate_plan,semantic_preflight,construct
 report={'status':'REJECTED','diagnostics':[],'stages':{},'native':'NOT_EXECUTED','new_native_steps':0}
 try:validated,order,_=validate_plan(plan)
 except (ValueError,TypeError,KeyError) as exc:
  report['diagnostics']=[{'code':'PLAN_SCHEMA_OR_DAG','message':str(exc)[:500],'step_id':None,'operation_index':None,'field':'plan','actual':None,'expected':'exact bounded plan and acyclic schedule'}];return report
 report['stages']['schema_dag']='PASS';sem=semantic_preflight(before,validated);declarations=declaration_audit(before,validated,order)
 report.update(declarations);report['diagnostics']=sem['diagnostics']+declarations['diagnostics'];report['stages']['semantic']='PASS' if not sem['diagnostics'] else 'FAIL';report['stages']['declarations']='PASS' if not declarations['diagnostics'] else 'FAIL'
 if report['diagnostics']:return report
 try:
  candidate,trace=construct(service,before,validated)
  from .assembly_rover import structural
  proof=structural(candidate,validated['roles'])
 except (ValueError,TypeError,KeyError) as exc:
  report['diagnostics']=[{'code':'COMPILED_CONSTRUCTION','message':str(exc)[:500],'step_id':None,'operation_index':None,'field':'plan','actual':None,'expected':'existing typed geometry, World, mounting and structural contracts'}];report['stages']['typed_geometry_compile']='FAIL';return report
 report['status']='COMPILED_REVIEW_READY';report['stages']['typed_geometry_compile']='PASS';report['compiled_contract_sha256']=proof['compiled']['contract_sha256'];report['proposed_project_sha256']=__import__('engineering.project',fromlist=['identity']).identity(candidate)
 from .assembly_direction import kinematics
 report['direction_semantics']=kinematics(candidate,validated['roles'])
 report['physical_requirements']=proof['criteria'];report['physical_status']='PENDING_EXPLICIT_NATIVE_PREVIEW_AND_REPLAY'
 return report
