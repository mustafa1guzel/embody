"""Real isolated trusted native physics; no model, VM or authoritative apply."""
import copy,json
import pytest
import numpy as np
from ide_api.ramp import RampService,DEFAULT,CONTRACT,config,measure
from ide_api.engineering import EngineeringService
from engineering.actions import execute_copy,check_operations
from engineering.project import identity,new_project
from engineering.assembly_rover import structural

@pytest.mark.parametrize('field,value',[('angle_deg',31),('angle_deg',-1),('angle_deg',True),('angle_deg',float('nan')),('angle_deg',float('inf')),('length_m',.59),('width_m',.24),('thickness_m',0),('friction',.69),('friction',2.01)])
def test_unsupported_config_rejects_before_project_creation(tmp_path,field,value):
 service=RampService(tmp_path);bad={**DEFAULT,field:value}
 with pytest.raises(ValueError):service.create(bad)
 assert not (tmp_path/'projects').exists()

def test_exact_config_and_static_surface_operation():
 for v in ({}, {**DEFAULT,'extra':1}):
  with pytest.raises(ValueError):config(v)
 p=new_project();before=copy.deepcopy(p)
 updated=execute_copy(p,[{'kind':'set_static_surface_friction','target':'floor','friction':[.9,.005,.0001]}])
 assert p==before and updated['world']['objects'][0]['contact']['friction']==[.9,.005,.0001]
 for friction in ([True,.005,.0001],[.5,.005],[float('nan'),.005,.0001]):
  with pytest.raises(ValueError):execute_copy(p,[{'kind':'set_static_surface_friction','target':'floor','friction':friction}])
 p['world']['objects'][0]['contact']['enabled']=False
 with pytest.raises(ValueError,match='enabled fixed'):execute_copy(p,[{'kind':'set_static_surface_friction','target':'floor','friction':[.9,.005,.0001]}])

@pytest.fixture(scope='module')
def native(tmp_path_factory):
 service=RampService(tmp_path_factory.mktemp('ramp_native'));cases={}
 for angle in (0,5,30):
  v=service.create({**DEFAULT,'angle_deg':angle});assert v['status']=='NOT_RUN' and v['proposal']['validation']['simulation'].startswith('NOT_RUN')
  folder=service.root/v['folder'];head=(folder/'review/head.json').read_bytes()
  r=service.run(v['id']);assert head==(folder/'review/head.json').read_bytes();cases[angle]=r
 return service,cases

@pytest.mark.parametrize('angle,outcome,status',[(0,'TRAVERSED_LEVEL_RAMP','PASS'),(5,'CLIMBED','PASS'),(30,'MOVED_DOWNHILL','FAIL')])
def test_real_bounded_outcomes_and_fresh_replay(native,angle,outcome,status):
 service,cases=native;v=cases[angle];r=v['result'];m=r['measurements']
 assert m['outcome']==outcome and m['status']==status and r['native']['independent_verification']['status']=='PASS'
 assert len(r['native']['samples'])==201 and r['native']['independent_verification']['fresh_native_integration_steps']==200
 assert all(m['wheel_ramp_pair_observations'].values()) and not m['unexpected_contacts'] and m['maximum_actuator_force_nm']==pytest.approx(.012)
 assert m['measured_contact_sliding_friction_range']==pytest.approx([.9,.9])
 assert m==json.loads(json.dumps(measure(r['native'],v['roles'],v['parameters'])))
 assert v['application_allowed'] is False and r['application_status']=='PROPOSED_NOT_APPLIED'
 if angle==5:assert m['signed_progress_m']>=.005 and m['height_change_m']>0
 if angle==30:assert m['signed_progress_m']<-.005 and m['height_change_m']<0 and m['checks']['fresh_replay']
 # The original flat predicate correctly refuses the added ramp and tilted chassis.
 with pytest.raises(ValueError):structural(v['proposal']['proposed_project'],v['roles'])

def test_native_collider_and_typed_reconstruction(native):
 service,cases=native;v=cases[5];q=v['proposal'];s=EngineeringService(service.root/v['folder']/'review');before=s.current();p,checks=s.preview(before,q['operations'])
 assert p==q['proposed_project'] and identity(before)==v['head_sha256']
 assert v['geometry']['status']=='REAL_STATIC_NATIVE_COLLIDER'
 np.testing.assert_allclose(v['geometry']['normal_world'],[-np.sin(np.deg2rad(5)),0,np.cos(np.deg2rad(5))],atol=1e-12)
 assert next(o for o in p['world']['objects'] if o['id']=='test_ramp')['mass_kg']==0
 assert json.loads((service.root/v['folder']/'construction.json').read_text())['construction_head_unchanged']

def test_reserved_run_cannot_repeat_native_execution(native,monkeypatch):
 service,cases=native;monkeypatch.setattr('ide_api.ramp.run_world',lambda *a:pytest.fail('Reserved fixture cannot run again'))
 with pytest.raises(FileExistsError):service.run(cases[5]['id'])

def test_corrupt_native_force_and_contact_evidence_rejected(native):
 _,cases=native;v=cases[5]
 for field in ('generalized_force','contacts','model_xml'):
  r=copy.deepcopy(v['result']['native'])
  if field=='model_xml':r[field]+=' '
  elif field=='contacts':r['samples'][0][field]+=1
  else:r['samples'][0][field][0]+=.1
  from physics.contracts import digest
  r['trajectory_sha256']=digest(r['samples'])
  with pytest.raises((ValueError,AssertionError)):measure(r,v['roles'],v['parameters'])

def test_source_and_head_drift_block_before_new_rollout(native,monkeypatch):
 service,cases=native
 monkeypatch.setattr('ide_api.ramp.source_identity',lambda:{})
 with pytest.raises(ValueError,match='source'):service.run(cases[0]['id'])

from tests.test_ide_api import service,http

def test_ramp_http_scope_and_origin_reject_before_mutation(http,tmp_path):
 client,server=http;server.ide._ramp=RampService(tmp_path)
 assert client.post('/api/ramp-review',json={'parameters':DEFAULT,'apply':True}).status_code==400
 assert client.post('/api/ramp-review',json={'parameters':DEFAULT},headers={'Origin':'https://evil.invalid'}).status_code==403
 assert client.post('/api/ramp-test',json={'id':'f'*64,'path':'anything'}).status_code==400
 assert not (tmp_path/'projects').exists()
