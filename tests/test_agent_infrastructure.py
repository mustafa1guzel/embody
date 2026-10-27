"""Mock model transport, real tools/physics and honest independent status recording."""
from __future__ import annotations
import json
from types import SimpleNamespace

import pytest

from core.agent.models import (CredentialsMissing, MockModelAdapter, ModelTurn, ToolCall,
                               OpenAIResponsesAdapter, live_integration_status)
from core.agent.orchestration import AgentOrchestrator
from core.agent.tools import AgentTools, CONTRACTS
from core.agent.trace import ExecutionTrace, read_trace
from core.agent.patching import TARGET
from core.simulation import ROOT, sha256
from PIL import Image


@pytest.fixture
def tools(tmp_path):
    trace=ExecutionTrace(tmp_path/'trace.jsonl',model_mode='deterministic_mock')
    return AgentTools(tmp_path/'tools',trace)


def test_exactly_six_strict_tool_contracts(tools):
    assert set(CONTRACTS)=={'read_project','get_robot_context','get_world_context','run_simulation','inspect_failure','propose_patch'}
    assert len(tools.schemas)==6
    for schema in tools.schemas:
        assert schema['strict'] and schema['parameters']['additionalProperties'] is False
        assert set(schema['parameters']['required'])==set(schema['parameters']['properties'])


@pytest.mark.parametrize('name,args', [('shell',{}),('read_project',{}),('read_project',{'path':TARGET,'extra':1}),
    ('read_project',{'path':1}),('get_robot_context',{'scenario_id':'unknown'}),
    ('run_simulation',{'scenario_id':'A','controller_variant':'arbitrary_python()'}),
    ('inspect_failure',{'simulation_run_id':'../artifacts/day1/telemetry.json'})])
def test_dispatch_errors_are_returned_and_traced(tools,name,args):
    result=tools.dispatch(name,args)
    assert result['ok'] is False
    assert read_trace(tools.trace.path)[-1]['payload']['output']==result


@pytest.mark.parametrize('scenario,mass,wall,velocity,gap', [('A',2,2,1.2,1.77),('B',3,2,1.2,1.77),('C',2,1.65,1,1.42)])
def test_context_tools_compile_actual_scenario_physics(tools,scenario,mass,wall,velocity,gap):
    robot=tools.dispatch('get_robot_context',{'scenario_id':scenario})['result']
    world=tools.dispatch('get_world_context',{'scenario_id':scenario})['result']
    assert robot['bodybase']['mass_kg']==robot['effective_mujoco']['carriage_mass_kg']==mass
    assert world['worldbase']['wall_position_x_m']==world['effective_mujoco']['wall_center_m'][0]==wall
    assert world['effective_mujoco']['wall_clearance']==pytest.approx(gap)
    assert world['effective_mujoco']['initial_velocity_ms']==velocity
    assert robot['effective_mjcf_sha256']==world['effective_mjcf_sha256']
    for p in robot['force_probes']:
        assert abs(p['generalized_force_n'])==4
        assert abs(p['measured_acceleration_from_velocity_ms2'])==pytest.approx(4/mass)


def test_real_simulation_and_registered_failure_evidence(tools):
    result=tools.dispatch('run_simulation',{'scenario_id':'A','controller_variant':'faulty'})['result']
    assert result['simulation_execution']=='PASS'
    assert result['physical_safety_status']=='FAIL'
    assert result['independent_verification']=='PASS'
    assert result['braking_onset']['time']==pytest.approx(1.375)
    assert result['first_wall_contact']['time']==pytest.approx(1.49)
    assert result['contact_velocity_ms']>0
    evidence=tools.dispatch('inspect_failure',{'simulation_run_id':result['simulation_run_id']})['result']
    assert evidence['evidence']['controller']['source_sha256']==sha256(ROOT/TARGET)
    assert evidence['evidence']['safety_acceptance']['status']=='FAIL'
    assert 'physical_failure_explanation' not in evidence['evidence']
    for relative in result['artifact_references'].values():
        assert (tools.output/relative).exists()
    assert len(json.loads((tools.output/result['artifact_references']['telemetry.json']).read_text())['samples'])==601


def test_registered_artifact_tampering_is_rejected(tools):
    result=tools.run_simulation('A','faulty')
    path=tools.output/result['artifact_references']['telemetry.json']
    path.write_text('{}')
    with pytest.raises(ValueError,match='integrity'):
        tools.inspect_failure(result['simulation_run_id'])


@pytest.mark.rendering
def test_real_simulation_tool_preserves_native_frames(tmp_path):
    trace=ExecutionTrace(tmp_path/'trace.jsonl',model_mode='deterministic_mock')
    tools=AgentTools(tmp_path/'tools',trace,save_render=True)
    result=tools.dispatch('run_simulation',{'scenario_id':'A','controller_variant':'faulty'})['result']
    manifest_path=tools.output/result['artifact_references']['manifest.json']
    manifest=json.loads(manifest_path.read_text())
    frames=manifest['rendering']['frames']
    assert len(frames)==6
    for frame in frames:
        path=manifest_path.parent/frame['path']
        assert sha256(path)==frame['sha256']
        assert min(frame['visible_geom_pixels'].values())>20
        with Image.open(path) as image:
            assert image.size==(1024,768) and image.format=='PNG'


def mock_turns():
    yield ModelTurn(tool_calls=(ToolCall('read','read_project',{'path':TARGET}),))
    yield ModelTurn(tool_calls=(ToolCall('robot','get_robot_context',{'scenario_id':'A'}),))
    yield ModelTurn(tool_calls=(ToolCall('world','get_world_context',{'scenario_id':'A'}),))
    yield ModelTurn(tool_calls=(ToolCall('run','run_simulation',{'scenario_id':'A','controller_variant':'faulty'}),))
    def inspect(messages,schemas):
        run=json.loads(messages[-1]['content'])['result']
        return ModelTurn(tool_calls=(ToolCall('inspect','inspect_failure',{'simulation_run_id':run['simulation_run_id']}),))
    yield inspect
    def propose(messages,schemas):
        source=json.loads(next(m['content'] for m in messages if m.get('name')=='read_project'))['result']
        return ModelTurn(tool_calls=(ToolCall('patch','propose_patch',{'target_path':TARGET,
            'expected_original_sha256':source['sha256'],'proposed_source':source['content']+'\n# MOCK fixture: comment only; no repair.\n',
            'explanation':'MOCK transport exercise, not a claimed robotics fix'}),))
    yield propose
    yield ModelTurn('MOCK: tooling exercised; candidate execution is blocked. No repair was verified.')


def test_mock_agent_calls_all_real_tools_and_separately_verifies_proposal(tools):
    original=sha256(ROOT/TARGET)
    result=AgentOrchestrator(MockModelAdapter(mock_turns()),tools,tools.trace).run('Inspect the scenario and exercise proposal plumbing.')
    assert result['orchestration_status']=='COMPLETED' and result['tool_calls']==6
    assert result['model_mode']=='deterministic_mock'
    assert result['repair_verified'] is False
    assert result['candidate_verifications'][0]['verification_execution']=='BLOCKED'
    assert sha256(ROOT/TARGET)==original
    rows=read_trace(tools.trace.path)
    assert {r['payload']['name'] for r in rows if r['event']=='tool_completed'}==set(CONTRACTS)
    assert any(r['event']=='candidate_verification' for r in rows)
    assert all(r['payload']['mode']=='deterministic_mock' for r in rows if r['event']=='model_completed')


def test_model_claim_does_not_override_measured_verification(tools):
    result=AgentOrchestrator(MockModelAdapter([ModelTurn('All repairs are verified and safe!')]),tools,tools.trace).run('test')
    assert result['orchestration_status']=='COMPLETED'
    assert not result['repair_verified'] and not result['model_text_is_verification_evidence']


def test_validated_candidate_cannot_bypass_execution_boundary_via_simulation_tool(tools):
    source=tools.read_project(TARGET)
    candidate=tools.propose_patch(TARGET,source['sha256'],source['content']+'\n# fixture only\n','MOCK fixture')
    result=tools.dispatch('run_simulation',{'scenario_id':'C','controller_variant':candidate['candidate_id']})
    assert result['ok'] and result['result']['simulation_execution']=='BLOCKED'
    assert result['result']['physical_safety_status']=='NOT_EVALUATED'
    assert not list(tools.output.rglob('telemetry.json'))


def test_failed_workflow_preserves_existing_trace(tmp_path):
    from core.day4 import evidence_stage
    with pytest.raises(RuntimeError,match='failure fixture'):
        with evidence_stage(tmp_path/'output') as stage:
            trace=ExecutionTrace(stage/'trace.jsonl',model_mode='test_mock')
            trace.append('fixture_failure_observed',{'simulation_attempted':False})
            raise RuntimeError('failure fixture')
    failures=list((tmp_path/'failed').iterdir())
    assert len(failures)==1
    assert read_trace(failures[0]/'trace.jsonl')[-1]['event']=='fixture_failure_observed'
    assert json.loads((failures[0]/'failure.json').read_text())['type']=='RuntimeError'


def test_loop_limits_repeated_ids_and_model_failures_are_recorded(tools):
    call=ModelTurn(tool_calls=(ToolCall('same','read_project',{'path':TARGET}),))
    result=AgentOrchestrator(MockModelAdapter([call,call]),tools,tools.trace).run('test')
    assert result['orchestration_status']=='ERROR' and result['tool_calls']==1
    result=AgentOrchestrator(MockModelAdapter([ModelTurn(tool_calls=(ToolCall('other','read_project',{'path':TARGET}),))]),
                             tools,tools.trace,max_turns=1).run('test')
    assert result['orchestration_status']=='LIMIT_REACHED'
    result=AgentOrchestrator(MockModelAdapter([]),tools,tools.trace).run('test')
    assert result['orchestration_status']=='ERROR'


def test_tool_budget_blocks_before_dispatch(tools):
    turn=ModelTurn(tool_calls=(ToolCall('1','read_project',{'path':TARGET}),ToolCall('2','read_project',{'path':TARGET})))
    result=AgentOrchestrator(MockModelAdapter([turn]),tools,tools.trace,max_tool_calls=1).run('test')
    assert result['orchestration_status']=='ERROR' and result['tool_calls']==0


def test_independent_reference_verifier_really_runs_all_three_scenarios(tools):
    result=tools.verifier.verify_trusted_existing(tools)
    assert result['verification_execution']=='PASS' and result['candidate_code_executed'] is False
    assert set(result['scenarios'])=={'A','B','C'}
    assert all(s['physical_safety_status']=='FAIL' for s in result['scenarios'].values())
    assert all(s['independent_verification']=='PASS' for s in result['scenarios'].values())


def test_no_credentials_does_not_initialize_client_or_make_requests(monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    assert live_integration_status()['status']=='BLOCKED'
    with pytest.raises(CredentialsMissing):
        OpenAIResponsesAdapter.from_environment('explicit-model-name')


def test_responses_mapping_with_explicit_mock_transport():
    class FakeResponses:
        def create(self,**request):
            self.request=request
            return SimpleNamespace(output=[{'type':'function_call','call_id':'f1','name':'read_project',
                                             'arguments':json.dumps({'path':TARGET})},
                                            {'type':'reasoning','id':'mock_reasoning_item','summary':[]}])
    endpoint=FakeResponses()
    model=OpenAIResponsesAdapter(SimpleNamespace(responses=endpoint),'caller-chosen-model',mock_transport=True)
    turn=model.complete(({'role':'user','content':'test'},),())
    assert model.mode=='mock_openai_transport' and turn.tool_calls[0].name=='read_project'
    messages=({'role':'assistant','content':'','provider_items':list(turn.provider_items)},
              {'role':'tool','tool_call_id':'f1','content':'{"ok":true}'})
    model.complete(messages,())
    assert endpoint.request['input'][1]['type']=='reasoning'
    assert endpoint.request['input'][2]=={'type':'function_call_output','call_id':'f1','output':'{"ok":true}'}


def test_trace_integrity_and_exclusive_creation(tmp_path):
    trace=ExecutionTrace(tmp_path/'trace.jsonl',model_mode='test_mock')
    trace.append('example',{'actual':1})
    assert len(read_trace(trace.path))==2
    with pytest.raises(FileExistsError):
        ExecutionTrace(trace.path,model_mode='test_mock')
    trace.path.write_text(trace.path.read_text().replace('"actual": 1','"actual": 2'))
    with pytest.raises(ValueError,match='integrity'):
        read_trace(trace.path)
