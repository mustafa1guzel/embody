"""Saved genuine public rail samples in isolated reader fixtures; no new physics.

Copying these files into a temporary job namespace tests protocol/readback only;
it is not new native execution, model authorship or local origin attestation.
"""
import copy,json,hashlib
from pathlib import Path
import pytest
from core.simulation import ROOT
from ide_api import rail_sweeps as rail
from ide_api.native_results import NativeResults,locator,split_locator,qualification,compare_records,MAX_JOBS
from ide_api.research.artifacts import ArtifactStore,finite_json
from ide_api.product_alpha import ProductAlpha
from ide_api.experiment_designer import ExperimentDesigner
from ide_api.toolkit import Toolkit
from ide_api.robot_import import template

@pytest.fixture(scope='module')
def recorded():
    p=ArtifactStore.verify_package(finite_json((ROOT/'examples/adaptive-rail-study/initial-evidence.json').read_bytes(),18*1024*1024))
    req=finite_json(p['decoded']['original_request.json']);summary=finite_json(p['decoded']['summary.json'])
    return req,[finite_json(p['decoded']['cases/'+r['id']+'/native.json']) for r in summary['records']]

@pytest.fixture
def saved(tmp_path,recorded):
    request,results=copy.deepcopy(recorded);service=rail.RailSweeps(tmp_path/'jobs');request['nonce']='a'*32
    folder=service.root/request['nonce'];folder.mkdir(parents=True)
    (folder/'request.json').write_bytes(rail.canonical(request));rows=[]
    for r in results:
        (folder/(r['case_id']+'.json')).write_bytes(rail.canonical(r));rows.append({'case_id':r['case_id'],'parameters':r['parameters'],'execution_status':'MEASURED','result_sha256':rail.digest(r)})
    (folder/'state.json').write_bytes(rail.canonical({'sweep_id':request['nonce'],'status':'COMPLETED','error':None,'cases':rows}))
    return NativeResults(service,ArtifactStore(tmp_path/'evidence')),request,results

def test_genuine_saved_discovery_readback_and_no_invented_provenance(saved):
    reader,req,results=saved;d=reader.discover('rail_carriage');assert len(d['records'])==3 and not d['unavailable']
    r,raw=reader.load(locator(req['nonce'],results[0]['case_id']));assert raw==results[0] and r['metrics']['minimum_clearance_m']==pytest.approx(.003)
    assert r['verdict']=='FAIL' and r['replay_status']=='PASS' and not r['source_current']
    assert r['provenance']['recorded_git_base'] is None and r['recording_timestamp'] is None and r['evidence_package_identity'] is None
    assert d['qualification']['status']=='VERIFIED_HISTORICAL_EVIDENCE'
    assert d['qualification']['application_compatible_cases']==0

def test_source_base_binding_is_metadata_not_authority(saved):
    reader,req,results=saved;definition={'base_commit':'1'*40,'request':req,'source_manifest':{'known.py':'2'*64}}
    v={'definition':definition,'sha256':rail.digest(definition),'authorization':'NOT_GRANTED'}
    reader.store.write_once('model_qualifications/'+req['nonce']+'/consent.json',rail.canonical(v))
    r,_=reader.load(locator(req['nonce'],results[0]['case_id']));meta=r['provenance']
    assert meta['recorded_git_base']=='1'*40 and meta['application_source_compatible'] is False and meta['execution_authority'] is False

@pytest.mark.parametrize('key',['../../private','native_'+('a'*32)+'_../../x','native_'+('a'*32)+'_'+('z'*64),None,{},'a'*64])
def test_path_and_locator_refusals(saved,key):
    with pytest.raises(ValueError):saved[0].load(key)

@pytest.mark.parametrize('field',['controller','source','parameters','criteria','samples','force','model','verdict','replay'])
def test_corrupt_rehashed_result_rejected(saved,field):
    reader,req,results=saved;r=results[0];cid=r['case_id']
    # Prime the bounded cache; changing bytes must invalidate prior verification.
    reader.load(locator(req['nonce'],cid))
    if field=='controller':r['controller_id']='unregistered'
    elif field=='source':r['source_sha256']='f'*64
    elif field=='parameters':r['parameters']['mass_kg']=3
    elif field=='criteria':r['criteria']['minimumClearance']=.001
    elif field=='samples':r['samples'][0]['position']+=.1;r['trajectory_sha256']=rail.digest(r['samples'])
    elif field=='force':r['samples'][0]['control']=2;r['samples'][0]['generalized_actuator_force']=2;r['samples'][0]['scalar_actuator_force']=2;r['trajectory_sha256']=rail.digest(r['samples']);r['replay']['samples']=copy.deepcopy(r['samples']);r['replay']['trajectory_sha256']=r['trajectory_sha256']
    elif field=='model':r['model_xml']='<mujoco/>';r['effective_model_sha256']=hashlib.sha256(r['model_xml'].encode()).hexdigest()
    elif field=='verdict':r['verdict']='PASS'
    elif field=='replay':r['replay']['fresh_steps']=0
    f=reader.service.root/req['nonce'];(f/(cid+'.json')).write_bytes(rail.canonical(r));state=json.loads((f/'state.json').read_text());state['cases'][0]['result_sha256']=rail.digest(r);(f/'state.json').write_bytes(rail.canonical(state))
    with pytest.raises((ValueError,KeyError,AssertionError)):reader.load(locator(req['nonce'],cid))
    bad=reader.discover('rail_carriage');assert bad['unavailable'] and all(v['id']!=locator(req['nonce'],cid) for v in bad['records'])

def test_missing_result_and_unexecuted_not_physical_fail(saved):
    reader,req,results=saved;f=reader.service.root/req['nonce'];(f/(results[0]['case_id']+'.json')).unlink();state=json.loads((f/'state.json').read_text());state['cases'][1]['execution_status']='EXECUTION_ERROR';(f/'state.json').write_bytes(rail.canonical(state))
    d=reader.discover('rail_carriage');assert len(d['records'])==1 and len(d['unavailable'])==2
    assert d['qualification']['physical_fail']==0

def test_symlinked_job_and_result_refused(saved,tmp_path):
    reader,req,results=saved;folder=reader.service.root/req['nonce'];file=folder/(results[0]['case_id']+'.json');real=tmp_path/'private';real.write_bytes(file.read_bytes());file.unlink();file.symlink_to(real)
    with pytest.raises((ValueError,OSError)):reader.load(locator(req['nonce'],results[0]['case_id']))
    alias=tmp_path/'alias';alias.symlink_to(reader.service.root,target_is_directory=True)
    with pytest.raises(ValueError):NativeResults(rail.RailSweeps(alias)).discover('rail_carriage')

def test_bounded_enumeration_and_wrong_model(saved):
    reader,req,results=saved;assert reader.discover('bounded_rover_ramp_v1')['records']==[]
    for i in range(MAX_JOBS): (reader.service.root/f'{i:032x}').mkdir()
    with pytest.raises(ValueError,match='retention'):reader.discover('rail_carriage')

def test_comparison_preserves_source_cohort_and_changed_conditions(saved):
    reader,req,results=saved;records=reader.discover('rail_carriage')['records'];c=compare_records(records[0],records[1]);assert c['minimum_clearance_delta_m']==pytest.approx(.05) and c['verdicts']==['FAIL','PASS']
    assert c['changed_parameters']['gap_m']=={'before':1.44,'after':1.49}
    with pytest.raises(ValueError):compare_records(records[0],records[0])
    b=copy.deepcopy(records[1]);b['compatibility']['model']='bounded_rover_ramp_v1'
    with pytest.raises(ValueError):compare_records(records[0],b)

def test_product_main_reader_loads_native_and_keeps_pinned_examples(saved,tmp_path):
    reader,req,results=saved;p=ProductAlpha(ExperimentDesigner(reader.service,tmp_path/'designer'),tmp_path/'projects');p.native=reader
    before={str(f):f.read_bytes() for f in reader.service.root.rglob('*.json')}
    c=p.catalog();assert len(c['records'])==7
    n=next(r for r in c['records'] if r.get('origin')=='LOCAL_SAVED_REGISTERED_JOB');v=p.case(n['id']);assert v['result']==results[0] and v['scene']['reference_position']==0
    assert p.history()['initial_intervals'][0]['width']==pytest.approx(.05)
    assert before=={str(f):f.read_bytes() for f in reader.service.root.rglob('*.json')}

def test_project_exact_result_isolation_and_stale_source(saved,tmp_path):
    reader,req,results=saved;toolkit=Toolkit(tmp_path/'numeric',native=reader);d=template('rail_carriage','Reader fixture, not new physics');d['parameters']=copy.deepcopy(results[0]['parameters']);p=toolkit.create(d)
    # These actual public samples have a different native source. Never qualify
    # a newly authored current-source project from their old execution identity.
    before=toolkit.read(p['id']);assert toolkit.results(p['id'])['results']==[]
    with pytest.raises(ValueError,match='does not belong'):toolkit.result(p['id'],req['nonce'],results[0]['case_id'])
    assert toolkit.read(p['id'])==before

def test_application_drift_never_inherits_qualification():
    r={'verified':True,'source_current':True,'provenance':{'application_source_compatible':False},'verdict':'PASS'}
    assert qualification([r])['status']=='VERIFIED_RECORDED_SOURCE' and qualification([r])['application_compatible_cases']==0
    r['source_current']=False;assert qualification([r])['status']=='VERIFIED_HISTORICAL_EVIDENCE'
    assert qualification([])['status']=='NO_QUALIFYING_EVIDENCE'

def test_existing_http_reader_routes_preserve_authorization_and_bounded_ids(saved,tmp_path):
    import threading
    from types import SimpleNamespace
    from http.client import HTTPConnection
    from ide_api.server import Server
    reader,req,results=saved;p=ProductAlpha(ExperimentDesigner(reader.service,tmp_path/'designer'),tmp_path/'projects');p.native=reader
    server=Server(('127.0.0.1',0),ide=SimpleNamespace(_product_alpha=p));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    def request(path,body=None,token=True):
        conn=HTTPConnection(server.host,timeout=15);headers={'Origin':'http://'+server.host}
        if token:headers['X-EMBODY-Token']=server.token
        if body is not None:headers['Content-Type']='application/json'
        conn.request('POST' if body is not None else 'GET','/api/product/'+path,None if body is None else json.dumps(body),headers);r=conn.getresponse();out=r.status,json.loads(r.read());conn.close();return out
    try:
        key=locator(req['nonce'],results[0]['case_id']);status,v=request('case?id='+key);assert status==200 and v['record']['verdict']=='FAIL'
        assert request('case?id=../../private')[0]==400
        assert request('catalog?path=private')[0]==400
        assert request('prepare',{'parameters':results[0]['parameters']},token=False)[0]==403
        assert request('execute',{})[0]==403
        assert request('prepare',{'parameters':results[0]['parameters']})[1]['execution_authorized'] is False
    finally:server.shutdown();thread.join();server.server_close()
