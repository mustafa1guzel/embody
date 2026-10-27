"""Data-boundary tests and real-physics verification; live VM tests require qualification."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import time
import io

import mujoco
import numpy as np
import pytest

from core.agent.vm_protocol import ProtocolError, MAX_FRAME, encode, decode, command_reply, numbers
from core.agent.vm_backend import AppleVMBackend, IsolationBlocked, clean_environment, DEFAULT_CONFIG
from core.agent.candidate_execution import verify_fresh, execute_candidate
from core.agent.patching import CandidateStore, TARGET, read_project_file
from core.agent.trace import ExecutionTrace
from core.agent.verification import CandidateVerifier
from core.day3 import load_scenarios
from core.simulation import ROOT, run_simulation

@pytest.mark.parametrize('raw', [b'{}', b'[]\n', b'null\n', b'{"x":1,"x":2}\n', b'{"x":NaN}\n', b'{"x":Infinity}\n', b'\xff\n', b'X'*(MAX_FRAME+1)+b'\n'])
def test_wire_rejects_invalid_frames(raw):
    with pytest.raises(ProtocolError):decode(raw)

def test_wire_unicode_roundtrip_and_bound():
    assert decode(encode({'source':'# developer fixture \u03c0\n'}))=={'source':'# developer fixture \u03c0\n'}
    with pytest.raises(ProtocolError):encode({'x':'x'*MAX_FRAME})
    with pytest.raises(ProtocolError):encode({'x':float('nan')})

@pytest.mark.parametrize('vector', [[True],[float('nan')],[float('inf')],['1'],[],[1,2],[1e100]])
def test_actuator_requests_require_bounded_finite_numbers(vector):
    with pytest.raises(ProtocolError):command_reply({'v':1,'seq':0,'ctrl':vector},0,1)

@pytest.mark.parametrize('reply', [
    {'v':1,'seq':1,'ctrl':[0]}, {'v':True,'seq':0,'ctrl':[0]},
    {'v':1,'seq':False,'ctrl':[0]}, {'v':1,'seq':0,'ctrl':[0],'safe':True},
    {'v':1,'seq':0,'safety_acceptance':'PASS'},
])
def test_worker_cannot_supply_safety_verdict_or_wrong_sequence(reply):
    with pytest.raises(ProtocolError):command_reply(reply,0,1)

def test_launcher_environment_is_explicit_and_does_not_forward_secrets(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','dummy-not-a-credential')
    monkeypatch.setenv('SSH_AUTH_SOCK','/host/dummy')
    result=clean_environment({'app_root':'/runtime','install_root':'/install','config_home':'/config'})
    assert set(result)=={'HOME','PATH','CONTAINER_APP_ROOT','CONTAINER_INSTALL_ROOT','XDG_CONFIG_HOME'}
    assert 'dummy-not-a-credential' not in result.values()

def test_missing_operator_config_fails_closed(tmp_path):
    with pytest.raises(FileNotFoundError):AppleVMBackend(tmp_path/'absent')

def test_download_budget_rejects_request_before_network(tmp_path,monkeypatch):
    from tools import day4b1_provision as provision
    monkeypatch.setattr(provision,'OUT',tmp_path)
    monkeypatch.setattr(provision,'LEDGER',tmp_path/'ledger.json')
    monkeypatch.setattr(provision,'BUDGET',100)
    provision.save({'entries':[{'received_bytes':60}],'unmetered_documentation_reserve_bytes':10})
    monkeypatch.setattr(provision.urllib.request,'urlopen',lambda *a,**k:pytest.fail('Budget failure must precede network access'))
    with pytest.raises(RuntimeError,match='budget'):provision.get('https://example.invalid',maximum=31)

def test_failed_digest_is_accounted_and_not_a_verified_cache_entry(tmp_path,monkeypatch):
    from tools import day4b1_provision as provision
    monkeypatch.setattr(provision,'OUT',tmp_path)
    monkeypatch.setattr(provision,'LEDGER',tmp_path/'ledger.json')
    provision.save({'entries':[],'unmetered_documentation_reserve_bytes':0})
    monkeypatch.setattr(provision.urllib.request,'urlopen',lambda *a,**k:io.BytesIO(b'wrong'))
    target=tmp_path/'payload'
    with pytest.raises(RuntimeError,match='digest mismatch'):
        provision.get('https://example.invalid',maximum=5,destination=target,expected='0'*64)
    record=provision.ledger()['entries'][0]
    assert record['received_bytes']==5 and record['status']=='FAILED'
    assert not provision.cached(target,'0'*64)

def test_configuration_cannot_escape_local_runtime(tmp_path):
    config={k:'/tmp/outside' for k in ('runtime','kernel','app_root','install_root','config_home','certificate')}
    config.update({'image':'image@sha256:abc','init_image':'init@sha256:abc',
                   'image_local_tag':'image:fixed','init_image_local_tag':'init:fixed'})
    path=tmp_path/'config.json';path.write_text(json.dumps(config))
    with pytest.raises(IsolationBlocked,match='escaped'):AppleVMBackend(path).preflight()

def test_absent_containment_certificate_blocks_validated_candidate(tmp_path):
    class BlockedBackend:
        def preflight(self):raise IsolationBlocked('Containment has not passed')
    store=CandidateStore(ROOT,tmp_path/'store')
    original=read_project_file(ROOT,TARGET)
    proposal=store.propose(target_path=TARGET,expected_original_sha256=original['sha256'],
                           proposed_source=original['content']+'\n# qualification fixture\n',explanation='developer fixture')
    verifier=CandidateVerifier(store,load_scenarios(),tmp_path/'verify',ExecutionTrace(tmp_path/'trace',model_mode='developer_test'),backend=BlockedBackend())
    result=verifier.verify(proposal['candidate_id'])
    assert result['verification_execution']=='BLOCKED' and result['candidate_code_executed'] is False
    assert all(r['simulation_execution']=='NOT_RUN' for r in result['scenario_results'].values())

class TrustedTransportFixture:
    """Unit-test transport replacement runs only named developer-owned callables.

    It never evaluates candidate text and is not evidence of isolation.
    All MuJoCo state transitions below are real.
    """
    def __init__(self,force=0):self.force=force;self.sessions=0
    @contextmanager
    def controller(self,source,xml):
        self.sessions+=1
        exchanges=[]
        def control(model,data):
            state=np.empty(mujoco.mj_stateSize(model,mujoco.mjtState.mjSTATE_INTEGRATION))
            mujoco.mj_getState(model,data,state,mujoco.mjtState.mjSTATE_INTEGRATION)
            data.ctrl[0]=self.force
            exchanges.append({'seq':len(exchanges),'state':state.tolist(),'ctrl':[self.force]})
        yield control,exchanges,{'kind':'unit_test_transport_only'}

def real_run(tmp_path,force=0):
    body,world=load_scenarios()['A']
    transport=TrustedTransportFixture(force)
    with transport.controller('not executed','') as (controller,exchanges,_):
        run=run_simulation(bodybase=body,worldbase=world,controller=controller,save_render=False,artifacts_dir=tmp_path/'physics')
    return run,exchanges

def test_fresh_verifier_uses_actual_requested_controller_not_original_baseline(tmp_path):
    run,exchanges=real_run(tmp_path)
    result=verify_fresh(run,TrustedTransportFixture(0),'not executed',exchanges)
    assert result['verification_execution']=='PASS'
    assert result['safety_acceptance']['status']=='FAIL'
    assert result['max_action_difference']==0 and result['max_precontrol_state_difference']==0
    assert all(r['control']==0 for r in result['trace'])
    assert any(s['wall_collision'] for s in run['telemetry'])

def test_fresh_verifier_rejects_changed_model_snapshot(tmp_path):
    run,exchanges=real_run(tmp_path)
    run['effective_model_xml']+='\n'
    with pytest.raises(ValueError,match='snapshot hash'):verify_fresh(run,TrustedTransportFixture(),'not executed',exchanges)

def test_failure_retains_completed_scenario_measurements(tmp_path):
    class LaterFailure(TrustedTransportFixture):
        def preflight(self):pass
        @contextmanager
        def controller(self,source,xml):
            if self.sessions==2:raise RuntimeError('developer transport failure on scenario B')
            with super().controller(source,xml) as result:yield result
    store=CandidateStore(ROOT,tmp_path/'store');source=read_project_file(ROOT,TARGET)
    proposal=store.propose(target_path=TARGET,expected_original_sha256=source['sha256'],proposed_source=source['content']+'\n# transport-only unit fixture\n',explanation='No candidate text executed by unit transport')
    verifier=CandidateVerifier(store,load_scenarios(),tmp_path/'verify',ExecutionTrace(tmp_path/'trace',model_mode='unit_transport_only'),backend=LaterFailure())
    result=verifier.verify(proposal['candidate_id'])
    assert result['verification_execution']=='FAIL'
    assert result['scenario_results']['A']['independent_verification']=='PASS'
    assert result['scenario_results']['B']['simulation_execution']=='NOT_VERIFIED'
    assert len(verifier.runs)==1

@pytest.mark.parametrize('tamper', ['state','action','telemetry','controller'])
def test_fresh_verifier_detects_state_action_telemetry_or_controller_inconsistency(tmp_path,tamper):
    run,exchanges=real_run(tmp_path)
    transport=TrustedTransportFixture()
    if tamper=='state':exchanges[10]['state'][0]+=.1
    if tamper=='action':exchanges[10]['ctrl'][0]=1
    if tamper=='telemetry':run['telemetry'][10]['velocity']+=.1
    if tamper=='controller':transport.force=1
    result=verify_fresh(run,transport,'not executed',exchanges)
    assert result['verification_execution']=='FAIL'

def test_three_scenario_host_authority_with_real_mujoco_and_test_transport(tmp_path):
    path=tmp_path/'fixture.py';path.write_text('# developer transport fixture, never executed')
    candidate={'candidate_id':'test_transport_only','source_path':path,
               'proposed_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    transport=TrustedTransportFixture(force=10)
    results,records=execute_candidate(candidate,load_scenarios(),transport,tmp_path/'runs')
    assert set(results)=={'A','B','C'} and transport.sessions==6
    assert len(records)==3
    for summary in results.values():
        assert summary['independent_verification']=='PASS'
        assert summary['physical_safety_status']=='FAIL'
        # Host MuJoCo clamps the requested 10 N to the scenario's actual 4 N motor limit.
        assert summary['applied_force_n']['maximum']==4
        assert summary['controller_consistency_checked']

@pytest.fixture(scope='module')
def qualified_live_backend():
    if os.environ.get('EMBODY_RUN_VM_TESTS')!='1':pytest.skip('Set EMBODY_RUN_VM_TESTS=1 after operator qualification')
    from core.day4b1 import qualify, OUTPUT
    result=qualify(output=OUTPUT/('pytest_containment_'+str(time.time_ns())))
    assert result['status']=='PASS',result['checks']
    backend=AppleVMBackend()
    backend.preflight()
    return backend

@pytest.mark.live_vm
def test_live_containment_all_probes(qualified_live_backend):
    proof=qualified_live_backend.preflight()
    assert len(proof['checks'])>=29 and all(proof['checks'].values())
    assert proof['checks']['original_project_integrity']
    assert proof['observations']['memory_group']['reply']['oom_kill_after']>0
    assert proof['observations']['network']['reply']['attempts'][0]['name']=='ENETUNREACH'

@pytest.mark.live_vm
def test_live_gate_stale_evidence_rejected_and_real_candidate_abc(tmp_path,qualified_live_backend):
    from core.agent.vm_backend import identity
    from core.agent.tools import AgentTools
    from core.agent.trace import read_trace
    from core.day4b1 import OUTPUT
    backend=qualified_live_backend
    proof=backend.preflight()
    assert proof['status']=='PASS' and proof['identity']==identity(backend.config)
    original_config=backend.config.copy()
    backend.config['image']=backend.config['image'].replace('sha256:','sha256:0')
    with pytest.raises(IsolationBlocked):backend.preflight()
    backend.config=original_config
    output=OUTPUT/('pytest_candidate_'+str(time.time_ns()))
    trace=ExecutionTrace(output/'execution_trace.jsonl',model_mode='developer_fixture_no_model')
    tools=AgentTools(output,trace,backend=backend)
    source=tools.read_project(TARGET)
    proposal=tools.propose_patch(TARGET,source['sha256'],source['content'].replace('BRAKING_THRESHOLD_M = 0.12','BRAKING_THRESHOLD_M = 0.0'),'Developer-authored unsafe negative control, no model')
    dispatched=tools.dispatch('run_simulation',{'scenario_id':'B','controller_variant':proposal['candidate_id']})
    assert dispatched['ok'],dispatched
    result=next(row['payload'] for row in reversed(read_trace(trace.path)) if row['event']=='candidate_verification')
    assert result['verification_execution']=='PASS',result
    assert result['physical_safety_status']=='FAIL' and result['candidate_code_executed'] is True
    assert set(result['scenario_results'])=={'A','B','C'}
    for summary in result['scenario_results'].values():
        assert summary['first_wall_contact'] is not None
        assert summary['independent_verification']=='PASS'
        assert summary['controller_consistency_checked']
        evidence=tools.inspect_failure(summary['simulation_run_id'])
        assert evidence['evidence']['controller']['source_sha256']==proposal['proposed_sha256']
    assert read_project_file(ROOT,TARGET)==source
    (OUTPUT/'pytest_candidate_index.json').write_text(json.dumps({'directory':str(output),'verification':result},indent=2)+'\n')

@pytest.mark.live_vm
@pytest.mark.parametrize('failure',['exception','nan'])
def test_live_candidate_failures_never_receive_safety_acceptance(tmp_path,qualified_live_backend,failure):
    source=read_project_file(ROOT,TARGET)
    proposed=(source['content'].replace('    joint =',"    raise ValueError('developer failure probe')\n    joint =",1)
              if failure=='exception' else source['content']+"    data.ctrl[motor] = float('nan')\n")
    store=CandidateStore(ROOT,tmp_path/'store')
    proposal=store.propose(target_path=TARGET,expected_original_sha256=source['sha256'],proposed_source=proposed,explanation='Developer failure probe, no model')
    assert proposal['validation_status']=='VALID'
    verifier=CandidateVerifier(store,load_scenarios(),tmp_path/'verify',ExecutionTrace(tmp_path/'trace',model_mode='developer_failure_probe'),backend=qualified_live_backend)
    result=verifier.verify(proposal['candidate_id'])
    assert result['verification_execution']=='FAIL' and result['physical_safety_status']=='NOT_EVALUATED'
    assert 'ProtocolError' in result['reason']
    from core.agent.vm_backend import runtime_command
    assert json.loads(runtime_command(qualified_live_backend.config,['list','--all','--format','json']))==[]
