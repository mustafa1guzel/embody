"""Operator-only containment qualification and developer-fixture evaluation; no model API."""
import argparse
import errno
import hashlib
import inspect
import json
import os
from pathlib import Path
import time
from unittest.mock import patch

import mujoco
import numpy as np

from core.agent.vm_backend import AppleVMBackend, VMProcess, DEFAULT_CONFIG, IsolationBlocked, identity, runtime_command, file_hash
from core.agent.vm_protocol import ProtocolError, VERSION, command_reply
from core.agent.patching import read_project_file, TARGET
from core.agent.tools import AgentTools
from core.agent.trace import ExecutionTrace
from core.day3 import load_scenarios
from core.simulation import ROOT, DEFAULT_MODEL_PATH, compile_context_model, write_json, collision_surfaces
from robot.controller import faulty_braking_controller

OUTPUT=ROOT/'artifacts/day4b1/implementation'

def reviewed_protected_inventory():
    # Explicit version2 selection after separate human migration approval.
    old_path=OUTPUT/'before.json'
    v2_path=ROOT/'artifacts/phase18e_2/20261025/security/protected_baseline_v2.json'
    if file_hash(old_path)!='13b3b8a215715518da7eb2b6af640512cceb36c62d165b93744e4c4742fb39be' or file_hash(v2_path)!='c58b168f2c6b8aae96802e59187d633e9fc93414372c9e047a624d6aa81eba14':
        raise IsolationBlocked('Versioned protected baseline identity differs')
    old=json.loads(old_path.read_text());data=json.loads(v2_path.read_text());new=data['files']
    if set(new)!=set(old) or [n for n in old if old[n]!=new[n]]!=['requirements.txt']:
        raise IsolationBlocked('Unapproved protected baseline delta')
    if old['requirements.txt']!='4bdc1ab8bcd6c287b4e0e4f73c6be2b38127a0f75ba49da858fadb1bc3201f5f' or new['requirements.txt']!='b90007317a9e384967c9a9e7c891795deeee4bcaa3b26c6514bac071fe281fcb':
        raise IsolationBlocked('Requirements migration differs')
    return new

def original_project_intact():
    baseline=reviewed_protected_inventory()
    # Explicitly authorized adapter integration changes do not alter the protected
    # controller/model, original tests or historical evidence. Current trusted
    # sources are still all bound into the containment certificate's identity.
    authorized={'.gitignore','README.md','pytest.ini','core/agent/tools.py','core/agent/verification.py',
                'core/agent/models.py', 'core/agent/patching.py'}
    # Day 4B.2 explicitly authorizes source-policy metadata/diagnostic refactoring.
    # Original validation acceptance is regression checked; the current full
    # source tree is still identity-bound and must pass fresh containment probes.
    # Finder metadata is not source or experiment evidence. Opening a directory
    # may rewrite it; never exempt any model, measurement, test or configuration.
    return all((ROOT/path).is_file() and file_hash(ROOT/path)==sha
               for path,sha in baseline.items() if path not in authorized and Path(path).name!='.DS_Store')

def qualify(config_path=DEFAULT_CONFIG, output=OUTPUT):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    config=json.loads(Path(config_path).read_text())
    certificate=Path(config['certificate'])
    certificate.unlink(missing_ok=True)
    observations={};checks={}
    def run(name,*,cpu=30,wall=15):
        started=time.monotonic()
        with VMProcess(config,cpu_seconds=cpu,wall_seconds=wall) as vm:
            answer=vm.send({'probe':name})
        observations[name]={'reply':answer,'wall_seconds':time.monotonic()-started,
                            'cleanup_confirmed':vm.cleaned,'command':vm.command}
        return answer
    try:
        checks['original_project_integrity']=original_project_intact()
        if not checks['original_project_integrity']:
            raise IsolationBlocked('Original project inventory differs before containment qualification')
        with patch.dict(os.environ, {'OPENAI_API_KEY':'EMBODY-DUMMY-NOT-A-CREDENTIAL', 'EMBODY_CANARY_SECRET':'EMBODY-DUMMY'}):
            inventory=run('inventory')
        checks['non_root']=inventory['uid']==65532
        helper=('import mujoco\nimport numpy as np\n'+inspect.getsource(collision_surfaces)).encode()
        checks['image_matches_current_worker_sources']=(
            inventory['worker_sha256']==hashlib.sha256((ROOT/'core/agent/vm_worker.py').read_bytes()).hexdigest()
            and inventory['protocol_sha256']==hashlib.sha256((ROOT/'core/agent/vm_protocol.py').read_bytes()).hexdigest()
            and inventory['helper_sha256']==hashlib.sha256(helper).hexdigest())
        checks['no_credentials_or_host_environment']=not ({'OPENAI_API_KEY','EMBODY_CANARY_SECRET','SSH_AUTH_SOCK','AWS_ACCESS_KEY_ID'} & set(inventory['env_keys']))
        checks['network_interface_absent']=inventory['interfaces']==['lo']
        checks['capabilities_dropped']='CapEff:\t0000000000000000' in inventory['status'] and 'CapBnd:\t0000000000000000' in inventory['status']
        checks['privilege_escalation_disabled']='NoNewPrivs:\t1' in inventory['status']
        checks['root_read_only']=any(' / ro,' in row for row in inventory['mountinfo'].splitlines())
        checks['scratch_mount_bounded']='size=32768k' in inventory['mountinfo'] and 'size=8192k' in inventory['mountinfo']
        checks['no_host_filesystem_mount']=not any(x in inventory['mountinfo'] for x in ('virtiofs','9p','/Users/','/host'))
        checks['memory_address_space_limit']=inventory['limits']['AS']==[805306368,805306368]
        checks['process_and_file_limits']=inventory['limits']['NPROC']==[16,16] and inventory['limits']['NOFILE']==[64,64] and inventory['limits']['CORE']==[0,0]
        cg=inventory['cgroup_limits']
        checks['cpu_workload_quota']=cg.get('cpu.max')=='100000 100000'
        checks['memory_workload_quota']=cg.get('memory.max')=='1073741824'
        checks['bounded_vm_overhead']=inventory['cpus']<=2 and inventory['memory_bytes']<=1_207_959_552
        canary=Path('/private/tmp/embody-host-canary')
        shared_canary=Path('/Users/Shared/embody-host-canary')
        created_canaries=[]
        marker='EMBODY dummy isolation canary; not a credential'
        try:
            for path in (canary,shared_canary):
                with path.open('x') as handle:
                    created_canaries.append(path)
                    handle.write(marker)
            checks['host_canaries_independent']=not canary.samefile(shared_canary)
            if not checks['host_canaries_independent']:
                raise IsolationBlocked('Host canaries must be distinct files')
            fs=run('filesystem')
            expected_fs={'/opt/embody/probe-writable','/etc/embody-forbidden','/host/README.md',str(canary),str(shared_canary)}
            checks['filesystem_denials']=set(fs)==expected_fs and fs['/opt/embody/probe-writable']==errno.EROFS and all(type(v) is int and v in (errno.ENOENT,errno.EACCES,errno.EROFS) for v in fs.values())
            checks['host_canary_unchanged']=all(path.read_text()==marker for path in created_canaries)
        finally:
            for path in reversed(created_canaries):path.unlink()
        net=run('network')
        checks['outbound_network_denied']=all(x['name'] in ('ENETUNREACH','EAFNOSUPPORT') for x in net['attempts'])
        scratch=run('scratch')
        checks['scratch_exhaustion_enforced']=scratch['errno'] in (errno.ENOSPC,errno.EFBIG) and scratch['written']<=33_554_432
        checks['memory_allocation_denied']=run('memory')=={'allocation':'DENIED'}
        group=run('memory_group',wall=20)
        checks['aggregate_memory_enforced']=group['oom_kill_after']>group['oom_kill_before'] and 9 in group['child_statuses']
        processes=run('processes')
        checks['process_limit_enforced']=processes['denial']=='EAGAIN' and processes['spawned']<=15
        files=run('files')
        checks['file_limit_enforced']=files['denial']=='EMFILE' and files['opened']<64
        for name in ('invalid','oversized'):
            try:
                run(name)
                checks[name+'_rejected']=False
            except ProtocolError as exc:
                checks[name+'_rejected']=True
                observations[name]={'rejection':str(exc),'cleanup_confirmed':True}
        for name in ('timeout','descendant'):
            started=time.monotonic()
            vm=None
            try:
                with VMProcess(config,wall_seconds=3) as vm:
                    vm.send({'probe':name})
                    if name=='descendant':vm.receive()
                checks[name+'_terminated']=False
            except TimeoutError:
                checks[name+'_terminated']=bool(vm and vm.cleaned) and time.monotonic()-started<15
                observations[name]={'elapsed_s':time.monotonic()-started,'cleanup_confirmed':vm.cleaned}
        started=time.monotonic()
        with VMProcess(config,wall_seconds=12,cpu_seconds=2) as vm:
            began=vm.send({'probe':'cpu'})
            try:vm.receive();ended=False
            except ProtocolError:ended=True
            code=vm.process.wait(timeout=3)
        elapsed=time.monotonic()-started
        checks['cpu_time_limit_enforced']=ended and began['cpu_limit']==[2,2] and code in (137,152) and elapsed<10
        observations['cpu']={'wall_seconds':elapsed,'cli_exit_code':code,'cleanup_confirmed':vm.cleaned,'reply':began}
        with VMProcess(config) as vm:
            vm.send({'probe':'inventory'})
            try:
                with VMProcess(config):pass
                checks['one_vm_lock']=False
            except IsolationBlocked:checks['one_vm_lock']=True
        # Trusted baseline only: prove actual Linux MuJoCo state transfer before any candidate gate.
        source=read_project_file(ROOT,TARGET)['content']
        parity=[]
        for name,(body,world) in load_scenarios().items():
            model,xml=compile_context_model(DEFAULT_MODEL_PATH,body,world)
            data=mujoco.MjData(model)
            with VMProcess(config) as vm:
                ready=vm.send({'v':VERSION,'source':source,'sha256':hashlib.sha256(source.encode()).hexdigest(),'xml':xml})
                assert ready['mujoco']==mujoco.__version__ and ready['xml_sha256']==hashlib.sha256(xml.encode()).hexdigest()
                maximum=0.0
                for seq,(position,velocity) in enumerate(((0,1.2),(.5,-.2),(1.3,1),(1.7,1.2),(1.8,.7))):
                    data.qpos[0]=position;data.qvel[0]=velocity;data.time=seq*.005
                    data.qacc_warmstart[:]=.17;data.qfrc_applied[:]=.1;data.ctrl[:]=.2
                    mujoco.mj_forward(model,data)
                    state=np.empty(mujoco.mj_stateSize(model,mujoco.mjtState.mjSTATE_INTEGRATION))
                    mujoco.mj_getState(model,data,state,mujoco.mjtState.mjSTATE_INTEGRATION)
                    answer=command_reply(vm.send({'v':VERSION,'seq':seq,'state':state.tolist()}),seq,model.nu)
                    faulty_braking_controller(model,data)
                    maximum=max(maximum,float(np.max(np.abs(np.array(answer)-data.ctrl))))
                parity.append({'scenario':name,'handshake':ready,'state_samples':5,'max_command_difference':maximum,'cleanup_confirmed':False})
            parity[-1]['cleanup_confirmed']=vm.cleaned
        observations['trusted_baseline_linux_parity']=parity
        checks['mujoco_state_sync']=all(p['max_command_difference']<=1e-12 for p in parity)
        checks['cleanup']=json.loads(runtime_command(config,['list','--all','--format','json']))==[]
        checks['original_project_integrity']=checks['original_project_integrity'] and original_project_intact()
    except Exception as exc:
        checks['probe_execution_completed']=False
        observations['exception']={'type':type(exc).__name__,'message':str(exc)}
    result={'status':'PASS' if checks and all(checks.values()) else 'FAIL','checks':checks,'observations':observations,
            'created_unix':time.time(),'identity':identity(config),
            'scope':'Developer-authored probes and existing trusted baseline only; no model source executed',
            'limitations':['Not an external security audit or proof against hypervisor/kernel vulnerabilities',
                           'No seccomp syscall filter is claimed; VM boundary, non-root UID, no-new-privileges and resource caps are used']}
    write_json(output/'containment.json',result)
    write_json(output/f'containment_attempt_{time.time_ns()}.json',result)
    if result['status']=='PASS':write_json(certificate,result)
    return result

def evaluate(config_path=DEFAULT_CONFIG,output=OUTPUT):
    backend=AppleVMBackend(config_path)
    backend.preflight()
    output=Path(output)/('candidate_evaluation_'+str(time.time_ns()))
    trace=ExecutionTrace(output/'execution_trace.jsonl',model_mode='developer_authored_fixture_no_model')
    tools=AgentTools(output,trace,backend=backend)
    original=tools.dispatch('read_project',{'path':TARGET})['result']
    for name in tools.scenarios:
        tools.dispatch('get_robot_context',{'scenario_id':name})
        tools.dispatch('get_world_context',{'scenario_id':name})
    proposal=tools.dispatch('propose_patch',{'target_path':TARGET,'expected_original_sha256':original['sha256'],
        'proposed_source':original['content'].replace('BRAKING_THRESHOLD_M = 0.12','BRAKING_THRESHOLD_M = 0.0'),
        'explanation':'Developer-authored deliberately later-braking negative control. No model or repair claim.'})['result']
    result=tools.verifier.verify(proposal['candidate_id'])
    write_json(output/'verification.json',result)
    write_json(OUTPUT/'candidate_evaluation_index.json',{'directory':str(output),'verification':result})
    return result

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=('qualify','evaluate'))
    args=parser.parse_args()
    result=qualify() if args.operation=='qualify' else evaluate()
    print(json.dumps(result,indent=2))
    if result.get('status',result.get('verification_execution'))!='PASS':raise SystemExit(1)

if __name__=='__main__':main()
