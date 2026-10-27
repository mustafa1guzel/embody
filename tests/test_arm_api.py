"""Same-origin arm routes over real evidence; execution is never implicit."""
import shutil
import pytest
from test_ide_api import http,LocalClient,finish
from ide_api.service import IDE
from core.simulation import ROOT
from core.agent.vm_backend import AppleVMBackend,IsolationBlocked
from workspace.workflow import Workflow


@pytest.fixture
def service(tmp_path):
    project=tmp_path/'project';project.mkdir()
    for name in ('core','physics','robot','configs','workspace'):
        shutil.copytree(ROOT/name,project/name,ignore=shutil.ignore_patterns('__pycache__','approved_controller.py','approved_arm_controller.py'))
    ide=IDE(workflow=Workflow(project,tmp_path/'rail'))
    ide.arm_workflow=Workflow(project,tmp_path/'arm',family='arm')
    return ide


def test_arm_read_routes_are_real_and_have_no_execution(http,monkeypatch):
    client,server=http
    def forbidden(*a,**kw):raise AssertionError('Read-only route must never execute')
    monkeypatch.setattr(AppleVMBackend,'preflight',forbidden)
    monkeypatch.setattr('ide_api.server.read_openai_api_key',forbidden)
    d=client.get('/api/arm/recording').json()
    assert d['recorded'] and d['agent']['status']=='COMPLETED'
    e=client.get('/api/arm/experiment',params={'scenario':'arm_nominal'})
    assert e.status_code==200 and len(e.json()['variants']['attempt_1']['samples'])==801
    assert e.json()['variants']['attempt_1']['summary']['physical_safety_status']=='PASS'
    f=client.get('/api/arm/file',params={'path':'robot/arm_controller.py'}).json()
    assert f['content']==(ROOT/'robot/arm_controller.py').read_text()
    p=client.get('/api/arm/proposal',params={'variant':'attempt_1'}).json()
    assert p['validation']['proposed_sha256']==p['provenance']['source_sha256']
    assert server.jobs=={}


@pytest.mark.parametrize('endpoint,params',[('file',{'path':'.env'}),('file',{'path':'configs/arm_evaluation.json'}),
    ('experiment',{'scenario':'A'}),('proposal',{'variant':'attempt_2'}),('file',{'path':'../robot/controller.py'}),('agent/recorded',{})])
def test_arm_read_scope_fail_closed(http,endpoint,params):
    client,_=http;r=client.get('/api/arm/'+endpoint,params=params)
    assert r.status_code==400 and r.json()['status']=='BLOCKED'


def test_arm_review_gates_and_family_separation(http,monkeypatch):
    client,server=http
    response=finish(client,client.post('/api/arm/review/create',json={'variant':'attempt_1'}))
    assert response['status']=='COMPLETED';rid=response['result']['review_id']
    state=client.get('/api/arm/review',params={'id':rid}).json()
    assert state['status']=='REVIEWED' and state['verification'] is None
    assert state['apply_target']=='robot/approved_arm_controller.py'
    assert client.get('/api/review',params={'id':rid}).status_code==400
    body={'id':rid,'action':'verify','confirmation':''}
    assert client.post('/api/arm/review/action',json=body).status_code==400
    def expired(*a,**k):raise IsolationBlocked('Developer test: expired qualification; no VM launched')
    monkeypatch.setattr(AppleVMBackend,'preflight',expired)
    result=finish(client,client.post('/api/arm/review/action',json={**body,'confirmation':'VERIFY IN VM ONLY'}))
    assert result['result']['status']=='BLOCKED' and result['result']['verification'] is None
    applied=finish(client,client.post('/api/arm/review/action',json={'id':rid,'action':'apply','confirmation':'APPLY '+state['source_sha256']}))
    assert applied['status']=='BLOCKED'
    rejected=finish(client,client.post('/api/arm/review/action',json={'id':rid,'action':'reject','confirmation':''}))
    assert rejected['result']['status']=='REJECTED'
    assert not (server.ide.arm_workflow.root/'robot/approved_arm_controller.py').exists()


def test_arm_writes_need_csrf_and_have_no_agent_endpoint(http):
    client,_=http
    assert client.post('/api/arm/review/create',json={'variant':'attempt_1'},headers={'X-EMBODY-Token':'wrong'}).status_code==403
    assert client.post('/api/arm/agent/start',json={}).status_code==400

