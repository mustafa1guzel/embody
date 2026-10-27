"""Untrusted proposals are validated and stored, never executed in this process."""
from __future__ import annotations
import hashlib
from pathlib import Path

import pytest

from core.agent.patching import CandidateStore, TARGET, read_project_file, source_errors
from core.agent.trace import ExecutionTrace, read_trace
from core.agent.verification import CandidateVerifier
from core.day3 import load_scenarios
from core.simulation import ROOT, sha256


@pytest.fixture
def source():
    return read_project_file(ROOT, TARGET)


@pytest.mark.parametrize('path', ['/etc/passwd','../robot/controller.py','robot/../robot/controller.py',
                                  './robot/controller.py','robot//controller.py','robot\\controller.py',
                                  '.env','requirements.txt','artifacts/day3/verification.json','C:/secret',''])
def test_file_allowlist_rejects_unauthorized_paths(path):
    with pytest.raises(ValueError):
        read_project_file(ROOT, path)


def test_read_actual_source_and_hash(source):
    assert source['content'] == (ROOT / TARGET).read_text()
    assert source['sha256'] == sha256(ROOT / TARGET)


@pytest.mark.parametrize('parent_link', [False,True])
def test_symlink_escapes_rejected(tmp_path, parent_link):
    project, outside = tmp_path/'project', tmp_path/'outside'
    project.mkdir(); outside.mkdir()
    (outside/'controller.py').write_text('do not read')
    if parent_link:
        (project/'robot').symlink_to(outside, target_is_directory=True)
    else:
        (project/'robot').mkdir()
        (project/TARGET).symlink_to(outside/'controller.py')
    with pytest.raises(ValueError, match='symlink'):
        read_project_file(project,TARGET)


def test_fifo_and_large_sources_are_rejected(tmp_path):
    import os
    # Avoid opening FIFOs: file reads must use nonblocking descriptors.
    (tmp_path/'robot').mkdir()
    (tmp_path/TARGET).write_text('a'*100_001)
    with pytest.raises(ValueError, match='size limit'):
        read_project_file(tmp_path,TARGET)
    (tmp_path/TARGET).unlink()
    os.mkfifo(tmp_path/TARGET)
    with pytest.raises(ValueError, match='regular file'):
        read_project_file(tmp_path,TARGET)


def test_valid_proposal_generates_diff_without_overwriting_source(tmp_path, source):
    store = CandidateStore(ROOT,tmp_path/'candidates')
    proposal = source['content'] + '\n# Mock test proposal: formatting only; no repair is claimed.\n'
    result = store.propose(target_path=TARGET,expected_original_sha256=source['sha256'],
                           proposed_source=proposal,explanation='MOCK fixture: exercise proposal plumbing only')
    assert result['validation_status']=='VALID'
    assert result['candidate_id'] and result['validation_errors']==[]
    assert '+# Mock test proposal' in result['unified_diff']
    assert read_project_file(ROOT,TARGET)==source
    record = store.get(result['candidate_id'])
    assert record['source_path'].read_text()==proposal
    assert record['proposed_sha256']==hashlib.sha256(proposal.encode()).hexdigest()
    assert result['execution_authorized'] is False


@pytest.mark.parametrize('replacement', [
    'data.qpos[0] = 0', 'data.qvel[0] = 0', 'model.opt.gravity[0] = 0',
    "model.body('carriage').mass[0] = 0.1", 'data.ctrl = [0]',
    "open('configs/worldbase.json','w')", "setattr(data,'qpos',[0])",
    'mujoco.mj_resetData(model,data)', 'data.ctrl.fill(0)',
    'data.__class__', 'exec("pass")', 'import os',
])
def test_unsafe_or_unsupported_function_effects_rejected(source, replacement):
    proposed = source['content'].replace('    joint =', '    '+replacement+'\n    joint =', 1)
    assert source_errors(source['content'],proposed)


@pytest.mark.parametrize('suffix', ["\nimport os\n", "\nopen('/tmp/untrusted','w')\n",'\nclass Other: pass\n'])
def test_module_execution_and_import_changes_rejected(source,suffix):
    assert source_errors(source['content'],source['content']+suffix)


def test_signature_syntax_and_stale_source_rejected(tmp_path,source):
    assert source_errors(source['content'], 'not valid python (')
    assert source_errors(source['content'],source['content'].replace(' -> None:',':'))
    assert source_errors(source['content'],source['content'].replace('model: mujoco.MjModel','model: object'))
    store = CandidateStore(ROOT,tmp_path/'store')
    record = store.propose(target_path=TARGET,expected_original_sha256='0'*64,
                           proposed_source=source['content']+'\n# fixture\n',explanation='stale fixture')
    assert record['validation_status']=='REJECTED' and record['candidate_id'] is None
    assert not list((tmp_path/'store').rglob('controller.py'))


def test_candidate_tampering_is_detected(tmp_path,source):
    store = CandidateStore(ROOT,tmp_path/'store')
    result = store.propose(target_path=TARGET,expected_original_sha256=source['sha256'],
                           proposed_source=source['content']+'\n# fixture\n',explanation='fixture')
    store.get(result['candidate_id'])['source_path'].write_text('changed')
    with pytest.raises(ValueError,match='hash changed'):
        store.get(result['candidate_id'])


def test_candidate_execution_is_explicitly_blocked_for_all_scenarios(tmp_path,source):
    store = CandidateStore(ROOT,tmp_path/'store')
    result = store.propose(target_path=TARGET,expected_original_sha256=source['sha256'],
                           proposed_source=source['content']+'\n# fixture only\n',explanation='MOCK')
    trace=ExecutionTrace(tmp_path/'trace.jsonl',model_mode='test_mock')
    verifier=CandidateVerifier(store,load_scenarios(),tmp_path/'verification',trace)
    checked=verifier.verify(result['candidate_id'])
    assert checked['verification_execution']=='BLOCKED'
    assert checked['physical_safety_status']=='NOT_EVALUATED'
    assert not checked['candidate_code_executed']
    assert set(checked['scenario_results'])=={'A','B','C'}
    assert all(r['simulation_execution']=='NOT_RUN' for r in checked['scenario_results'].values())
    assert not list(tmp_path.rglob('telemetry.json'))
    assert read_trace(trace.path)[-1]['event']=='candidate_verification'
