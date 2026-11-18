"""Shared physical contracts/lifecycle/tools/verifier, real rail and mobile dynamics."""
import copy,json,threading,time
from uuid import uuid4
import pytest
from physical_core import adapters,contracts,language,engine
from physical_core.service import APPLY,RUN,validate_answer
from ide_api.workbench import Workbench
from ide_api import rail_sweeps as rail
@pytest.fixture
def svc(tmp_path):return Workbench(tmp_path/'shared').physical

def create(svc,family):return svc.create(contracts.template(family),svc.examples()[family]['initial_source'])
def propose(svc,p,source=None,d=None):return svc.agent_task(p['project_id'],p['sha256'],'Explicit developer source plan, not model reasoning',source or svc.examples()[p['definition']['family']]['corrected_source'],d or p['definition'])['proposal']
def apply(svc,p,q):return svc.decide(p['project_id'],p['sha256'],q['review_id'],'APPLY',APPLY)
def run(svc,p):
 n=uuid4().hex;svc.start(p['project_id'],p['sha256'],n,RUN,lambda f:f());return n,svc.run(p['project_id'],n)

@pytest.mark.parametrize('family',['rail','differential_rover'])
def test_same_source_lifecycle_tools_and_real_native_verifier(svc,family):
 p=create(svc,family);n,failed=run(svc,p);assert failed['verified'] and failed['record']['verdict']=='FAIL'
 q=propose(svc,p);assert svc.read(p['project_id'])['sha256']==p['sha256']
 with pytest.raises(PermissionError):svc.decide(p['project_id'],p['sha256'],q['review_id'],'APPLY','')
 fixed=apply(svc,p,q);assert not svc.run(p['project_id'],n)['same_head'];n2,passed=run(svc,fixed)
 assert passed['verified'] and passed['record']['verdict']=='PASS' and all(passed['record']['checks'].values())
 assert passed['record']['source_sha256']==fixed['compiled']['source_sha256'] and passed['record']['artifact_sha256']==fixed['compiled']['artifact_sha256']
 assert failed['record']['model_sha256']==passed['record']['model_sha256']
 assert failed['record']['trajectory_sha256']!=passed['record']['trajectory_sha256']
 assert svc.explain(p['project_id'],n2)['answer']['requirements']
 report=svc.report(p['project_id'],n2);h=report.pop('report_sha256');assert rail.digest(report)==h
 assert Workbench(svc.w.root).physical.read(p['project_id'])['sha256']==fixed['sha256']
 restore=svc.restore(p['project_id'],fixed['sha256'],p['sha256']);assert restore['compiled']['source']==p['compiled']['source']
 assert svc.view(p['project_id'],n2,0)['origin']=='ACTUAL_SAVED_NATIVE_STATE'

@pytest.mark.parametrize('bad',['arm','drone','../../private','universal_robot'])
def test_unsupported_families_reject_without_execution(bad):
 with pytest.raises(ValueError):contracts.template(bad)

@pytest.mark.parametrize('bad',['__import__("os")','speed_mps.__class__','[x for x in []]','True','speed_mps[0]','1 / 0','9'*3000])
def test_shared_language_rejects_unsafe_syntax_and_invalid_types(bad):
 c=contracts.contract(contracts.template('rail'))
 with pytest.raises(ValueError):language.compile_source('physical_controller 1\nforce_n = '+bad,c)


def test_units_missing_actions_and_post_action_feedback_reject():
 c=contracts.contract(contracts.template('differential_rover'))
 for source in ['physical_controller 1\nleft_nm = 1','physical_controller 1\nleft_nm = speed_mps\nright_nm = 0','physical_controller 1\nleft_nm = actuator_peak\nright_nm = 0']:
  with pytest.raises(ValueError):language.compile_source(source,c)

@pytest.mark.parametrize('case',['missing','weaken','duplicate','unknown_metric','wrong_unit','nonfinite','unknown_parameter','wrong_band'])
def test_generic_project_requirement_contract_is_strict(case):
 d=contracts.template('rail')
 if case=='missing':d['requirements']=d['requirements'][1:]
 elif case=='weaken':next(r for r in d['requirements'] if r['id']=='clearance')['threshold']=.001
 elif case=='duplicate':d['requirements'].append(copy.deepcopy(d['requirements'][0]))
 elif case=='unknown_metric':d['requirements'][0]['expression']='invented_measurement'
 elif case=='wrong_unit':d['requirements'][0]['unit']='m'
 elif case=='nonfinite':d['requirements'][0]['threshold']=float('nan')
 elif case=='unknown_parameter':d['parameters']['path']='private'
 elif case=='wrong_band':d['requirements'][0]['band']=.1
 with pytest.raises(ValueError):contracts.validate(d)


def test_project_requirements_are_data_not_wall_hardcoding():
 d=contracts.template('differential_rover');d['requirements'].append(contracts.req('new_task_heading','abs(yaw_rad)','final','<=',.12,'rad'))
 d['requirements'][0]['threshold']*=.9
 assert contracts.validate(d)['requirements'][-1]['id']=='new_task_heading'
 assert contracts.contract(d)['requirements'][-1]['expression']=='abs(yaw_rad)'


def test_discard_reproposal_stale_foreign_restore_and_concurrent_apply(svc):
 p=create(svc,'rail');q=propose(svc,p);svc.decide(p['project_id'],p['sha256'],q['review_id'],'REJECT',APPLY)
 with pytest.raises(ValueError):svc.decide(p['project_id'],p['sha256'],q['review_id'],'APPLY',APPLY)
 q2=propose(svc,p);assert q2['review_id']!=q['review_id'];other=create(svc,'rail')
 with pytest.raises(ValueError):svc.decide(other['project_id'],other['sha256'],q2['review_id'],'APPLY',APPLY)
 results=[]
 def save():
  try:results.append(apply(svc,p,q2)['revision'])
  except ValueError:results.append('REJECTED')
 threads=[threading.Thread(target=save) for _ in range(2)]
 for t in threads:t.start()
 for t in threads:t.join()
 assert sorted(map(str,results))==['1','REJECTED']
 with pytest.raises(ValueError):svc.tool(p['project_id'],p['sha256'],'inspect_system',{})


def test_cancellation_duplicate_restart_and_no_tool_authority(svc):
 p=create(svc,'rail');n=uuid4().hex;ops=[];svc.start(p['project_id'],p['sha256'],n,RUN,lambda f:ops.append(f));assert svc.start(p['project_id'],p['sha256'],n,RUN,lambda f:pytest.fail('duplicate'))['reused']
 assert Workbench(svc.w.root).physical.run(p['project_id'],n)['state']['status']=='INTERRUPTED_NO_RETRY';svc.cancel(p['project_id'],n);ops[0]();assert svc.run(p['project_id'],n)['state']['status']=='CANCELLED'
 with pytest.raises(ValueError):ops[0]()
 for tool in ('apply','run','shell','provider'):
  with pytest.raises(ValueError):svc.tool(p['project_id'],p['sha256'],tool,{})
 with pytest.raises(ValueError):svc.read('../outside')


def test_general_explanation_keeps_every_canonical_reference_exact():
 record={'verdict':'FAIL','checks':{'custom_target':False,'custom_force':True},'metrics':{'custom_target':.01,'custom_force':4.}}
 good={'requirements':[{'id':k,'passed':v} for k,v in record['checks'].items()],'observations':[{'id':k,'measured':v} for k,v in record['metrics'].items()],'interpretation':'Recorded physical FAIL. Failed project IDs: custom_target'};validate_answer(good,record)
 for case in ('missing','duplicate','label','wrong_number','wrong_outcome','false_pass'):
  bad=copy.deepcopy(good)
  if case=='missing':bad['requirements']=[]
  elif case=='duplicate':bad['requirements'].append(copy.deepcopy(bad['requirements'][0]))
  elif case=='label':bad['requirements'][0]['id']='human readable target description'
  elif case=='wrong_number':bad['observations'][0]['measured']=10
  elif case=='wrong_outcome':bad['requirements'][0]['passed']=True
  else:bad['interpretation']='Recorded physical PASS'
  with pytest.raises(ValueError):validate_answer(bad,record)


def test_corrupted_generic_native_values_never_verify(svc):
 p=create(svc,'rail');n,r=run(svc,p);path=svc.path('runs',n,'result.json');v=json.loads(path.read_text())
 for case in ('metric','artifact','contact','observation'):
  bad=copy.deepcopy(v)
  if case=='metric':bad['metrics']['clearance']=1
  elif case=='artifact':bad['request']['compiled']['artifact_sha256']='0'*64
  elif case=='contact':bad['samples'][0]['contacts']=[[0,1]];bad['trajectory_sha256']=rail.digest(bad['samples'])
  else:bad['samples'][0]['observations']['clearance_m']=1;bad['trajectory_sha256']=rail.digest(bad['samples'])
  with pytest.raises(ValueError):engine.verify(bad)


def test_actual_http_shared_contract_routes_and_authority(svc):
 from http.client import HTTPConnection
 from ide_api.workbench_http import WorkbenchServer
 server=WorkbenchServer(('127.0.0.1',0),workbench=svc.w);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
 def request(path,body=None,token=True):
  c=HTTPConnection('127.0.0.1',server.server_port,timeout=20);headers={'Origin':'http://'+server.host}
  if body is not None:
   headers['Content-Type']='application/json'
   if token:headers['X-EMBODY-Token']=server.token
  c.request('GET' if body is None else 'POST','/api/workbench/'+path,None if body is None else json.dumps(body),headers);r=c.getresponse();value=json.loads(r.read());c.close();return r.status,value
 try:
  status,catalog=request('physical-catalog');assert status==200 and len(catalog['families'])==2
  d=contracts.template('differential_rover');source=svc.examples()['differential_rover']['initial_source']
  assert request('physical-create',{'definition':d,'source':source},False)[0]==403
  status,p=request('physical-create',{'definition':d,'source':source});assert status==200
  assert request('physical-project?id='+p['project_id'])[1]['sha256']==p['sha256']
  assert request('physical-tool',{'id':p['project_id'],'expected':p['sha256'],'name':'shell','arguments':{}})[0]==400
  assert request('physical-project?id=../../private')[0]==400
  assert request('physical-start',{'id':p['project_id'],'expected':p['sha256'],'nonce':uuid4().hex,'confirmation':''})[0]==403
 finally:server.shutdown();thread.join();server.server_close()


def test_low_storage_blocks_before_admission_or_native_work(svc,monkeypatch):
 from types import SimpleNamespace
 import physical_core.service as module
 p=create(svc,'rail');monkeypatch.setattr(module.shutil,'disk_usage',lambda path:SimpleNamespace(free=0))
 n=uuid4().hex
 with pytest.raises(ValueError,match='storage'):svc.start(p['project_id'],p['sha256'],n,RUN,lambda f:pytest.fail('No dispatch'))
 assert not svc.path('runs',n).exists()
