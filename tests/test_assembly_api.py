"""Actual bounded HTTP assembly endpoints; no paid/VM/application side effects."""
import pytest
from test_ide_api import http
from ide_api.service import IDE
from ide_api.engineering import EngineeringService
from engineering.project import new_project
from engineering.assembly_fixture import fixture_plan

@pytest.fixture
def service(tmp_path):
 p=new_project();p['world']['environment']['duration_s']=1.
 ide=IDE();ide._engineering=EngineeringService((tmp_path/'empty').resolve(),initial_project=p);return ide


def test_real_http_aggregate_propose_has_empty_head_and_no_hidden_apply(http):
 client,server=http;boot=client.get('/api/engineering/assembly/bootstrap').json();assert boot['head']['revision']==0 and not boot['head'].get('shape_specs')
 args={'expected_sha256':boot['head_sha256'],'expected_revision':0,'plan':fixture_plan()}
 r=client.post('/api/engineering/assembly/propose',json=args);assert r.status_code==200 and r.json()['resulting_revision']==1
 assert client.get('/api/engineering/assembly/bootstrap').json()['head_sha256']==boot['head_sha256']
 assert client.post('/api/engineering/assembly/propose',json={**args,'apply':True}).status_code==400
 assert client.post('/api/engineering/assembly/propose',json={**args,'expected_revision':1}).status_code==400
 assert client.post('/api/engineering/assembly/native',json={'expected_sha256':boot['head_sha256'],'expected_revision':0,'proposal_id':r.json()['proposal_id']},headers={'Origin':'https://evil.invalid'}).status_code==403
 assert client.get('/api/engineering/assembly/bootstrap?source=anything').status_code==400

def test_http_semantic_errors_are_structured_and_historical_failures_inspectable(http):
 import json
 from pathlib import Path
 client,_=http;b=client.get('/api/engineering/assembly/bootstrap').json()
 p=json.loads((Path(__file__).parents[1]/'artifacts/phase18e/20261025/actual_model_plan.json').read_text())['arguments']['plan']
 r=client.post('/api/engineering/assembly/propose',json={'expected_sha256':b['head_sha256'],'expected_revision':0,'plan':p})
 assert r.status_code==400 and sum(d['code']=='WRONG_ID_NAMESPACE' for d in r.json()['diagnostics'])==8
 after=client.get('/api/engineering/assembly/bootstrap').json()
 assert after['head_sha256']==b['head_sha256'] and after['rejections'][0]['original']['plan']==p
 assert after['semantic_contract']['current_inventory']['parts']==[]
