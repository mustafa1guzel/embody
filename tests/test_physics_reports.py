"""Real recorded evidence, missing signals, metric semantics and read-only boundaries."""
import copy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import shutil
import pytest
from core.simulation import ROOT
from core.agent.tools import AgentTools
from core.agent.trace import ExecutionTrace, read_trace
from core.agent.vm_backend import AppleVMBackend
from physics.contracts import canonical, digest
from physics.extraction import extract_contract
from physics.integration import PhysicsToolsAdapter
from physics.profiler import profile
from physics.reports import recorded_report, markdown, write_reports
from workspace.data import default_recording, EvidenceError
from workspace.workflow import Workflow, WorkflowBlocked


@pytest.fixture(scope='module')
def contract():
    return extract_contract('A')


@pytest.mark.parametrize('scenario', ['A', 'B', 'C'])
@pytest.mark.parametrize('variant', ['original', 'attempt_1', 'attempt_2'])
def test_actual_recorded_nine_case_analysis(scenario, variant):
    report = recorded_report(scenario, variant)
    assert report['analytical_feasibility']['status'] == 'CONDITIONALLY_FEASIBLE'
    assert report['controller_static_assessment']['status'] == 'UNKNOWN'
    assert report['outside_envelope']['status'] == 'UNKNOWN'
    assert report['observed_physics']['safety_status'] == ('PASS' if variant == 'attempt_2' else 'FAIL')
    assert report['recorded_independent_verification'] == 'PASS'
    assert report['braking_onset']['analysis']['status'] == ('PROVEN_INFEASIBLE' if variant == 'original' else 'CONDITIONALLY_FEASIBLE')
    assert report['profiler']['metrics']['contact_episodes']['value'] == (1 if variant == 'original' else 0)
    assert report['authorization'] == {'vm_execution_approved': False, 'permanent_apply_approved': False}
    assert report['profiler']['metrics']['electrical_energy']['status'] == 'NOT_AVAILABLE'
    assert len(report['profiler']['series']['position']['value']) == 601
    assert len(report['profiler']['series']['acceleration']['value']) == 600
    assert len(report['profiler']['series']['jerk']['value']) == 599
    if variant == 'attempt_2':
        assert report['observed_physics']['clearance_margin_m'] > .002
        assert report['observed_physics']['final_absolute_velocity_mps'] < 1e-12
    elif variant == 'attempt_1':
        assert report['observed_physics']['final_absolute_velocity_mps'] == pytest.approx(.02)
        assert report['profiler']['metrics']['travel_after_last_braking']['value'] > .02
    before = report.pop('report_sha256')
    assert before == digest(report)


def test_hand_calculated_derivatives_work_power_and_last_sample_saturation(contract):
    c = replace(contract, timestep_s=1)
    samples = [
        {'time': 0, 'position': 0, 'velocity': 2, 'control': -4, 'generalized_actuator_force': -4, 'wall_collision': False},
        {'time': 1, 'position': 1, 'velocity': 1, 'control': 0, 'generalized_actuator_force': 0, 'wall_collision': True},
        {'time': 2, 'position': 1, 'velocity': 0, 'control': 4, 'generalized_actuator_force': 4, 'wall_collision': True},
        {'time': 3, 'position': 2, 'velocity': 2, 'control': -4, 'generalized_actuator_force': -4, 'wall_collision': False},
    ]
    p = profile(samples, c); metrics = p['metrics']; series = p['series']
    assert series['acceleration']['value'] == [-1, -1, 2]
    assert series['acceleration_interval_midpoints']['value'] == [.5, 1.5, 2.5]
    assert series['jerk']['value'] == [0, 3] and series['jerk_times']['value'] == [1, 2]
    assert series['mechanical_power']['value'] == [-8, 0, 0, -8]
    assert metrics['signed_mechanical_work']['value'] == 0
    assert metrics['positive_mechanical_work']['value'] == 4
    assert metrics['braking_work_magnitude']['value'] == 4
    assert metrics['force_saturation_duration']['value'] == 2
    assert metrics['force_saturation_fraction']['value'] == pytest.approx(2/3)
    assert metrics['command_saturation_duration']['value'] == 2
    assert metrics['contact_episodes']['value'] == 1
    assert p['contact_events'] == [{'sample_index': 1, 'time_s': 1}]
    assert metrics['minimum_clearance']['status'] == 'NOT_AVAILABLE'


@pytest.mark.parametrize('missing', ['position', 'velocity', 'generalized_actuator_force', 'time', 'wall_clearance', 'control'])
def test_missing_signals_are_unavailable_not_fabricated(contract, missing):
    samples = copy.deepcopy(default_recording().trajectory('A', 'attempt_2')['samples'])
    samples[12].pop(missing)
    p = profile(samples, contract)
    if missing in ('position', 'generalized_actuator_force', 'time'):
        assert p['metrics']['signed_mechanical_work']['status'] == 'NOT_AVAILABLE'
    if missing == 'velocity':
        assert p['series']['acceleration']['status'] == 'NOT_AVAILABLE'
        assert p['series']['jerk']['status'] == 'NOT_AVAILABLE'
    if missing == 'control':
        assert p['metrics']['command_saturation_duration']['status'] == 'NOT_AVAILABLE'
    if missing == 'wall_clearance':
        assert p['metrics']['clearance_safety_margin']['status'] == 'NOT_AVAILABLE'


def test_missing_short_nonuniform_nonfinite_samples(contract):
    assert profile([], contract)['status'] == 'NOT_AVAILABLE'
    p = profile([{'time': 0, 'velocity': 1}], contract)
    assert p['series']['acceleration']['status'] == 'NOT_AVAILABLE'
    for time in (.01, -.005, float('nan')):
        with pytest.raises(ValueError):
            profile([{'time': 0}, {'time': time}], contract)


def test_requested_command_clipping_distinct_from_applied_force_saturation(contract):
    h = contract.timestep_s
    p = profile([{'time': 0, 'control': -1000, 'generalized_actuator_force': -4},
                 {'time': h, 'control': 0, 'generalized_actuator_force': 0}], contract)
    assert p['metrics']['command_saturation_duration']['value'] == h
    assert p['metrics']['force_saturation_duration']['value'] == h


def test_reports_are_deterministic_complete_and_refuse_overwrite(tmp_path):
    r1 = recorded_report('A', 'attempt_2'); r2 = recorded_report('A', 'attempt_2')
    assert canonical(r1) == canonical(r2) and markdown(r1) == markdown(r2)
    assert json.loads(canonical(r1)) == r1
    output = tmp_path/'reports'; reports = write_reports(output)
    assert len(reports) == 9
    assert len(list(output.glob('*.json'))) == 11 and len(list(output.glob('*.md'))) == 11
    for name, sha in json.loads((output/'inventory.json').read_text()).items():
        assert hashlib.sha256((output/name).read_bytes()).hexdigest() == sha
    with pytest.raises(FileExistsError):
        write_reports(output)


@pytest.mark.parametrize('mutation', ['model', 'source', 'context', 'initial', 'geometry', 'horizon', 'independent', 'physical_source'])
def test_report_evidence_identity_failures(mutation):
    real = default_recording()
    class Changed:
        def __getattr__(self, name): return getattr(real, name)
        def trajectory(self, *args):
            t = copy.deepcopy(real.trajectory(*args))
            if mutation == 'model': t['metadata']['effective_mjcf_sha256'] = 'a'*64
            if mutation == 'source': t['metadata']['controller']['source_sha256'] = 'b'*64
            if mutation == 'physical_source': t['metadata']['source_sha256']['core/simulation.py'] = 'b'*64
            if mutation == 'context': t['metadata']['context']['bodybase']['mass_kg'] = 40
            if mutation == 'initial': t['samples'][0]['velocity'] = 1
            if mutation == 'geometry': t['samples'][3]['wall_clearance'] += .01
            if mutation == 'horizon': t['samples'].pop()
            if mutation == 'independent': t['independent']['fresh_worker_handshake']['xml_sha256'] = 'b'*64
            return t
    with pytest.raises(EvidenceError):
        recorded_report('A', 'attempt_2', recording=Changed())


def test_analysis_never_calls_vm_model_or_workflow(monkeypatch):
    def forbidden(*args, **kwargs): raise AssertionError('Analysis must be read-only and execution-free')
    monkeypatch.setattr(AppleVMBackend, 'preflight', forbidden)
    monkeypatch.setattr(AppleVMBackend, 'controller', forbidden)
    monkeypatch.setattr(Workflow, 'verify', forbidden)
    monkeypatch.setattr(Workflow, 'apply', forbidden)
    monkeypatch.setattr('core.agent.credentials.create_openai_client', forbidden)
    monkeypatch.setattr('core.agent.credentials.read_openai_api_key', forbidden)
    assert recorded_report('B', 'attempt_2')['observed_physics']['safety_status'] == 'PASS'


def test_analysis_cannot_silently_authorize_verification_or_apply(tmp_path, monkeypatch):
    project = tmp_path/'project'; project.mkdir()
    for name in ('core', 'robot', 'configs'):
        shutil.copytree(ROOT/name, project/name, ignore=shutil.ignore_patterns('__pycache__', 'approved_controller.py', '.approved-controller.lock'))
    workflow = Workflow(project, tmp_path/'reviews'); r = default_recording(); p = r.proposal('attempt_2')
    review = workflow.create(source=p['source'], explanation='Review only', expected_original_sha256=r.original()['sha256'], provenance={'kind': 'recorded'})
    analysis = recorded_report('A', 'attempt_2')
    assert not analysis['authorization']['vm_execution_approved']
    with pytest.raises(WorkflowBlocked):
        workflow.verify(review, approved=False)
    with pytest.raises(WorkflowBlocked):
        workflow.apply(review, confirmation='APPLY VERIFIED PATCH')
    assert workflow.get(review)['status'] == 'REVIEWED'
    assert not (project/'robot/approved_controller.py').exists()
    assert (project/'robot/controller.py').read_bytes() == (ROOT/'robot/controller.py').read_bytes()


def test_optional_tool_adapter_preserves_schemas_and_annotates_real_context(tmp_path):
    trace = ExecutionTrace(tmp_path/'trace.jsonl', model_mode='offline_deterministic_test_no_model')
    base = AgentTools(tmp_path/'tools', trace); tools = PhysicsToolsAdapter(base)
    assert tools.schemas == base.schemas and len(tools.schemas) == 6
    result = tools.dispatch('get_robot_context', {'scenario_id': 'B'})
    assert result['ok'] and result['result']['bodybase']['mass_kg'] == 3
    assert result['result']['physics_analysis']['task_assessment']['status'] == 'CONDITIONALLY_FEASIBLE'
    assert read_trace(trace.path)[-1]['event'] == 'physics_analysis'
    assert tools.dispatch('get_robot_context', {'scenario_id': 'unknown'})['ok'] is False
    assert tools.dispatch('read_project', {'path': '.env'})['ok'] is False
    summary = tools.dispatch('run_simulation', {'scenario_id': 'A', 'controller_variant': 'faulty'})['result']
    diagnostic = tools.dispatch('inspect_failure', {'simulation_run_id': summary['simulation_run_id']})['result']
    assert diagnostic['evidence']['safety_acceptance']['status'] == 'FAIL'
    assert diagnostic['physics_analysis']['measured_onset_assessment']['status'] == 'PROVEN_INFEASIBLE'
    assert diagnostic['physics_analysis']['task_assessment']['status'] == 'CONDITIONALLY_FEASIBLE'


def test_physics_endpoint_is_read_only_bounded_and_fail_closed():
    # Reuse the existing real loopback test server/client, not a mock physics API.
    from ide_api.server import Server
    from test_ide_api import LocalClient
    import threading
    server = Server(('127.0.0.1', 0)); thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        client = LocalClient(server)
        good = client.get('/api/physics', params={'scenario': 'C', 'variant': 'attempt_2'})
        assert good.status_code == 200 and good.json() == recorded_report('C', 'attempt_2')
        for path in ['/api/physics?scenario=C', '/api/physics?scenario=C&variant=../../.env',
                     '/api/physics?scenario=C&variant=original&run=1', '/api/physics?scenario=A&scenario=B&variant=original']:
            assert client.get(path).status_code == 400
        assert server.jobs == {}
    finally:
        server.shutdown(); server.server_close(); thread.join(5)
