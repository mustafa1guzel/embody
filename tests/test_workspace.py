"""Real evidence/UI integration and fail-closed review boundaries. No GPT calls."""
import hashlib
import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from core.simulation import ROOT
from workspace.data import (EvidenceError, LABELS, Recording, bounded_read, chart_rows,
                            decode_json, default_recording, native_frame, physical_context)


@pytest.fixture
def recording():
    return default_recording()


@pytest.mark.parametrize('scenario,mass,velocity,wall',[('A',2,1.2,2),('B',3,1.2,2),('C',2,1,1.65)])
def test_real_context_telemetry_and_independent_results(recording,scenario,mass,velocity,wall):
    trajectories={v:recording.trajectory(scenario,v) for v in LABELS}
    context=physical_context(scenario,trajectories['original'])
    assert context['mass_kg']==mass and context['initial_velocity_ms']==velocity
    assert context['braking_force_n']==4 and context['wall_center_x_m']==wall
    assert context['wall_near_x']==pytest.approx(wall-.05)
    assert context['wall_clearance']==pytest.approx(wall-.05-.18)
    assert context['minimum_clearance_m']==.05 and context['max_final_speed_ms']==.03
    assert context['completion_deadline_s']==3 and context['joint_axis']==[1,0,0]
    rows=chart_rows(trajectories)
    assert len(rows)==1803
    for variant,t in trajectories.items():
        measured=[r for r in rows if r['controller']==LABELS[variant]]
        assert [r['clearance'] for r in measured]==[r['wall_clearance'] for r in t['samples']]
        assert [r['velocity'] for r in measured]==[r['velocity'] for r in t['samples']]
        assert [r['wall_contact'] for r in measured]==[r['wall_collision'] for r in t['samples']]
        assert t['summary']['independent_verification']=='PASS'
        assert t['summary']['physical_safety_status']==('PASS' if variant=='attempt_2' else 'FAIL')


def test_exact_model_sources_diffs_and_feedback(recording):
    original=recording.original()
    first,second=(recording.proposal(v) for v in ('attempt_1','attempt_2'))
    assert 'BRAKING_THRESHOLD_M = 0.12' in original['content']
    assert first['validation']['validation_status']==second['validation']['validation_status']=='VALID'
    assert first['verification']['physical_safety_status']=='FAIL'
    assert second['verification']['physical_safety_status']=='PASS'
    assert first['provenance']['exact_api_arguments_match'] is True
    assert first['diff'].startswith('--- robot/controller.py\n+++ candidate/robot/controller.py\n')
    calls=recording.tool_trace()
    assert len(calls)==17 and calls[-2]['name']==calls[-1]['name']=='propose_patch'
    assert calls[-2]['arguments']['proposed_source']==first['source']
    assert calls[-1]['arguments']['proposed_source']==second['source']
    assert calls[-2]['verification_feedback']['physical_safety_status']=='FAIL'
    assert calls[-1]['verification_feedback']['physical_safety_status']=='PASS'


@pytest.mark.parametrize('path',['../.env','/etc/passwd','.env','session/../../.env','a\\b',''])
def test_unindexed_or_unsafe_paths_rejected(recording,path):
    with pytest.raises(EvidenceError):recording.read(path)
    with pytest.raises(EvidenceError):recording.read(recording.reference(path))


def test_missing_corrupt_and_symlink_files_fail_closed(tmp_path):
    raw=b'{"value": 1}'
    (tmp_path/'valid.json').write_bytes(raw)
    inventory={'valid.json':hashlib.sha256(raw).hexdigest()}
    index=json.dumps(inventory).encode();(tmp_path/'final_evidence_inventory.json').write_bytes(index)
    digest=hashlib.sha256(index).hexdigest();r=Recording(tmp_path,digest)
    assert r.json('valid.json')=={'value':1}
    (tmp_path/'valid.json').write_text('changed')
    with pytest.raises(EvidenceError,match='hash'):r.read('valid.json')
    (tmp_path/'valid.json').unlink()
    with pytest.raises(EvidenceError,match='missing'):r.read('valid.json')
    private=tmp_path/'private';private.mkdir();(private/'secret').write_text('dummy-private-file')
    (tmp_path/'valid.json').symlink_to(private/'secret')
    with pytest.raises(EvidenceError,match='symlink'):r.read('valid.json')
    (tmp_path/'linked').symlink_to(private,target_is_directory=True)
    with pytest.raises(EvidenceError,match='symlink'):bounded_read(tmp_path,'linked/secret')
    with pytest.raises(EvidenceError,match='inventory'):Recording(tmp_path,'0'*64)


@pytest.mark.parametrize('raw',[b'{',b'{"a":1,"a":2}',b'{"a":NaN}',b'{"a":Infinity}'])
def test_invalid_json_never_becomes_evidence(raw):
    with pytest.raises(EvidenceError):decode_json(raw)


def test_external_artifact_reference_and_unknown_selection_rejected(recording):
    with pytest.raises(EvidenceError,match='escaped'):recording.reference('/etc/passwd')
    with pytest.raises(EvidenceError):recording.summary('D','attempt_2')
    with pytest.raises(EvidenceError):recording.proposal('candidate_arbitrary')


def test_context_drift_is_visible_not_relabelled_as_verified(recording):
    trajectory=recording.trajectory('A','original')
    trajectory['metadata']['effective_mjcf_sha256']='0'*64
    with pytest.raises(EvidenceError,match='context differs'):physical_context('A',trajectory)


def test_original_source_drift_blocks_review(monkeypatch,recording):
    import workspace.data as data
    monkeypatch.setattr(data,'read_project_file',lambda *a: {'sha256':'0'*64,'content':'changed'})
    with pytest.raises(EvidenceError,match='differs'):recording.original()


@pytest.mark.parametrize('scenario',['A','B','C'])
def test_native_frames_are_hash_checked_measured_state_reconstructions(recording,scenario):
    for variant in LABELS:
        pixels,frame=native_frame(scenario,variant,400)
        assert pixels.startswith(b'\x89PNG\r\n\x1a\n')
        trajectory=recording.trajectory(scenario,variant)
        row=trajectory['samples'][400]
        assert frame['time']==row['time'] and frame['position']==row['position']
        assert frame['wall_clearance']==row['wall_clearance']
        assert frame['wall_collision']==row['wall_collision']
        assert frame['dimensions']==[1024,768] and min(frame['visible_geom_pixels'].values())>0


def app():
    return AppTest.from_file(ROOT/'streamlit_app.py',default_timeout=30).run()


def test_workspace_user_flow_without_api_or_artifact_writes(monkeypatch,recording):
    from core.agent import credentials
    def forbidden(*a,**kw):raise AssertionError('Review must not load credentials or call a model')
    monkeypatch.setattr(credentials,'read_openai_api_key',forbidden)
    monkeypatch.setattr(credentials,'create_openai_client',forbidden)
    inventory_before={p:hashlib.sha256((recording.root/p).read_bytes()).hexdigest() for p in recording.inventory}
    at=app()
    assert not at.exception and not at.error
    assert at.radio(key='version').value=='original'
    assert any('Original controller' in w.value for w in at.warning)
    at.radio(key='version').set_value('attempt_1').run()
    assert not at.exception and any('Safety rejected' in w.value for w in at.warning)
    assert any(c.language=='diff' and 'TARGET_FINAL_SPEED_MPS' in c.value for c in at.code)
    at.radio(key='proposal_view').set_value('Source').run()
    # Streamlit strips a terminal newline for display; exported source stays exact.
    assert recording.proposal('attempt_1')['source'].rstrip() in [c.value.rstrip() for c in at.code]
    at.radio(key='version').set_value('attempt_2').run()
    at.selectbox(key='tool_call').set_value(16).run()
    assert any('Verified candidate' in s.value for s in at.success)
    assert any('revised candidate PASS' in s.value for s in at.success)
    at.radio(key='proposal_view').set_value('Validation').run()
    assert not at.exception and not at.error
    for scenario,mass in [('B','3 kg'),('C','2 kg'),('A','2 kg')]:
        at.selectbox(key='scenario').set_value(scenario).run()
        assert not at.exception and not at.error
        assert any(m.label=='Robot mass' and m.value==mass for m in at.metric)
    at.select_slider(key='frame').set_value(600).run()
    at.selectbox(key='native_version').set_value('attempt_1').run()
    assert not at.exception and not at.error
    inventory_after={p:hashlib.sha256((recording.root/p).read_bytes()).hexdigest() for p in recording.inventory}
    assert inventory_after==inventory_before


def test_app_missing_evidence_reports_error_without_success(monkeypatch):
    import workspace.app as ui
    def missing():raise EvidenceError('Recorded evidence file hash mismatch')
    monkeypatch.setattr(ui,'default_recording',missing)
    at=app()
    assert not at.exception and at.error
    assert not at.success
    assert 'Workspace evidence unavailable' in at.error[0].value


def test_missing_or_corrupt_native_replay_is_explicit(monkeypatch):
    import workspace.data as data
    config=data.settings();config['native_index_sha256']=None
    monkeypatch.setattr(data,'settings',lambda:config)
    with pytest.raises(EvidenceError,match='not been generated'):native_frame('A','original',0)
    config['native_index_sha256']='0'*64
    with pytest.raises(EvidenceError,match='hash'):native_frame('A','original',0)
