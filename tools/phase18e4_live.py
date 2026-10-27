"""Frozen Phase18E.4 driver. NOT authorized by preparation or a CLI hash alone."""
from pathlib import Path
import argparse
import signal
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from engineering.assembly import AssemblyComposer
from engineering.assembly_experiment import (CAP, INPUT_BOUND, MAX_REQUESTS, OUTPUT_BOUND,
    WINDOW_SECONDS, audit_completed_protocol, check_manifest, check_project, forward_measurement, run_protocol)
from ide_api.engineering import EngineeringService
from core.agent.trace import ExecutionTrace
from physics.contracts import digest
from robustness.contracts import file_hash,write_once
from workspace.data import decode_json

DEFAULT=ROOT/'artifacts/phase18e_4/20261025/live_consent_request.json'

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path,default=DEFAULT)
    parser.add_argument('--approve',help='Requires a separate explicit human approval of the exact manifest')
    args=parser.parse_args()
    if not args.approve:raise SystemExit('BLOCKED: fresh explicit Phase18E.4 approval required; no client or execution created')
    m=decode_json(args.manifest.read_bytes());d=check_manifest(ROOT,m,args.approve)
    here=args.manifest.parent.resolve()
    if here!=ROOT/d['evidence_root']:raise SystemExit('Frozen manifest location differs')
    project=ROOT/d['project']['root']
    if (here/'live_execution').exists():raise SystemExit('Execution scope consumed; never resume/retry paid dispatch')
    # Every initial file has already been verified before creating any service.
    composer=AssemblyComposer(EngineeringService(project));check_project(composer,m)
    for folder in ('assembly_proposals','assembly_failures','assembly_preview_reservations'):
        if any((project/folder).glob('*')):raise SystemExit('Initial project is not unused')
    before=composer.service.current();heads=(project/'head.json').read_bytes()
    out=here/'live_execution';out.mkdir(exist_ok=False);started=time.monotonic()
    trace=ExecutionTrace(out/'trace.jsonl',model_mode='openai_responses')
    client=budget=native=directional=protocol=None;failure=None;status='FAILED'
    def guard():
        if time.monotonic()-started>=WINDOW_SECONDS:raise TimeoutError('Authorized 600-second execution window exhausted')
        check_manifest(ROOT,m,args.approve);check_project(composer,m)
        for n,h in decode_json((here/'preservation_frozen.json').read_bytes()).items():
            if not (ROOT/n).is_file() or file_hash(ROOT/n)!=h:raise ValueError('Historical/source preservation drift: '+n)
    def timeout(*unused):raise TimeoutError('Authorized execution window exhausted')
    def no_process(event,args):
        if event in ('subprocess.Popen','os.system','os.fork','os.posix_spawn'):
            raise PermissionError('No VM, controller or subprocess execution authority')
    write_once(out/'authorization.json',{'manifest_sha256':args.approve,
        'authority':'Separate explicit current-user approval required; CLI hash alone is not consent',
        'max_requests':MAX_REQUESTS,'hard_cap_usd':CAP,'review_only':True})
    previous=signal.signal(signal.SIGALRM,timeout)
    signal.setitimer(signal.ITIMER_REAL,WINDOW_SECONDS);sys.addaudithook(no_process)
    try:
        guard()
        from core.agent.credentials import create_openai_client
        from core.agent.live_model import BudgetedOpenAIAdapter
        from core.agent.development_budget import DevelopmentBudget
        from core.agent.api_budget import GPT54_POLICY
        history=[ROOT/n for n in d['historical_api_ledgers']]
        budget=DevelopmentBudget(out/'api_cost_ledger.json',cumulative_path=out/'cumulative.json',
            historical_paths=history,policy=GPT54_POLICY,limit=CAP,max_requests=MAX_REQUESTS,
            input_token_bound=INPUT_BOUND,max_output_tokens=OUTPUT_BOUND)
        client=create_openai_client().with_options(timeout=180.,max_retries=0)
        if str(client.base_url)!='https://api.openai.com/v1/':raise ValueError('Pinned endpoint differs')
        adapter=BudgetedOpenAIAdapter(client,budget,out/'api',trace)
        protocol=run_protocol(adapter,composer,trace,out/'protocol',guard)
        write_once(out/'protocol_result.json',protocol)
        if protocol['proposal']:
            proposal=protocol['proposal'];guard()
            candidate,proof=composer.reconstruct(proposal)
            write_once(out/'independent_construction.json',{'project':candidate,'structural':proof,
                'original_model_arguments_unchanged':proposal['assembly_plan']==protocol['attempts'][-1]['arguments']['plan']})
            native=composer.preview_native(proposal['base_project_sha256'],0,proposal['proposal_id'])
            write_once(out/'native_verification.json',native)
            directional=forward_measurement(native);write_once(out/'forward_verification.json',directional)
            status='MEASURED_AI_ROVER_REVIEW_READY' if directional['status']=='PASS' else 'MEASURED_PHYSICAL_REQUIREMENT_FAILURE'
        else:status='FINAL_MODEL_PLAN_REJECTION'
        independent=audit_completed_protocol(composer,protocol,out,budget.snapshot(),native=native)
        write_once(out/'independent_evidence_audit.json',independent)
    except Exception as exc:
        failure={'type':type(exc).__name__,'message':str(exc)[:600]}
        trace.append('phase18e4_stopped',failure)
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous)
        if client is not None:client.close()
        receipt=budget.snapshot() if budget else None
        changed=[n for n,h in decode_json((here/'preservation_frozen.json').read_bytes()).items()
            if not (ROOT/n).is_file() or file_hash(ROOT/n)!=h]
        unchanged=composer.service.current()==before and (project/'head.json').read_bytes()==heads
        if changed or not unchanged:status='FAILED_PRESERVATION'
        provenance={'manifest_sha256':m['sha256'],'usage_cost_receipt':receipt,
            'request_files':{str(p.relative_to(out)):file_hash(p) for p in sorted((out/'api').glob('request_*.json'))},
            'response_files':{str(p.relative_to(out)):file_hash(p) for p in sorted((out/'api').glob('response_*.json'))},
            'directional_acceptance':directional,
            'protocol_attempts':[{'index':a['request_index'],'tool':a['tool'],'response_id':a['response_id'],
                'plan_sha256':digest(a['arguments']['plan']) if 'plan' in a['arguments'] else None,
                'accepted':a['output']['ok'],'failure_id':a['output'].get('failure_id')} for a in (protocol or {}).get('attempts',[])],
            'authorship':'Only genuine provider arguments dispatched. One model-authored full revision permitted after structured rejection; no deterministic corrections or plan examples sent.'}
        record={'status':status,'origin':'GENUINE_PROVIDER_RESPONSE' if provenance['response_files'] else 'NO_PROVIDER_RESPONSE',
            'proposal_id':protocol['proposal']['proposal_id'] if protocol and protocol['proposal'] else None,
            'native_ref':native['evidence_ref'] if native else None,'failure':failure,'provenance':provenance}
        write_once(out/'review_record.json',record);composer.publish(record)
        audit={'status':status,'failure':failure,'elapsed_seconds':time.monotonic()-started,
            'head_unchanged':unchanged,'head_revision':composer.service.current()['revision'],
            'preexisting_changed':changed,'request_reservations':len(receipt['requests']) if receipt else 0,
            'actual_cost_usd':receipt['measured_cost_usd'] if receipt else '0',
            'native_attempts':len(list((project/'assembly_preview_reservations').glob('*'))),
            'vm_launches':0,'automatic_applications':0,'retry_requests':0,'installations':0}
        trace.append('phase18e4_finished',audit);write_once(out/'audit.json',audit)
        write_once(out/'inventory.json',{str(p.relative_to(out)):file_hash(p) for p in sorted(out.rglob('*')) if p.is_file() and not p.name.endswith('.lock')})
    if status!='MEASURED_AI_ROVER_REVIEW_READY':raise SystemExit(1)

if __name__=='__main__':main()
