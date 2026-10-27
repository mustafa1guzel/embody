"""Portable saved-data checks; never integrate dynamics or invoke a model/VM."""
import hashlib
import json
from pathlib import Path

import pytest

from core.simulation import ROOT
from tools.public_study import HOST, derive, export
from workspace.data import Recording, EvidenceError, bounded_read, default_recording, native_frame


PACKAGE = ROOT / 'examples/rail-braking-study'


def test_public_source_anchor_and_every_payload_hash_are_distinct_and_valid():
    manifest = json.loads((PACKAGE / 'derivation.json').read_text())
    source = (PACKAGE / 'source-manifest.json').read_bytes()
    assert hashlib.sha256(source).hexdigest() == manifest['source_inventory_sha256']
    original_index = json.loads(source)
    recording = default_recording()
    assert recording.root == PACKAGE
    assert recording.inventory_sha256 == manifest['public_inventory_sha256']
    assert manifest['public_inventory_sha256'] != manifest['source_inventory_sha256']
    for row in manifest['files']:
        assert original_index[row['file']] == row['source_sha256']
        raw = recording.read(row['file'])
        assert hashlib.sha256(raw).hexdigest() == row['public_sha256']
        assert not HOST.search(raw.decode())
        if not row['metadata_changes']:
            assert row['public_sha256'] == row['source_sha256']


@pytest.mark.parametrize('scenario', ['A', 'B', 'C'])
@pytest.mark.parametrize('variant', ['original', 'attempt_1', 'attempt_2'])
def test_all_saved_cases_keep_original_verdict_and_actual_measurements(scenario, variant):
    recording = default_recording()
    result = recording.trajectory(scenario, variant)
    manifest = json.loads((PACKAGE / 'derivation.json').read_text())
    assert len(result['samples']) == 601
    assert result['summary']['physical_safety_status'] == manifest['source_verdicts'][scenario + '/' + variant]
    assert result['summary']['physical_safety_status'] == ('PASS' if variant == 'attempt_2' else 'FAIL')
    assert result['summary']['independent_verification'] == 'PASS'
    for key in ('telemetry.json', 'independent_safety_trace.json', 'effective_model.xml'):
        ref = recording.reference(result['summary']['artifact_references'][key])
        assert ref in recording.inventory
        assert not Path(ref).is_absolute()


def test_all_native_frames_are_saved_original_bytes_not_new_renders():
    index = json.loads((PACKAGE / 'native/index.json').read_text())
    assert index['packaging']['source_index_sha256']
    count = 0
    for scenario, variants in index['scenarios'].items():
        for variant, frames in variants.items():
            for frame in frames:
                raw, returned = native_frame(scenario, variant, frame['step'])
                assert hashlib.sha256(raw).hexdigest() == frame['sha256']
                assert returned == frame
                count += 1
    assert count == 51


@pytest.mark.parametrize('path', ['../.env', '/etc/passwd', 'session/../../secret', 'a\\b'])
def test_public_reader_still_rejects_escape_and_unindexed_paths(path):
    with pytest.raises(EvidenceError):
        default_recording().read(path)


def test_public_reader_does_not_accept_foreign_absolute_root_or_unbundled_payload():
    recording = default_recording()
    with pytest.raises(EvidenceError, match='escaped'):
        recording.reference('/outside-recording/telemetry.json')
    with pytest.raises(EvidenceError, match='inventory'):
        recording.read('session/api/api_request_000.json')


def test_projection_rejects_unknown_fields_and_metadata_path_escape():
    synthetic = Path('/').joinpath('Users', 'fixture-account', 'project')
    with pytest.raises(ValueError, match='Unreviewed'):
        derive({'unknown': str(synthetic / 'secret')}, source=synthetic, project_root=synthetic)
    with pytest.raises(ValueError):
        derive({'artifact_references': {'telemetry.json': str(synthetic / '../outside/file')}},
               source=synthetic, project_root=synthetic)


def test_pinned_inventory_corruption_and_symlink_are_rejected(tmp_path):
    raw = b'{"v":1}'
    (tmp_path / 'record.json').write_bytes(raw)
    index = json.dumps({'record.json': hashlib.sha256(raw).hexdigest()}).encode()
    (tmp_path / 'final_evidence_inventory.json').write_bytes(index)
    recording = Recording(tmp_path, hashlib.sha256(index).hexdigest())
    assert recording.json('record.json') == {'v': 1}
    (tmp_path / 'record.json').write_text('tampered')
    with pytest.raises(EvidenceError, match='hash'):
        recording.read('record.json')
    (tmp_path / 'record.json').unlink()
    (tmp_path / 'record.json').symlink_to('/etc/passwd')
    with pytest.raises(EvidenceError, match='symlink'):
        bounded_read(tmp_path, 'record.json')
    with pytest.raises(EvidenceError, match='inventory hash'):
        Recording(tmp_path, '0' * 64)


def test_packaging_refuses_to_overwrite_existing_output(tmp_path):
    with pytest.raises(ValueError, match='write-once'):
        export(tmp_path, 'unused', tmp_path, 'unused', tmp_path, project_root=tmp_path)


def test_frontend_projection_has_no_host_paths_and_has_its_own_hash():
    path = ROOT / 'frontend/test/recorded-study.public.json'
    raw = path.read_bytes()
    provenance = json.loads((ROOT / 'frontend/test/recorded-study.derivation.json').read_text())
    assert hashlib.sha256(raw).hexdigest() == provenance['public_sha256']
    assert provenance['public_sha256'] != provenance['source_sha256']
    assert provenance['all_retained_non_metadata_leaves_preserved'] is True
    assert provenance['all_non_metadata_leaves_preserved'] is False
    snapshot = json.loads(raw)
    assert 'recording/final_report.md' not in snapshot['files']
    assert all(row['path'] != 'recording/final_report.md' for row in snapshot['bootstrap']['files'])
    assert len(provenance['omitted_records']) == 2
    # Physical payloads and genuine session provenance remain present.
    assert set(snapshot['experiments']) == {'A', 'B', 'C'}
    assert snapshot['agent']['result']['api_budget']['requests']
    assert not HOST.search(raw.decode())


def test_API_file_list_only_advertises_packaged_records_and_denies_raw_private_report(tmp_path):
    from ide_api.service import IDE
    from workspace.workflow import Workflow
    ide = IDE(workflow=Workflow(ROOT, tmp_path / 'reviews'))
    paths = {item['path'] for item in ide.files()}
    assert 'recording/diagnosis.txt' in paths and 'recording/agent_trace.jsonl' in paths
    assert 'recording/final_report.md' not in paths
    with pytest.raises(EvidenceError, match='inventory'):
        ide.file('recording/final_report.md')
