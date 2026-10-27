"""Approval and transaction controls; positive safety/apply paths use real VM measurements."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import time

import pytest
from streamlit.testing.v1 import AppTest

from core.agent.vm_backend import AppleVMBackend, IsolationBlocked
from core.agent.credentials import CredentialsMissing
from core.simulation import ROOT
from workspace.data import default_recording
from workspace.workflow import Workflow, WorkflowBlocked, MANAGED_TARGET


def project_copy(target):
    target.mkdir()
    for name in ('core','configs','robot'):
        shutil.copytree(ROOT/name,target/name,ignore=shutil.ignore_patterns('__pycache__','.approved-controller.lock','approved_controller.py'))
    return target


def create(service,variant='attempt_2'):
    r=default_recording();p=r.proposal(variant)
    return service.create(source=p['source'],explanation='Exact recorded GPT proposal, reviewed in a developer test',
        expected_original_sha256=p['validation']['original_sha256'],provenance=p['provenance'])


@pytest.fixture
def service(tmp_path):
    return Workflow(project_copy(tmp_path/'project'),tmp_path/'reviews')


def test_new_review_is_not_freshly_verified_and_rejection_is_terminal(service):
    review=create(service);s=service.get(review)
    assert s['status']=='REVIEWED' and s['verification'] is None
    assert not s['permanent_application_approved']
    with pytest.raises(WorkflowBlocked,match='approval'):service.verify(review)
    service.reject(review)
    assert service.get(review)['status']=='REJECTED'
    with pytest.raises(WorkflowBlocked):service.verify(review,approved=True)
    assert not (service.root/MANAGED_TARGET).exists()


def test_invalid_source_stale_hash_and_stale_context_block(service):
    original=(service.root/'robot/controller.py').read_text()
    review=service.create(source=original+'\ndef helper():\n    pass\n',explanation='Developer invalid fixture',
        expected_original_sha256=hashlib.sha256(original.encode()).hexdigest(),provenance={'test':True})
    assert service.get(review)['status']=='INVALID'
    with pytest.raises(WorkflowBlocked):service.verify(review,approved=True)
    review=create(service)
    (service.root/'configs/scenarios.json').write_text('{}')
    assert service.verify(review,approved=True)['status']=='BLOCKED'
    assert 'stale' in service.get(review)['reason']


def test_expired_missing_vm_and_wrong_backend_fail_closed(service,monkeypatch):
    review=create(service)
    def expired(*a):raise IsolationBlocked('Containment evidence expired; repeat probes')
    monkeypatch.setattr(AppleVMBackend,'preflight',expired)
    s=service.verify(review,approved=True)
    assert s['status']=='BLOCKED' and s['verification'] is None and 'expired' in s['reason']
    review=create(service)
    assert service.verify(review,approved=True,backend=object())['status']=='BLOCKED'


def test_source_tampering_and_unknown_ids_fail_closed(service):
    review=create(service)
    (service.sessions/review/'proposed_source.txt').write_text('changed')
    with pytest.raises(WorkflowBlocked,match='integrity'):service.get(review)
    for bad in ('../escape','/etc/passwd','x'*32):
        with pytest.raises(WorkflowBlocked):service.get(bad)


def test_managed_symlink_and_external_drift_not_overwritten(service,tmp_path):
    target=service.root/MANAGED_TARGET
    private=tmp_path/'private';private.write_text('Dummy private file')
    target.symlink_to(private)
    with pytest.raises(WorkflowBlocked,match='link'):create(service)
    assert private.read_text()=='Dummy private file'


def test_missing_api_credentials_are_an_explicit_non_generation_state(monkeypatch):
    import core.agent.credentials as c
    from workspace.workflow_ui import credentials_status
    def missing():raise CredentialsMissing('not configured')
    monkeypatch.setattr(c,'read_openai_api_key',missing)
    assert credentials_status().startswith('BLOCKED: API credentials')


def test_interactive_ui_review_reject_and_verification_consent(service,monkeypatch):
    import workspace.workflow_ui as ui
    monkeypatch.setattr(ui,'workflow_service',lambda:service)
    at=AppTest.from_file(ROOT/'streamlit_app.py',default_timeout=30).run()
    at.radio(key='workspace_mode').set_value('Interactive workflow').run()
    assert not at.exception
    assert 'review_id' not in at.session_state
    at.button(key='review_candidate').click().run()
    review=at.session_state['review_id']
    assert service.get(review)['verification'] is None
    at.button(key='verify_candidate').click().run()
    assert any('Explicit verification approval' in e.value for e in at.error)
    assert not (service.root/MANAGED_TARGET).exists()
    at.button(key='reject_candidate').click().run()
    assert service.get(review)['status']=='REJECTED'
    assert not any(b.key=='apply_candidate' for b in at.button)
    assert not at.exception


@pytest.fixture(scope='module')
def verified_project(tmp_path_factory):
    if os.environ.get('EMBODY_RUN_VM_TESTS')!='1':pytest.skip('Requires approved real Apple VM tests')
    backend=AppleVMBackend()
    try:backend.preflight()
    except IsolationBlocked:
        from core.day4b1 import qualify,OUTPUT
        assert qualify(output=OUTPUT/('day6_qualification_'+str(time.time_ns())))['status']=='PASS'
    directory=tmp_path_factory.mktemp('day6_real_workflow')
    project=project_copy(directory/'project')
    service=Workflow(project,directory/'reviews')
    review=create(service)
    state=service.verify(review,approved=True,backend=backend)
    assert state['status']=='VERIFIED',state.get('reason')
    assert set(state['verification']['scenario_results'])=={'A','B','C'}
    return service,review


@pytest.fixture
def verified(verified_project,tmp_path):
    original,review=verified_project
    project=project_copy(tmp_path/'project')
    shutil.copytree(original.sessions,tmp_path/'reviews')
    return Workflow(project,tmp_path/'reviews'),review


@pytest.mark.live_vm
def test_actual_candidate_measurements_and_restart(verified):
    service,review=verified;s=service.checked_verification(review)
    assert Workflow(service.root,service.sessions).get(review)==s
    for result in s['verification']['scenario_results'].values():
        assert result['physical_safety_status']==result['independent_verification']=='PASS'
        assert result['first_wall_contact'] is None and result['minimum_clearance_m']>=.05
        assert result['final_speed_ms']<.03
    assert not (service.root/MANAGED_TARGET).exists()


@pytest.mark.live_vm
def test_apply_requires_separate_consent_and_rollback_restores_absence(verified):
    service,review=verified;before=(service.root/'robot/controller.py').read_bytes()
    state=service.get(review)
    with pytest.raises(WorkflowBlocked,match='confirmation'):service.apply(review,confirmation='VERIFY')
    applied=service.apply(review,confirmation='APPLY '+state['source_sha256'])
    assert applied['status']=='APPLIED'
    assert hashlib.sha256((service.root/MANAGED_TARGET).read_bytes()).hexdigest()==state['source_sha256']
    with pytest.raises(WorkflowBlocked,match='confirmation'):service.rollback(review,confirmation='')
    assert service.rollback(review,confirmation='REVERT '+review)['status']=='REVERTED'
    assert not (service.root/MANAGED_TARGET).exists()
    assert (service.root/'robot/controller.py').read_bytes()==before


@pytest.mark.live_vm
def test_apply_failure_is_recoverable_and_preserves_original(verified,monkeypatch):
    service,review=verified;s=service.get(review)
    def failure(*a):raise OSError('Developer injected atomic-rename failure')
    monkeypatch.setattr(service,'_replace',failure)
    with pytest.raises(OSError):service.apply(review,confirmation='APPLY '+s['source_sha256'])
    assert service.get(review)['status']=='APPLYING'
    assert not (service.root/MANAGED_TARGET).exists()
    assert service.rollback(review,confirmation='REVERT '+review)['status']=='REVERTED'


@pytest.mark.live_vm
def test_verified_evidence_tamper_and_managed_drift_block_apply(verified):
    service,review=verified;s=service.get(review)
    (service.root/MANAGED_TARGET).write_text('external edit')
    with pytest.raises(WorkflowBlocked,match='changed since review'):service.apply(review,confirmation='APPLY '+s['source_sha256'])
    (service.root/MANAGED_TARGET).unlink()
    relative=next(iter(s['verification_inventory']))
    (service.sessions/review/relative).write_text('changed')
    with pytest.raises(WorkflowBlocked,match='integrity'):service.apply(review,confirmation='APPLY '+s['source_sha256'])


@pytest.mark.live_vm
def test_corrupt_backup_and_external_edits_block_rollback(verified):
    service,review=verified;s=service.get(review)
    service.apply(review,confirmation='APPLY '+s['source_sha256'])
    (service.root/MANAGED_TARGET).write_text('external edit')
    with pytest.raises(WorkflowBlocked,match='externally'):service.rollback(review,confirmation='REVERT '+review)


@pytest.mark.live_vm
def test_rollback_restores_previous_managed_controller(verified_project,tmp_path):
    old,old_id=verified_project
    project=project_copy(tmp_path/'project')
    previous=b'# Existing managed developer fixture; never executed\n'
    (project/MANAGED_TARGET).write_bytes(previous)
    service=Workflow(project,tmp_path/'reviews');review=create(service)
    # Real fresh verification with the existing managed file present; no receipt fabrication.
    s=service.verify(review,approved=True)
    assert s['status']=='VERIFIED'
    service.apply(review,confirmation='APPLY '+s['source_sha256'])
    backup=service.sessions/review/'previous_controller.backup'
    assert backup.read_bytes()==previous and backup.stat().st_mode & 0o077==0
    backup.write_bytes(b'developer backup-corruption probe')
    with pytest.raises(WorkflowBlocked,match='backup hash'):
        service.rollback(review,confirmation='REVERT '+review)
    backup.write_bytes(previous)  # restore the known developer fixture, never alter model source
    assert service.rollback(review,confirmation='REVERT '+review)['status']=='REVERTED'
    assert (project/MANAGED_TARGET).read_bytes()==previous


@pytest.mark.live_vm
def test_ui_actual_apply_rollback_and_fresh_result_views(verified,monkeypatch):
    import workspace.workflow_ui as ui
    service,review=verified;monkeypatch.setattr(ui,'workflow_service',lambda:service)
    at=AppTest.from_file(ROOT/'streamlit_app.py',default_timeout=30)
    at.session_state['review_id']=review
    at.run();at.radio(key='workspace_mode').set_value('Interactive workflow').run()
    assert not at.exception and not at.error
    at.button(key='show_results').click().run()
    assert len(at.get('vega_lite_chart'))==2
    at.text_input(key='apply_confirmation').set_value('APPLY '+service.get(review)['source_sha256'])
    at.button(key='apply_candidate').click().run()
    assert service.get(review)['status']=='APPLIED' and not at.exception, [e.value for e in at.error]
    at.text_input(key='revert_confirmation').set_value('REVERT '+review)
    at.button(key='rollback_candidate').click().run()
    assert service.get(review)['status']=='REVERTED' and not at.exception


@pytest.mark.live_vm
def test_measured_failed_candidate_cannot_be_applied(service):
    review=create(service,'attempt_1')
    s=service.verify(review,approved=True)
    assert s['status']=='FAILED'
    assert s['verification']['verification_execution']=='PASS'
    assert s['verification']['physical_safety_status']=='FAIL'
    with pytest.raises(WorkflowBlocked,match='physically verified'):
        service.apply(review,confirmation='APPLY '+s['source_sha256'])
    assert not (service.root/MANAGED_TARGET).exists()
