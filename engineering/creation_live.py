"""Frozen one-request protocol using the existing orchestrator/budget adapter."""
import copy,json,time
from pathlib import Path
from decimal import Decimal
from importlib.metadata import version
from core.agent.models import OpenAIResponsesAdapter
from core.agent.live_model import BudgetedOpenAIAdapter
from core.agent.api_budget import GPT54_POLICY,cost,BudgetBlocked
from core.agent.orchestration import SYSTEM_INSTRUCTIONS
from hardware.library import catalog
from physics.contracts import digest,canonical
from robustness.contracts import file_hash
from workspace.data import decode_json
from .creation_experiment import GOAL,SCHEMAS,LIMITS

INPUT_BOUND=24576
OUTPUT_BOUND=4096
ENDPOINT='https://api.openai.com/v1/responses'

def context():
    parts=catalog()
    return {'user_request':GOAL,'experiment':'PHASE17_ONE_REQUEST_REVIEW_ONLY',
     'capabilities':{
      'construction':'Day16 parameterized hinged-barrier template expands into bounded typed engineering batches, a DeviceDesignPlan and a compiled MuJoCo review copy. No existing finished project is cloned.',
      'supported_parts':[{k:p[k] for k in ('id','model','kind','pins','properties','assumptions','confidence')} for p in parts.values()],
      'interfaces':'Only IO18 trigger, IO19 decoded Echo through the supported 2.2k/3.3k resistor divider, IO23 servo request, external regulated 4.8V servo supply and common ground are supported by this versioned template. These are tool compatibility constraints, not proof of electrical safety.',
      'controller':'TRUSTED_BARRIER_V1: existing sampled ray/debounce/open/hold/close logic with bounded PD torque; no arbitrary firmware or source execution.',
      'mechanics':'Single beam hinged at one end. Gravity 9.81 m/s^2. Select your own plausible SI configuration within tool bounds and justify mechanical authority; native measurements determine acceptance.',
      'verification':{'duration_s':5,'dt_s':.005,'control_s':.02,'opening_angle_rad':1.25,'deadline_after_detection_s':2,'final_angle_tolerance_rad':.04,'final_speed_limit_rad_s':.05,'peak_speed_limit_rad_s':6,'joint_range_rad':[0,1.65],'joint_tolerance_rad':.01,'contacts':'No prohibited contact','sensor_range_m':[.02,4]},
      'unsupported_domains':LIMITS},
     'instructions':'Interpret the user request. Choose an appropriate available tool, or report unsupported if necessary. Supply your own structured design intent and parameter selection; do not claim verification or application. The tool expands your intent into exact reviewable actions. There is no prewritten final action list or example answer in this context. Only one model request is permitted: choose once, without requesting follow-up tool observations. Review-only local evaluation may occur afterward; no second model request, build or application is available.'}

def normalize_request(request):
    wire=copy.deepcopy(request)
    wire.update(reasoning={'effort':'low'},max_output_tokens=OUTPUT_BOUND,service_tier='default',store=True,parallel_tool_calls=False,tool_choice='auto')
    return wire

def request_body():
    messages=({'role':'system','content':SYSTEM_INSTRUCTIONS},{'role':'user','content':canonical(context())})
    return normalize_request(OpenAIResponsesAdapter(None,'gpt-5.4',continuation='server')._build_request(messages,SCHEMAS))

def versions():return {n:version(n) for n in ('openai','mujoco','numpy','jsonschema')}

def preflight(root,manifest,approval):
    """No credentials, network or mutation; fail closed before any paid dispatch."""
    definition=manifest['definition']
    if approval!=manifest['sha256'] or digest(definition)!=approval:raise ValueError('BLOCKED: fresh explicit approval of this exact Phase17 manifest required')
    if not 0<=time.time()-definition['frozen_unix']<=86400:raise ValueError('BLOCKED: frozen scope expired or clock precedes freeze')
    if definition['endpoint']!=ENDPOINT or definition['max_requests']!=1 or definition['hard_cap_usd']!='0.13' or definition['input_token_bound']!=INPUT_BOUND or definition['max_output_tokens']!=OUTPUT_BOUND:raise ValueError('BLOCKED: scope limits differ')
    if definition['model']!='gpt-5.4' or definition['reasoning_effort']!='low' or definition['tool_choice']!='auto':raise ValueError('BLOCKED: model/tool policy differs')
    if cost(INPUT_BOUND,0,OUTPUT_BOUND,policy=GPT54_POLICY)!=Decimal('0.12288'):raise ValueError('BLOCKED: pricing policy differs')
    if definition['versions']!=versions():raise ValueError('BLOCKED: dependency versions changed')
    from .creation import implementation_identity
    if definition['creation_implementation_sha256']!=implementation_identity():raise ValueError('BLOCKED: creation implementation identities changed')
    for name,sha in definition['source_sha256'].items():
        if file_hash(Path(root)/name)!=sha:raise ValueError('BLOCKED: frozen local identity changed')
    body=decode_json((Path(root)/definition['request_path']).read_bytes())
    if digest(body)!=definition['request_sha256'] or digest(body)!=digest(request_body()):raise ValueError('BLOCKED: transmitted context/schema changed')
    bound=len(json.dumps(body,ensure_ascii=True,allow_nan=False).encode())+4096
    if bound>INPUT_BOUND or bound!=definition['serialized_payload_bound']:raise ValueError('BLOCKED: serialized reservation envelope differs')
    return body

class FrozenCreationAdapter(BudgetedOpenAIAdapter):
    def __init__(self,*args,frozen_request,**kwargs):
        super().__init__(*args,**kwargs);self.frozen_request=copy.deepcopy(frozen_request)
    def _request(self,**request):
        wire=normalize_request(request)
        if digest(wire)!=digest(self.frozen_request):raise BudgetBlocked('Actual orchestrator wire payload differs from approval')
        response=super()._request(**wire)
        raw=response.model_dump(mode='json');calls=[x for x in raw['output'] if x['type']=='function_call']
        if len(calls)!=1:raise BudgetBlocked('One actual model tool selection required; no retry')
        call=calls[0]
        if call['name'] not in {t['name'] for t in SCHEMAS}:raise BudgetBlocked('Unsupported model tool selected')
        # Reject duplicate keys before the generic adapter parses model arguments.
        args=decode_json(call['arguments'].encode())
        if not isinstance(args,dict):raise BudgetBlocked('Tool arguments must be an exact JSON object')
        return response
