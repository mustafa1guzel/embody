"""Actual HTTP routes remain bounded and review-only for mobility shapes."""
import pytest
from test_ide_api import http
from ide_api.service import IDE
from shapebase.mobility_examples import create_example
from core.agent.vm_backend import AppleVMBackend

@pytest.fixture
def service(tmp_path):
 ide=IDE();ide._engineering=create_example((tmp_path/'rover').resolve(),'rover')[0];return ide


def test_mobility_real_http_proposal_validation_and_no_execution(http,monkeypatch):
 client,server=http
 def forbidden(*args,**kw):raise AssertionError('No API credential/model request or VM permitted')
 monkeypatch.setattr('ide_api.server.run_live',forbidden);monkeypatch.setattr('ide_api.server.read_openai_api_key',forbidden);monkeypatch.setattr(AppleVMBackend,'preflight',forbidden)
 b=client.get('/api/engineering/bootstrap').json();expected={'expected_sha256':b['identities']['project'],'expected_revision':b['project']['revision']}
 assert set(('wheel','axle','chassis','motor_mount','drone_arm','motor_pad'))<=set(b['shapebase']['families'])
 ops=[{'kind':'update_shape_parameter','target':'shape_front_left_wheel','parameter':'outer_diameter_m','value':.144}]
 q=client.post('/api/engineering/propose',json={**expected,'operations':ops,'explanation':'Explicit review only'});assert q.status_code==200
 assert q.json()['proposed_project']['shape_specs']!=b['project']['shape_specs']
 assert client.get('/api/engineering/bootstrap').json()['identities']['project']==expected['expected_sha256']
 assert client.post('/api/engineering/edit',json={**expected,'operations':ops}).status_code==400
 assert client.post('/api/engineering/propose',json={**expected,'operations':ops,'explanation':'No extra apply field','apply':True}).status_code==400
 assert client.post('/api/engineering/propose',json={**expected,'operations':[{'kind':'attach_part_to_mount','target':'shape_front_left_wheel','mount_body_id':'floor','frame_id':'axle'}],'explanation':'Wrong support'}).status_code==400
 assert client.get('/api/engineering/bootstrap').json()['project']==b['project']
