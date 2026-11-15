"""Offline research integration. No native rollout or paid request is allowed."""
import copy,json
from pathlib import Path
import pytest
from ide_api import rail_sweeps as rail
from ide_api.experiment_designer import ExperimentDesigner
from ide_api.research.store import Research
from ide_api.research import contracts as c,evidence,reproducibility as repro,reporting

@pytest.fixture(autouse=True)
def prohibit_execution(monkeypatch):
 import mujoco
 from core.agent import credentials
 def forbidden(*a,**kw):raise AssertionError('No native/provider execution authorized by these research tests')
 for n in ['mj_step','mj_step1','mj_step2']:monkeypatch.setattr(mujoco,n,forbidden)
 monkeypatch.setattr(credentials,'create_openai_client',forbidden)
 monkeypatch.setattr(rail,'simulate_case',forbidden)

@pytest.fixture
def service(tmp_path):return Research(ExperimentDesigner(rail.RailSweeps(tmp_path/'native'),tmp_path/'designer'),tmp_path/'research')
@pytest.fixture
def read(service):return service.new('Bounded investigation','What affects sampled clearance?',rail.EXPERIMENT)
@pytest.fixture
def config(service):return {'experiment_id':rail.EXPERIMENT,'controller_id':rail.CONTROLLER,'objective':'Study gap sensitivity','type':'adaptive_1d','axes':[{'parameter':'gap_m','minimum':.35,'maximum':2.2}],'fixed_parameters':{'mass_kg':4.,'speed_mps':1.2,'force_n':2.,'gap_m':1.49},'criteria':copy.deepcopy(rail.DEFAULT_CRITERIA),'strategy':'uniform','count':3,'seed':1,'minimum_spacing':.001,'proposal_budget':12,'hypothesis_ids':[]}

def create(service,read,config):
 read=service.campaign(read['project']['id'],read['sha256'],config);cid=read['project']['campaigns'][0]['id'];return service.propose(read['project']['id'],read['sha256'],cid,'initial'),cid

@pytest.mark.parametrize('key,value',[('experiment_id','unknown'),('controller_id','generated.py'),('count',26),('count',True),('count',float('nan')),('proposal_budget',0),('seed',-1),('minimum_spacing',0),('type','run_source'),('extra','code')])
def test_strict_config_rejection(service,read,config,key,value):
 config[key]=value
 with pytest.raises((ValueError,TypeError)):service.campaign(read['project']['id'],read['sha256'],config)
 assert not service.read(read['project']['id'])['project']['campaigns']

@pytest.mark.parametrize('parameter,value',[('mass_kg',0),('speed_mps',float('inf')),('force_n',True),('gap_m',20)])
def test_fixed_bounds(service,read,config,parameter,value):
 config['fixed_parameters'][parameter]=value
 with pytest.raises((ValueError,TypeError)):service.campaign(read['project']['id'],read['sha256'],config)

@pytest.mark.parametrize('name,value',[('minimumClearance',0),('maximumFinalSpeed',.1),('maximumSettlingTime',3.1),('maximumContactEpisodes',1)])
def test_cannot_weaken_criteria(service,read,config,name,value):
 config['criteria'][name]=value
 with pytest.raises(ValueError):service.campaign(read['project']['id'],read['sha256'],config)

def test_hypothesis_edit_and_campaign_relation(service,read,config):
 content={'statement':'Larger gap may preserve clearance','relationship':'Gap versus sampled clearance','variables':['gap_m'],'direction':'increase','assumptions':['Other conditions fixed'],'evaluation':'Compare verified equal-condition cases'}
 key=read['project']['id'];read=service.hypothesis(key,read['sha256'],content);hid=read['project']['hypotheses'][0]['id'];config['hypothesis_ids']=[hid];read=service.campaign(key,read['sha256'],config)
 assert read['project']['hypotheses'][0]['status']=='UNDER_INVESTIGATION';content['statement']='Edited expectation';read=service.hypothesis(key,read['sha256'],content,hid);assert read['project']['hypotheses'][0]['content']==content
 read=service.note(key,read['sha256'],'Which fixed conditions are still untested?');assert read['project']['open_questions']
 with pytest.raises(ValueError):service.note(key,'0'*64,'stale request')

def test_full_review_transfer_rejection_no_execution(service,read,config):
 read,cid=create(service,read,config);key=read['project']['id'];b=read['project']['campaigns'][0]['batches'][0]
 with pytest.raises(ValueError):service.transfer(key,cid,b['id'])
 read=service.review(key,read['sha256'],cid,b['id'],'reject')
 with pytest.raises(ValueError):service.transfer(key,cid,b['id'])
 read=service.review(key,read['sha256'],cid,b['id'],'accept');t=service.mark_transfer(key,read['sha256'],cid,b['id']);assert t['execution_authorized'] is False;assert len(t['cases'])==3;assert service.read(key)['project']['campaigns'][0]['status']=='TRANSFERRED'
 assert not service.designer.rail.root.exists()
 with pytest.raises(ValueError):service.transition(key,service.read(key)['sha256'],cid,'MEASURED')
 with pytest.raises(ValueError):service.transition(key,service.read(key)['sha256'],cid,'COMPLETED')

def test_proposal_duplicate_budget_and_adaptive_insufficient(service,read,config):
 read,cid=create(service,read,config)
 with pytest.raises(ValueError):service.propose(read['project']['id'],read['sha256'],cid,'initial')
 with pytest.raises(ValueError,match='INSUFFICIENT'):service.propose(read['project']['id'],read['sha256'],cid,'adaptive')

@pytest.mark.parametrize('bad',['../../secret','https://example.invalid','import os','read /Users/example/private.txt','<script>alert(1)</script>'])
def test_untrusted_text_no_paths_code_or_urls(service,bad):
 with pytest.raises(ValueError):service.new('Unsafe',bad,rail.EXPERIMENT)

def test_persistence_corruption_quota_and_archive(service,read,config):
 key=read['project']['id'];read=service.transition(key,read['sha256'],None,'ARCHIVED');assert service.read(key)==read
 with pytest.raises(ValueError):service.note(key,read['sha256'],'must not edit archived')
 for i in range(7):service.new('Study '+str(i),'Which measured conditions matter?',rail.EXPERIMENT)
 with pytest.raises(ValueError,match='retention'):service.new('Overflow','Which conditions?',rail.EXPERIMENT)
 pointer=json.loads((service.root/key/'head.json').read_text());(service.root/key/(pointer['sha256']+'.json')).write_text('{}')
 with pytest.raises(ValueError):service.read(key)
 assert any(p['status']=='CORRUPT' for p in service.listing())

def test_stale_context_and_unknown_descriptor(service,read,config,monkeypatch):
 before=service.context;monkeypatch.setattr(service,'context',lambda:{**before(),'context_sha256':'f'*64})
 assert service.read(read['project']['id'])['stale']
 with pytest.raises(ValueError):service.campaign(read['project']['id'],read['sha256'],config)
 with pytest.raises(ValueError):service.new('Bad','Question','unknown')
 r=service.new('Rover metadata','What is available?','rover_ramp_reference_descriptor_v1')
 with pytest.raises(ValueError):service.campaign(r['project']['id'],r['sha256'],config)
 assert service.context()['descriptors'][1]['execution']=='UNAVAILABLE_IN_RESEARCH'

def test_manifest_roundtrip_drops_review_authority(service,read,config):
 read,cid=create(service,read,config);key=read['project']['id'];b=read['project']['campaigns'][0]['batches'][0];read=service.review(key,read['sha256'],cid,b['id'],'accept');m=repro.export(service,key);assert repro.compare(service,m,m)['status']=='IDENTICAL_CONFIGURATION_AND_EVIDENCE'
 imported=repro.import_manifest(service,m);assert imported['project']['id']!=key;assert imported['project']['campaigns'][0]['batches'][0]['status']=='AWAITING_REVIEW'
 with pytest.raises(ValueError):service.transfer(imported['project']['id'],cid,b['id'])
 assert service.read(key)==read
 bad=copy.deepcopy(m);bad['format']='UNKNOWN';bad['manifest_sha256']=c.data_digest({k:v for k,v in bad.items() if k!='manifest_sha256'})
 with pytest.raises(ValueError):repro.import_manifest(service,bad)
 bad=copy.deepcopy(m);bad['project']['campaigns'][0]['config']['fixed_parameters']['force_n']=3.;bad['manifest_sha256']=c.data_digest({k:v for k,v in bad.items() if k!='manifest_sha256'});
 with pytest.raises(ValueError):repro.compare(service,m,bad)
 bad['project']['campaigns'][0]['batches']=[];bad['project']['campaigns'][0]['status']='DRAFT';bad['manifest_sha256']=c.data_digest({k:v for k,v in bad.items() if k!='manifest_sha256'});assert repro.compare(service,m,bad)['differences']

@pytest.mark.parametrize('field,value',[('output_path','/tmp/unsafe'),('code','import os'),('source','<mujoco/>')])
def test_manifest_injection(service,read,field,value):
 m=repro.export(service,read['project']['id']);m[field]=value
 with pytest.raises(ValueError):repro.import_manifest(service,m)

def test_import_stale_requires_acknowledgement(service,read):
 m=repro.export(service,read['project']['id']);m['project']['context_sha256']='d'*64;m['manifest_sha256']=c.data_digest({k:v for k,v in m.items() if k!='manifest_sha256'})
 with pytest.raises(ValueError):repro.import_manifest(service,m)
 result=repro.import_manifest(service,m,True);assert result['stale'];assert result['project']['status']=='ACTIVE'

def test_real_pinned_historical_reader_findings_graph_report(service,read,config):
 read,cid=create(service,read,config);key=read['project']['id'];read=service.link(key,read['sha256'],cid,'recorded','portable_rail_study');view=service.view(key,cid)
 assert len(view['records'])==9;assert all(r['verified'] and not r['source_current'] for r in view['records']);assert view['campaign']['evidence'][0]['association']=='EXTERNAL_REFERENCE';assert view['budgets']['submitted']==0
 summary=view['summaries'][0];fact=next(f for f in summary['facts'] if f['metric']=='minimum_clearance_m');read=service.finding(key,read['sha256'],cid,summary['summary_sha256'],fact['id']);view=service.view(key,cid)
 assert view['findings'][0]['fact']==fact;assert view['findings'][0]['status']=='VERIFIED';assert any(e['type']=='derived_from' and e['to']==fact['case_id'] for e in view['graph']['edges'])
 report=reporting.generate(service,key,[cid],[]);assert str(fact['value']) in report['markdown'];assert fact['case_id'] in report['markdown'];assert 'No new current-source' in report['markdown'];assert report['ai_status']=='UNAVAILABLE_NOT_CALLED'
 with pytest.raises(ValueError):service.finding(key,read['sha256'],cid,summary['summary_sha256'],'unknown:metric')
 with pytest.raises(ValueError):service.transition(key,read['sha256'],cid,'COMPLETED')
 # Corrupt/unavailable readers invalidate dependent findings rather than retaining a verified badge.
 old=service._records
 def missing(v):return [],[],[{'reference':'portable_rail_study','status':'UNVERIFIED','error':'ValueError'}]
 service._records=missing;assert service.view(key,cid)['findings'][0]['status']=='UNVERIFIED';assert 'numerical claim retained' in reporting.generate(service,key,[cid],[])['markdown'];service._records=old
 assert not service.designer.rail.root.exists()

def test_empty_report_is_proposal_not_empirical(service,read):
 report=reporting.generate(service,read['project']['id'],[],[]);assert report['kind']=='RESEARCH_PROPOSAL_ANALYTICAL_STUDY';assert '0 unique' in report['markdown'];assert 'No empirical completion' in report['markdown']
 assert reporting.escape('<img src=x> [x](bad) |')=='&lt;img src=x&gt; \\[x\\](bad) \\|'

def test_atomic_head_and_event_bounds(service,read):
 key=read['project']['id'];folder=service.root/key;old=json.loads((folder/'head.json').read_text());before=(folder/(old['sha256']+'.json')).read_bytes();read=service.note(key,read['sha256'],'A real unresolved question');assert (folder/(old['sha256']+'.json')).read_bytes()==before;assert json.loads((folder/'head.json').read_text())['sha256']==read['sha256'];assert not list(folder.glob('*.tmp'))
 p=read['project'];p['events']=[{'id':f'{i:032x}','at':'synthetic_time','kind':'TEST_ONLY','subject':key} for i in range(128)];service._save(p);before=service.read(key)
 with pytest.raises(ValueError,match='timeline'):service.note(key,before['sha256'],'Must not silently discard events')
 assert service.read(key)==before

def test_tampered_batch_import_and_duplicate_identifiers(service,read,config):
 read,cid=create(service,read,config);m=repro.export(service,read['project']['id']);m['project']['campaigns'][0]['batches'][0]['cases'][0]['mass_kg']=2.;m['manifest_sha256']=c.data_digest({k:v for k,v in m.items() if k!='manifest_sha256'})
 with pytest.raises(ValueError):repro.import_manifest(service,m)
 p=read['project'];p['campaigns'].append(copy.deepcopy(p['campaigns'][0]))
 with pytest.raises(ValueError):c.validate_project(p,service.context()['catalog'])

def test_imported_result_claim_never_creates_finding(service,read,config):
 read,cid=create(service,read,config);m=repro.export(service,read['project']['id']);m['project']['findings']=[{'id':'e'*32,'campaign_id':cid,'summary_sha256':'f'*64,'fact_id':'pretend_case:minimum_clearance_m'}];m['manifest_sha256']=c.data_digest({k:v for k,v in m.items() if k!='manifest_sha256'});new=repro.import_manifest(service,m);v=service.view(new['project']['id'],cid);assert v['findings'][0]['status']=='UNVERIFIED';assert not any(n['type']=='finding' for n in v['graph']['nodes'])

def test_real_completion_requires_matching_current_results_only(service,read,config,monkeypatch):
 # Explicit synthetic lifecycle fixture. It tests transitions, never physics or real measurement claims.
 read,cid=create(service,read,config);key=read['project']['id'];b=read['project']['campaigns'][0]['batches'][0];read=service.review(key,read['sha256'],cid,b['id'],'accept');ctx=service.context()['catalog'];request={'cases':b['cases'],'criteria':config['criteria'],'experiment_id':rail.EXPERIMENT,'controller_id':rail.CONTROLLER,'source_sha256':ctx['source_sha256']}
 s={'kind':'native','id':'1'*32,'summary_sha256':'d'*64,'records':[],'facts':[],'counts':{'planned':3,'measured':1},'request':request}
 monkeypatch.setattr(evidence,'load',lambda *a,**kw:copy.deepcopy(s));read=service.link(key,read['sha256'],cid,'native','1'*32);assert read['project']['campaigns'][0]['status']=='PARTIAL'
 with pytest.raises(ValueError):service.transition(key,read['sha256'],cid,'COMPLETED')
 s['counts']['measured']=3;read=service.link(key,read['sha256'],cid,'native','1'*32);read=service.transition(key,read['sha256'],cid,'COMPLETED');assert read['project']['campaigns'][0]['status']=='COMPLETED'
 with pytest.raises(ValueError):service.propose(key,read['sha256'],cid,'initial')


def test_real_browser_json_numeric_roundtrip_preserves_identity_and_drops_review(service,read,config):
 read,cid=create(service,read,config);m=repro.export(service,read['project']['id'])
 # Equivalent to JSON.parse -> JSON.stringify: whole doubles, exponent spellings and -0 normalize.
 def browser(v):
  if isinstance(v,float) and v.is_integer():return int(v)
  if isinstance(v,dict):return {k:browser(x) for k,x in v.items()}
  if isinstance(v,(tuple,list)):return [browser(x) for x in v]
  return v
 actual=json.loads(json.dumps(browser(m)));assert repro.validate_manifest(service,actual)==actual
 imported=repro.import_manifest(service,actual);assert imported['project']['campaigns'][0]['batches'][0]['status']=='AWAITING_REVIEW'
 assert repro.compare(service,m,actual)['status']=='IDENTICAL_CONFIGURATION_AND_EVIDENCE'
 assert c.data_digest({'x':4.0,'z':-0.0})==c.data_digest({'x':4,'z':0})
 assert c.data_digest({'x':True})!=c.data_digest({'x':1})
 assert c.data_digest({'x':'1'})!=c.data_digest({'x':1})
