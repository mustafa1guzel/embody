"""v1 local composition. Real native tests use fresh disposable projects only."""
import copy,json,threading,time
from pathlib import Path
from uuid import uuid4
import pytest
from ide_api.workbench import Workbench,RUN,SAVE,pretty
from ide_api import rail_sweeps as rail

@pytest.fixture
def wb(tmp_path):return Workbench(tmp_path/'lab')

def test_project_json_review_discard_save_reopen_restore(wb):
 p=wb.create('Controller authority');original=p['sha256'];d=copy.deepcopy(p['declaration']);d['parameters']['force_n']=3
 r=wb.review(p['id'],original,pretty(d));assert wb.read(p['id'])['sha256']==original and r['applied'] is False
 wb.decide(p['id'],original,r['review_id'],'DISCARD',SAVE);assert wb.read(p['id'])['sha256']==original
 with pytest.raises(ValueError):wb.decide(p['id'],original,r['review_id'],'SAVE',SAVE)
 d['parameters']['force_n']=4;r=wb.review(p['id'],original,pretty(d));saved=wb.decide(p['id'],original,r['review_id'],'SAVE',SAVE)
 assert saved['revision']==1 and saved['declaration']['parameters']['force_n']==4
 with pytest.raises(ValueError):wb.decide(p['id'],original,r['review_id'],'SAVE',SAVE)
 reopened=Workbench(wb.root).read(p['id']);assert reopened['sha256']==saved['sha256']
 back=wb.restore(p['id'],saved['sha256'],r['review_id']);assert wb.read(p['id'])['sha256']==saved['sha256']
 restored=wb.decide(p['id'],saved['sha256'],back['review_id'],'SAVE',SAVE);assert restored['revision']==2 and restored['declaration']==p['declaration']

@pytest.mark.parametrize('change',[{'force_n':True},{'mass_kg':5},{'speed_mps':float('nan')},{'path':'../../secret'}])
def test_bad_numeric_source_never_changes_head(wb,change):
 p=wb.create('Negative source');d=copy.deepcopy(p['declaration']);d['parameters'].update(change)
 with pytest.raises((ValueError,TypeError)):wb.review(p['id'],p['sha256'],json.dumps(d))
 assert wb.read(p['id'])['sha256']==p['sha256']

@pytest.mark.parametrize('source',['{}','{"title":"a","title":"b"}','__import__("os")','x'*17000])
def test_malformed_oversized_or_executable_source_rejected(wb,source):
 p=wb.create('Bad file')
 with pytest.raises(ValueError):wb.review(p['id'],p['sha256'],source)


def test_threshold_model_controller_and_foreign_head_rejections(wb):
 p=wb.create('Contract');d=copy.deepcopy(p['declaration']);d['requirements']['minimumClearance']=.001
 with pytest.raises(ValueError):wb.review(p['id'],p['sha256'],pretty(d))
 d=p['declaration'].copy();d['controller_id']='user_python'
 with pytest.raises(ValueError):wb.review(p['id'],p['sha256'],pretty(d))
 with pytest.raises(ValueError):wb.review('../secret',p['sha256'],'{}')
 with pytest.raises(ValueError):wb.review(p['id'],'0'*64,'{}')
 with pytest.raises(PermissionError):wb.start(p['id'],p['sha256'],uuid4().hex,'',lambda op:None)


def test_no_incomplete_run_explanation_or_report(wb):
 p=wb.create('No evidence');nonce=uuid4().hex;ops=[]
 wb.start(p['id'],p['sha256'],nonce,RUN,lambda op:ops.append(op) or {'job_id':'explicit_queued_fixture'})
 assert wb.run(p['id'],nonce)['verified'] is False
 for f in (lambda:wb.explain(p['id'],nonce,'Explain'),lambda:wb.report(p['id'],nonce)):
  with pytest.raises(ValueError):f()
 assert wb.start(p['id'],p['sha256'],nonce,RUN,lambda op:pytest.fail('No duplicate submission'))['reused']
 wb.cancel(p['id'],nonce);ops[0]();assert wb.run(p['id'],nonce)['state']['status']=='CANCELLED'


def test_restart_and_foreign_run_do_not_resume_or_rebind(wb):
 a=wb.create('First');b=wb.create('Other');nonce=uuid4().hex;wb.start(a['id'],a['sha256'],nonce,RUN,lambda op:{'job_id':'queued_fixture'})
 assert Workbench(wb.root).run(a['id'],nonce)['state']['status']=='INTERRUPTED'
 with pytest.raises(ValueError):wb.run(b['id'],nonce)
 with pytest.raises(ValueError):wb.start(b['id'],b['sha256'],nonce,RUN,lambda op:None)


def test_symlink_run_directory_and_review_source_drift_fail_closed(wb,tmp_path):
 p=wb.create('Symlink');other=tmp_path/'outside';other.mkdir();(wb.root/'runs').symlink_to(other,target_is_directory=True)
 with pytest.raises(ValueError):wb.start(p['id'],p['sha256'],uuid4().hex,RUN,lambda op:None)
 assert list(other.iterdir())==[]


def test_concurrent_stale_saves_have_one_winner(wb):
 p=wb.create('Concurrent');d=copy.deepcopy(p['declaration']);d['parameters']['force_n']=4;r=wb.review(p['id'],p['sha256'],pretty(d));results=[]
 def save():
  try:results.append(wb.decide(p['id'],p['sha256'],r['review_id'],'SAVE',SAVE)['revision'])
  except ValueError:results.append('REJECTED')
 threads=[threading.Thread(target=save) for _ in range(2)]
 for t in threads:t.start()
 for t in threads:t.join()
 assert sorted(map(str,results))==['1','REJECTED'] and wb.read(p['id'])['revision']==1


def test_real_native_fail_tool_review_save_pass_and_report(wb,tmp_path):
 # These are new current-source developer-run experiments, not the historical
 # live qualification and not model-authored decisions. No provider is involved.
 p=wb.create('Actual local physical debugging');nonce=uuid4().hex
 wb.start(p['id'],p['sha256'],nonce,RUN,lambda op:op() or {'job_id':'synchronous_native_test'})
 failed=wb.run(p['id'],nonce);assert failed['verified'] and failed['record']['verdict']=='FAIL'
 assert failed['record']['metrics']['minimum_clearance_m']==pytest.approx(.003,abs=1e-10)
 explanation=wb.explain(p['id'],nonce,'Why did this fail?');assert explanation['origin']=='DETERMINISTIC_TOOLS_NOT_GPT' and explanation['model_requests']==0
 assert explanation['tool_calls'][0]['name']=='inspect_result'
 proposed=wb.suggest(p['id'],p['sha256'],nonce);assert proposed['origin']=='DETERMINISTIC_ANALYTICAL_NOT_AI' and wb.read(p['id'])['sha256']==p['sha256']
 saved=wb.decide(p['id'],p['sha256'],proposed['review_id'],'SAVE',SAVE);assert wb.run(p['id'],nonce)['same_head'] is False
 with pytest.raises(ValueError):wb.suggest(p['id'],saved['sha256'],nonce)
 new=uuid4().hex;wb.start(p['id'],saved['sha256'],new,RUN,lambda op:op() or {'job_id':'synchronous_native_test'})
 passed=wb.run(p['id'],new);assert passed['verified'] and passed['record']['verdict']=='PASS' and all(passed['record']['checks'].values())
 report=wb.report(p['id'],new);assert report['result']['replay_status']=='PASS' and report['limits']['fresh_replay_steps']==600
 assert wb.read(p['id'])['sha256']==saved['sha256'];assert Workbench(wb.root).run(p['id'],new)['record']['verdict']=='PASS'

@pytest.fixture
def http(wb):
 from ide_api.workbench_http import WorkbenchServer
 server=WorkbenchServer(('127.0.0.1',0),workbench=wb);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
 yield server
 server.shutdown();thread.join();server.server_close()

def req(server,path,b=None,token=True,origin=True):
 from http.client import HTTPConnection
 c=HTTPConnection('127.0.0.1',server.server_port,timeout=15);h={}
 if origin:h['Origin']='http://'+server.host
 if b is not None:
  h['Content-Type']='application/json'
  if token:h['X-EMBODY-Token']=server.token
 c.request('GET' if b is None else 'POST','/api/workbench/'+path,body=None if b is None else json.dumps(b),headers=h);r=c.getresponse();data=json.loads(r.read());status=r.status;c.close();return status,data


def test_http_guards_paths_schema_and_no_provider(http):
 assert req(http,'bootstrap')[0]==200
 for name in ('provider','approve','apply','execute-python','credentials'):
  assert req(http,name,{})[0]==403
 assert req(http,'create',{'title':'Test'},token=False)[0]==403
 assert req(http,'create',{'title':'Test'},origin=False)[0]==403
 assert req(http,'create',{'title':'Test','path':'bad'})[0]==400
 status,p=req(http,'create',{'title':'HTTP project'});assert status==200
 assert req(http,'project?id='+p['id'])[1]['sha256']==p['sha256']
 assert req(http,'project?id=../../secret')[0]==400
 assert req(http,'project?id='+p['id']+'&id='+p['id'])[0]==400
 assert req(http,'create?unexpected=1',{'title':'Bad'})[0]==400


def test_actual_http_native_job_workflow(http):
 status,p=req(http,'create',{'title':'HTTP native failure'});assert status==200;nonce=uuid4().hex
 status,started=req(http,'start',{'id':p['id'],'expected':p['sha256'],'nonce':nonce,'confirmation':RUN});assert status==200
 deadline=time.monotonic()+30
 while time.monotonic()<deadline:
  status,r=req(http,'run?id='+p['id']+'&nonce='+nonce)
  if r['state']['status'] not in ('QUEUED','RUNNING'):break
  time.sleep(.02)
 assert status==200 and r['verified'] and r['record']['verdict']=='FAIL'
 assert req(http,'report?id='+p['id']+'&nonce='+nonce)[1]['result']['verdict']=='FAIL'

@pytest.mark.parametrize('kind',['missing','duplicate','description','unknown','other_project','wrong_number','wrong_outcome','false_PASS'])
def test_strict_deterministic_explanation_negatives(kind):
 from ide_api.workbench import validate_explanation,explanation_text
 from ide_api.engineering_agent_live import EngineeringAgentLive
 # Explicit unit fixture, never physical or model success evidence.
 ev={'id':'unit_evidence','verdict':'FAIL','metrics':{'minimum_clearance_m':.003},'checks':{'selected_clearance':False,'selected_final_speed':True}}
 a={'observations':[{'result_id':ev['id'],'metric':'minimum_clearance_m','value':.003}],'requirements':[{'result_id':ev['id'],'check':k,'passed':v} for k,v in ev['checks'].items()],'interpretation':explanation_text(ev),'hypotheses':[],'proposed_action':'Review','verification_required':'Native verification','proposal_id':None}
 validate_explanation(a,ev)
 if kind=='missing':a['requirements']=[]
 if kind=='duplicate':a['requirements'].append(copy.deepcopy(a['requirements'][0]))
 if kind=='description':a['requirements'][0]['check']='clearance >=0.05 m'
 if kind=='unknown':a['requirements'][0]['check']='not_a_requirement'
 if kind=='other_project':a['requirements'][0]['result_id']='foreign'
 if kind=='wrong_number':a['observations'][0]['value']=.3
 if kind=='wrong_outcome':a['requirements'][0]['passed']=True
 if kind=='false_PASS':a['interpretation']='All checks PASS'
 with pytest.raises(ValueError):validate_explanation(a,ev)


def test_run_association_tampering_cannot_relabel_snapshot(wb):
 p=wb.create('Association');nonce=uuid4().hex;wb.start(p['id'],p['sha256'],nonce,RUN,lambda op:{'job_id':'queued_fixture'})
 path=wb.root/'runs'/(nonce+'.json');value=json.loads(path.read_text());value['parameters']['mass_kg']=1;path.write_text(json.dumps(value))
 with pytest.raises(ValueError,match='immutable'):wb.run(p['id'],nonce)


def test_interrupted_before_admission_never_silently_retries(wb):
 p=wb.create('Interrupted mapping');nonce=uuid4().hex;root=wb.root/'runs';root.mkdir()
 (root/(nonce+'.json')).write_text(json.dumps({'project_id':p['id'],'project_sha256':p['sha256'],'project_revision':p['revision'],'parameters':p['declaration']['parameters'],'requirements':p['declaration']['requirements'],'native_source':rail.source_identity()}))
 with pytest.raises(ValueError,match='Interrupted'):wb.start(p['id'],p['sha256'],nonce,RUN,lambda op:pytest.fail('No resubmission'))
