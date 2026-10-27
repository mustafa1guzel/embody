"""Actual empty-head reconstruction, real native preview and explicit commit gates."""
from pathlib import Path
import copy,json,shutil
import pytest
from engineering.verified_construction import VerifiedConstruction,PHASE17
from engineering.project import identity
from robustness.contracts import file_hash

@pytest.fixture
def review_service(tmp_path):
    original=json.loads((PHASE17/'selection.json').read_text())['construction_proposal']
    source=PHASE17/'review_registry/projects'/original['project_id'];target=tmp_path/'project'
    shutil.copytree(source,target,ignore=shutil.ignore_patterns('*.lock'))
    return VerifiedConstruction(tmp_path/'review',project_root=target)

def prepare(service):
    b=service.bootstrap();return service.prepare(b['project_sha256'],b['project']['revision'])

def test_new_construction_uses_actual_empty_base_and_preserves_verified_model(review_service):
    service=review_service;before=service.project.current();p=prepare(service)
    assert p['base_revision']==0 and p['base_sha256']==identity(before)!=p['old_changeset_base_sha256']
    assert p['proposed_project']['revision']==1 and len(p['batches'])==11
    old=json.loads((PHASE17/'selection.json').read_text())
    assert p['batches'][:10]==old['construction_proposal']['batches'] and p['original_model_intent']==old['model_design_intent']
    assert p['native_model_sha256']=='079f36389952359e8028ca5383c3e4df5047caff96d268a55b91984ee4b0ca80'
    assert p['proposed_project']['circuit']==old['construction_proposal']['proposed_project']['circuit']
    assert service.project.current()==before and p['physics_preflight']['status']=='READY_FOR_NATIVE_PREVIEW'

def test_commit_requires_both_separate_confirmation_and_fresh_native_evidence(review_service):
    s=review_service;p=prepare(s);before=s.project.current()
    with pytest.raises(ValueError,match='human'):s.commit(p['review_id'],p['base_sha256'],0,'')
    with pytest.raises(ValueError,match='Fresh passing'):s.commit(p['review_id'],p['base_sha256'],0,'COMMIT VERIFIED CONSTRUCTION '+p['review_id'])
    assert s.project.current()==before

def test_real_fresh_preview_then_explicit_commit_only_on_disposable_test_copy(review_service):
    s=review_service;p=prepare(s);source_head=PHASE17/'review_registry/projects'/p['project_id']/'head.json';original_hash=file_hash(source_head)
    before=s.project.current();m=s.preview(p['review_id'],p['base_sha256'],0,render_image=False)
    assert m['result']['acceptance']['first_open_s']==pytest.approx(1.755) and all(m['result']['acceptance']['checks'].values())
    assert m['result']['independent_verification']['status']=='PASS' and s.project.current()==before
    committed=s.commit(p['review_id'],p['base_sha256'],0,'COMMIT VERIFIED CONSTRUCTION '+p['review_id'])
    assert committed['project']['revision']==1 and committed['project']['creation']['state']=='BUILT'
    assert len(committed['project']['world']['objects'])==7 and s.project.current()==committed['project']
    assert file_hash(source_head)==original_hash # The actual Phase17 head is never committed by tests.
    assert list((s.root/'decisions').glob('base_head_*.json'))

def test_stale_base_and_implementation_block_before_native_or_commit(review_service,monkeypatch):
    s=review_service;p=prepare(s)
    with pytest.raises(ValueError,match='Stale'):s.prepare('f'*64,0)
    monkeypatch.setattr(s,'_identity',lambda:{'changed':'identity'})
    with pytest.raises(ValueError,match='Stale'):s.preview(p['review_id'],p['base_sha256'],0,render_image=False)
    assert s.project.current()['revision']==0 and not list((s.root/'decisions').iterdir())

def test_tampered_stored_review_rejected(review_service):
    s=review_service;p=prepare(s);altered=copy.deepcopy({k:v for k,v in p.items() if k!='review_id'})
    altered['repair_operations'][0]['mass_kg']=.18;key=s.reviews.put(altered)
    with pytest.raises(ValueError,match='reconstruction'):s.preview(key,p['base_sha256'],0,render_image=False)
    assert s.project.current()['revision']==0
