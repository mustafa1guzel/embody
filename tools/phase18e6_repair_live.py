"""Future Phase18E.6 repair experiment. Preparation does NOT authorize requests."""
from pathlib import Path
import argparse,copy,json,signal,sys,time
from decimal import Decimal
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from engineering.assembly import AssemblyComposer
from engineering.assembly_direction import physical_feedback
from engineering.assembly_physical_repair import PhysicalRepairTools
from engineering.assembly_experiment import source_inventory,parse_call
from engineering.assembly_live import versions
from engineering.project import identity
from ide_api.engineering import EngineeringService
from core.agent.api_budget import GPT54_POLICY,cost
from core.agent.models import OpenAIResponsesAdapter
from core.agent.trace import ExecutionTrace
from physics.contracts import canonical,digest
from robustness.contracts import file_hash,write_once
from workspace.data import decode_json

HERE=ROOT/'artifacts/phase18e_6/20261026'
CAP='0.30';INPUT_BOUND=32768;OUTPUT_BOUND=4096;WINDOW=600
TASK='Inspect the existing proposed rover and its measured native failure. Propose one supported actuator-parameter engineering change that can meet the existing signed-forward requirement while preserving geometry, masses, connections, authority, acceptance checks and the EMPTY authoritative head. Supply your own typed arguments; do not claim physical success before native verification.'

def wire(body):
    body=copy.deepcopy(body);body.update(reasoning={'effort':'low'},max_output_tokens=OUTPUT_BOUND,
        service_tier='default',store=True,parallel_tool_calls=False,tool_choice='auto');return body
def first_request(tools):
    return wire(OpenAIResponsesAdapter(None,'gpt-5.4',continuation='server')._build_request(
        ({'role':'system','content':'You are a review-only engineering repair author. Inspect actual measured feedback, then propose one exact typed change. No code, apply, automatic correction, retries or simulation tool.'},
         {'role':'user','content':TASK}),tools.schemas))
def second_request(tools,obs,response_id,call_id):
    return wire({'model':'gpt-5.4','previous_response_id':response_id,'tools':tools.schemas,
        'input':[{'type':'function_call_output','call_id':call_id,'output':json.dumps({'ok':True,'result':obs},allow_nan=False)}]})
def source_hashes(root):
    result=source_inventory(root)
    for name in ('devices','configs','hardware'):
        result.update({str(p.relative_to(root)):file_hash(p) for p in (root/name).rglob('*') if p.is_file() and p.suffix in ('.py','.json') and '__pycache__' not in p.parts})
    return dict(sorted(result.items()))
def settings():
    return {'model':'gpt-5.4','reasoning':'low','endpoint':'https://api.openai.com/v1/responses',
        'max_requests':2,'hard_cap_usd':CAP,'input_token_bound':INPUT_BOUND,'output_token_bound':OUTPUT_BOUND,
        'worst_case_reservation_usd':str(cost(INPUT_BOUND,0,OUTPUT_BOUND,policy=GPT54_POLICY)*2),
        'window_seconds':WINDOW,'approval_validity_seconds':86400,'native_previews':1,'native_steps_total':400,
        'retries':0,'fallbacks':0,'vm_launches':0,'apply':False,'versions':versions(),
        'pricing':{'input':str(GPT54_POLICY.input_rate),'cached':str(GPT54_POLICY.cached_rate),
            'output_including_reasoning':str(GPT54_POLICY.output_rate),'units':'USD/million tokens','source':GPT54_POLICY.pricing_source}}
def preflight(root,m,approval):
    d=m['definition']
    if approval!=m['sha256'] or digest(d)!=approval:raise ValueError('Fresh explicit physical-repair experiment approval required')
    if not 0<=time.time()-d['frozen_unix']<=86400:raise ValueError('Physical-repair freeze expired')
    if any(d.get(k)!=v for k,v in settings().items()):raise ValueError('Frozen repair limits/pricing/version differ')
    if source_hashes(root)!=d['source_sha256']:raise ValueError('Repair source identities changed')
    for n,h in d['input_sha256'].items():
        if not (root/n).is_file() or (root/n).is_symlink() or file_hash(root/n)!=h:raise ValueError('Repair context/project/evidence drift: '+n)
def open_tools(root,d,trace):
    data=decode_json((root/d['baseline_context']).read_bytes())
    c=AssemblyComposer(EngineeringService(root/d['project_root']))
    t=PhysicalRepairTools(c,c.load(data['baseline_proposal_id']),data['native'],trace)
    if c.session().get('review_only') is not True or identity(t.before)!=d['head_sha256'] or t.before['revision']!=0:raise ValueError('Actual EMPTY r0 review-only head differs')
    if digest(t.inspection())!=d['inspection_sha256']:raise ValueError('Frozen repair inspection differs')
    return c,t
def run_protocol(adapter,tools,output,guard):
    output=Path(output);output.mkdir(exist_ok=False);body=first_request(tools);attempts=[]
    for i in range(2):
        guard();raw=adapter._request(**body).model_dump(mode='json');call,args=parse_call(raw,tools.schemas[0])
        result=tools.dispatch(call['name'],args)
        row={'index':i,'response_id':raw['id'],'call_id':call['call_id'],'name':call['name'],'arguments':args,'output':result}
        write_once(output/f'tool_{i:03d}.json',row);attempts.append(row)
        if not result['ok']:return {'status':'REJECTED','attempts':attempts,'proposal':None}
        if i==0:body=second_request(tools,result['result'],raw['id'],call['call_id'])
        else:return {'status':'COMPILED_REVIEW_ONLY','attempts':attempts,'proposal':result['result'],'repair':result['repair']}
    raise ValueError('Invalid bounded repair protocol')

def audit_protocol(protocol,tools,execution,receipt,*,native=None):
    """Independent read-back; compares JSON values, never repairs model inputs."""
    rows=protocol['attempts'];execution=Path(execution)
    if len(rows)!=2 or len(receipt['requests'])!=2:raise ValueError('Expected exactly two completed repair requests')
    original=PhysicalRepairTools(tools.composer,tools.baseline,tools.native,None)
    expected_first=first_request(original)
    for i,row in enumerate(rows):
        request=decode_json((execution/'api'/f'request_{i:03d}.json').read_bytes())
        response=decode_json((execution/'api'/f'response_{i:03d}.json').read_bytes())
        if i==0:
            if request!=expected_first:raise ValueError('Frozen inspection request changed')
            if row['output']!={'ok':True,'result':original.inspection()}:raise ValueError('Actual physical inspection differs')
            original.stage=1 # New data-only audit facade, after the checked inspection.
        else:
            expected=second_request(original,original.inspection(),rows[0]['response_id'],rows[0]['call_id'])
            if json.loads(request['input'][0]['output'])!=json.loads(expected['input'][0]['output']):raise ValueError('Physical feedback/context changed')
            normalized=copy.deepcopy(request);normalized['input'][0]['output']=expected['input'][0]['output']
            if normalized!=expected:raise ValueError('Actual continuation/tool/schema changed')
        schema=(expected_first if i==0 else expected)['tools'][0]
        call,args=parse_call(response,schema)
        if args!=row['arguments'] or response['id']!=row['response_id'] or call['call_id']!=row['call_id']:raise ValueError('Model arguments/provider identities changed')
        e=receipt['requests'][i];u=response['usage']
        calculated=cost(u['input_tokens'],u['input_tokens_details']['cached_tokens'],u['output_tokens'],policy=GPT54_POLICY)
        if e['state']!='SETTLED' or e['usage']!=u or e['response_id']!=response['id'] or Decimal(e['actual_cost_usd'])!=calculated:raise ValueError('Usage receipt mismatch')
    total=sum(Decimal(e['actual_cost_usd']) for e in receipt['requests'])
    if total!=Decimal(receipt['measured_cost_usd']) or total!=Decimal(receipt['accounted_cost_usd']) or total>=Decimal(CAP):raise ValueError('Budget total mismatch')
    if protocol['proposal']:
        q=protocol['proposal'];tools.composer.reconstruct(q)
        if q['assembly_plan']['steps'][:-1]!=tools.baseline['assembly_plan']['steps'] or q['assembly_plan']['steps'][-1]['operations']!=rows[1]['arguments']['operations']:raise ValueError('Repair changed original construction or model arguments')
        if native:physical_feedback(q,native)
    return {'status':'PASS_INDEPENDENT_REPAIR_EVIDENCE_AUDIT','request_count':2,'recomputed_cost_usd':str(total),
        'exact_model_operations_preserved':True,'original_construction_preserved':True,
        'native_evidence_audited':bool(native),'additional_integration_steps':0,
        'meaning':'Provenance/evidence audit, not by itself a physical repair PASS.'}

def main():
    p=argparse.ArgumentParser();p.add_argument('--approve');a=p.parse_args()
    if not a.approve:raise SystemExit('BLOCKED: fresh explicit approval required; no client or live execution')
    m=decode_json((HERE/'live_consent_request.json').read_bytes());preflight(ROOT,m,a.approve);d=m['definition']
    out=HERE/'live_execution'
    if out.exists():raise SystemExit('Repair scope consumed; no retry or resumed paid dispatch')
    data=decode_json((ROOT/d['baseline_context']).read_bytes())
    c=AssemblyComposer(EngineeringService(ROOT/d['project_root']))
    if (c.root/'assembly_preview_session.reservation').exists() or (c.root/'assembly_live_review.json').exists():raise ValueError('Repair native/review scope already consumed')
    if {p.stem for p in c.proposals.root.glob('*.json')}!={d['baseline_proposal_id']} or any(c.failures.root.glob('*')) or any((c.root/'assembly_preview_reservations').glob('*')):
        raise ValueError('Prepared repair scope is not unused except for its frozen baseline proposal')
    out.mkdir(exist_ok=False);started=time.monotonic();trace=ExecutionTrace(out/'trace.jsonl',model_mode='openai_responses')
    c,t=open_tools(ROOT,d,trace);before=c.service.current();client=budget=protocol=native=feedback=None;failure=None;status='FAIL'
    def guard():
        if time.monotonic()-started>=WINDOW:raise TimeoutError('Approved repair window exhausted')
        preflight(ROOT,m,a.approve)
        if c.service.current()!=before:raise ValueError('Authoritative head changed')
        for n,h in decode_json((HERE/'preservation_frozen.json').read_bytes()).items():
            if not (ROOT/n).is_file() or file_hash(ROOT/n)!=h:raise ValueError('Historical/source drift: '+n)
    def no_process(event,args):
        if event in ('subprocess.Popen','os.system','os.fork','os.posix_spawn'):raise PermissionError('No subprocess/VM/source/controller execution authority')
    def timeout(*args):raise TimeoutError('Approved repair window exhausted')
    old=signal.signal(signal.SIGALRM,timeout);signal.setitimer(signal.ITIMER_REAL,max(.001,WINDOW-(time.monotonic()-started)));sys.addaudithook(no_process)
    write_once(out/'approval.json',{'manifest_sha256':a.approve,'source':'Separate current-user explicit approval required; never prior approval or CLI hash alone','review_only':True})
    try:
        guard()
        from core.agent.credentials import create_openai_client
        from core.agent.live_model import BudgetedOpenAIAdapter
        from core.agent.development_budget import DevelopmentBudget
        budget=DevelopmentBudget(out/'api_cost_ledger.json',cumulative_path=out/'cumulative.json',historical_paths=[ROOT/n for n in d['historical_api_ledgers']],
            policy=GPT54_POLICY,limit=CAP,max_requests=2,input_token_bound=INPUT_BOUND,max_output_tokens=OUTPUT_BOUND)
        client=create_openai_client().with_options(timeout=180.,max_retries=0)
        if str(client.base_url)!='https://api.openai.com/v1/':raise ValueError('Pinned endpoint differs')
        adapter=BudgetedOpenAIAdapter(client,budget,out/'api',trace)
        protocol=run_protocol(adapter,t,out/'protocol',guard);write_once(out/'protocol_result.json',protocol)
        if protocol['proposal']:
            q=protocol['proposal'];guard();c.reconstruct(q)
            if q['assembly_plan']['steps'][-1]['operations']!=protocol['attempts'][1]['arguments']['operations']:raise ValueError('Model arguments changed')
            native=c.preview_native(q['base_project_sha256'],0,q['proposal_id']);write_once(out/'native.json',native)
            feedback=physical_feedback(q,native);write_once(out/'physical_feedback.json',feedback)
            status='AI_PHYSICAL_REPAIR_PASS' if feedback['status']=='PHYSICAL_PASS' else 'AI_PHYSICAL_REPAIR_FAIL'
        else:status='AI_REPAIR_REJECTED'
        write_once(out/'independent_audit.json',audit_protocol(protocol,t,out,budget.snapshot(),native=native))
    except Exception as e:failure={'type':type(e).__name__,'message':str(e)[:500]};status='FAIL'
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old)
        if client is not None:client.close()
        receipt=budget.snapshot() if budget else None
        changed=[n for n,h in decode_json((HERE/'preservation_frozen.json').read_bytes()).items() if not (ROOT/n).is_file() or file_hash(ROOT/n)!=h]
        if changed or c.service.current()!=before:status='FAIL_PRESERVATION'
        record={'status':status,'origin':'GENUINE_PROVIDER_RESPONSE' if list((out/'api').glob('response_*.json')) else 'NO_PROVIDER_RESPONSE',
            'proposal_id':protocol['proposal']['proposal_id'] if protocol and protocol['proposal'] else None,
            'native_ref':native['evidence_ref'] if native else None,'failure':failure,
            'provenance':{'manifest_sha256':m['sha256'],'usage_cost_receipt':receipt,'physical_failure_feedback':feedback,
                'baseline_feedback_sha256':t.feedback['feedback_sha256'],'baseline_origin':t.baseline['origin'],
                'authorship':'Only the new supplied operations are model repair decisions. Baseline construction is labelled reused historical-plan reconstruction.'}}
        write_once(out/'review.json',record);c.publish(record)
        write_once(out/'audit.json',{'status':status,'failure':failure,'elapsed_seconds':time.monotonic()-started,
            'head_unchanged':c.service.current()==before,'preservation_changed':changed,
            'requests':len(receipt['requests']) if receipt else 0,'actual_cost_usd':receipt['measured_cost_usd'] if receipt else '0',
            'native_attempts':len(list((c.root/'assembly_preview_reservations').glob('*'))),
            'vm_launches':0,'applications':0,'retries':0})
        write_once(out/'inventory.json',{str(p.relative_to(out)):file_hash(p) for p in out.rglob('*') if p.is_file() and not p.name.endswith('.lock')})
    if status!='AI_PHYSICAL_REPAIR_PASS':raise SystemExit(1)
if __name__=='__main__':main()
