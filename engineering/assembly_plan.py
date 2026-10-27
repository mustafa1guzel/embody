"""AssemblyPlan: bounded existing actions + explicit DAG, never a new language."""
import copy,json,time
from jsonschema import Draft202012Validator
from world.schema import obj,ID
from .actions import SCHEMAS
from .assembly_semantics import annotate_schema

GOAL='Create a simple four-wheel toy rover with a rectangular chassis, two horizontal axles, four wheels and two rear motor mounting plates.\n\nKeep all mechanical components correctly connected.\n\nUse simple dimensions suitable for a small desktop robot and prepare the assembly for physical simulation.'
MAX_BATCHES=12
MAX_ACTIONS=96
ALLOWED={'create_free_root','create_object','move_object','rotate_object','set_geometry','set_shape','set_mass','create_joint','set_actuator','create_parametric_part','update_shape_parameter','add_mounting_hole','update_mounting_hole','set_attachment_frame','attach_part_to_joint','attach_part_to_mount'}
OPS={'type':'array','minItems':1,'maxItems':16,'items':{'anyOf':[copy.deepcopy(s) for s in SCHEMAS if s['properties']['kind']['enum'][0] in ALLOWED]}}
# No arbitrary floor/assets, deletion, source, environment or circuit operations.
for s in OPS['items']['anyOf']:
 if s['properties']['kind']['enum']==['create_parametric_part']:
  s['properties']['part']['anyOf']=[v for v in s['properties']['part']['anyOf'] if v['properties']['family']['const'] in ('wheel','axle','chassis','motor_mount')]
 if s['properties']['kind']['enum']==['create_object']:s['properties']['primitive']['enum']=['dynamic_body','rigid_link','anchor','revolute','motor']
TEXT=lambda n:{'type':'string','minLength':1,'maxLength':n}
STEP=obj({'id':ID,'depends_on':{'type':'array','items':ID,'maxItems':12},'purpose':TEXT(500),'operations':OPS})
WHEEL=obj({'part_id':ID,'joint_body_id':ID})
ROLES=obj({'root_body_id':ID,'chassis_part_id':ID,'front_axle_part_id':ID,'rear_axle_part_id':ID,
 'wheels':obj({k:WHEEL for k in ('front_left','front_right','rear_left','rear_right')}),
 'motor_mount_parts':obj({'left':ID,'right':ID})})
PLAN=obj({'schema_version':{'type':'integer','enum':[1]},'goal':TEXT(2000),'roles':ROLES,
 'assumptions':{'type':'array','items':TEXT(500),'minItems':1,'maxItems':8},
 'limitations':{'type':'array','items':TEXT(500),'minItems':1,'maxItems':12},
 'explanation':TEXT(2000),'steps':{'type':'array','items':STEP,'minItems':1,'maxItems':MAX_BATCHES}})

annotate_schema(PLAN)

class PlanError(ValueError):
 def __init__(self,message,diagnostics=None):
  super().__init__(message);self.diagnostics=copy.deepcopy(diagnostics or [])

def semantic_preflight(before,plan):
 from .assembly_semantics import preflight
 validated,order,ancestors=validate_plan(plan)
 return preflight(before,validated,order,ancestors)

def validate_plan(plan):
 try:
  if len(json.dumps(plan,allow_nan=False).encode())>100000:raise PlanError('Plan exceeds 100000 bytes')
  Draft202012Validator(PLAN).validate(plan)
 except PlanError:raise
 except Exception as exc:raise PlanError('Invalid exact AssemblyPlan schema: '+str(exc).splitlines()[0][:160]) from None
 if type(plan['schema_version']) is not int:raise PlanError('Exact integer plan version required')
 steps=plan['steps'];by={s['id']:s for s in steps}
 if len(by)!=len(steps):raise PlanError('Duplicate step identity')
 if sum(len(s['operations']) for s in steps)>MAX_ACTIONS:raise PlanError('Assembly action budget exhausted (96)')
 for s in steps:
  if len(set(s['depends_on']))!=len(s['depends_on']) or any(d not in by or d==s['id'] for d in s['depends_on']):raise PlanError('Unknown, duplicate or self dependency')
 order=[];ancestors={};remaining=list(by)
 while remaining:
  ready=next((k for k in remaining if all(d in ancestors for d in by[k]['depends_on'])),None)
  if ready is None:raise PlanError('Cyclic assembly dependency graph')
  deps=set(by[ready]['depends_on']);ancestors[ready]=deps|set().union(*(ancestors[d] for d in deps)) if deps else set()
  order.append(ready);remaining.remove(ready)
 return copy.deepcopy(plan),order,ancestors


def resources(operation):
 k=operation['kind'];created=[];refs=[]
 if k=='create_free_root':created=[('body',operation['id'])]
 elif k=='create_object':
  created=[('body',operation['id'])];refs=[('body',operation['parent'])] if operation['parent'] else []
 elif k=='create_parametric_part':
  p=operation['part'];created=[('part',p['id']),('body',p['body_id'])];refs=[('body',p['parent_body_id'])] if p['parent_body_id'] else []
 else:
  refs=[('part' if k in {'update_shape_parameter','add_mounting_hole','update_mounting_hole','set_attachment_frame','attach_part_to_joint','attach_part_to_mount'} else 'body',operation['target'])]
  for field in ('joint_body_id','mount_body_id','mounted_body_id'):
   if operation.get(field) is not None:refs.append(('body',operation[field]))
 return created,refs


def construct(service,before,plan,*,deadline=None,action_budget=MAX_ACTIONS):
 plan,order,ancestors=validate_plan(plan)
 semantic=semantic_preflight(before,plan)
 from .assembly_validation import declaration_audit
 diagnostics=semantic['diagnostics']+declaration_audit(before,plan,order)['diagnostics']
 if diagnostics:
  first=diagnostics[0]
  raise PlanError(f"{len(diagnostics)} engineering error(s); {first['step_id']} operation {first['operation_index']}: {first['message']}",diagnostics)
 if not 0<action_budget<=MAX_ACTIONS:raise PlanError('Invalid local action budget')
 by={s['id']:s for s in plan['steps']};owners={('body',o['id']):None for o in before['world']['objects']}
 owners.update({('part',s['id']):None for s in before.get('shape_specs',[])})
 candidate=copy.deepcopy(before);trace=[];used=0
 from .project import identity
 for key in order:
  if deadline is not None and time.monotonic()>=deadline:raise PlanError('Assembly planning deadline exhausted')
  step=by[key];used+=len(step['operations'])
  if used>action_budget:raise PlanError('Assembly action budget exhausted')
  for op in step['operations']:
   created,refs=resources(op)
   for ref in refs:
    if ref not in owners:raise PlanError('Missing or forward construction reference: '+':'.join(ref))
    origin=owners[ref]
    if origin is not None and origin!=key and origin not in ancestors[key]:raise PlanError('Undeclared dependency for '+':'.join(ref))
   for resource in created:
    if resource in owners:raise PlanError('Duplicate construction identity: '+':'.join(resource))
    owners[resource]=key
  base_hash=identity(candidate);base_rev=candidate['revision']
  try:candidate,checks=service.preview(candidate,step['operations'])
  except (ValueError,TypeError,KeyError) as exc:raise PlanError('Step '+key+' rejected: '+str(exc)[:200]) from None
  trace.append({'step_id':key,'depends_on':step['depends_on'],'base_stage_sha256':base_hash,'base_stage_revision':base_rev,'result_stage_sha256':identity(candidate),'result_stage_revision':candidate['revision'],'operation_count':len(step['operations']),'validation':checks})
 if deadline is not None and time.monotonic()>=deadline:raise PlanError('Assembly planning deadline exhausted')
 # Atomic aggregate revision, not a silent rebase. All private stage revisions
 # above remain evidence; one later explicit commit increments head once.
 candidate['revision']=before['revision']+1
 from .project import validate
 return validate(candidate),{'schedule':order,'total_actions':used,'stage_trace':trace,'revision_policy':'Private stages increment locally; one aggregate proposal/commit increments authoritative revision once.'}
