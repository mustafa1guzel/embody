"""Real bounded source execution and provider-free adversarial/lifecycle tests."""
import copy,json,threading,time
from uuid import uuid4
import pytest
from ide_api import controller_language as dsl,controller_native as native,rail_sweeps as rail
from ide_api.controller_engineering import RUN,APPLY
from ide_api.workbench import Workbench

@pytest.fixture
def lab(tmp_path):return Workbench(tmp_path/'source_lab')
def setup(lab):
 p=lab.controllers.create('Source test');return p,p['controller_source']
def proposal(lab,p,s,source=dsl.REPAIR):return lab.controllers.tool(p['id'],p['sha256'],s['head_sha256'],'propose_source',{'source':source,'intent':'Explicit source test'})['data']
def run(lab,p,s):
 n=uuid4().hex;lab.controllers.start(p['id'],p['sha256'],s['head_sha256'],n,RUN,lambda f:f());return n,lab.controllers.run(p['id'],n)

@pytest.mark.parametrize('condition',['__import__("os")','clearance_m.__class__','clearance_m[0]','[x for x in []]','True','-True < 0','speed_mps <= mass_kg','(speed_mps < 1) + 1','10 ** 100 < 1','clearance_m / 0 < 1','lambda: 1','0 < float("nan")','1e999 < 1'])
def test_unsafe_or_wrong_dimension_source_rejected(condition):
 with pytest.raises(ValueError):dsl.compile_source('rail_controller 1\nwhen '+condition+'\nthen brake\nelse coast\n')

@pytest.mark.parametrize('source',['import os',dsl.INITIAL+'while True: pass\n','x'*4097,'rail_controller 1\nwhen 1 < 2\nthen shell\nelse coast'])
def test_bad_structure_bounds_and_actions_reject(source):
 with pytest.raises(ValueError):dsl.compile_source(source)

def test_source_hash_is_not_artifact_hash_and_mapping_is_deterministic():
 a=dsl.compile_source(dsl.INITIAL);b=dsl.compile_source(dsl.INITIAL+'\n')
 assert a['source_sha256']!=a['artifact_sha256'] and a['source_sha256']!=b['source_sha256'] and a['artifact_sha256']==b['artifact_sha256']


def test_review_discard_repeat_apply_restore_and_conflicts(lab):
 p,s=setup(lab);q=proposal(lab,p,s)
 assert lab.controllers.read(p['id'])['head_sha256']==s['head_sha256']
 with pytest.raises(PermissionError):lab.controllers.decide(p['id'],p['sha256'],s['head_sha256'],q['review_id'],'APPLY','')
 lab.controllers.decide(p['id'],p['sha256'],s['head_sha256'],q['review_id'],'REJECT',APPLY)
 with pytest.raises(ValueError):lab.controllers.decide(p['id'],p['sha256'],s['head_sha256'],q['review_id'],'APPLY',APPLY)
 q2=proposal(lab,p,s);assert q2['review_id']!=q['review_id']
 new=lab.controllers.decide(p['id'],p['sha256'],s['head_sha256'],q2['review_id'],'APPLY',APPLY);ns=new['controller_source'];assert ns['revision']==1
 assert Workbench(lab.root).controllers.read(p['id'])['head_sha256']==ns['head_sha256']
 with pytest.raises(ValueError):proposal(lab,p,s)
 other,os=setup(lab)
 with pytest.raises(ValueError):lab.controllers.decide(other['id'],other['sha256'],os['head_sha256'],q2['review_id'],'APPLY',APPLY)
 restore=lab.controllers.restore(p['id'],p['sha256'],ns['head_sha256'],s['head_sha256']);restored=lab.controllers.decide(p['id'],p['sha256'],ns['head_sha256'],restore['review_id'],'APPLY',APPLY)
 assert restored['controller_source']['revision']==2 and restored['controller_source']['compiled']['source']==dsl.INITIAL
 assert lab.toolkit.read(p['id'])['sha256']==p['sha256']


def test_concurrent_source_apply_has_one_winner(lab):
 p,s=setup(lab);q=proposal(lab,p,s);results=[]
 def save():
  try:results.append(lab.controllers.decide(p['id'],p['sha256'],s['head_sha256'],q['review_id'],'APPLY',APPLY)['controller_source']['revision'])
  except ValueError:results.append('REJECTED')
 ts=[threading.Thread(target=save) for _ in range(2)]
 for t in ts:t.start()
 for t in ts:t.join()
 assert sorted(map(str,results))==['1','REJECTED']


def test_bound_tools_and_no_execution_or_apply_authority(lab):
 p,s=setup(lab)
 for name in ('apply','shell','read_file','execute','provider'):
  with pytest.raises(ValueError):lab.controllers.tool(p['id'],p['sha256'],s['head_sha256'],name,{})
 with pytest.raises(ValueError):lab.controllers.tool(p['id'],'0'*64,s['head_sha256'],'inspect_controller',{})
 with pytest.raises(ValueError):lab.controllers.read('../../private')
 inspected=lab.controllers.tool(p['id'],p['sha256'],s['head_sha256'],'inspect_controller',{})
 assert inspected['data']['source']==s['compiled'] and inspected['data']['requirements']==rail.DEFAULT_CRITERIA
 with pytest.raises(ValueError):lab.start(p['id'],p['sha256'],uuid4().hex,'RUN ONE LOCAL TRUSTED RAIL VERIFICATION',lambda f:pytest.fail('Wrong controller cannot dispatch'))


def test_cancel_restart_and_duplicate_job_do_not_execute_twice(lab):
 p,s=setup(lab);n=uuid4().hex;ops=[]
 lab.controllers.start(p['id'],p['sha256'],s['head_sha256'],n,RUN,lambda f:ops.append(f))
 assert lab.controllers.start(p['id'],p['sha256'],s['head_sha256'],n,RUN,lambda f:pytest.fail('duplicate'))['reused']
 assert Workbench(lab.root).controllers.run(p['id'],n)['state']['status']=='INTERRUPTED_NO_RETRY'
 lab.controllers.cancel(p['id'],n);ops[0]();assert lab.controllers.run(p['id'],n)['state']['status']=='CANCELLED'
 with pytest.raises(ValueError):ops[0]()
 with pytest.raises(ValueError):lab.controllers.explain(p['id'],n)


def test_real_source_fail_to_pass_changes_control_and_exact_provenance(lab):
 p,s=setup(lab);n,failed=run(lab,p,s);assert failed['verified'] and failed['record']['verdict']=='FAIL' and failed['record']['metrics']['wall_contact_episodes']>0
 offline=lab.controllers.offline(p['id'],p['sha256'],s['head_sha256'],'Stop before the wall using the physical limits',n)
 assert offline['origin']=='OFFLINE DETERMINISTIC ENGINEERING ASSISTANT' and offline['model_requests']==0
 q=offline['proposal'];new=lab.controllers.decide(p['id'],p['sha256'],s['head_sha256'],q['review_id'],'APPLY',APPLY);ns=new['controller_source']
 assert not lab.controllers.run(p['id'],n)['same_head']
 n2,passed=run(lab,p,ns);assert passed['verified'] and passed['record']['verdict']=='PASS' and all(passed['record']['checks'].values())
 assert passed['record']['parameters']==failed['record']['parameters']
 assert [v['control'] for v in passed['samples']]!=[v['control'] for v in failed['samples']]
 assert passed['record']['source_sha256']==ns['compiled']['source_sha256']!=failed['record']['source_sha256']
 assert passed['record']['artifact_sha256']==ns['compiled']['artifact_sha256']
 assert passed['record']['metrics']['minimum_clearance_m']==pytest.approx(.099,abs=1e-10)
 explanation=lab.controllers.explain(p['id'],n2);assert explanation['answer']['requirements'] and explanation['source_sha256']==ns['compiled']['source_sha256']
 report=lab.controllers.report(p['id'],n2);h=report.pop('report_sha256');assert rail.digest(report)==h
 assert Workbench(lab.root).controllers.run(p['id'],n2)['record']['verdict']=='PASS'
 assert lab.controllers.history(p['id'])[-1]['revision']==1


def test_valid_coasting_controller_remains_physical_failure(lab):
 p,s=setup(lab);source='rail_controller 1\nwhen 0 < 1\nthen coast\nelse coast\n';q=proposal(lab,p,s,source);ns=lab.controllers.decide(p['id'],p['sha256'],s['head_sha256'],q['review_id'],'APPLY',APPLY)['controller_source']
 n,r=run(lab,p,ns);assert r['verified'] and r['record']['verdict']=='FAIL'


def test_corrupt_source_result_or_cross_project_binding_never_passes(lab):
 p,s=setup(lab);n,r=run(lab,p,s);other,os=setup(lab)
 with pytest.raises(ValueError):lab.controllers.run(other['id'],n)
 path=lab.root/'source_runs'/n/'result.json';v=json.loads(path.read_text());v['artifact_sha256']='0'*64
 with pytest.raises(ValueError):native.verify(v)
 v=json.loads(path.read_text());v['metrics']['minimum_clearance_m']=1
 with pytest.raises(ValueError):native.verify(v)
 v=json.loads(path.read_text());v['request']['controller']['source']=dsl.REPAIR
 with pytest.raises(ValueError):native.verify(v)


def test_source_symlink_escape_is_refused(lab,tmp_path):
 p,s=setup(lab);folder=lab.root/'source_reviews';folder.symlink_to(tmp_path,target_is_directory=True)
 with pytest.raises(ValueError):proposal(lab,p,s)


def test_large_literal_and_excessively_nested_condition_are_rejected():
 for condition in ['9'*3000+' < 1','('+('1 + '*100)+'1'+') < 1']:
  with pytest.raises(ValueError):dsl.compile_source('rail_controller 1\nwhen '+condition+'\nthen brake\nelse coast\n')


def test_actual_production_http_source_golden_path(lab):
 from http.client import HTTPConnection
 from ide_api.workbench_http import WorkbenchServer
 server=WorkbenchServer(('127.0.0.1',0),workbench=lab);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
 def request(path,body=None,token=True):
  c=HTTPConnection('127.0.0.1',server.server_port,timeout=20);headers={'Origin':'http://'+server.host}
  if body is not None:
   headers['Content-Type']='application/json'
   if token:headers['X-EMBODY-Token']=server.token
  c.request('GET' if body is None else 'POST','/api/workbench/'+path,None if body is None else json.dumps(body),headers);r=c.getresponse();value=json.loads(r.read());c.close();return r.status,value
 try:
  assert request('controller-create',{'title':'Denied'},False)[0]==403
  status,p=request('controller-create',{'title':'Actual source HTTP'});assert status==200
  s=p['controller_source'];b={'id':p['id'],'expected':p['sha256'],'controller_head':s['head_sha256']}
  def measured(b):
   nonce=uuid4().hex;assert request('controller-start',{**b,'nonce':nonce,'confirmation':RUN})[0]==200
   until=time.monotonic()+20
   while time.monotonic()<until:
    status,r=request('controller-run?id='+p['id']+'&nonce='+nonce)
    assert status==200
    if r['state']['status'] not in ('QUEUED','RUNNING'):return nonce,r
    time.sleep(.02)
   pytest.fail('Real source native job timeout')
  nonce,r=measured(b);assert r['verified'] and r['record']['verdict']=='FAIL'
  assert request('controller-tool',{**b,'name':'apply','arguments':{}})[0]==400
  status,q=request('controller-offline',{**b,'nonce':nonce,'task':'Avoid the wall using the physical limits'});assert status==200;q=q['proposal']
  assert request('controller-decide',{**b,'review_id':q['review_id'],'decision':'APPLY','confirmation':''})[0]==403
  status,new=request('controller-decide',{**b,'review_id':q['review_id'],'decision':'APPLY','confirmation':APPLY});assert status==200
  b['controller_head']=new['controller_source']['head_sha256'];n2,r=measured(b);assert r['verified'] and r['record']['verdict']=='PASS'
  status,report=request('controller-report?id='+p['id']+'&nonce='+n2);assert status==200;h=report.pop('report_sha256');assert h==rail.digest(report)
 finally:server.shutdown();thread.join();server.server_close()


def test_physical_revision_change_stales_source_review_and_foreign_arguments_reject(lab):
 from jsonschema import ValidationError
 p,s=setup(lab);q=proposal(lab,p,s);d=copy.deepcopy(p['declaration']);d['parameters']['mass_kg']=3
 r=lab.review(p['id'],p['sha256'],json.dumps(d));from ide_api.workbench import SAVE
 new=lab.decide(p['id'],p['sha256'],r['review_id'],'SAVE',SAVE)
 with pytest.raises(ValueError):lab.controllers.decide(p['id'],new['sha256'],s['head_sha256'],q['review_id'],'APPLY',APPLY)
 with pytest.raises(ValidationError):lab.controllers.tool(p['id'],new['sha256'],s['head_sha256'],'validate_controller',{'source':dsl.REPAIR,'path':'../../private'})


def test_changed_compiler_and_execution_errors_never_claim_physical_pass(lab,monkeypatch):
 p,s=setup(lab)
 with monkeypatch.context() as m:
  m.setattr(native,'identity',lambda:'0'*64)
  with pytest.raises(ValueError):proposal(lab,p,s)
 def failure(*args,**kwargs):raise TimeoutError('Explicit test-only native interruption')
 monkeypatch.setattr(native,'execute',failure)
 n,r=run(lab,p,s);assert r['state']['status']=='EXECUTION_ERROR' and r['state']['verdict'] is None and not r['verified']
 with pytest.raises(ValueError):lab.controllers.report(p['id'],n)


def test_source_and_numerical_cancellation_tools_cannot_cross_job_types(lab):
 p,s=setup(lab);n=uuid4().hex;lab.controllers.start(p['id'],p['sha256'],s['head_sha256'],n,RUN,lambda f:None)
 with pytest.raises((FileNotFoundError,ValueError)):lab.cancel(p['id'],n)
 with pytest.raises(PermissionError):lab.controllers.start(p['id'],p['sha256'],s['head_sha256'],uuid4().hex,'',lambda f:pytest.fail('No execution'))
