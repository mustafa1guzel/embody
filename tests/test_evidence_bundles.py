"""Actual pinned-reader readback + synthetic security fixtures; zero new integration."""
import base64,copy,json
from pathlib import Path
import pytest
from ide_api import rail_sweeps as rail
from ide_api.experiment_designer import ExperimentDesigner
from ide_api.research.bundles import EvidenceBundles
from ide_api.research.artifacts import *
from ide_api.research import evidence,readback

@pytest.fixture
def bundles(tmp_path):return EvidenceBundles(ExperimentDesigner(rail.RailSweeps(tmp_path/'native'),tmp_path/'designer'),tmp_path/'store')
@pytest.fixture
def captured(bundles):
 summary=evidence.load(bundles.designer,'recorded','portable_rail_study');cid=summary['records'][0]['id']
 return bundles.capture('recorded','portable_rail_study',[cid])

def test_genuine_reader_capture_independent_readback_portable_roundtrip(bundles,captured,tmp_path):
 assert captured['verified_local'] and captured['availability']=='VERIFIED_HISTORICAL'
 assert captured['case_count']==1 and captured['readback']=='PASS'
 package=bundles.store.package(captured['id']);checked=ArtifactStore.verify_package(json.loads(json.dumps(package)))
 assert checked['status']=='INTEGRITY_VALID_EXTERNAL_UNVERIFIED' and checked['readback']['cases']==1
 assert checked['readback']['native_steps']==0
 other=ArtifactStore(tmp_path/'external');result=other.import_package(package)
 assert not result['execution_authorized'] and not result['local_attestation_created']
 assert other.verify(result['id'],external=True)['availability']=='EXTERNAL_UNVERIFIED'
 assert not (other.root/'attestations').exists()
 assert b'/Users/' not in canonical(package)

def test_missing_corrupt_raw_downgrades_without_deleting_bundle(bundles,captured):
 d=next(a for a in captured['manifest']['artifacts'] if a['name'].endswith('telemetry.json'));p=bundles.store.root/'objects'/d['sha256'];raw=p.read_bytes();p.unlink()
 assert bundles.inspect(captured['id'])['availability']=='PARTIALLY_AVAILABLE'
 with pytest.raises(ValueError):bundles.summary(captured['id'])
 p.write_bytes(raw+b' ')
 assert bundles.inspect(captured['id'])['availability']=='INTEGRITY_FAILED'
 assert (bundles.store.root/'bundles'/(captured['id']+'.json')).exists()

def test_package_tampering_duplicates_and_absent_independent(bundles,captured):
 package=bundles.store.package(captured['id'])
 def reseal(v):v['package_sha256']=data_digest({k:x for k,x in v.items() if k!='package_sha256'});return v
 bad=copy.deepcopy(package);bad['artifacts'][0]['data_base64']='e30='
 with pytest.raises(ValueError):ArtifactStore.verify_package(reseal(bad))
 bad=copy.deepcopy(package);bad['artifacts'][0]=bad['artifacts'][1]
 with pytest.raises(ValueError):ArtifactStore.verify_package(reseal(bad))
 checked=ArtifactStore.verify_package(package);del checked['decoded'][next(n for n in checked['decoded'] if n.endswith('independent.json'))]
 from ide_api.research.bundles import package_readback
 with pytest.raises((ValueError,KeyError)):package_readback(checked['manifest'],checked['decoded'])

@pytest.mark.parametrize('value',['../escape','/etc/passwd','a//b','a/./b','a/../b','a\\b',''])
def test_relative_path_rejection(value):
 with pytest.raises(ValueError):relative(value)

@pytest.mark.parametrize('raw',[b'{"a":1,"a":2}',b'{"a":NaN}',b'{"a":1e999}',b'[] trailing'])
def test_strict_finite_json(raw):
 with pytest.raises(ValueError):finite_json(raw)

def test_write_once_read_bounds_and_symlink_escape(tmp_path):
 store=ArtifactStore(tmp_path/'store');store.write_once('objects/first',b'original');store.write_once('objects/first',b'original')
 with pytest.raises(ValueError):store.write_once('objects/first',b'new')
 with pytest.raises(ValueError):store.read('objects/first',2)
 outside=tmp_path/'outside';outside.mkdir();(store.root/'escape').symlink_to(outside,target_is_directory=True)
 with pytest.raises((ValueError,OSError)):store.write_once('escape/file',b'bad')
 (store.root/'objects'/'link').symlink_to(store.root/'objects'/'first')
 with pytest.raises(OSError):store.read('objects/link')
 assert not list(outside.iterdir())

def test_retention_quotas_refuse_no_pruning(tmp_path):
 store=ArtifactStore(tmp_path/'store');(store.root/'uploads').mkdir(parents=True)
 for i in range(8):store.write_once('uploads/'+str(i)+'/request.json',b'{}')
 with pytest.raises(ValueError):store.begin_upload(1,'a'*64,'verify')
 assert len(list((store.root/'uploads').glob('*/request.json')))==8

def test_real_package_bounded_chunk_verification_and_idempotence(bundles,captured):
 raw=canonical(bundles.store.package(captured['id']));request=bundles.store.begin_upload(len(raw),byte_hash(raw),'verify')
 with pytest.raises(FileNotFoundError):bundles.store.finish_upload(request['id'])
 for index in range(request['parts']):bundles.store.upload_chunk(request['id'],index,base64.b64encode(raw[index*49152:(index+1)*49152]).decode())
 out=bundles.store.finish_upload(request['id']);assert out==bundles.store.finish_upload(request['id'])
 assert out['status']=='INTEGRITY_VALID_EXTERNAL_UNVERIFIED' and out['readback']['native_steps']==0
 with pytest.raises(ValueError):bundles.store.upload_chunk(request['id'],0,'')

def test_saved_metrics_threshold_entry_and_suffix_are_distinct():
 samples=[{'time':i*.005,'position':i*.001,'velocity':.01 if i in (10,599,600) else .1,'wall_clearance':.2,'generalized_actuator_force':-2.,'wall_collision':i in (2,3,8)} for i in range(601)]
 result=readback.metrics(samples,rail.DEFAULT_CRITERIA,{'timestep_s':.005,'duration_s':3.})
 assert result['first_speed_threshold_entry_s']==.05 and result['sustained_sampled_suffix_start_s']==2.995
 assert result['metrics']['wall_contact_samples']==3 and result['metrics']['wall_contact_episodes']==2
 assert result['metrics']['absolute_impulse_ns']==pytest.approx(6.) and result['metrics']['signed_work_j']<0
 samples[0]['time']=.1
 with pytest.raises(ValueError):readback.metrics(samples,rail.DEFAULT_CRITERIA,{'timestep_s':.005,'duration_s':3.})

def test_replay_requires_actual_saved_primary_and_fresh_samples():
 with pytest.raises(KeyError):readback.native_replay({'samples':[],'trajectory_sha256':rail.digest([])})

def test_unknown_raw_reference_remains_missing(bundles):
 assert bundles.catalog()['historical_missing'][0]['availability']=='MISSING'
 assert bundles.inspect('a'*32)['availability']=='MISSING'

def test_bundle_finding_loses_verified_status_when_required_raw_disappears(bundles,captured,tmp_path):
 from ide_api.research.store import Research
 from test_research_workflow import config as config_fixture
 research=Research(bundles.designer,tmp_path/'research');research._bundles=bundles
 read=research.new('Evidence dependency','Does a finding retain raw support?',rail.EXPERIMENT)
 cfg={'experiment_id':rail.EXPERIMENT,'controller_id':rail.CONTROLLER,'objective':'Dependency test','type':'adaptive_1d','axes':[{'parameter':'gap_m','minimum':1.4,'maximum':1.6}],'fixed_parameters':{'mass_kg':4.,'speed_mps':1.2,'force_n':2.,'gap_m':1.49},'criteria':rail.DEFAULT_CRITERIA,'strategy':'uniform','count':3,'seed':1,'minimum_spacing':.001,'proposal_budget':8,'hypothesis_ids':[]}
 read=research.campaign(read['project']['id'],read['sha256'],cfg);key=read['project']['id'];cid=read['project']['campaigns'][0]['id']
 read=research.link(key,read['sha256'],cid,'bundle',captured['id']);view=research.view(key,cid);summary=view['summaries'][0]
 read=research.finding(key,read['sha256'],cid,summary['summary_sha256'],summary['facts'][0]['id']);assert research.view(key,cid)['findings'][0]['status']=='VERIFIED'
 d=next(d for d in captured['manifest']['artifacts'] if d['name'].endswith('telemetry.json'));(bundles.store.root/'objects'/d['sha256']).unlink()
 view=research.view(key,cid);assert view['findings'][0]['status']=='UNVERIFIED' and view['findings'][0]['fact'] is None
 assert view['evidence_completeness']['unknown_missing_case_count'] and view['evidence_completeness']['incomplete_findings']==1
 assert len(research.read(key)['project']['findings'])==1
