import pytest
from test_ide_api import http
from ide_api.service import IDE
from ide_api.engineering import EngineeringService
from engineering.creation import CreationManager

@pytest.fixture
def service(tmp_path):
    ide=IDE();ide._creation=CreationManager(tmp_path/'registry');ide._engineering=EngineeringService(tmp_path/'legacy');return ide

def test_http_new_project_review_boundary_identity_selection_and_legacy_preservation(http):
    client,server=http;legacy=client.get('/api/engineering/bootstrap').json()['project']
    response=client.post('/api/creation/plan',json={'request':'Build a barrier.','parameters':{}});assert response.status_code==200;p=response.json()
    assert client.get('/api/engineering/bootstrap').json()['project']==legacy
    assert p['initial_project']['world']['objects']==[] and p['initial_project']['circuit']['components']==[]
    payload={'proposal_id':p['proposal_id'],'expected_sha256':p['base_sha256'],'expected_revision':0,'decision':'build','confirmation':'BUILD REVIEWED SUPPORTED PROJECT'}
    assert client.post('/api/creation/decide',json={**payload,'auto_apply':True}).status_code==400
    assert client.post('/api/creation/decide',json=payload,headers={'Origin':'https://evil.invalid'}).status_code==403
    assert client.post('/api/creation/decide',json=payload).json()['status']=='BUILT_NOT_YET_SIMULATED'
    assert client.get('/api/engineering/bootstrap').json()['project']['id']==p['project_id']
    assert client.post('/api/creation/open',json={'project_id':'engineering_project','confirmation':'OPEN SUPPORTED PROJECT'}).json()['project']==legacy

def test_http_unsupported_paths_requests_and_commit_arguments(http):
    client,_=http
    assert client.post('/api/creation/plan',json={'request':'Build a gripper.','parameters':{}}).status_code==400
    assert client.post('/api/creation/plan',json={'request':'Build a barrier.','parameters':{},'source':'execute me'}).status_code==400
    assert client.post('/api/creation/open',json={'project_id':'../legacy','confirmation':'OPEN SUPPORTED PROJECT'}).status_code==400
    assert client.get('/api/creation/capabilities').json()['capabilities']['model_or_vm_authority'] is False
