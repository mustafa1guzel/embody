import pytest
from test_ide_api import http
from test_phase17_2_construction import review_service
from ide_api.service import IDE
from ide_api.engineering import EngineeringService
from engineering.creation import CreationManager

@pytest.fixture
def service(tmp_path,review_service):
    ide=IDE();ide._construction_review=review_service;ide._engineering=EngineeringService(tmp_path/'legacy');ide._creation=CreationManager(tmp_path/'registry');return ide

def test_real_http_empty_head_prepare_and_no_implicit_commit(http):
    client,server=http;b=client.get('/api/construction-review/bootstrap').json()
    assert b['project']['revision']==0 and not b['project']['world']['objects']
    expected={'expected_sha256':b['project_sha256'],'expected_revision':0}
    p=client.post('/api/construction-review/prepare',json=expected).json();assert len(p['batches'])==11
    assert client.get('/api/construction-review/measurement',params={'review_id':p['review_id']}).json()['measurement'] is None
    body={**expected,'review_id':p['review_id'],'confirmation':''}
    assert client.post('/api/construction-review/commit',json=body).status_code==400
    assert client.post('/api/construction-review/prepare',json={**expected,'force':True}).status_code==400
    assert client.post('/api/construction-review/prepare',json=expected,headers={'Origin':'https://evil.invalid'}).status_code==403
    assert client.post('/api/construction-review/preview',json={**expected,'review_id':p['review_id'],'source':'untrusted'}).status_code==400
    assert client.get('/api/construction-review/bootstrap').json()['project_sha256']==b['project_sha256']
