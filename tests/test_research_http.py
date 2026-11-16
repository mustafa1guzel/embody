"""Actual guarded local HTTP integration; no transport or simulation mocks as evidence."""
import json,threading
from http.client import HTTPConnection
import pytest
from ide_api.server import Server
from ide_api.service import IDE
from ide_api.rail_sweeps import RailSweeps
from ide_api.experiment_designer import ExperimentDesigner
from ide_api.research.store import Research

@pytest.fixture
def http(tmp_path,monkeypatch):
 import mujoco
 from core.agent import credentials
 def forbidden(*a,**kw):raise AssertionError('No native/provider request in research HTTP test')
 monkeypatch.setattr(mujoco,'mj_step',forbidden);monkeypatch.setattr(credentials,'create_openai_client',forbidden)
 ide=IDE();ide._rail_sweeps=RailSweeps(tmp_path/'native');ide._experiment_designer=ExperimentDesigner(ide._rail_sweeps,tmp_path/'designer');ide._research=Research(ide._experiment_designer,tmp_path/'research');server=Server(('127.0.0.1',0),ide=ide);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
 def request(path,value=None,authorized=True):
  connection=HTTPConnection('127.0.0.1',server.server_port,timeout=15);headers={'Host':server.host}
  if authorized:headers.update({'Origin':'http://'+server.host,'X-EMBODY-Token':server.token})
  if value is not None:headers['Content-Type']='application/json'
  connection.request('GET' if value is None else 'POST','/api/'+path,body=None if value is None else json.dumps(value),headers=headers);response=connection.getresponse();data=json.loads(response.read());connection.close();return response.status,data
 yield request,ide
 server.shutdown();server.server_close();thread.join(2)

def test_research_http_requires_real_same_origin_guard_and_exact_schema(http):
 request,ide=http
 assert request('research/context')[0]==200
 assert not ide.research.root.exists()
 body={'title':'HTTP research','question':'What changes measured clearance?','experiment_id':'rail_velocity_brake_v1'}
 assert request('research/new',body,False)[0]==403
 assert request('research/new',{**body,'run':True})[0]==400
 status,read=request('research/new',body);assert status==200;key=read['project']['id']
 assert request('research/project?id='+key)[1]['sha256']==read['sha256']
 for route in ['start','approve','execute','apply','model']:
  assert request('research/'+route,{'key':key})[0]==403
 assert not ide.rail_sweeps.root.exists()
 assert request('research/project?id=../../secret')[0]==400
 assert request('research/context?extra=1')[0]==400

def test_native_admission_remains_independent_of_research(http):
 request,ide=http
 from ide_api import rail_sweeps as rail
 catalog=rail.catalog();base={'experiment_id':rail.EXPERIMENT,'controller_id':'model_generated.py','source_sha256':catalog['source_sha256'],'cases':[{'mass_kg':2,'speed_mps':1,'force_n':4,'gap_m':1}],'criteria':catalog['defaults'],'nonce':'a'*32,'confirmation':rail.CONFIRMATION}
 assert request('rail-sweeps/start',base)[0]==400
 base['controller_id']=rail.CONTROLLER;base['experiment_id']='unknown';assert request('rail-sweeps/start',base)[0]==400
 assert not ide.rail_sweeps.root.exists()


def test_evidence_and_benchmark_http_exact_guards_and_no_authority(http):
 request,ide=http
 from test_research_workflow import config as config_fixture
 from ide_api import rail_sweeps as rail
 read=request('research/new',{'title':'Evidence checks','question':'Which outcomes have available raw data?','experiment_id':rail.EXPERIMENT})[1];pid=read['project']['id']
 cfg={'experiment_id':rail.EXPERIMENT,'controller_id':rail.CONTROLLER,'objective':'Study gap','type':'adaptive_1d','axes':[{'parameter':'gap_m','minimum':1.4,'maximum':1.6}],'fixed_parameters':{'mass_kg':4,'speed_mps':1.2,'force_n':2,'gap_m':1.49},'criteria':rail.DEFAULT_CRITERIA,'strategy':'uniform','count':3,'seed':1,'minimum_spacing':.001,'proposal_budget':8,'hypothesis_ids':[]}
 read=request('research/campaign',{'key':pid,'expected':read['sha256'],'config':cfg})[1];cid=read['project']['campaigns'][0]['id']
 value={'project_id':pid,'campaign_id':cid,'config':{'environment':'single_transition','budget':12,'seed':1,'resolution':.005}}
 assert request('research-benchmarks/run',value,False)[0]==403
 status,out=request('research-benchmarks/run',value);assert status==200 and out['native_integration_steps']==0
 assert request('research-benchmarks/run?id='+out['id'])[1]==out
 assert request('research-benchmarks/run',{**value,'execute':True})[0]==400
 assert request('research-evidence/catalog')[1]['historical_missing'][0]['availability']=='MISSING'
 for route in ('attest','execute','apply','approve'):
  assert request('research-evidence/'+route,{'id':'a'*32})[0]==403
 cap={'project_id':pid,'campaign_id':cid,'expected':'0'*64,'kind':'recorded','evidence_id':'portable_rail_study','case_ids':[]}
 assert request('research-evidence/capture',cap)[0]==400
 assert not ide.rail_sweeps.root.exists()
