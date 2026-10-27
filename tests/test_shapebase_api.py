"""Real HTTP contracts and native preview, isolated independent project only."""
import pytest
from test_ide_api import http
from test_engineering_api import finish
from ide_api.service import IDE
from engineering.creation import CreationManager
from shapebase.examples import create_disposable_arm

@pytest.fixture
def service(tmp_path):
 ide=IDE();ide._creation=CreationManager(tmp_path/'creation');ide._engineering=create_disposable_arm(tmp_path/'sample')[0];return ide

def test_http_shape_review_preview_and_explicit_apply(http):
 client,_=http;b=client.get('/api/engineering/bootstrap').json();expected={'expected_sha256':b['identities']['project'],'expected_revision':b['project']['revision']}
 ops=[{'kind':'update_shape_parameter','target':'shape_link_one','parameter':'length_m','value':.42}]
 assert client.post('/api/engineering/edit',json={**expected,'operations':ops}).status_code==400
 q=client.post('/api/engineering/propose',json={**expected,'operations':ops,'explanation':'Explicit local length review'});assert q.status_code==200;q=q.json()
 assert client.get('/api/engineering/bootstrap').json()['identities']['project']==expected['expected_sha256']
 assert q['validation']['shapes']['parts'][0]['geometry']['holes'][1]['center_m'][0]==pytest.approx(.1344)
 bad={**expected,'proposal_id':q['proposal_id'],'source':'anything'}
 assert client.post('/api/engineering/shape_preview',json=bad).status_code==400
 assert client.post('/api/engineering/shape_preview',json={**expected,'proposal_id':q['proposal_id']},headers={'Origin':'https://evil.invalid'}).status_code==403
 r=finish(client,client.post('/api/engineering/shape_preview',json={**expected,'proposal_id':q['proposal_id']}));assert r['status']=='COMPLETED'
 assert r['result']['status']=='NATIVE_PROXY_REPLAY_PASS' and r['result']['result']['independent_verification']['status']=='PASS'
 assert client.get('/api/engineering/bootstrap').json()['project']['revision']==4
 decision={**expected,'proposal_id':q['proposal_id'],'decision':'apply','confirmation':''}
 assert client.post('/api/engineering/decide',json=decision).status_code==400
 decision['confirmation']='APPLY REVIEWED ENGINEERING CHANGE';applied=client.post('/api/engineering/decide',json=decision);assert applied.status_code==200
 assert applied.json()['project']['revision']==5 and applied.json()['project']['shape_specs'][0]['parameters']['length_m']==.42

def test_http_unsupported_operations_and_extra_application_fields_rejected(http):
 client,_=http;b=client.get('/api/engineering/bootstrap').json();e={'expected_sha256':b['identities']['project'],'expected_revision':4}
 assert client.post('/api/engineering/propose',json={**e,'operations':[{'kind':'update_shape_parameter','target':'shape_link_one','parameter':'length_m','value':.4}],'explanation':'Invalid extra field','apply':True}).status_code==400
 assert client.post('/api/engineering/propose',json={**e,'operations':[{'kind':'cut_step','filename':'anything'}],'explanation':'Unsupported CAD'}).status_code==400
 assert client.get('/api/engineering/bootstrap').json()['project']['revision']==4
