"""Run the complete real test suite and publish a factual Day 4B.1 evidence index."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import tempfile
import getpass
import shutil

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from core.agent.vm_backend import AppleVMBackend, file_hash, runtime_command
from core.agent.trace import read_trace
from tools.day4b1_provision import cached

OUT=ROOT/'artifacts/day4b1/implementation'

def main():
    env=os.environ.copy();env['EMBODY_RUN_VM_TESTS']='1'
    command=[sys.executable,'-m','pytest','-ra']
    started=time.monotonic()
    result=subprocess.run(command,cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    (OUT/'pytest_output.txt').write_text(result.stdout)
    match=re.search(r'(\d+) passed',result.stdout)
    passed=int(match.group(1)) if match else 0
    pytest_result={'command':'EMBODY_RUN_VM_TESTS=1 .venv/bin/python -m pytest -ra',
                   'exit_code':result.returncode,'passed':passed,'elapsed_s':time.monotonic()-started,
                   'output':'pytest_output.txt','live_vm_tests_enabled':True}
    (OUT/'pytest_result.json').write_text(json.dumps(pytest_result,indent=2)+'\n')
    print(result.stdout,flush=True)
    if result.returncode:raise SystemExit(result.returncode)
    backend=AppleVMBackend();proof=backend.preflight()
    baseline=json.loads((OUT/'before.json').read_text())
    permitted={'.gitignore','pytest.ini','README.md','core/agent/verification.py','core/agent/tools.py'}
    changed=[p for p,h in baseline.items() if not (ROOT/p).is_file() or file_hash(ROOT/p)!=h]
    unexpected=sorted(set(changed)-permitted)
    preservation={'baseline_files':len(baseline),'intentionally_updated_files':sorted(set(changed)&permitted),
                  'unexpected_changes':unexpected,'original_tests_preserved':all(p not in changed for p in baseline if p.startswith('tests/')),
                  'historical_artifacts_preserved':all(p not in changed for p in baseline if p.startswith('artifacts/')),
                  'original_controller_and_model_preserved':all(p not in changed for p in ('robot/controller.py','robot/rail_carriage.xml'))}
    (OUT/'preservation.json').write_text(json.dumps(preservation,indent=2)+'\n')
    ledger=json.loads((OUT/'downloads.json').read_text())
    tracked=sum(e['received_bytes'] for e in ledger['entries'])
    reserve=ledger['unmetered_documentation_reserve_bytes']
    plan=json.loads((OUT/'download_plan.json').read_text())
    zstandard=json.loads((OUT/'zstandard_dependency.json').read_text())
    payloads=[]
    for kind in ('runtime','kernel'):
        a=plan[kind];payloads.append((ROOT/'.runtime/day4b1/downloads'/a['name'],a['published_sha256']))
    for a in plan['wheels']:payloads.append((ROOT/'.runtime/day4b1/downloads'/a['filename'],a['sha256']))
    for image in plan['images']:
        for blob in [image['manifest']['config'],*image['manifest']['layers']]:
            payloads.append((ROOT/'.runtime/day4b1/downloads/blobs'/blob['digest'].split(':')[1],blob['digest']))
    payloads.append((ROOT/'.runtime/day4b1/downloads'/zstandard['filename'],zstandard['sha256']))
    download={'tracked_response_body_bytes':tracked,'documentation_metadata_reserve_bytes':reserve,
              'budget_accounted_bytes':tracked+reserve,'budget_bytes':ledger['budget_bytes'],
              'verified_binary_payload_bytes':plan['expected_payload_bytes']+zstandard['bytes'],
              'all_cached_download_hashes_match':all(cached(path,sha) for path,sha in payloads),
              'no_unaccounted_runtime_pulls':'Images were loaded from locally verified OCI archives; runtime startup used an unavailable local placeholder until preloading completed.'}
    (OUT/'download_summary.json').write_text(json.dumps(download,indent=2)+'\n')
    index=json.loads((OUT/'pytest_candidate_index.json').read_text())
    rows=read_trace(Path(index['directory'])/'execution_trace.jsonl')
    verdict=index['verification']
    scenarios={}
    for name,s in verdict['scenario_results'].items():
        directory=Path(index['directory'])/'simulations'/s['simulation_run_id']
        independent=json.loads((directory/'independent_safety_trace.json').read_text())
        scenarios[name]={'simulation_execution':s['simulation_execution'],'independent_verification':s['independent_verification'],
            'physical_safety_status':s['physical_safety_status'],'contact_time_s':s['first_wall_contact']['time'],
            'contact_velocity_ms':s['contact_velocity_ms'],'minimum_clearance_m':s['minimum_clearance_m'],'final_speed_ms':s['final_speed_ms'],
            'force_range_n':s['applied_force_n'],'max_telemetry_difference':independent['max_telemetry_difference'],
            'max_action_difference':independent['max_action_difference'],'max_precontrol_state_difference':independent['max_precontrol_state_difference'],
            'measured_actuator_force_within_limits':independent['measured_actuator_force_within_limits'],
            'artifacts':str(directory.relative_to(ROOT))}
    empty=json.loads(runtime_command(backend.config,['list','--all','--format','json']))==[]
    checks={'complete_pytest_passed':result.returncode==0 and passed>=154,
            'real_containment_passed':proof['status']=='PASS' and all(proof['checks'].values()),
            'all_abc_independently_executed':set(scenarios)=={'A','B','C'} and all(s['independent_verification']=='PASS' for s in scenarios.values()),
            'unsafe_negative_control_rejected':all(s['physical_safety_status']=='FAIL' for s in scenarios.values()),
            'candidate_trace_valid':bool(rows),'old_tests_and_artifacts_unchanged':not unexpected,
            'downloads_verified_within_budget':download['all_cached_download_hashes_match'] and tracked+reserve<=ledger['budget_bytes'],
            'no_candidate_vms_remain':empty}
    status='PASS' if all(checks.values()) else 'FAIL'
    evidence={'secure_execution_backend':status,'day4b2_readiness':'GO' if status=='PASS' else 'NO-GO',
              'checks':checks,'pytest':pytest_result,'downloads':download,'preservation':preservation,
              'containment_check_count':len(proof['checks']),'containment_certificate':proof,
              'candidate_provenance':'Developer-authored unsafe negative control; no model, no repaired-controller claim',
              'candidate_sha256':verdict['source_sha256'],'candidate_evidence_directory':index['directory'],
              'candidate_trace_events':len(rows),'scenarios':scenarios,'live_ai_integration':'BLOCKED; no API credentials used',
              'remaining_limitations':proof['limitations']+['Qualification expires after 24 hours and binds this machine/build; rerun after changes.',
                 'Only supported controller interface and A/B/C behavior are qualified; nondeterminism causes failure.',
                 'Local runtime services and verified images/downloads remain installed; candidate VMs are deleted.',
                 'User-local payload installation is used; no system-wide installer receipt was created.']}
    failures=[]
    current=Path(tempfile.gettempdir())/('pytest-of-'+getpass.getuser())/'pytest-current'
    for folder in sorted(current.glob('test_live_candidate_failures_*')):
        if folder.is_symlink():continue
        target=OUT/'failure_evidence'/folder.name
        target.mkdir(parents=True,exist_ok=True)
        for file in (folder/'verify').glob('candidate_*.json'):
            shutil.copyfile(file,target/file.name)
            failures.append({'artifact':str(target/file.name),'result':json.loads(file.read_text())})
        if (folder/'trace').exists():shutil.copyfile(folder/'trace',target/'execution_trace.jsonl')
        if (folder/'store').exists():shutil.copytree(folder/'store',target/'proposal',dirs_exist_ok=True)
    (OUT/'failure_evidence.json').write_text(json.dumps(failures,indent=2)+'\n')
    evidence['candidate_failure_probes']=failures
    (OUT/'verification.json').write_text(json.dumps(evidence,indent=2)+'\n')
    from tools.day4b1_report import write_report
    write_report(evidence)
    print(json.dumps({'secure_execution_backend':status,'checks':checks,'downloads':download,'scenarios':scenarios},indent=2))
    if status!='PASS':raise SystemExit(1)

if __name__=='__main__':main()
