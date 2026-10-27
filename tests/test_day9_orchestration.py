"""Explicitly mocked model transport; real scoped validation, no candidate execution."""
import pytest
from core.agent.models import MockModelAdapter,ModelTurn,ToolCall
from core.agent.orchestration import AgentOrchestrator
from core.agent.trace import ExecutionTrace
from core.agent.patching import read_project_file
from core.robots.arm import TARGET
from core.simulation import ROOT
from ide_api.agent import ReviewTools
from workspace.workflow import Workflow
from tools.day9_experiment import ApprovedReviewVerifier,run


def test_operator_requires_scope_confirmation_before_any_api_or_files(tmp_path,monkeypatch):
    monkeypatch.setattr('tools.day9_experiment.create_openai_client',lambda:pytest.fail('No API'))
    with pytest.raises(ValueError,match='consent'):run(tmp_path/'not_created',confirmation='')
    assert not (tmp_path/'not_created').exists()


def test_same_orchestrator_mocked_model_scoped_review_and_explicit_block(tmp_path,monkeypatch):
    trace=ExecutionTrace(tmp_path/'trace',model_mode='deterministic_mock')
    workflow=Workflow(sessions=tmp_path/'reviews',family='arm',evaluation=False)
    tools=ReviewTools(tmp_path/'tools',trace,workflow=workflow,mode='physical',family='arm')
    original=read_project_file(ROOT,TARGET,{TARGET})
    approved=[]
    def blocked(identifier,*,approved=False,backend=None):
        assert approved is True
        return {'verification':None,'reason':'MOCK approval gate blocked execution'}
    monkeypatch.setattr(workflow,'verify',blocked)
    tools.verifier=ApprovedReviewVerifier(tools,workflow,None)
    calls=[ToolCall('ctx','get_robot_context',{'scenario_id':'arm_nominal'}),
           ToolCall('patch','propose_patch',{'target_path':TARGET,'expected_original_sha256':original['sha256'],
             'proposed_source':original['content']+'\n# mocked model validation-only fixture\n','explanation':'Mock proposal, not a genuine repair'})]
    model=MockModelAdapter([ModelTurn(tool_calls=tuple(calls)),ModelTurn(text='Mock loop complete; candidate BLOCKED')])
    result=AgentOrchestrator(model,tools,trace,max_turns=2,max_tool_calls=2).run('Explicit mock transport test')
    assert result['orchestration_status']=='COMPLETED' and not result['repair_verified']
    assert result['candidate_verifications'][0]['candidate_code_executed'] is False
    assert len(tools.review_ids)==1
