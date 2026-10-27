"""Unexecuted frozen two-turn assembly protocol, existing Responses/budget stack."""
import copy,json,time
from decimal import Decimal
from pathlib import Path
from importlib.metadata import version
from jsonschema import Draft202012Validator
from world.schema import obj
from shapebase.mobility import PARAMETERS
from engineering.shape_live import compact_schema
from core.agent.models import OpenAIResponsesAdapter
from core.agent.live_model import BudgetedOpenAIAdapter
from core.agent.api_budget import GPT54_POLICY,cost,BudgetBlocked
from core.agent.orchestration import SYSTEM_INSTRUCTIONS
from physics.contracts import canonical,digest
from robustness.contracts import file_hash
from workspace.data import decode_json
from .assembly_plan import GOAL,PLAN
from .assembly_rover import CRITERIA

INPUT_BOUND=49152
OUTPUT_BOUND=8192
ENDPOINT='https://api.openai.com/v1/responses'

def wire_schema(x):
 if isinstance(x,list):return [wire_schema(v) for v in x]
 if not isinstance(x,dict):return x
 x={k:wire_schema(v) for k,v in x.items()}
 if 'const' in x:x['enum']=[x.pop('const')]
 if 'enum' in x and 'type' not in x:
  if all(isinstance(v,str) for v in x['enum']):x['type']='string'
  else:raise ValueError('Explicit type required for nonstring enum')
 return x

def tools_for(stage):
 if stage==0:return [{'type':'function','name':'inspect_assembly_capabilities','strict':True,'description':'Inspect actual empty project identity, allowed part bounds, datum semantics, typed batch/dependency and native acceptance contracts. No execution or application.','parameters':obj({})}]
 if stage==1:
  params=obj({'expected_sha256':{'type':'string','pattern':'^[0-9a-f]{64}$','minLength':64,'maxLength':64},'expected_revision':{'type':'integer','minimum':0,'maximum':999999},'plan':PLAN})
  return [{'type':'function','name':'propose_assembly_plan','strict':True,'description':'Submit your own full AssemblyPlan of existing typed action batches and explicit DAG dependencies. Use kind, exact required fields and SI arguments. Each batch <=16 actions; total <=96 and <=12 batches. Model authors all action arguments; backend schedules/validates copied states and regenerates existing proxies/datums. No hidden template expansion, source execution, simulation or apply tool. Every reference created in an earlier batch must have a declared transitive dependency.','parameters':compact_schema(wire_schema(params))}]
 return []

def context():
 return {'user_request':GOAL,'instructions':'First inspect actual capabilities using the available inspection tool. After its actual observation, submit one structured plan using your own stable IDs, numerical dimensions/masses, assembly action arguments and dependency choices. No final plan, complete numerical example or prewritten action sequence is provided. Reason about connected mechanical structure and proxy limits. At most two turns, one call per turn. Do not claim application, simulation, steering or safety. No third request is available.'}

def observation(composer):
 from .project import identity
 from .assembly_semantics import contract
 from world.objects import primitive
 p=composer.service.current()
 from .assembly_direction import contract as direction_contract
 return {'project':{'id':p['id'],'revision':p['revision'],'sha256':identity(p),'world':p['world'],'shape_specs':p.get('shape_specs',[])},
 'physical_direction_contract':direction_contract(),
 'identity_and_attachment_contract':contract(p),
 'construction_defaults':{'recommended_mobile_root':'Use create_free_root with explicit id,mass_kg,position_m,dimensions_m; no parent or joint fields. Legacy free joint declarations are never corrected: range must be exactly [-1,1], zero scalar initial state/damping. Scalar revolute ranges must stay within exact +/-pi.',
 'primitive_defaults':{k:primitive(k,'declaration_example') for k in ('dynamic_body','rigid_link','revolute','motor','anchor')},'mass_allocation':'Every primitive and ShapeSpec contributes its own mass. Defaults are real masses, not negligible helpers. Total <=2 kg includes root, intermediaries and all nine shape proxies. Set helper masses and box dimensions explicitly; avoid duplicate overlapping envelopes. Fixed links require joint=null. Parent and part ownership contracts still apply.'},
 'families':{k:PARAMETERS[k] for k in ('wheel','axle','chassis','motor_mount')},
 'mass_contract':'All moving bodies need explicit >=.001 kg entered mass; no density inference. Total mass <=2 kg. Fixed links require moving parents; a moving root needs a free joint. Chassis length <=.6 and width <=.4 m.',
 'datum_contract':{'part_orientation':'ShapeSpec rotations local Z only; native cylinders use local Z as their axis.','chassis':'Stable front_axle/rear_axle datums at X +/-0.32*length, Z -thickness/2, fixed rotation [pi/2,0,0]. rear_left_mount/rear_right_mount at rear X and +/-0.3*width, top Z. These position actual intermediate bodies via set_attachment_frame.','axle':'Solid cylinder, endpoints axle_left/axle_right at local Z -length/2,+length/2. Named endpoint frames fixed rotation zero.','wheel':'Bore/hub are display geometry, proxy is full solid cylinder. Wheel must use its axle frame at local origin and an actual parent local+Z revolute hinge registered to the correct axle endpoint. Nominal bore minus axle diameter must be .0002..004 m.','fixed':'Mobility attach_part_to_mount uses actual fixed parent intermediary and an existing unrotated local frame. Requires no joint or actuator on that mount. New parts supply origin/top/bottom and family datums.','graph':'Create parent objects before children. Fixed mount/joint bodies between shapes must exist explicitly. Use raw existing actions; backend does not generate assembly action lists. Declared dependencies must cover all cross-batch references.'},
 'action_semantics':{'create_object':'Creates trusted world primitive defaults. dynamic_body is a free dynamic root; rigid_link default has a scalar joint: explicitly create_joint null for a fixed moving link. anchor is static zero mass; revolute/motor are moving scalar joints. Configure finite geometry/mass/position/joint/motor inputs with existing actions.','create_parametric_part':'Creates one owned rigid proxy; parent must exist. Moving parent needs positive mass. It creates stable built-in frames and derived physical mapping. No actuator/joint inferred from a part.','set_attachment_frame':'Register an existing correctly parented intermediate body at a named frame. Built-in datums cannot change sources/rotations. Use null hole_id for non-hole sources.','attach_part_to_joint':'Part must already be parented to that actual +Z revolute joint. Wheel uses its axle frame.','attach_part_to_mount':'Part must already be parented to that actual fixed intermediary. Anchors its local datum to mount origin.','set_geometry':'World primitive dimensions are full extents, cylinder axis Z. No arbitrary XML/assets.','transaction':'Each copied stage has its own diagnostic revision; final aggregate is one proposed authoritative revision increment. No application.'},
 'roles_contract':'Exactly one chassis, front/rear axles, four distinct wheel parts/hinges, two rear motor plates, one free root and only required intermediate mounts. Front wheels passive; rear two motors bounded nonzero. Existing ground and unbound circuit/device defaults preserved. No complete construction sequence is provided.',
 'limits':{'shape_specs':12,'batches':12,'actions_per_batch':16,'total_actions':96,'holes_per_part':8,'chassis_frames':20,'other_part_frames':12,'native':CRITERIA},
 'unsupported':['Vehicle shell','Suspension/steering','Continuous wheel rotation (hinges +/-pi)','Wiring/MCU or controller execution','Detailed tire compliance/bearing fit','Robust autonomy or certified safety'],
 'permissions':{'apply':False,'execute_code':False,'model_simulation_tool':False}}

def normalize(body):
 body=copy.deepcopy(body);body.update(reasoning={'effort':'low'},max_output_tokens=OUTPUT_BOUND,service_tier='default',store=True,parallel_tool_calls=False,tool_choice='auto');return body

def request_first():
 return normalize(OpenAIResponsesAdapter(None,'gpt-5.4',continuation='server')._build_request(({'role':'system','content':SYSTEM_INSTRUCTIONS},{'role':'user','content':canonical(context())}),tools_for(0)))

def request_second(obs,response_id,call_id):
 body=request_first();body.update(tools=tools_for(1),previous_response_id=response_id,input=[{'type':'function_call_output','call_id':call_id,'output':json.dumps({'ok':True,'result':obs},allow_nan=False)}]);return body

class AssemblyTools:
 def __init__(self,composer,trace):self.composer=composer;self.trace=trace;self.stage=0;self.result=None;self.obs=observation(composer)
 @property
 def schemas(self):return tools_for(self.stage)
 def dispatch(self,name,arguments):
  try:
   schema=next((s for s in self.schemas if s['name']==name),None)
   if schema is None:raise ValueError('One inspection then one proposal only; no retry/execution/apply tool')
   Draft202012Validator(schema['parameters']).validate(arguments)
   if observation(self.composer)!=self.obs:raise ValueError('Actual empty inspection changed')
   if self.stage==0:result={'ok':True,'result':copy.deepcopy(self.obs)}
   else:
    q=self.composer.propose(arguments['expected_sha256'],arguments['expected_revision'],arguments['plan'],origin='MODEL_TOOL_UNTRUSTED_ASSEMBLY');result={'ok':True,'result':q};self.result=result
   self.stage+=1
  except Exception as exc:
   self.stage=2;result={'ok':False,'error':{'type':type(exc).__name__,'message':str(exc)[:400],'diagnostics':getattr(exc,'diagnostics',[])}};self.result=result
  self.trace.append('assembly_tool_completed',{'name':name,'output':result});return result


def versions():return {n:version(n) for n in ('openai','mujoco','numpy','jsonschema')}

def preflight(root,manifest,approval,composer):
 d=manifest['definition']
 if approval!=manifest['sha256'] or digest(d)!=approval:raise ValueError('Fresh explicit Phase18E approval required')
 if not 0<=time.time()-d['frozen_unix']<=86400:raise ValueError('Frozen approval expired or clock precedes freeze')
 expected={'model':'gpt-5.4','reasoning_effort':'low','endpoint':ENDPOINT,'max_requests':2,'hard_cap_usd':'0.50','input_token_bound':INPUT_BOUND,'max_output_tokens':OUTPUT_BOUND,'execution_window_seconds':600,'max_native_previews':1,'native_steps_total':400,'retries':0,'vm_launches':0,'automatic_application':False}
 if any(d.get(k)!=v for k,v in expected.items()) or versions()!=d['versions'] or d['native_criteria']!=CRITERIA:raise ValueError('Frozen policy/criteria/version differs')
 if str(cost(INPUT_BOUND,0,OUTPUT_BOUND,policy=GPT54_POLICY)*2)!=d['worst_case_reservation_usd']:raise ValueError('Pricing reservation changed')
 for name,h in {**d['source_sha256'],**d['input_files_sha256']}.items():
  if file_hash(Path(root)/name)!=h:raise ValueError('Frozen source/project/context identity changed: '+name)
 obs=observation(composer)
 if digest(obs)!=d['inspection_sha256'] or digest(request_first())!=d['first_request_sha256']:raise ValueError('Actual observation or first request changed')
 b1=len(json.dumps(request_first(),ensure_ascii=True).encode())+4096
 b2=len(json.dumps(request_second(obs,'R'*128,'C'*128),ensure_ascii=True).encode())+4096+b1+OUTPUT_BOUND
 if [b1,b2]!=d['serialized_bounds'] or max(b1,b2)>INPUT_BOUND:raise ValueError('Frozen request envelope changed/exceeds reservation')
 return obs

class FrozenAssemblyAdapter(BudgetedOpenAIAdapter):
 def __init__(self,*args,observation,**kwargs):super().__init__(*args,**kwargs);self.obs=copy.deepcopy(observation);self.completed=[]
 def _request(self,**body):
  n=len(self.completed);wire=normalize(body);expected=request_first() if n==0 else request_second(self.obs,*self.completed[0]) if n==1 else None
  if expected is None or expected!=wire:raise BudgetBlocked('Actual assembly request differs from frozen protocol')
  response=super()._request(**wire);raw=response.model_dump(mode='json');calls=[c for c in raw['output'] if c['type']=='function_call'];tool=tools_for(n)[0]
  if len(calls)!=1 or calls[0]['name']!=tool['name']:raise BudgetBlocked('Actual model did not select the single scoped tool; no retry')
  call=calls[0];args=decode_json(call['arguments'].encode());Draft202012Validator(tool['parameters']).validate(args)
  for value in (raw.get('id'),call.get('call_id')):
   if not isinstance(value,str) or not 1<=len(value)<=128 or not value.isascii() or not all(c.isalnum() or c in '_-' for c in value):raise BudgetBlocked('Provider continuation identity exceeds frozen bounds')
  self.completed.append((raw['id'],call['call_id']));return response
