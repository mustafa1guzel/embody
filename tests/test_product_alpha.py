"""Real public saved-data product integration; native integration never invoked."""
import copy,json
import pytest
from ide_api.product_alpha import ProductAlpha,diagnosis
from ide_api.experiment_designer import ExperimentDesigner
from ide_api import rail_sweeps as rail

@pytest.fixture
def product(tmp_path):return ProductAlpha(ExperimentDesigner(rail.RailSweeps(tmp_path/'native'),tmp_path/'designer'),tmp_path/'projects')

def test_public_evidence_debugger_replay_and_source_scope(product):
 c=product.catalog();assert len(c['records'])==4 and c['controller']['editable'] is False
 assert all(r['source_current'] is False for r in c['records'])
 r=product.case(c['records'][0]['id']);assert r['record']['verdict']=='FAIL' and r['result']['replay']['status']=='PASS'
 issue=next(i for i in r['diagnosis']['issues'] if i['id']=='clearance');assert issue['measured']==pytest.approx(.003) and issue['deficit']==pytest.approx(.047) and issue['required']==.05
 assert r['scene']['transform_check'].startswith('Saved XML compiled') and r['scene']['slide_axis_world']==[1,0,0]
 assert not r['source_compatible_with_current']
 h=c['adaptive_history'];assert h['initial_selection']['points'][0]['parameters']['gap_m']==1.465 and h['next_selection']['points'][0]['parameters']['gap_m']==1.4775
 assert h['initial_intervals'][0]['width']==pytest.approx(.05) and h['updated_intervals'][0]['width']==pytest.approx(.025)

def test_real_persisted_project_exact_head_save_and_reload(product):
 p=product.new('Payload test');key=p['project']['id'];assert p['verification']=='NOT_VERIFIED' and len(product.listing())==1
 before=p['sha256'];saved=product.save(key,before,{'mass_kg':4,'speed_mps':1.2,'force_n':2,'gap_m':1.54});assert saved['sha256']!=before and product.project(key)['configuration']['gap_m']==1.54
 with pytest.raises(ValueError):product.save(key,before,p['configuration'])
 assert saved['verification']=='NOT_VERIFIED' and len(saved['project']['campaigns'])==2

@pytest.mark.parametrize('p',[{'mass_kg':True,'speed_mps':1,'force_n':2,'gap_m':1.4},{'mass_kg':5,'speed_mps':1,'force_n':2,'gap_m':1.4},{'mass_kg':4,'speed_mps':float('nan'),'force_n':2,'gap_m':1.4},{'mass_kg':4,'speed_mps':1,'force_n':2,'gap_m':1.4,'source':'bad'}])
def test_invalid_prepare_rejects_without_authority(product,p):
 with pytest.raises(ValueError):product.prepare(p)

def test_preparation_has_no_execution_effect(product,tmp_path):
 p=product.prepare({'mass_kg':4,'speed_mps':1.2,'force_n':2,'gap_m':1.54});assert not p['execution_authorized'] and p['native_steps']==0 and p['maximum_steps']==1200
 assert not (tmp_path/'native').exists()

def test_missing_and_invalid_measures_do_not_become_pass(product):
 assert diagnosis(None)['status']=='INSUFFICIENT_EVIDENCE'
 r=copy.deepcopy(product.catalog()['records'][0]);r['metrics']['minimum_clearance_m']=None
 d=diagnosis(r);assert d['status']=='INSUFFICIENT_EVIDENCE' and d['issues'][0]['status']=='UNAVAILABLE'
 r['status']='ERROR';assert diagnosis(r)['status']=='EXECUTION_OR_DATA_UNAVAILABLE'

def test_compatible_comparison_and_mixed_contract_rejected(product):
 records=product.catalog()['records'];out=product.compare(records[0]['id'],records[1]['id']);assert out['verdicts']==['FAIL','PASS'] and out['minimum_clearance_delta_m']==pytest.approx(.05)
 bad=copy.deepcopy(product.records()[0]);bad[1]['compatibility']={};product.records=lambda:(bad,{})
 with pytest.raises(ValueError):product.compare(records[0]['id'],records[1]['id'])

def test_corrupt_package_withheld_not_fabricated(product,tmp_path):
 root=tmp_path/'evidence';root.mkdir();(root/'initial-evidence.json').write_text('{}');(root/'refinement-evidence.json').write_text('{}');product.evidence_root=root
 with pytest.raises(ValueError,match='Pinned'):product.records()

@pytest.mark.parametrize('lo,hi,budget',[(1.5,1.4,1),(.1,1.5,1),(1.4,1.5,True),(1.4,1.5,0),(1.4,1.5,9)])
def test_investigation_bounds(product,lo,hi,budget):
 with pytest.raises(ValueError):product.investigate(lo,hi,budget)

def test_actual_adaptive_engine_no_hardcoded_correction(product):
 r=product.investigate(1.44,1.54,1);assert r['points'][0]['parameters']['gap_m']==1.4775 and not r['execution_authorized']
 r=product.investigate(1.49,1.54,1);assert not r['execution_authorized'] and all(p['parameters']['gap_m']>=1.49 for p in r['points'])

@pytest.mark.parametrize('title',['','a'*81,None])
def test_invalid_project_name(product,title):
 with pytest.raises(ValueError):product.new(title)

@pytest.fixture
def http_product(product):
 import threading
 from types import SimpleNamespace
 from ide_api.server import Server
 server=Server(('127.0.0.1',0),ide=SimpleNamespace(_product_alpha=product));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
 yield server
 server.shutdown();thread.join();server.server_close()

def http_request(server,path,body=None,*,token=True,origin=True):
 import urllib.request,urllib.error
 url='http://'+server.host;headers={}
 if origin:headers['Origin']=url
 if body is not None:
  headers['Content-Type']='application/json'
  if token:headers['X-EMBODY-Token']=server.token
 request=urllib.request.Request(url+'/api/product/'+path,data=None if body is None else json.dumps(body).encode(),headers=headers)
 try:
  with urllib.request.urlopen(request,timeout=15) as response:return response.status,json.load(response)
 except urllib.error.HTTPError as e:return e.code,json.load(e)

def test_http_catalog_exact_case_and_no_authority(http_product):
 status,c=http_request(http_product,'catalog');assert status==200
 status,case=http_request(http_product,'case?id='+c['records'][0]['id']);assert status==200 and case['diagnosis']['status']=='MEASURED_REQUIREMENT_FAILURE'
 assert http_request(http_product,'case?id=../../secrets')[0]==400
 assert http_request(http_product,'catalog?unknown=1')[0]==400

@pytest.mark.parametrize('action',['execute','apply','approve','start','provider'])
def test_no_product_execution_or_approval_endpoint(http_product,action):assert http_request(http_product,action,{})[0]==403

def test_http_mutation_requires_csrf_origin_and_exact_fields(http_product):
 assert http_request(http_product,'new',{'title':'Test'},token=False)[0]==403
 assert http_request(http_product,'new',{'title':'Test'},origin=False)[0]==403
 assert http_request(http_product,'new',{'title':'Test','source':'bad'})[0]==400
 status,p=http_request(http_product,'new',{'title':'Test'});assert status==200 and p['verification']=='NOT_VERIFIED'

@pytest.mark.parametrize('metric,value,issue',[('final_speed_mps',.03,'speed'),('wall_contact_episodes',1,'contacts'),('maximum_actuator_force_n',2.1,'force'),('sampled_settling_time_s',3.1,'settling')])
def test_synthetic_negative_requirement_boundaries_remain_fail(product,metric,value,issue):
 r=copy.deepcopy(product.catalog()['records'][1]);r['metrics'][metric]=value
 check=next(i for i in diagnosis(r)['issues'] if i['id']==issue)
 assert check['status']=='FAIL'

def test_same_record_is_not_a_before_after_experiment(product):
 key=product.catalog()['records'][0]['id']
 with pytest.raises(ValueError,match='distinct'):product.compare(key,key)
