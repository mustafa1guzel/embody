import pytest
from test_ide_api import http,finish
from ide_api.service import IDE
from ide_api.engineering import EngineeringService
from core.agent.vm_backend import AppleVMBackend

@pytest.fixture
def service(tmp_path):
    ide=IDE();ide._engineering=EngineeringService(tmp_path/'new_project');return ide


def test_real_http_shared_project_schematic_cas_and_no_paid_or_vm_path(http,monkeypatch):
    client,server=http
    def forbidden(*a,**kw):raise AssertionError('No API request, credentials or VM allowed')
    monkeypatch.setattr('ide_api.server.run_live',forbidden);monkeypatch.setattr('ide_api.server.read_openai_api_key',forbidden);monkeypatch.setattr(AppleVMBackend,'preflight',forbidden)
    b=client.get('/api/engineering/bootstrap').json();expected={'expected_sha256':b['identities']['project'],'expected_revision':b['project']['revision']}
    r=client.post('/api/engineering/edit',json={**expected,'operations':[{'kind':'create_object','primitive':'motor','id':'beam','parent':None}]});assert r.status_code==200
    assert client.post('/api/engineering/edit',json={**expected,'operations':[{'kind':'set_device_mass','mass_kg':.5}]}).status_code==400
    b=client.get('/api/engineering/bootstrap').json();assert b['schematic']['connections']==b['project']['circuit']['wires']
    assert client.post('/api/engineering/edit',json={**expected,'operations':[]},headers={'Origin':'https://evil.invalid'}).status_code==403
    r=client.post('/api/engineering/simulate',json={'expected_sha256':b['identities']['project'],'expected_revision':b['project']['revision'],'kind':'world'})
    measured=finish(client,r);assert measured['status']=='COMPLETED'
    assert measured['result']['result']['independent_verification']['status']=='PASS'
    assert client.get('/api/engineering/context').json()['permissions'].startswith('Inspection')


def test_http_source_and_automatic_apply_fields_are_rejected(http):
    client,_=http;b=client.get('/api/engineering/bootstrap').json();e={'expected_sha256':b['identities']['project'],'expected_revision':0}
    assert client.post('/api/engineering/propose',json={**e,'operations':[{'kind':'set_device_mass','mass_kg':.1}],'explanation':'Typed proposal','apply':True}).status_code==400
    assert client.post('/api/engineering/edit',json={**e,'operations':[{'kind':'run_code','source':'anything'}]}).status_code==400
    assert client.post('/api/engineering/simulate',json={**e,'kind':'world','source':'anything'}).status_code==400
    assert client.get('/api/engineering/bootstrap').json()['project']['revision']==0


def test_shape_agent_review_http_is_readonly_and_rejects_queries(http):
    client,server=http
    before=server.ide.engineering.current()
    assert client.get('/api/engineering/shape_agent_review').json()=={'status':'NO_SESSION'}
    assert client.get('/api/engineering/shape_agent_review?path=anything').status_code==400
    assert client.post('/api/engineering/shape_agent_review',json={}).status_code==400
    assert server.ide.engineering.current()==before
