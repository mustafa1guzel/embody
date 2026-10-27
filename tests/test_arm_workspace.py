"""Offline evidence checks; fresh positive transactions require explicit live_vm scope."""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil

import mujoco
import numpy as np
import pytest

from core.simulation import ROOT
from core.agent.vm_backend import AppleVMBackend
from core.robots.arm import ArmFamily, TARGET
from core.robots.execution import first_run, independent
from workspace.arm_data import ArmRecording, default_arm_recording
from workspace.data import EvidenceError
from workspace.workflow import Workflow, WorkflowBlocked


@pytest.mark.parametrize('scenario',list(ArmFamily(evaluation=True).scenarios))
def test_recorded_arm_states_are_real_and_source_bound(scenario,monkeypatch):
    def forbidden(*a,**k):raise AssertionError('Review must not execute candidate or API')
    monkeypatch.setattr(AppleVMBackend,'controller',forbidden)
    r=default_arm_recording();e=r.experiment(scenario)
    assert e['recorded'] and e['robot_family']=='arm'
    if scenario=='arm_unreachable':
        assert e['scene'] is None
        assert all(t['samples']==[] and t['summary']['task_rejection_verified'] for t in e['variants'].values())
        assert e['context']['analytical_guard']['status']=='PROVEN_INFEASIBLE'
        return
    assert {'link1_box','link2_box','target_marker','tool_marker'} <= {g['name'] for g in e['scene']['geoms']}
    for variant,t in e['variants'].items():
        assert len(t['samples'])==801
        assert t['summary']['physical_safety_status']==('FAIL' if variant=='original' else 'PASS')
        if variant!='original':
            meta=r.json(t['summary']['artifact_references']['telemetry.json'])['metadata']
            assert meta['controller_origin']=='isolated_untrusted_candidate'
        assert t['independent']['verification_execution']=='PASS'
        assert max(t['independent']['max_action_difference'],t['independent']['max_trajectory_difference'])<=1e-10
        s=t['samples'][400]
        assert s['target_error_m']==pytest.approx(np.linalg.norm(np.array(s['end_effector_m'])-e['context']['contract']['target_m']))
        assert max(abs(v) for v in s['generalized_torque_nm'])<=3


def test_genuine_proposal_trace_and_no_holdout_leak():
    r=default_arm_recording();metadata=r.metadata();assert metadata['proposals']==['attempt_1']
    p=r.proposal('attempt_1');assert p['validation']['validation_status']=='VALID'
    assert p['provenance']['kind']=='genuine_api_proposal' and not p['provenance']['operator_modified_source']
    assert p['verification']['physical_safety_status']=='PASS'
    a=metadata['agent'];assert a['status']=='COMPLETED' and len(a['calls'])==15
    assert {call['name'] for call in a['calls']}=={'read_project','get_robot_context','get_world_context','run_simulation','inspect_failure','propose_patch'}
    assert any(c.get('verification_feedback') for c in a['calls'])
    # All model-selected inputs and returned development feedback exclude holdouts.
    text=json.dumps(a)
    assert 'arm_different_initial' not in text and 'arm_limit_adjacent' not in text
    assert 'anti-damping' in a['diagnosis']
    with pytest.raises(EvidenceError):r.proposal('attempt_2')
    with pytest.raises(EvidenceError):r.experiment('A')
    with pytest.raises(EvidenceError):r.read('../../.env')


def copied_recording(tmp_path,monkeypatch):
    config=json.loads((ROOT/'workspace/arm_recording.json').read_text())
    root=tmp_path/config['root'];shutil.copytree(ROOT/config['root'],root)
    index=json.loads((root/config['index']).read_text())
    for name in index['project_hashes']:
        target=tmp_path/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,target)
    monkeypatch.setattr('workspace.arm_data.ROOT',tmp_path)
    return root,config


@pytest.mark.parametrize('kind',['hash','symlink','pose','source','missing'])
def test_recording_corruption_never_substitutes_evidence(tmp_path,kind,monkeypatch):
    root,c=copied_recording(tmp_path,monkeypatch);path=root/c['index'];index=json.loads(path.read_text())
    summary=json.loads((root/index['scenarios']['arm_nominal']['original']).read_text())
    relative=Path(summary['artifact_references']['telemetry.json']).relative_to(c['root']).as_posix()
    telemetry=root/relative
    if kind=='hash':telemetry.write_bytes(telemetry.read_bytes()+b' ')
    elif kind=='symlink':telemetry.unlink();telemetry.symlink_to(ROOT/'.env')
    elif kind=='missing':telemetry.unlink()
    elif kind=='source':index['project_hashes'][TARGET]='0'*64
    else:
        d=json.loads(telemetry.read_text());d['samples'][10]['geom_poses'][2]['position'][0]+=.1
        telemetry.write_text(json.dumps(d));index['files'][relative]=hashlib.sha256(telemetry.read_bytes()).hexdigest()
    path.write_text(json.dumps(index));sha=hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises((ValueError,OSError)):ArmRecording(root,c['index'],sha).experiment('arm_nominal')


def test_independent_loop_detects_controller_inconsistency_and_trace_tampering():
    f=ArmFamily();c=f.compile('arm_nominal')[2]
    run=first_run(f,'arm_nominal',f.baseline(),c.controller_sha256)
    changed=copy.deepcopy(run['samples']);changed[100]['command'][0]+=.1
    assert independent({**run,'samples':changed},None,None,family=f)['verification_execution']=='FAIL'
    def different_controller(model,data):data.ctrl[:]=0
    assert independent(run,None,None,family=f,trusted_controller=different_controller)['verification_execution']=='FAIL'


def disposable_arm_project(path):
    path.mkdir()
    for name in ('core','physics','robot','configs','workspace'):
        shutil.copytree(ROOT/name,path/name,ignore=shutil.ignore_patterns('__pycache__','approved_arm_controller.py','approved_controller.py'))
    return path

def copied_historical_arm_review(tmp_path):
    config=json.loads((ROOT/'workspace/arm_recording.json').read_text());out=ROOT/config['root']
    recording=default_arm_recording();final=recording.json(recording.index['full_evaluation']);state=final['state'];rid=final['review_id']
    project=disposable_arm_project(tmp_path/'project')
    sessions=tmp_path/'reviews';sessions.mkdir();shutil.copytree(out/final.get('review_directory','full_reviews')/rid,sessions/rid)
    return Workflow(project,sessions,family='arm'),rid,state

def test_historical_arm_verification_is_stale_for_current_project_copy(tmp_path,monkeypatch):
    """Old genuine evidence keeps its old fingerprint; never rebase it."""
    w,rid,state=copied_historical_arm_review(tmp_path);before=(w.sessions/rid/'state.json').read_bytes()
    def forbidden(*a,**k):raise AssertionError('Stale evidence must stop before containment or execution')
    monkeypatch.setattr(AppleVMBackend,'preflight',forbidden)
    assert w._fingerprint()!=state['fingerprint']
    with pytest.raises(WorkflowBlocked,match='previous verification is stale'):w.checked_verification(rid)
    with pytest.raises(WorkflowBlocked,match='previous verification is stale'):w.apply(rid,confirmation='APPLY '+state['source_sha256'])
    assert (w.sessions/rid/'state.json').read_bytes()==before
    assert not (w.root/w.managed_target).exists() and not (ROOT/w.managed_target).exists()

def test_exact_archival_context_can_be_inspected_without_current_application_authority(tmp_path,monkeypatch):
    """Reconstruct archived bytes as DATA only, not current VM qualification."""
    w,rid,state=copied_historical_arm_review(tmp_path)
    old_core=ROOT/'artifacts/phase18e_3/20261025_gate1/core_day4b1_before.py'
    assert hashlib.sha256(old_core.read_bytes()).hexdigest()==state['fingerprint']['core/day4b1.py']
    (w.root/'core/day4b1.py').write_bytes(old_core.read_bytes())
    # No fingerprint/state edit: the disposable source bytes match the archive.
    assert w._fingerprint()==state['fingerprint']
    def forbidden(*a,**k):raise AssertionError('Data-only historical inspection cannot invoke containment')
    monkeypatch.setattr(AppleVMBackend,'preflight',forbidden)
    original_state=(w.sessions/rid/'state.json').read_bytes()
    assert w.checked_verification(rid)['status']=='VERIFIED'
    with pytest.raises(WorkflowBlocked,match='Separate explicit'):w.apply(rid,confirmation='VERIFY IN VM ONLY')
    assert (w.sessions/rid/'state.json').read_bytes()==original_state
    assert not (w.root/w.managed_target).exists() and not (ROOT/w.managed_target).exists()

def fresh_arm_review(tmp_path):
    project=disposable_arm_project(tmp_path/'project');w=Workflow(project,tmp_path/'reviews',family='arm')
    archived=default_arm_recording().proposal('attempt_1')
    rid=w.create(source=archived['source'],explanation='Fresh disposable review of archived source bytes; historical verification is NOT reused',expected_original_sha256=archived['validation']['original_sha256'],provenance={'kind':'developer_test_fresh_review_of_historical_source','model_requests':0,'historical_measurements_reused_for_authority':False})
    return w,rid

def test_fresh_disposable_arm_review_needs_new_verification_and_real_containment(tmp_path,monkeypatch):
    w,rid=fresh_arm_review(tmp_path);s=w.get(rid)
    def forbidden(*a,**k):raise AssertionError('No VM/candidate execution permitted in offline fixture')
    monkeypatch.setattr(AppleVMBackend,'controller',forbidden)
    assert s['status']=='REVIEWED' and s['fingerprint']==w._fingerprint() and s['verification'] is None
    with pytest.raises(WorkflowBlocked,match='No fresh verification'):w.checked_verification(rid)
    with pytest.raises(WorkflowBlocked,match='Explicit verification approval'):w.verify(rid)
    blocked=w.verify(rid,approved=True,backend=object())
    assert blocked['status']=='BLOCKED' and 'Only the qualified AppleVMBackend' in blocked['reason']
    assert blocked['verification'] is None and blocked['verification_inventory']=={}
    with pytest.raises(WorkflowBlocked,match='No fresh verification'):w.apply(rid,confirmation='APPLY '+s['source_sha256'])
    assert not list((w.sessions/rid).glob('execution_*')) and not (w.root/w.managed_target).exists()

@pytest.fixture
def fresh_vm_verified_arm_review(tmp_path):
    """Separate future VM-test authorization required; never auto-qualify.

    This is NOT part of the seventeen-launch Gate2 containment scope. Current
    arm communication qualification and fresh candidate evaluation are required.
    No archived fingerprint or measurement is promoted to current authority.
    """
    if os.environ.get('EMBODY_RUN_VM_TESTS')!='1':pytest.skip('Requires separately approved fresh arm VM regression batch')
    from core.robots.qualification import require_qualification
    backend=AppleVMBackend();backend.preflight()
    w,rid=fresh_arm_review(tmp_path);require_qualification(backend,w.family)
    state=w.verify(rid,approved=True,backend=backend)
    assert state['status']=='VERIFIED',state.get('reason')
    return w,rid,state

@pytest.mark.live_vm
def test_arm_transactions_with_real_verified_evidence_on_disposable_copy(fresh_vm_verified_arm_review):
    """Positive apply/rollback contract retained; requires NEW real VM proof."""
    w,rid,state=fresh_vm_verified_arm_review;project=w.root;sessions=w.sessions;before=(project/TARGET).read_bytes()
    assert w.checked_verification(rid)['status']=='VERIFIED'
    with pytest.raises(WorkflowBlocked,match='Separate explicit'):w.apply(rid,confirmation='VERIFY IN VM ONLY')
    applied=w.apply(rid,confirmation='APPLY '+state['source_sha256'])
    assert applied['status']=='APPLIED' and (project/w.managed_target).read_bytes()==(sessions/rid/'proposed_source.txt').read_bytes()
    assert (project/TARGET).read_bytes()==before
    with pytest.raises(WorkflowBlocked):w.rollback(rid,confirmation='')
    assert w.rollback(rid,confirmation='REVERT '+rid)['status']=='REVERTED'
    assert not (project/w.managed_target).exists() and (project/TARGET).read_bytes()==before
    assert not (ROOT/w.managed_target).exists()
    # A second, developer-defined transaction precondition on this disposable
    # copy: existing managed bytes. Actual verification files/results are kept
    # unchanged; this is a backup/rollback test, never a new physics verdict.
    prior=b'# developer-owned previous managed source; never executed\n'
    (project/w.managed_target).write_bytes(prior)
    transaction=copy.deepcopy(state)
    transaction['managed_before_sha256']=hashlib.sha256(prior).hexdigest()
    (sessions/rid/'state.json').write_text(json.dumps(transaction))
    assert w.apply(rid,confirmation='APPLY '+state['source_sha256'])['status']=='APPLIED'
    backup=sessions/rid/'previous_controller.backup';assert backup.read_bytes()==prior
    backup.write_bytes(b'corrupt backup')
    with pytest.raises(WorkflowBlocked,match='backup hash'):w.rollback(rid,confirmation='REVERT '+rid)
    backup.write_bytes(prior)
    assert w.rollback(rid,confirmation='REVERT '+rid)['status']=='REVERTED'
    assert (project/w.managed_target).read_bytes()==prior and (project/TARGET).read_bytes()==before


@pytest.mark.rendering
def test_native_arm_renderer_writes_real_provenance_and_refuses_overwrite(tmp_path):
    from workspace.arm_render import render
    from PIL import Image
    output=tmp_path/'render';index=render(output,steps=(0,))
    assert index['status']=='PASS' and len(index['frames'])==2
    for row in index['frames']:
        path=output/row['path']
        assert hashlib.sha256(path.read_bytes()).hexdigest()==row['sha256']
        assert min(row['visible_geom_pixels'].values())>0
        with Image.open(path) as im:assert im.size==(640,480) and np.asarray(im).std()>5
    with pytest.raises(FileExistsError):render(output,steps=(0,))
    with pytest.raises(ValueError,match='No dynamic'):render(tmp_path/'unreachable','arm_unreachable')


def test_frontend_fixture_and_recorded_report_are_exact_exports():
    fixture=json.loads((ROOT/'frontend/test/arm_evidence.json').read_text());r=default_arm_recording()
    assert fixture['metadata']==r.metadata()
    assert fixture['proposal']==r.proposal('attempt_1')
    for s in fixture['experiments']:assert fixture['experiments'][s]==json.loads(json.dumps(r.experiment(s)))
    from tools.day9_report import measurements
    assert measurements()==measurements()


def test_baseline_reproduction_refuses_history_and_matches_measured_contract(tmp_path):
    from tools.day9_prepare import prepare
    output=tmp_path/'reproduction';rows=prepare(output)
    actual=default_arm_recording()
    for s,row in rows.items():
        recorded=actual.experiment(s)['variants']['original']['summary']
        assert row['physical_safety_status']==recorded['physical_safety_status']
        if 'safety_acceptance' in row:assert row['safety_acceptance']==recorded['safety_acceptance']
    with pytest.raises(FileExistsError):prepare(output)

