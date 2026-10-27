"""Saved real native evidence and GET-only workspace integration, no rollout/model."""
import copy,json
from pathlib import Path
import pytest
from ide_api.workspace import SealedEvidence,rover_snapshot,current_snapshot,bootstrap,SEAL
from ide_api.engineering import EngineeringService
from core.simulation import ROOT
from engineering.project import new_project,identity
from physics.contracts import digest
from workspace.data import EvidenceError


def test_real_historical_rover_snapshots_keep_separate_fail_pass_and_empty_head(monkeypatch):
    def forbidden(*a,**kw):raise AssertionError('Review cannot execute physics/model/apply')
    monkeypatch.setattr('world.simulation.run',forbidden)
    monkeypatch.setattr('world.simulation.verify',forbidden)
    monkeypatch.setattr(EngineeringService,'_commit',forbidden)
    before=(ROOT/'artifacts/phase18e_6/20261026/live_project/head.json').read_bytes()
    b=rover_snapshot();assert b['project']['revision']==0 and not b['project'].get('shape_specs')
    old,new=b['runs'];assert old['verification']['status']=='FAIL' and new['verification']['status']=='PASS'
    assert old['verification']['signed_forward_displacement_m']==pytest.approx(-.018516035883634246,abs=1e-15)
    assert new['verification']['signed_forward_displacement_m']==pytest.approx(.018515946952333998,abs=1e-15)
    assert not old['verification']['checks']['signed_forward_displacement']
    assert all(new['verification']['checks'].values())
    assert old['proposal']['proposal_id']!=new['proposal']['proposal_id']
    assert old['provenance']['phase']=='18E.5' and new['provenance']['phase']=='18E.7'
    assert new['provenance']['api_cost_usd']=='0.0190800'
    assert len(old['native']['result']['samples'])==len(new['native']['result']['samples'])==201
    assert old['native']['result']['trajectory_sha256']!=new['native']['result']['trajectory_sha256']
    assert all(r['application_status']=='PROPOSED_NOT_APPLIED' for r in b['runs'])
    assert not b['editable'] and b['historical'] and 'UNBOUND' in b['circuit_binding']
    assert before==(ROOT/'artifacts/phase18e_6/20261026/live_project/head.json').read_bytes()


def test_historical_seal_missing_modified_or_unlisted_is_not_substituted(tmp_path):
    with pytest.raises(EvidenceError):rover_snapshot(tmp_path)
    f=tmp_path/SEAL;f.parent.mkdir(parents=True);f.write_text('{}')
    with pytest.raises(ValueError,match='seal mismatch'):rover_snapshot(tmp_path)
    evidence=SealedEvidence()
    with pytest.raises(ValueError,match='not in'):evidence.read('../.env')
    # Redirect one sealed read to a disposable copy with an altered receipt.
    name='artifacts/phase18e_6/20261026/live_execution/api_cost_ledger.json'
    evidence.root=tmp_path;f=tmp_path/name;f.parent.mkdir(parents=True,exist_ok=True);f.write_text('{}')
    with pytest.raises(ValueError,match='bytes differ'):evidence.read(name)


def test_current_backend_project_not_historical_default_and_review_does_not_mutate(tmp_path):
    service=EngineeringService(tmp_path/'current',initial_project=new_project())
    class IDE:engineering=service
    head=service.current();before=(service.root/'head.json').read_bytes()
    b=bootstrap(IDE());s=b['snapshot']
    assert s['key']=='current' and s['project']==head and s['project_sha256']==identity(head)
    assert s['runs']==[] and not s['historical'] and s['editable']
    assert 'UNBOUND_REFERENCE' in s['circuit_binding']
    assert not b['policy']['application'] and b['policy']['new_api_calls']==0
    assert before==(service.root/'head.json').read_bytes()
    with pytest.raises(ValueError,match='Unknown workspace'):bootstrap(IDE(),'../../.env')


def test_real_workspace_http_is_read_only_and_exact_query(http,monkeypatch):
    # Reuse the repository's real loopback client fixture.
    client,server=http
    r=client.get('/api/workspace',params={'project':'rover'});assert r.status_code==200,r.text
    assert r.json()['snapshot']['runs'][0]['verification']['status']=='FAIL'
    assert client.get('/api/workspace',params={'project':'../.env'}).status_code==400
    assert client.get('/api/workspace',params={'project':'rover','extra':'x'}).status_code==400
    assert client.post('/api/workspace',json={'project':'rover'}).status_code==404
    assert server.jobs=={}

# Standard-library real HTTP fixtures; no transport mocking for the API assertions.
from tests.test_ide_api import service,http


def test_current_saved_native_run_retains_original_input_and_only_claims_replay(tmp_path):
    original=copy.deepcopy(rover_snapshot()['runs'][1]['native']['result'])
    original['base_project_sha256']='a'*64 # Existing EngineeringService.simulate storage binding; native states unchanged.
    # Reuse actual saved states, not synthetic physics; bind to a disposable project reference.
    service=EngineeringService(tmp_path/'reference',initial_project=new_project())
    ref=service.measured.put(original);p=service.current();p['evidence_refs']=[{'id':'saved_real_run','kind':'world','sha256':ref,'base_project_sha256':'a'*64}]
    service._commit(p)
    class IDE:engineering=service
    before=(service.root/'head.json').read_bytes();b=current_snapshot(IDE());r=b['runs'][0]
    assert r['native']['result']==original
    assert r['input_project_sha256']=='a'*64 and r['verification']['status']=='REPLAY_PASS'
    assert 'no device-specific' in r['verification']['summary']
    assert r['proposal'] is None and before==(service.root/'head.json').read_bytes()
    (service.measured.root/(ref+'.json')).unlink()
    b=current_snapshot(IDE());assert b['runs']==[] and 'missing or invalid' in b['unavailable'][0]
    assert str(tmp_path) not in b['unavailable'][0]


def test_stale_saved_proposal_cannot_be_presented_as_current_change(tmp_path):
    service=EngineeringService(tmp_path/'current',initial_project=new_project())
    from engineering.store import Store
    q=copy.deepcopy(rover_snapshot()['runs'][1]['proposal']);q['base_project_sha256']='a'*64
    key=Store(service.root/'assembly_proposals').put({k:v for k,v in q.items() if k!='proposal_id'})
    record=Store(service.root/'assembly_reviews').put({'proposal_id':key,'origin':'GENUINE_PROVIDER_RESPONSE'})
    (service.root/'assembly_live_review.json').write_text(json.dumps({'sha256':record}))
    class IDE:engineering=service
    before=(service.root/'head.json').read_bytes();b=current_snapshot(IDE());assert b['proposals']==[] and 'unavailable or invalid' in b['unavailable'][0]
    assert before==(service.root/'head.json').read_bytes()
