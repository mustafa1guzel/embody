from test_assembly_api import service
from test_ide_api import http
from engineering.assembly_examples import rover_plan

def test_assessment_api_is_read_only_and_preserves_invalid_input(http):
 client,_=http;b=client.get('/api/engineering/assembly/bootstrap').json();p=rover_plan();p['steps'][0]['operations'][0]['mass_kg']=2
 args={'expected_sha256':b['head_sha256'],'expected_revision':0,'plan':p}
 r=client.post('/api/engineering/assembly/assess',json=args);assert r.status_code==200 and r.json()['status']=='REJECTED' and r.json()['total_mass_kg']>2
 after=client.get('/api/engineering/assembly/bootstrap').json();assert after['head_sha256']==b['head_sha256'] and not after['rejections']
 assert client.post('/api/engineering/assembly/assess',json={**args,'expected_revision':1}).status_code==400
 assert client.post('/api/engineering/assembly/assess',json={**args,'apply':True}).status_code==400
 assert client.post('/api/engineering/assembly/assess',json=args,headers={'Origin':'https://evil.invalid'}).status_code==403

def test_positive_assessment_does_not_create_proposal_or_native_evidence(http):
 client,_=http;b=client.get('/api/engineering/assembly/bootstrap').json()
 r=client.post('/api/engineering/assembly/assess',json={'expected_sha256':b['head_sha256'],'expected_revision':0,'plan':rover_plan()})
 assert r.json()['status']=='COMPILED_REVIEW_READY' and r.json()['native']=='NOT_EXECUTED'
 assert client.get('/api/engineering/assembly/bootstrap').json()['head_sha256']==b['head_sha256']
