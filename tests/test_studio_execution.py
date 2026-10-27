"""Explicit offline approval/provider fixtures; real engineering, never paid AI."""
import copy
import json
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from ide_api.engineering_ai import EngineeringAI,settings
from ide_api.studio_execution import StudioExecution,NativeOperator,SCRIPT
from engineering.project import identity
from robustness.contracts import write_once
from tests.test_workspace_ai import prepare,approve,mock_client
from tools.studio_worker import execute

@pytest.fixture
def ai(tmp_path):
    value=EngineeringAI(tmp_path/'studio');value.draft(create=True);return value

class FixtureOperator:
    def __init__(self,answer=True):self.answer=answer;self.calls=[]
    def available(self):return True
    def confirm(self,q):self.calls.append(q);return self.answer

def fixture_runner(ai,key,receipt,folder):
    client,_=mock_client(ai)
    return execute(ai,key,receipt,folder,offline_client=client)

def test_expanded_policy_realistic_reservation_and_exact_native_scope(ai):
    options={'profile':'expanded','hard_cap_usd':'2.50','native_preview':False}
    p=ai.draft().current();v=ai.prepare(workflow='assembly',task='Build me a simple four-wheel robot car.',expected_sha256=identity(p),expected_revision=0,selection='',run_options=options)
    d=v['manifest']['definition'];assert d['run_options']==options and d['policy']['maximum_reservation_usd']=='2.3538'
    assert d['policy']['max_requests']==3 and d['policy']['max_output_tokens']==25000 and max(d['serialized_input_bounds'])<=163840
    assert d['policy']['native_previews']==0 and 'NOT AUTHORIZED' in d['native_execution']
    other=ai.prepare(workflow='assembly',task=v['task'],expected_sha256=identity(p),expected_revision=0,selection='',run_options={**options,'native_preview':True})
    assert other['request_id']!=v['request_id']
    c,_=mock_client(ai);result=ai.execute(v['request_id'],approve(v),offline_client=c);assert result['status']=='COMPILED'
    with pytest.raises(ValueError,match='not authorized'):ai.verify(v['request_id'],approve(v))

@pytest.mark.parametrize('options',[{}, {'profile':'expanded','hard_cap_usd':'1.24','native_preview':False},{'profile':'expanded','hard_cap_usd':'2.51','native_preview':False},{'profile':'standard','hard_cap_usd':'NaN','native_preview':False},{'profile':'standard','hard_cap_usd':2.5,'native_preview':False},{'profile':'standard','hard_cap_usd':'2.50','native_preview':1},{'profile':'other','hard_cap_usd':'2.50','native_preview':False},{'profile':'standard','hard_cap_usd':'2.50','native_preview':False,'approve':True}])
def test_bad_budget_options_reject_without_authority(options):
    with pytest.raises(ValueError):settings('assembly',options)

def test_native_operator_is_fixed_script_data_argv_and_cancel_default(monkeypatch):
    op=NativeOperator();monkeypatch.setattr(op,'available',lambda:True);calls=[]
    def run(command,**kw):calls.append((command,kw));return SimpleNamespace(returncode=0,stdout='EXPLICIT_APPROVE\n')
    monkeypatch.setattr('ide_api.studio_execution.subprocess.run',run)
    q={'task':'quoted " & do shell script "malicious"','policy':settings('assembly'),'project_sha256':'p'*64,'manifest_sha256':'m'*64}
    assert op.confirm(q);command,kw=calls[0];assert command[:4]==['/usr/bin/osascript','-e',SCRIPT,'--'] and q['task'] in command[4]
    assert 'default button "Cancel"' in SCRIPT and not kw.get('shell') and kw['timeout']==125
    monkeypatch.setattr('ide_api.studio_execution.subprocess.run',lambda *a,**k:SimpleNamespace(returncode=1,stdout='EXPLICIT_APPROVE'))
    assert op.confirm(q) is False

def test_declined_operator_never_creates_client_reservation_or_approval(ai,monkeypatch):
    v=prepare(ai);op=FixtureOperator(False);service=StudioExecution(ai,operator=op,runner=lambda *a:pytest.fail('No runner after rejection'))
    monkeypatch.setattr('core.agent.credentials.create_openai_client',lambda:pytest.fail('No client'))
    review=service.quote(v['request_id']);result=service.run(review['review_id'])
    assert result['status']=='OPERATOR_DECLINED' and ai.read(v['request_id'])['execution_consumed'] is False
    assert not (service._folder(v['request_id'])/'operator_receipt.json').exists()
    with pytest.raises((ValueError,FileExistsError)):service.run(review['review_id'])

@pytest.mark.parametrize('change',['expired','source','head','cancel'])
def test_stale_review_gate_before_operator_and_client(ai,monkeypatch,change):
    v=prepare(ai);op=FixtureOperator();service=StudioExecution(ai,operator=op,runner=fixture_runner);review=service.quote(v['request_id'])
    if change=='expired':monkeypatch.setattr('ide_api.studio_execution.time.time',lambda:review['expires_unix']+1)
    if change=='source':monkeypatch.setattr(ai,'source_identities',lambda:{})
    if change=='head':
        p=ai.draft().current();p['world']['environment']['gravity_m_s2']=[0,0,-9.6];ai.draft()._commit(p)
    if change=='cancel':ai.cancel(v['request_id'])
    with pytest.raises(ValueError):service.launch(review['review_id'],lambda f:f())
    assert not op.calls and not (service._folder(v['request_id'])/'begin.json').exists()

def test_broker_rechecks_after_confirmation_and_duplicate_launch_uses_one_job(ai):
    v=prepare(ai,run_options={'profile':'standard','hard_cap_usd':'1.24','native_preview':False});op=FixtureOperator();service=StudioExecution(ai,operator=op,runner=fixture_runner);review=service.quote(v['request_id']);jobs=[]
    def queue(fn):jobs.append(fn);return {'job_id':'fixture-job'}
    assert service.launch(review['review_id'],queue)==service.launch(review['review_id'],queue)
    assert len(jobs)==1;before=ai.draft().current();out=jobs[0]();assert out['status']=='COMPILED'
    r=ai.read(v['request_id']);assert r['origin']=='OFFLINE_MOCK_TRANSPORT_NOT_AI' and r['proposal'] and ai.draft().current()==before
    assert service.status(v['request_id'])['active'] is False and len(op.calls)==1
    events=service.status(v['request_id'])['events'];assert any(e['event']=='model_request_started' for e in events) and any(e['event']=='geometry_compiled' for e in events)

def test_server_restart_never_turns_reservation_into_running(ai):
    v=prepare(ai);service=StudioExecution(ai,operator=FixtureOperator());folder=service._folder(v['request_id']);folder.mkdir(parents=True);write_once(folder/'begin.json',{'request_id':v['request_id']})
    state=service.status(v['request_id']);assert state['active'] is False and state['stage']=='UNKNOWN_OUTCOME'
    with pytest.raises(ValueError):service.quote(v['request_id'])

def test_manual_wheel_followup_uses_actual_typed_compiler_and_preserves_model_plan(ai):
    v=prepare(ai);c,_=mock_client(ai);r=ai.execute(v['request_id'],approve(v),offline_client=c);q=copy.deepcopy(r['proposal']);before=ai.draft().current()
    edit=ai.followup(request_id=v['request_id'],proposal_id=q['proposal_id'],diameter_m=.072)
    assert edit['origin']=='MANUAL_TYPED_FOLLOWUP_NOT_AI' and edit['parent_origin']=='OFFLINE_MOCK_TRANSPORT_NOT_AI' and edit['new_model_decisions'] is False
    assert edit['proposal']['assembly_plan']['steps'][:-1]==q['assembly_plan']['steps'] and len(edit['operations'])==4
    assert {s['parameters']['outer_diameter_m'] for s in edit['proposal']['proposed_project']['shape_specs'] if s['family']=='wheel'}=={.072}
    assert edit['simulation']=='NOT_VERIFIED' and ai.read(v['request_id'])['proposal']==q and ai.draft().current()==before
    assert ai.read_followup(edit['followup_id'])==edit and ai.followup(request_id=v['request_id'],proposal_id=q['proposal_id'],diameter_m=.072)==edit
    for diameter in (True,float('nan'),-.01,.251):
        with pytest.raises(ValueError):ai.followup(request_id=v['request_id'],proposal_id=q['proposal_id'],diameter_m=diameter)
    with pytest.raises(ValueError):ai.followup(request_id=v['request_id'],proposal_id='f'*64,diameter_m=.072)

def test_http_never_accepts_browser_approval_or_transport(http,tmp_path,monkeypatch):
    client,server=http;server.ide._engineering_ai=EngineeringAI(tmp_path/'http');server.ide.engineering_ai.draft(create=True)
    v=prepare(server.ide.engineering_ai);broker=StudioExecution(server.ide.engineering_ai,operator=FixtureOperator(False));server.ide._studio_execution=broker
    monkeypatch.setattr('core.agent.credentials.create_openai_client',lambda:pytest.fail('No credentials before real operator authority'))
    q=client.post('/api/ai-engineering/review-run',json={'request_id':v['request_id']});assert q.status_code==200
    for extra in ({'approval':approve(v)},{'offline_client':True},{'command':'anything'}):assert client.post('/api/ai-engineering/start-building',json={'review_id':q.json()['review_id'],**extra}).status_code==400
    assert client.post('/api/ai-engineering/start-building',json={'review_id':q.json()['review_id']},headers={'Origin':'https://evil.invalid'}).status_code==403
    assert server.jobs=={} and not v['execution_consumed']

def test_native_confirmation_cannot_cover_source_change_during_dialog(ai):
    v=prepare(ai)
    class ChangingOperator(FixtureOperator):
        def confirm(self,q):
            p=ai.draft().current();p['world']['environment']['gravity_m_s2']=[0,0,-9.5];ai.draft()._commit(p);return True
    service=StudioExecution(ai,operator=ChangingOperator(),runner=lambda *a:pytest.fail('No runner after head drift'))
    q=service.quote(v['request_id'])
    with pytest.raises(ValueError):service.run(q['review_id'])
    assert not (service._folder(v['request_id'])/'operator_receipt.json').exists() and not ai.read(v['request_id'])['execution_consumed']

def test_worker_is_fixed_deadline_command_with_no_browser_arguments(ai,monkeypatch):
    v=prepare(ai,run_options={'profile':'standard','hard_cap_usd':'1.24','native_preview':False});service=StudioExecution(ai,operator=FixtureOperator());review=service.quote(v['request_id']);commands=[]
    class Process:
        def __init__(self,command,**kwargs):commands.append((command,kwargs))
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def poll(self):return None
        def wait(self,*,timeout):assert timeout==600;raise __import__('subprocess').TimeoutExpired('fixture-worker',timeout)
        def kill(self):self.killed=True
    # Second wait after kill is argument-free, like the actual subprocess contract.
    calls=0
    def wait(self,timeout=None):
        nonlocal calls
        calls+=1
        if timeout is not None:assert timeout==600;raise __import__('subprocess').TimeoutExpired('fixture-worker',timeout)
        return -9
    Process.wait=wait
    monkeypatch.setattr('ide_api.studio_execution.subprocess.Popen',Process)
    with pytest.raises(TimeoutError):service.run(review['review_id'])
    cmd,kw=commands[0];assert cmd[1:3]==['-m','tools.studio_worker'] and not kw.get('shell')
    assert service.status(v['request_id'])['active'] is False and service.status(v['request_id'])['stage']=='STOPPED_OR_UNKNOWN'

def test_real_native_fixture_through_broker_records_physical_failure_and_no_apply(ai):
    v=prepare(ai,run_options={'profile':'standard','hard_cap_usd':'1.24','native_preview':True});before=ai.draft().current()
    service=StudioExecution(ai,operator=FixtureOperator(),runner=fixture_runner);q=service.quote(v['request_id']);out=service.run(q['review_id'])
    assert out['status']=='PHYSICAL_FAIL'
    r=ai.read(v['request_id']);assert r['origin']=='OFFLINE_MOCK_TRANSPORT_NOT_AI' and r['verification']['measured_signed_forward_displacement_m']<-.005
    assert r['native']['result']['independent_verification']['fresh_native_integration_steps']==200 and ai.draft().current()==before
    assert any(e['event']=='native_simulation_started' for e in service.status(v['request_id'])['events'])

from tests.test_ide_api import service,http

@pytest.mark.parametrize('tamper',['fixture_method','quote_identity','native_scope','expired_handoff'])
def test_production_worker_rejects_invalid_native_receipt_before_client(ai,monkeypatch,tamper):
    from tools.studio_worker import main
    from physics.contracts import digest
    v=prepare(ai);service=StudioExecution(ai,operator=FixtureOperator());review=service.quote(v['request_id']);q=service.quotes.get(review['review_id'])
    folder=service._folder(v['request_id']);folder.mkdir(parents=True)
    receipt={'review_id':review['review_id'],'quote_sha256':digest(q),'approval':approve(v),'native_preview':bool(q['policy']['native_previews']),'method':'NATIVE_MACOS_OPERATOR_CONFIRMATION','browser_approval_accepted':False}
    if tamper=='fixture_method':receipt['method']='OFFLINE_OPERATOR_FIXTURE_NOT_USER'
    if tamper=='quote_identity':receipt['quote_sha256']='f'*64
    if tamper=='native_scope':receipt['native_preview']=False
    if tamper=='expired_handoff':receipt['approval']['approved_unix']-=121
    write_once(folder/'operator_receipt.json',receipt)
    monkeypatch.setattr('sys.argv',['studio_worker','--root',str(ai.root),'--request',v['request_id'],'--review',review['review_id']])
    monkeypatch.setattr('core.agent.credentials.create_openai_client',lambda:pytest.fail('Invalid authority must not load a client'))
    with pytest.raises(ValueError):main()
    assert not (folder/'worker_claimed.json').exists() and not ai.read(v['request_id'])['execution_consumed']
