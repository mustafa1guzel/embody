"""Admission/protocol tests. Explicit doubles never stand in for native physics."""
import copy,json,threading,time
from types import SimpleNamespace
from http.client import HTTPConnection
import pytest
import mujoco
from ide_api import rail_sweeps as lab
from ide_api.server import Server

@pytest.fixture(autouse=True)
def no_native_integration(monkeypatch):
    def forbidden(*a,**k):raise AssertionError('Native demonstrations have a separate six-rollout budget')
    monkeypatch.setattr(mujoco,'mj_step',forbidden)

def request(**update):
    return {**{'experiment_id':lab.EXPERIMENT,'controller_id':lab.CONTROLLER,'source_sha256':lab.source_identity(),
     'cases':[{'mass_kg':2,'speed_mps':1.2,'force_n':4,'gap_m':1.77}], 'criteria':dict(lab.DEFAULT_CRITERIA),
     'nonce':'a'*32,'confirmation':lab.CONFIRMATION},**update}

def fake_result(*args):
    # Deliberate unit-test protocol double, not simulator measurements.
    return {'execution_status':'MEASURED','verdict':'FAIL','metrics':{},'checks':{},'failure_reasons':['UNIT_TEST_DOUBLE'],
      'comparison':{},'effective_model_sha256':__import__('hashlib').sha256(b'<mock/>').hexdigest(),'model_xml':'<mock/>',
      'samples':[],'trajectory_sha256':lab.digest([]),'replay':{'samples':[],'trajectory_sha256':lab.digest([])}}

@pytest.mark.parametrize('patch',[{'controller_id':'attempt_2'},{'experiment_id':'other'},{'source_sha256':'0'*64},
 {'confirmation':''},{'nonce':'../escape'},{'source':'print(1)'},{'path':'robot/controller.py'}, {'xml':'<mujoco/>'}])
def test_rejects_nonregistered_source_paths_identity_and_confirmation(patch):
    with pytest.raises(ValueError):lab.validate(request(**patch))

@pytest.mark.parametrize('key,value',[('mass_kg',0),('mass_kg',5),('mass_kg',True),('force_n',0),('speed_mps',float('nan')),
 ('speed_mps',float('inf')),('speed_mps',-1),('speed_mps',1.3),('gap_m',0),('gap_m',2.3),('mass_kg',1.0000001)])
def test_numeric_admission_rejects(key,value):
    r=request();r['cases'][0][key]=value
    with pytest.raises(ValueError):lab.validate(r)

def test_grid_case_step_request_and_policy_limits():
    r=request(cases=[])
    with pytest.raises(ValueError):lab.validate(r)
    r=request(cases=[{'mass_kg':1+i/10,'speed_mps':1,'force_n':4,'gap_m':1} for i in range(26)])
    with pytest.raises(ValueError):lab.validate(r)
    with pytest.raises(ValueError):lab.validate(request(cases=request()['cases']*2))
    assert lab.validate(request())['criteria']['maximumContactEpisodes']==0
    with pytest.raises(ValueError):lab.validate(request(criteria={**lab.DEFAULT_CRITERIA,'maximumFinalSpeed':0}))
    with pytest.raises(ValueError):lab.validate(request(criteria={**lab.DEFAULT_CRITERIA,'maximumContactEpisodes':.5}))
    assert lab.POLICY['maximum_total_steps']==25*600*2 and lab.POLICY['samples_per_trajectory']==601

def test_catalog_never_executes_and_is_source_bound():
    c=lab.catalog();assert c['source_sha256']==lab.source_identity();assert c['controller_id']==lab.CONTROLLER
    assert c['model_template_sha256'] and c['policy']['maximum_cases']==25

def test_duplicate_nonce_never_resubmits_and_inputs_cannot_change(tmp_path):
    s=lab.RailSweeps(tmp_path);submitted=[];r=request()
    a=s.start(r,lambda op:submitted.append(op) or {'job_id':'mock'});b=s.start(r,lambda op:pytest.fail('Duplicate submit'))
    assert a['sweep_id']==b['sweep_id'] and b['reused'] and len(submitted)==1
    r['cases'][0]['mass_kg']=3
    with pytest.raises(ValueError):s.start(r,lambda op:None)

def test_explicit_cancel_preserves_request_and_executes_zero_cases(tmp_path,monkeypatch):
    s=lab.RailSweeps(tmp_path);r=request();s.start(r,lambda op:{'job_id':'mock'});before=(tmp_path/r['nonce']/'request.json').read_bytes()
    s.cancel(r['nonce']);s.execute(r['nonce']);state=s.read(r['nonce'])
    assert state['status']=='CANCELLED' and all(c['execution_status']=='CANCELLED' for c in state['cases'])
    assert (tmp_path/r['nonce']/'request.json').read_bytes()==before
    with pytest.raises(ValueError):s.execute(r['nonce'])

def test_source_drift_blocks_before_case_and_restart_never_retries(tmp_path,monkeypatch):
    s=lab.RailSweeps(tmp_path);r=request();s.start(r,lambda op:{'job_id':'mock'})
    assert lab.RailSweeps(tmp_path).read(r['nonce'])['status']=='INTERRUPTED'
    monkeypatch.setattr(lab,'source_identity',lambda:'f'*64);s.execute(r['nonce']);assert s.read(r['nonce'])['status']=='EXECUTION_ERROR'

def test_partial_execution_failure_is_preserved_without_retry(tmp_path,monkeypatch):
    r=request();r['cases'].append({**r['cases'][0],'mass_kg':3});s=lab.RailSweeps(tmp_path);s.start(r,lambda op:{'job_id':'mock'})
    def fail(*a):raise RuntimeError('/private/host/not-returned')
    monkeypatch.setattr(lab,'simulate_case',fail);s.execute(r['nonce']);state=s.read(r['nonce'])
    assert state['status']=='PARTIAL';assert [c['execution_status'] for c in state['cases']]==['EXECUTION_ERROR','NOT_EXECUTED']
    assert '/private/' not in json.dumps(state)

def test_written_case_identity_integrity_and_controller_are_checked(tmp_path,monkeypatch):
    s=lab.RailSweeps(tmp_path);r=request();s.start(r,lambda op:{'job_id':'mock'});monkeypatch.setattr(lab,'simulate_case',fake_result);s.execute(r['nonce'])
    state=s.read(r['nonce']);case_id=state['cases'][0]['case_id'];a=s.case(r['nonce'],case_id);assert a['controller_id']==lab.CONTROLLER
    p=tmp_path/r['nonce']/(case_id+'.json');v=json.loads(p.read_text());v['verdict']='PASS';p.write_text(json.dumps(v))
    with pytest.raises(ValueError,match='integrity'):s.case(r['nonce'],case_id)
    with pytest.raises(ValueError):s.case(r['nonce'],'../controller.py')

def test_retention_and_output_size_are_fail_closed(tmp_path):
    s=lab.RailSweeps(tmp_path)
    for i in range(16):(tmp_path/str(i)).mkdir()
    with pytest.raises(ValueError,match='quota'):s.start(request(),lambda op:None)
    with pytest.raises(ValueError,match='size'):lab.write_once(tmp_path/'huge.json',{'x':'x'*100},10)
    assert not (tmp_path/'huge.json').exists()

def test_controller_cancellation_and_step_deadline_without_native_integration():
    cancel=threading.Event();cancel.set();lab._local.context={'cancel':cancel,'deadline':time.monotonic()+60,'calls':0}
    with pytest.raises(lab.Cancelled):lab.reference_controller(None,None)
    cancel.clear();lab._local.context['deadline']=0
    with pytest.raises(lab.Deadline):lab.reference_controller(None,None)
    lab._local.context=None

def test_compiled_context_mapping_without_stepping():
    from core.simulation import compile_context_model
    for p in [{'mass_kg':1,'speed_mps':0,'force_n':2,'gap_m':.35},{'mass_kg':4,'speed_mps':1.2,'force_n':6,'gap_m':2.2}]:
        b,w=lab.contexts(p);m,_=compile_context_model(lab.DEFAULT_MODEL_PATH,b,w)
        assert m.body('carriage').mass[0]==p['mass_kg'];assert m.actuator_forcerange[0].tolist()==[-p['force_n'],p['force_n']]
        assert w.initial_velocity_ms==p['speed_mps'];assert w.wall_position_x_m==pytest.approx(.18+p['gap_m']+.05)

def test_exact_metric_boundaries_without_simulation():
    samples=[{'time':i*.005,'position':i*.001,'velocity':.03,'wall_clearance':.05,'wall_collision':False,
              'control':0,'generalized_actuator_force':0,'scalar_actuator_force':0} for i in range(601)]
    m,c=lab.measure(samples,lab.DEFAULT_CRITERIA);assert c['selected_clearance'] and not c['selected_final_speed'] and not c['selected_settling_time'];assert m['sampled_settling_time_s'] is None
    samples[-1]['velocity']=0;m,c=lab.measure(samples,lab.DEFAULT_CRITERIA);assert m['sampled_settling_time_s']==3 and c['selected_settling_time']

def test_http_authorization_and_admission_use_existing_job_lock(tmp_path,monkeypatch):
    s=lab.RailSweeps(tmp_path);server=Server(('127.0.0.1',0),ide=SimpleNamespace(rail_sweeps=s));t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
    def call(method,path,value=None,headers=None):
        conn=HTTPConnection('127.0.0.1',server.server_port,timeout=5)
        body=None if value is None else json.dumps(value);h={'Content-Type':'application/json',**(headers or {})}
        conn.request(method,path,body=body,headers=h);response=conn.getresponse();raw=response.read();code=response.status;conn.close();return code,json.loads(raw)
    try:
        assert call('GET','/api/rail-sweeps/catalog')[0]==200
        assert call('POST','/api/rail-sweeps/start',request())[0]==403
        h={'Origin':'http://'+server.host,'X-EMBODY-Token':server.token}
        assert call('POST','/api/rail-sweeps/start',request(),{**h,'Origin':'https://outside.invalid'})[0]==403
        assert call('POST','/api/rail-sweeps/start',request(),{**h,'Sec-Fetch-Site':'cross-site'})[0]==403
        assert call('POST','/api/rail-sweeps/start',request(controller_id='attempt_2'),h)[0]==400
        assert server.jobs=={}
        server.job_lock.acquire()
        try:assert call('POST','/api/rail-sweeps/start',request(),h)[0]==400
        finally:server.job_lock.release()
        assert s.read('a'*32)['status']=='EXECUTION_ERROR'
        monkeypatch.setattr(lab,'simulate_case',fake_result)
        code,value=call('POST','/api/rail-sweeps/start',request(nonce='c'*32),h)
        assert code==202
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            code,state=call('GET','/api/rail-sweeps/state?id='+value['sweep_id'])
            if state['status'] not in ('QUEUED','RUNNING'):break
            time.sleep(.01)
        assert state['status']=='COMPLETED' and state['cases'][0]['execution_status']=='MEASURED'
        assert call('GET','/api/rail-sweeps/case?id='+value['sweep_id']+'&case='+state['cases'][0]['case_id'])[0]==200

    finally:server.shutdown();server.server_close();t.join(5)
