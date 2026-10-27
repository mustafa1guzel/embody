"""Real loopback HTTP, measured read models and explicit Day 6 action boundaries.

Mock transport is used only in the named API-model tests, never for physics.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import threading
import time
from types import SimpleNamespace

from http.client import HTTPConnection
from urllib.parse import urlencode
import mujoco
import numpy as np
import pytest

from core.simulation import ROOT
from core.agent.patching import READ_ALLOWLIST, TARGET, read_project_file
from core.agent.trace import ExecutionTrace
from core.agent.vm_backend import AppleVMBackend, IsolationBlocked
from ide_api.service import IDE
from ide_api.server import Server, MAX_BODY
from ide_api.agent import CONSENT, ReviewTools, run_live
from workspace.data import default_recording, EvidenceError
from workspace.workflow import Workflow, MANAGED_TARGET


@pytest.fixture
def service(tmp_path):
    project=tmp_path/'project';project.mkdir()
    for name in ('core','robot','configs'):
        shutil.copytree(ROOT/name,project/name,ignore=shutil.ignore_patterns('__pycache__','.approved-controller.lock','approved_controller.py'))
    return IDE(workflow=Workflow(project,tmp_path/'reviews'))


@pytest.fixture
def http(service):
    server=Server(('127.0.0.1',0),ide=service)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    client=LocalClient(server)
    token=client.get('/api/bootstrap').json()['csrf_token']
    client.headers.update({'Origin':f'http://{server.host}','X-EMBODY-Token':token})
    yield client,server
    server.shutdown();server.server_close();thread.join(5)


class LocalClient:
    """Standard-library test client; no new Python HTTP framework dependency."""
    def __init__(self,server):self.server=server;self.headers={}
    def request(self,method,path,*,params=None,json=None,content=None,headers=None):
        if params:path+='?'+urlencode(params)
        merged={**self.headers,**(headers or {})}
        if json is not None:
            content=__import__('json').dumps(json).encode();merged.setdefault('Content-Type','application/json')
        if isinstance(content,str):content=content.encode()
        conn=HTTPConnection('127.0.0.1',self.server.server_port,timeout=15)
        try:
            conn.request(method,path,body=content,headers=merged)
            response=conn.getresponse();raw=response.read();status=response.status
            return SimpleNamespace(status_code=status,text=raw.decode(),json=lambda:__import__('json').loads(raw))
        finally:conn.close()
    def get(self,*args,**kwargs):return self.request('GET',*args,**kwargs)
    def post(self,*args,**kwargs):return self.request('POST',*args,**kwargs)


def finish(client,response):
    assert response.status_code==202,response.text
    identifier=response.json()['job_id'];deadline=time.monotonic()+180
    while time.monotonic()<deadline:
        result=client.get('/api/job',params={'id':identifier}).json()
        if result['status']!='RUNNING':return result
        time.sleep(.02)
    pytest.fail('Local job did not finish')


def create(client,variant='attempt_2'):
    result=finish(client,client.post('/api/review/create',json={'variant':variant}))
    assert result['status']=='COMPLETED',result
    return result['result']['review_id']


def action(client,identifier,name,confirmation=''):
    return client.post('/api/review/action',json={'id':identifier,'action':name,'confirmation':confirmation})


def test_bootstrap_does_not_load_credentials_run_physics_or_call_model(http,monkeypatch):
    def forbidden(*a,**kw):raise AssertionError('No startup inference / execution / credentials')
    monkeypatch.setattr('ide_api.server.read_openai_api_key',forbidden)
    monkeypatch.setattr('ide_api.server.run_live',forbidden)
    monkeypatch.setattr(AppleVMBackend,'preflight',forbidden)
    client,server=http
    data=client.get('/api/bootstrap').json()
    assert data['api_cost_on_open']=='0.00' and data['live_policy']['project_cap_usd']=='30'
    assert len(data['csrf_token'])>=32
    assert {f['path'] for f in data['files'] if not f['historical']}==set(READ_ALLOWLIST)
    assert 'robot/rail_carriage.xml' in {f['path'] for f in data['files']}
    assert server.jobs=={}


@pytest.mark.parametrize('scenario',['A','B','C'])
def test_actual_601_state_scene_and_measurements(http,scenario):
    client,_=http;response=client.get('/api/experiment',params={'scenario':scenario})
    assert response.status_code==200,response.text
    data=response.json();assert data['scenario']==scenario and 'RECORDED' in data['provenance']
    context=data['context'];assert context['mass_kg']==(3 if scenario=='B' else 2)
    assert context['braking_force_n']==4 and context['minimum_clearance_m']==.05
    assert context['initial_velocity_ms']==(1 if scenario=='C' else 1.2)
    assert context['wall_center_x_m']-context['wall_near_x']==pytest.approx(.05)
    r=default_recording();xml=r.trajectory(scenario,'original')['xml']
    model=mujoco.MjModel.from_xml_string(xml);state=mujoco.MjData(model)
    for variant,trajectory in data['variants'].items():
        original=r.trajectory(scenario,variant)
        assert len(trajectory['samples'])==601 and trajectory['samples']==original['samples']
        assert trajectory['summary']==original['summary']
        assert trajectory['markers'][-1]['index']==600
        assert trajectory['summary']['physical_safety_status']==('PASS' if variant=='attempt_2' else 'FAIL')
        for sample in trajectory['samples'][::100]:
            state.qpos[0],state.qvel[0]=sample['position'],sample['velocity'];mujoco.mj_forward(model,state)
            for geom in data['scene']['geoms']:
                expected=np.array(geom['position'])+(np.array(data['scene']['slide_axis_world'])*(sample['position']-data['scene']['reference_position']) if geom['moving'] else 0)
                assert np.allclose(expected,state.geom_xpos[model.geom(geom['name']).id],rtol=0,atol=1e-12)
    assert {'floor','wall','carriage_box','front_bumper','rail_base','rail_track'}=={g['name'] for g in data['scene']['geoms']}
    assert data['scene']['joints'][0]['name']=='x_slide'
    assert data['scene']['actuators'][0]['force_range_n']==[-4,4]


def test_authorized_sources_and_exact_diff_identity(http):
    client,_=http
    for path in READ_ALLOWLIST:
        data=client.get('/api/file',params={'path':path}).json()
        assert data['content']==(ROOT/path).read_text()
        assert data['sha256']==hashlib.sha256((ROOT/path).read_bytes()).hexdigest()
    for variant in ('attempt_1','attempt_2'):
        proposal=client.get('/api/proposal',params={'variant':variant}).json()
        assert proposal==default_recording().proposal(variant)
        source=client.get('/api/file',params={'path':f'recording/{variant}/controller.py'}).json()
        assert source['historical'] and source['content']==proposal['source']
    trace=client.get('/api/agent/recorded').json()
    assert trace['mode']=='recorded' and len(trace['calls'])==17
    assert trace['diagnosis']==default_recording().read('model_diagnosis.txt').decode()


@pytest.mark.parametrize('path',['.env','/etc/passwd','../.env','robot/../../.env','robot/robot.xml','core/agent/credentials.py','recording/../.env'])
def test_file_denials(http,path):
    response=http[0].get('/api/file',params={'path':path})
    assert response.status_code==400 and response.json()['status']=='BLOCKED'
    assert 'OPENAI_API_KEY' not in response.text


def test_symlink_missing_corrupt_and_stale_evidence_fail_closed(tmp_path,monkeypatch):
    root=tmp_path/'view';(root/'robot').mkdir(parents=True)
    (root/'robot/controller.py').symlink_to(ROOT/'robot/controller.py')
    monkeypatch.setattr('ide_api.service.ROOT',root)
    with pytest.raises(ValueError):IDE().file(TARGET)
    monkeypatch.setattr('ide_api.service.ROOT',ROOT)
    missing=SimpleNamespace(trajectory=lambda *a:(_ for _ in ()).throw(EvidenceError('Missing or corrupt evidence')))
    with pytest.raises(EvidenceError,match='Missing'):IDE(recording=missing).experiment('A')
    real=default_recording()
    class Drift:
        def trajectory(self,scenario,variant):
            result=real.trajectory(scenario,variant)
            if variant=='attempt_1':result['samples'][1]['time']+=.001
            return result
    with pytest.raises(EvidenceError,match='timestamp'):IDE(recording=Drift()).experiment('A')


def test_host_origin_csrf_and_bounded_strict_json(http):
    client,server=http
    assert client.get('/api/bootstrap',headers={'Host':'evil.example'}).status_code==403
    assert client.get('/api/bootstrap',headers={'Origin':'https://evil.example'}).status_code==403
    assert client.get('/api/bootstrap',headers={'Sec-Fetch-Site':'cross-site'}).status_code==403
    assert client.post('/api/review/create',json={'variant':'attempt_2'},headers={'X-EMBODY-Token':'bad'}).status_code==403
    for raw in ('{"variant":"attempt_2","variant":"attempt_1"}','{"value":NaN}','[]','{"variant":true}'):
        response=client.post('/api/review/create',content=raw,headers={'Content-Type':'application/json'})
        if response.status_code==202:assert finish(client,response)['status']=='BLOCKED'
        else:assert response.status_code==400
    assert client.post('/api/review/create',content=b'x'*(MAX_BODY+1),headers={'Content-Type':'application/json'}).status_code==400
    assert client.post('/api/review/create',content='x').status_code==400
    assert client.get('/api/experiment?scenario=A&scenario=B').status_code==400
    assert client.get('/api/file?path=.env&extra=x').status_code==400
    assert client.post('/api/shell',json={'command':'anything'}).status_code==404
    assert client.get('/../.env').status_code==400
    with pytest.raises(ValueError,match='loopback'):Server(('0.0.0.0',0))


def test_new_review_approval_rejection_and_stale_vm_are_separate(http,service,monkeypatch):
    client,_=http;identifier=create(client)
    state=client.get('/api/review',params={'id':identifier}).json()
    assert state['status']=='REVIEWED' and state['verification'] is None and not state['permanent_application_approved']
    source=client.get('/api/review/source',params={'id':identifier}).json()
    assert hashlib.sha256(source['modified'].encode()).hexdigest()==state['source_sha256']
    assert action(client,identifier,'verify','').status_code==400
    applied=finish(client,action(client,identifier,'apply','APPLY '+state['source_sha256']))
    assert applied['status']=='BLOCKED' and 'fresh' in applied['error']
    def expired(*a):raise IsolationBlocked('Developer negative probe: VM qualification expired')
    monkeypatch.setattr(AppleVMBackend,'preflight',expired)
    result=finish(client,action(client,identifier,'verify','VERIFY IN VM ONLY'))['result']
    assert result['status']=='BLOCKED' and result['verification'] is None and 'expired' in result['reason']
    rejected=finish(client,action(client,identifier,'reject'))['result'];assert rejected['status']=='REJECTED'
    assert finish(client,action(client,identifier,'verify','VERIFY IN VM ONLY'))['status']=='BLOCKED'
    assert not (service.workflow.root/MANAGED_TARGET).exists()


def test_manual_editor_draft_is_not_ai_source_or_verified(http,service):
    client,_=http;original=read_project_file(ROOT,TARGET)
    response=client.post('/api/review/create',json={'source':original['content']+'\n# developer local draft\n',
       'expected_original_sha256':original['sha256'],'explanation':'Manual editor fixture'})
    identifier=finish(client,response)['result']['review_id'];state=service.workflow.get(identifier)
    assert state['provenance']=={'kind':'manual_editor_draft','ai_generated':False}
    assert state['verification'] is None
    assert (ROOT/TARGET).read_text()==original['content']


def test_one_expensive_job_at_a_time(http):
    client,server=http;gate=threading.Event()
    try:
        first=server.job(lambda:gate.wait(5))
        response=client.post('/api/review/create',json={'variant':'attempt_2'})
        assert response.status_code==400 and 'already running' in response.json()['error']
    finally:gate.set()
    assert finish(client,SimpleNamespace(status_code=202,json=lambda:first))['status']=='COMPLETED'


def test_live_requires_paid_consent_allowlisted_references_and_credentials(http,monkeypatch):
    client,server=http
    def forbidden(*a,**kw):raise AssertionError('No paid API request in tests')
    monkeypatch.setattr('ide_api.server.run_live',forbidden)
    body={'mode':'physical','message':'Inspect','references':[TARGET],'confirmation':''}
    assert client.post('/api/agent/start',json=body).status_code==400
    body['confirmation']=CONSENT;body['references']=['.env']
    assert client.post('/api/agent/start',json=body).status_code==400
    body['references']=[TARGET]
    response=client.post('/api/agent/start',json=body)
    assert response.status_code==409 and 'credentials' in response.json()['error']
    assert server.jobs=={}


def test_real_agent_tools_cannot_execute_proposals_without_user_vm_approval(service,tmp_path):
    trace=ExecutionTrace(tmp_path/'tool_trace',model_mode='deterministic_test_no_model')
    tools=ReviewTools(tmp_path/'tools',trace,workflow=service.workflow,mode='physical')
    assert len(tools.schemas)==6 and tools.verifier.backend is None
    p=default_recording().proposal('attempt_2')
    result=tools.dispatch('propose_patch',{'target_path':TARGET,'expected_original_sha256':p['validation']['original_sha256'],
        'proposed_source':p['source'],'explanation':'Revalidating exact recorded source; no new inference'})
    assert result['ok'] and result['verification_approval_required']
    assert tools.verifier.verify(result['result']['candidate_id'])['candidate_code_executed'] is False
    assert service.workflow.get(result['review_id'])['verification'] is None
    code=ReviewTools(tmp_path/'code',trace,workflow=service.workflow,mode='code')
    assert [s['name'] for s in code.schemas]==['read_project']
    with pytest.raises(ValueError):code.dispatch('run_simulation',{'scenario_id':'A','controller_variant':'faulty'})


def test_mocked_live_transport_uses_existing_budget_and_preserves_trace(service,tmp_path):
    class Response:
        id='resp_day7_mock'
        @property
        def output(self):return self.model_dump()['output']
        def model_dump(self,**_):return {'id':'resp_day7_mock','status':'completed','model':'gpt-5.4-2026-03-05','service_tier':'default',
            'output':[{'type':'message','role':'assistant','content':[{'type':'output_text','text':'Explicitly mocked transport output; no genuine inference.'}]}],
            'usage':{'input_tokens':500,'input_tokens_details':{'cached_tokens':0},'output_tokens':30,'output_tokens_details':{'reasoning_tokens':10},'total_tokens':530}}
    class Client:
        max_retries=0
        def __init__(self):self.responses=self;self.requests=[];self.closed=False
        def with_options(self,**_):return self
        def create(self,**request):self.requests.append(request);return Response()
        def close(self):self.closed=True
    client=Client();result=run_live(tmp_path/'mock_session',{'mode':'code','message':'Inspect this actual controller','references':[TARGET]},service.workflow,client_factory=lambda:client)
    assert result['orchestration_status']=='COMPLETED' and 'mocked' in result['model_final_text']
    assert result['api_budget']['totals']['reasoning_tokens']==10
    assert result['api_budget']['requests'][0]['state']=='SETTLED'
    request=client.requests[0]
    assert request['model']=='gpt-5.4' and request['reasoning']['effort']=='low' and request['store'] is True
    assert [s['name'] for s in request['tools']]==['read_project']
    assert result['review_ids']==[] and client.closed
    cumulative=json.loads((tmp_path/'mock_session/cumulative.json').read_text())
    assert cumulative['overall_limit_usd']=='30' and float(cumulative['accounted_cost_usd'])<30


@pytest.mark.live_vm
def test_api_genuine_vm_abc_apply_and_rollback(http,service):
    if os.environ.get('EMBODY_RUN_VM_TESTS')!='1':pytest.skip('Real VM qualification required')
    from core.day4b1 import qualify, OUTPUT
    proof=qualify(output=OUTPUT/('ide_api_containment_'+str(time.time_ns())))
    assert proof['status']=='PASS',proof
    client,_=http;identifier=create(client)
    original=(service.workflow.root/TARGET).read_bytes()
    result=finish(client,action(client,identifier,'verify','VERIFY IN VM ONLY'))
    assert result['status']=='COMPLETED',result
    state=result['result'];assert state['status']=='VERIFIED',state
    assert not (service.workflow.root/MANAGED_TARGET).exists()
    for scenario in ('A','B','C'):
        summary=state['verification']['scenario_results'][scenario]
        assert summary['physical_safety_status']=='PASS' and summary['independent_verification']=='PASS'
        assert summary['minimum_clearance_m']>=.05 and summary['final_speed_ms']<.03
        assert summary['controller_consistency_checked']
    assert finish(client,action(client,identifier,'apply','VERIFY IN VM ONLY'))['status']=='BLOCKED'
    applied=finish(client,action(client,identifier,'apply','APPLY '+state['source_sha256']))['result']
    assert applied['status']=='APPLIED'
    assert hashlib.sha256((service.workflow.root/MANAGED_TARGET).read_bytes()).hexdigest()==state['source_sha256']
    reverted=finish(client,action(client,identifier,'rollback','REVERT '+identifier))['result']
    assert reverted['status']=='REVERTED' and not (service.workflow.root/MANAGED_TARGET).exists()
    assert (service.workflow.root/TARGET).read_bytes()==original
    # Preserve a byte-for-byte export of this actual API/VM transaction.
    destination=OUTPUT.parent/'ide_api_functional_evidence'
    shutil.copytree(service.workflow.sessions/identifier,destination/identifier)
    (destination/'result.json').write_text(json.dumps({'review_id':identifier,'verification':state['verification'],'final_status':reverted['status'],'test_project':str(service.workflow.root)},indent=2))
