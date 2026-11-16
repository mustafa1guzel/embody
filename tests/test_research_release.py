"""Release bookkeeping tests, with no historical counts manufactured."""
from copy import deepcopy
import pytest
from ide_api.research.artifacts import ArtifactStore,RECEIPT,byte_hash,now
from tools.research_release_verify import parse_counts

def test_actual_output_count_parser():
 assert parse_counts('= 165 passed, 2 failed, 3 skipped, 14 deselected in 1s =','backend')=={'pass':165,'fail':2,'skip':3,'deselected':14,'errors':0}
 assert parse_counts('2 errors in 1s','backend')['errors']==2
 assert parse_counts('Tests  143 passed (143)','frontend')['pass']==143
 assert parse_counts('interrupted before summary','frontend')['pass'] is None

def test_receipt_completed_failure_retained_not_promoted(tmp_path):
 store=ArtifactStore(tmp_path);raw=b'actual completed failure';time=now()
 receipt={'format':RECEIPT,'id':'a'*32,'command':['python','-V'],'started_utc':time,'completed_utc':time,'source_identity':'a'*64,'base_commit':'b'*40,'versions':{'python':'local'},'exit_status':1,'counts':{k:0 for k in ('pass','fail','skip','deselected','errors')},'stage':'backend','status':'FAIL','guard_counters':None,'limits':{},'limitations':[],'log_sha256':byte_hash(raw)}
 store.receipt(receipt,raw);assert (tmp_path/'receipts'/('a'*32+'.json')).exists()
 bad=deepcopy(receipt);bad['status']='PASS'
 with pytest.raises(ValueError):store.receipt(bad,raw)
 bad=deepcopy(receipt);bad['log_sha256']='c'*64
 with pytest.raises(ValueError):store.receipt(bad,raw)

def test_denial_entrypoint_records_attempt_before_refusal():
 from tools import non_native_guards as guards
 original=guards.COUNTERS;guards.COUNTERS={'test':0}
 try:
  with pytest.raises(AssertionError):guards.deny('test')()
  assert guards.COUNTERS['test']==1
 finally:guards.COUNTERS=original

def test_native_preparation_tool_has_no_execution_action_and_checks_source_drift(tmp_path,monkeypatch):
 from pathlib import Path
 from tools import research_native_preflight as preflight
 original=preflight.ROOT
 monkeypatch.setattr(preflight,'ROOT',tmp_path);(tmp_path/'requirements.txt').write_bytes((original/'requirements.txt').read_bytes())
 monkeypatch.setattr(preflight,'sources',lambda:{'synthetic_preparation_fixture.py':'a'*64})
 prepared=preflight.prepare();raw=(tmp_path/prepared['relative_path']).read_bytes()
 from ide_api.research.artifacts import finite_json
 value=finite_json(raw,120000);result=preflight.check(value)
 assert result['native_steps']==0 and not result['execution_authorized']
 assert result['approval']=='MISSING_EXPLICIT_USER_APPROVAL'
 assert value['definition']['limits']['maximum_integration_steps']==3600
 assert value['definition']['campaign_planning_ceiling']['total_cases']==8
 monkeypatch.setattr(preflight,'sources',lambda:{'synthetic_preparation_fixture.py':'b'*64})
 with pytest.raises(ValueError,match='source/base'):preflight.check(value)
 value['sha256']='0'*64
 with pytest.raises(ValueError,match='consent identity'):preflight.check(value)
