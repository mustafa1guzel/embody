"""Phase18E.4 source-pinned protocol, not an execution approval or mutation engine.

Existing revision tools own all validation/proposals. Existing native paths own
physics. No examples, archived plans, model source, or secrets enter context.
"""
import copy
import json
import re
import time
from decimal import Decimal
from pathlib import Path

import mujoco
import numpy as np
from jsonschema import Draft202012Validator

from core.agent.api_budget import GPT54_POLICY, BudgetBlocked, cost
from core.agent.models import OpenAIResponsesAdapter
from engineering.assembly_live import ENDPOINT, normalize, observation, tools_for, versions
from engineering.assembly_revision import AssemblyRevisionTools, proposal_schema
from engineering.assembly_rover import CRITERIA
from engineering.project import identity
from physics.contracts import canonical, digest
from robustness.contracts import file_hash, write_once
from workspace.data import decode_json

TASK='Build a simple four-wheel toy rover with a rectangular chassis, two axles, four wheels, two rear motor mounts, and basic powered forward movement.'
INPUT_BOUND=114688
OUTPUT_BOUND=8192
FEEDBACK_BYTES=16384
WINDOW_SECONDS=600
CAP='1.24'
MAX_REQUESTS=3
FORWARD_CONTRACT={
    'axis':'Initial chassis local +X, toward the protected front_axle datum',
    'minimum_signed_displacement_m':.005,
    'duration_s':1.,
    'meaning':'Signed chassis displacement projected on its INITIAL native +X axis; horizontal path length or backwards motion is insufficient.',
    'existing_predicates':'All unchanged assembly_rover.CRITERIA checks and fresh native replay must also pass.',
}

def context():
    return {'user_request':TASK,'instructions':
        'Inspect the actual EMPTY project and engineering contracts first. Then independently author a complete typed AssemblyPlan, with your own identities, arguments, mass allocation, attachments and actuator choices. '
        'Use the safe create_free_root operation for the mobile root. Inspection provides exact schemas, primitive defaults and ownership rules; it does not provide a final plan. '
        'Forward means initial chassis +X toward front_axle. Choose numerical actuation accordingly; native physics will measure it. '
        'If your first complete plan is rejected with structured whole-plan feedback and a failure_id, you may author ONE complete revised plan linked through revision_of. '
        'No revision after a compiled candidate, final rejection, schema/protocol failure or transport error. At most three requests including inspection. '
        'No source code, arbitrary execution, application, steering, suspension or real-world safety claims. Explain physical assumptions and unsupported capabilities. All results are review-only.'}

def inspect(composer):
    result=observation(composer)
    result['experiment_contract']={'task':TASK,'forward_acceptance':FORWARD_CONTRACT,
        'max_proposals':2,'revision_link':'null initially; exact returned failure_id on the single complete revision',
        'validation':'All schema, whole-plan mass/default, identity, joint, geometry, mount, structural and compilation checks remain strict. Compilation alone is not physical success.',
        'permissions':{'apply':False,'execute_source':False,'model_native_tool':False}}
    return result

def request_first():
    body=OpenAIResponsesAdapter(None,'gpt-5.4',continuation='server')._build_request(
        ({'role':'system','content':'You are a review-only engineering assembly author. Use only the supplied typed tools and actual inspected contracts. Never execute source or apply proposals.'},
         {'role':'user','content':canonical(context())}),tools_for(0))
    return normalize(body)

def continuation(response_id,call_id,output):
    return normalize({'model':'gpt-5.4','tools':proposal_schema(),
        'previous_response_id':response_id,
        'input':[{'type':'function_call_output','call_id':call_id,'output':json.dumps(output,allow_nan=False)}]})

def feedback(result):
    # Full diagnostics and mass/default allocation, not a corrected plan.
    value={k:copy.deepcopy(result[k]) for k in ('ok','failure_id','assessment','revision_of')}
    if len(json.dumps(value,ensure_ascii=True,allow_nan=False).encode())>FEEDBACK_BYTES:
        raise BudgetBlocked('Complete validation feedback exceeds frozen envelope; stop without truncation or another request')
    return value

def serialized_bounds(obs):
    first=len(json.dumps(request_first(),ensure_ascii=True).encode())+4096
    second=len(json.dumps(continuation('R'*128,'C'*128,{'ok':True,'result':obs}),ensure_ascii=True).encode())+4096+first+OUTPUT_BOUND
    # Feedback's entire serialized JSON is transmitted as a string. In the worst
    # case each ASCII byte needs an additional escape; reserve twice its limit.
    empty=continuation('R'*128,'C'*128,{})
    third=len(json.dumps(empty,ensure_ascii=True).encode())+2*FEEDBACK_BYTES+4096+second+OUTPUT_BOUND
    return [first,second,third]

def policy():
    return {'model':'gpt-5.4','reasoning_effort':'low','endpoint':ENDPOINT,
        'max_requests':MAX_REQUESTS,'hard_cap_usd':CAP,'input_token_bound':INPUT_BOUND,
        'max_output_tokens':OUTPUT_BOUND,'max_feedback_bytes':FEEDBACK_BYTES,
        'execution_window_seconds':WINDOW_SECONDS,'max_native_previews':1,'native_steps_total':400,
        'native_criteria':copy.deepcopy(CRITERIA),'forward_contract':copy.deepcopy(FORWARD_CONTRACT),
        'retries':0,'fallbacks':0,'vm_launches':0,'automatic_application':False,
        'installations':0,'arbitrary_source_execution':False,
        'worst_case_reservation_usd':str(cost(INPUT_BOUND,0,OUTPUT_BOUND,policy=GPT54_POLICY)*MAX_REQUESTS),
        'pricing':{'input':str(GPT54_POLICY.input_rate),'cached_input':str(GPT54_POLICY.cached_rate),
            'output_including_reasoning':str(GPT54_POLICY.output_rate),'units':'USD per million tokens',
            'source':GPT54_POLICY.pricing_source,'reasoning_charged_once':True},
        'versions':versions()}

def source_inventory(root):
    root=Path(root)
    prefixes=('core','engineering','shapebase','world','ide_api','physics','robustness','workspace','bodybase','worldbase','circuitbase','tests','tools','frontend/src','frontend/test')
    paths={p for name in prefixes for p in (root/name).rglob('*') if p.is_file() and p.suffix in ('.py','.json','.ts','.tsx','.css') and '__pycache__' not in p.parts}
    paths.update(root/n for n in ('requirements.txt','AGENTS.md','frontend/package.json','frontend/package-lock.json'))
    if any(p.is_symlink() for p in paths):raise ValueError('Source symlink not authorized')
    return {str(p.relative_to(root)):file_hash(p) for p in sorted(paths)}

def check_manifest(root,manifest,approval,*,now=None):
    """Identity check only. Never creates a client, credentials, project or VM."""
    root=Path(root);d=manifest['definition']
    if not approval or approval!=manifest['sha256'] or digest(d)!=approval:
        raise ValueError('Fresh explicit Phase18E.4 approval of this exact manifest required')
    if not 0<=(time.time() if now is None else now)-d['frozen_unix']<=d['approval_validity_seconds'] or d['approval_validity_seconds']!=86400:
        raise ValueError('Frozen approval expired or clock precedes freeze')
    if any(d.get(k)!=v for k,v in policy().items()):raise ValueError('Frozen policy, acceptance, pricing or versions changed')
    if source_inventory(root)!=d['source_sha256']:raise ValueError('Exact source identity set changed')
    for n,h in d['input_files_sha256'].items():
        p=root/n
        if p.is_symlink() or not p.is_file() or file_hash(p)!=h:raise ValueError('Frozen project/context/input differs: '+n)
    return d

def check_project(composer,manifest):
    obs=inspect(composer);d=manifest['definition'];p=composer.service.current()
    if p['revision']!=0 or p.get('creation') or p.get('shape_specs') or [o['id'] for o in p['world']['objects']]!=['floor']:
        raise ValueError('Actual authoritative project must remain independent EMPTY r0')
    if identity(p)!=d['project']['sha256'] or digest(obs)!=d['inspection_sha256']:
        raise ValueError('Frozen actual project/inspection differs')
    if composer.session().get('review_only') is not True or composer.session().get('task')!=TASK:
        raise ValueError('Frozen review-only session/task required')
    if digest(request_first())!=d['first_request_sha256'] or serialized_bounds(obs)!=d['serialized_bounds'] or max(d['serialized_bounds'])>INPUT_BOUND:
        raise ValueError('Frozen request chain envelope differs/exceeds bound')
    return obs

def parse_call(raw,schema):
    if raw.get('status')!='completed':raise ValueError('Incomplete response; no revision or retry')
    calls=[v for v in raw.get('output',[]) if v.get('type')=='function_call']
    if len(calls)!=1 or calls[0].get('name')!=schema['name']:raise ValueError('Exactly the current scoped tool call required')
    call=calls[0]
    for value in (raw.get('id'),call.get('call_id')):
        if not isinstance(value,str) or not re.fullmatch('[A-Za-z0-9_-]{1,128}',value):raise ValueError('Invalid bounded continuation identity')
    args=decode_json(call['arguments'].encode())
    Draft202012Validator(schema['parameters']).validate(args)
    return call,args

def run_protocol(adapter,composer,trace,output,guard):
    """Real or explicitly mocked transport; never authors or changes plan inputs."""
    output=Path(output);output.mkdir(exist_ok=False)
    tools=AssemblyRevisionTools(composer,trace);body=request_first();attempts=[]
    for index in range(MAX_REQUESTS):
        guard()
        raw=adapter._request(**body).model_dump(mode='json')
        call,args=parse_call(raw,tools.schemas[0])
        result=tools.dispatch(call['name'],args)
        if index==0 and result.get('ok'):
            # Host inspection enrichment, not a change to model arguments.
            if result['result']!=observation(composer):raise ValueError('Inspection drift')
            result={'ok':True,'result':inspect(composer)}
        attempt={'request_index':index,'response_id':raw['id'],'call_id':call['call_id'],
            'tool':call['name'],'arguments':copy.deepcopy(args),'output':result}
        write_once(output/f'tool_{index:03d}.json',attempt);attempts.append(attempt)
        if index and result.get('ok'):
            return {'status':'COMPILED_REVIEW_READY','proposal':result['result'],'attempts':attempts}
        if index==0:
            if not result.get('ok'):break
            next_output=result
        elif index==1 and result.get('failure_id') and not tools.done:
            next_output=feedback(result)
        else:break
        body=continuation(raw['id'],call['call_id'],next_output)
    return {'status':'FINAL_REJECTION','proposal':None,'attempts':attempts}

def forward_measurement(native):
    """Independent saved-state forward kinematics; no additional integration."""
    r=native['result'];proof=native['structural'];samples=r['samples']
    if len(samples)!=201 or r['independent_verification']['fresh_native_integration_steps']!=200:
        raise ValueError('Exact 200-step primary/replay required')
    if abs(samples[0]['time_s'])>1e-12 or abs(samples[-1]['time_s']-1.)>1e-12:
        raise ValueError('Frozen one-second acceptance window differs')
    m=mujoco.MjModel.from_xml_string(r['model_xml']);d=mujoco.MjData(m)
    gid=m.geom('geom_'+proof['chassis_body']).id
    d.qpos[:]=samples[0]['qpos'];d.qvel[:]=samples[0]['qvel'];mujoco.mj_forward(m,d)
    start=d.geom_xpos[gid].copy();axis=d.geom_xmat[gid].reshape(3,3)[:,0].copy()
    d.qpos[:]=samples[-1]['qpos'];d.qvel[:]=samples[-1]['qvel'];mujoco.mj_forward(m,d)
    delta=d.geom_xpos[gid]-start;signed=float(delta@axis)
    if not np.isfinite(signed):raise ValueError('Nonfinite forward displacement')
    checks={'all_existing_physical_checks':all(native['observations']['checks'].values()),
        'fresh_replay':r['independent_verification']['status']=='PASS',
        'signed_forward_displacement':signed>=FORWARD_CONTRACT['minimum_signed_displacement_m'],
        'head_unchanged':native['head_unchanged']}
    return {'status':'PASS' if all(checks.values()) else 'FAIL','checks':checks,
        'signed_forward_displacement_m':signed,'initial_forward_axis_world':axis.tolist(),
        'chassis_displacement_world_m':delta.tolist(),'contract':FORWARD_CONTRACT,'extra_integration_steps':0,
        'scope':'Additional directional measurement; original horizontal-magnitude acceptance and historical results remain unchanged.'}

def audit_completed_protocol(composer,protocol,execution,receipt,*,native=None):
    """Independent read-back of provider payloads and evidence, no integration.

    This also audits final engineering rejection. Interrupted/invalid API output
    retains its raw record but is not represented as a completed protocol.
    """
    execution=Path(execution);attempts=protocol['attempts'];previous=None;total=Decimal(0)
    if not 2<=len(attempts)<=3 or len(receipt['requests'])!=len(attempts):raise ValueError('Completed protocol count mismatch')
    for i,a in enumerate(attempts):
        request=decode_json((execution/'api'/f'request_{i:03d}.json').read_bytes())
        response=decode_json((execution/'api'/f'response_{i:03d}.json').read_bytes())
        expected=request_first() if i==0 else continuation(previous['response_id'],previous['call_id'],
            previous['output'] if i==1 else feedback(previous['output']))
        if request!=expected:raise ValueError('Actual request/continuation/context mismatch')
        call,args=parse_call(response,(tools_for(0) if i==0 else proposal_schema())[0])
        if args!=a['arguments'] or response['id']!=a['response_id'] or call['call_id']!=a['call_id']:raise ValueError('Returned arguments were altered')
        if i and args['revision_of']!=(attempts[1]['output']['failure_id'] if i==2 else None):raise ValueError('Invalid revision linkage')
        if i==0 and a['output']!={'ok':True,'result':inspect(composer)}:raise ValueError('Inspection output mismatch')
        if i and a['output'].get('assessment')!=composer.assess(args['expected_sha256'],args['expected_revision'],args['plan']):raise ValueError('Independent whole-plan feedback mismatch')
        entry=receipt['requests'][i];u=response['usage'];cached=u['input_tokens_details']['cached_tokens']
        actual=cost(u['input_tokens'],cached,u['output_tokens'],policy=GPT54_POLICY)
        if entry['state']!='SETTLED' or entry['response_id']!=response['id'] or entry['usage']!=u or actual!=Decimal(entry['actual_cost_usd']):raise ValueError('Independent cost receipt mismatch')
        if response.get('service_tier')!='default' or not re.fullmatch(r'gpt-5\.4(?:-\d{4}-\d{2}-\d{2})?',response.get('model','')):raise ValueError('Unapproved provider model/tier')
        total+=actual;previous=a
    if total!=Decimal(receipt['measured_cost_usd']) or total!=Decimal(receipt['accounted_cost_usd']) or total>=Decimal(CAP):raise ValueError('Independent budget total mismatch')
    q=protocol['proposal']
    if q:
        if q['assembly_plan']!=attempts[-1]['arguments']['plan']:raise ValueError('Proposal not exact model plan')
        candidate,proof=composer.reconstruct(q)
        if native:
            from world.compiler import compile_world
            from engineering.assembly_rover import measured
            r=native['result'];m,xml,compiled=compile_world(candidate['world'])
            if r['world']!=candidate['world'] or xml!=r['model_xml'] or compiled['contract_sha256']!=r['contract_sha256'] or digest(r['samples'])!=r['trajectory_sha256']:raise ValueError('Native input/trajectory/compiled identity mismatch')
            if proof!=native['structural'] or measured(r,proof)!=native['observations']:raise ValueError('Independent native force/contact acceptance mismatch')
            forward_measurement(native)
    return {'status':'PASS_COMPLETED_PROTOCOL_EVIDENCE','request_count':len(attempts),'recomputed_cost_usd':str(total),
        'exact_model_arguments_preserved':True,'exact_continuation_chain':True,
        'compiled_proposal_verified':bool(q),'native_saved_state_audit':bool(native),
        'additional_integration_steps':0,'authoritative_head_revision':composer.service.current()['revision'],
        'meaning':'Evidence audit, including genuine rejection if present; not by itself AI or physical success.'}
