"""Day 4A offline infrastructure verification. No live model call or candidate execution."""
from __future__ import annotations
from datetime import datetime, timezone
from contextlib import contextmanager
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from uuid import uuid4

from core.agent.models import MockModelAdapter, ModelTurn, ToolCall, live_integration_status
from core.agent.orchestration import AgentOrchestrator
from core.agent.patching import TARGET
from core.agent.tools import AgentTools, CONTRACTS
from core.agent.trace import ExecutionTrace, read_trace
from core.day2 import file_inventory
from core.simulation import ROOT, DEFAULT_MODEL_PATH, source_hashes, sha256, write_json

DEFAULT_OUTPUT = ROOT / 'artifacts' / 'day4a'


@contextmanager
def evidence_stage(output):
    with tempfile.TemporaryDirectory(prefix='.day4a-',dir=output.parent) as temporary:
        stage=Path(temporary)/'run'
        stage.mkdir()
        try:
            yield stage
        except Exception as exc:
            write_json(stage/'failure.json',{'type':type(exc).__name__,'message':str(exc)})
            failed=output.parent/'failed'/('day4a-'+uuid4().hex)
            failed.parent.mkdir(parents=True,exist_ok=True)
            stage.rename(failed)
            raise


def demonstration_turns():
    """Scripted transport exercise. Reads real results; never generates a braking fix."""
    yield ModelTurn(tool_calls=(ToolCall('read','read_project',{'path':TARGET}),))
    yield ModelTurn(tool_calls=(ToolCall('robot','get_robot_context',{'scenario_id':'A'}),))
    yield ModelTurn(tool_calls=(ToolCall('world','get_world_context',{'scenario_id':'A'}),))
    yield ModelTurn(tool_calls=(ToolCall('run','run_simulation',{'scenario_id':'A','controller_variant':'faulty'}),))
    def inspect(messages,schemas):
        result=json.loads(messages[-1]['content'])['result']
        return ModelTurn(tool_calls=(ToolCall('inspect','inspect_failure',{'simulation_run_id':result['simulation_run_id']}),))
    yield inspect
    def propose(messages,schemas):
        source=json.loads(next(m['content'] for m in messages if m.get('name')=='read_project'))['result']
        return ModelTurn(tool_calls=(ToolCall('patch','propose_patch',{
            'target_path':TARGET,'expected_original_sha256':source['sha256'],
            'proposed_source':source['content']+'\n# MOCK transport fixture only: no controller repair is proposed.\n',
            'explanation':'Deterministic MOCK fixture that exercises source validation and diff generation without changing control behavior.'}),))
    yield propose
    yield ModelTurn('MOCK TRANSPORT: all six tools were exercised. The proposal is a comment-only fixture. Candidate execution is BLOCKED, and no repair is verified.')


def run_offline(output=DEFAULT_OUTPUT, *, pytest_output=None, pytest_exit_code=None):
    output=Path(output).resolve()
    output.parent.mkdir(parents=True,exist_ok=True)
    historical={day:file_inventory(ROOT/'artifacts'/day) for day in ('day1','day2','day3')}
    pinned={str(p.relative_to(ROOT)):sha256(p) for directory in ('robot','configs','tests')
            for p in (ROOT/directory).rglob('*') if p.is_file() and p.suffix in ('.py','.json','.xml')
            and '__pycache__' not in p.parts and not p.name.startswith('test_agent_') and p.name!='test_candidate_validation.py'}
    with evidence_stage(output) as stage:
        trace=ExecutionTrace(stage/'execution_trace.jsonl',model_mode='deterministic_mock')
        tools=AgentTools(stage,trace,save_render=True)
        write_json(stage/'tool_contracts.json',list(tools.schemas))
        report=AgentOrchestrator(MockModelAdapter(demonstration_turns()),tools,trace).run(
            'MOCK infrastructure exercise: inspect source and physical context, simulate, inspect measured evidence, and submit a non-solution fixture proposal.')
        write_json(stage/'agent_result.json',report)
        # These executions are deterministic application verification, not LLM reasoning.
        references=tools.verifier.verify_trusted_existing(tools)
        for scenario in tools.scenarios:
            tools.get_robot_context(scenario)
            tools.get_world_context(scenario)
        rows=read_trace(trace.path)
        actual_tools={r['payload']['name'] for r in rows if r['event']=='tool_completed' and r['payload']['output']['ok']}
        checks={
            'exact_six_tool_interfaces':actual_tools==set(CONTRACTS),
            'mock_orchestration_completed':report['orchestration_status']=='COMPLETED',
            'all_tool_dispatches_succeeded':all(r['payload']['output']['ok'] for r in rows if r['event']=='tool_completed'),
            'real_reference_verification':references['verification_execution']=='PASS',
            'all_abc_references_measured':set(references['scenarios'])=={'A','B','C'},
            'candidate_boundary_honestly_blocked':len(report['candidate_verifications'])==1 and all(
                r['verification_execution']=='BLOCKED' and not r['candidate_code_executed'] for r in report['candidate_verifications']),
            'no_repair_claimed':report['repair_verified'] is False,
            'trace_integrity':bool(rows),
            'previous_artifacts_preserved':all(file_inventory(ROOT/'artifacts'/day)==inventory for day,inventory in historical.items()),
            'previous_sources_and_tests_preserved':all(sha256(ROOT/path)==digest for path,digest in pinned.items()),
            'complete_pytest_execution':pytest_exit_code==0 if pytest_exit_code is not None else False,
        }
        verification={'created_at_utc':datetime.now(timezone.utc).isoformat(),
            'day4a_infrastructure':'PASS' if all(checks.values()) else 'FAIL',
            'checks':{name:'PASS' if value else 'FAIL' for name,value in checks.items()},
            'live_ai_integration':live_integration_status(), 'untrusted_candidate_execution':'BLOCKED',
            'live_model_requests_by_this_offline_workflow':0,
            'candidate_execution_reason':report['candidate_verifications'][0]['reason'],
            'model_provenance':'Deterministic mocked transport only; no live GPT reasoning was produced',
            'real_physics_evidence':references, 'source_sha256':source_hashes(DEFAULT_MODEL_PATH),
            'historical_artifact_sha256':historical,'preserved_source_sha256':pinned,
            'native_visual_inspection':'Pending direct inspection',
            'scope':'API-independent Day 4A infrastructure; no controller fix or original-source overwrite'}
        write_json(stage/'verification.json',verification)
        if pytest_output is not None:
            (stage/'pytest_output.txt').write_text(pytest_output)
        if output.exists():
            archive=output.parent/'archive'
            archive.mkdir(exist_ok=True)
            output.rename(archive/f'day4a-{uuid4()}')
        stage.rename(output)
    return verification


def main():
    command=[sys.executable,'-m','pytest','-ra']
    completed=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,check=False)
    text=completed.stdout+completed.stderr
    print(text,end='',flush=True)
    if completed.returncode:
        failed=ROOT/'artifacts/failed'/('day4a-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
        failed.mkdir(parents=True,exist_ok=True)
        (failed/'pytest_output.txt').write_text(text)
        raise SystemExit(completed.returncode)
    verification=run_offline(pytest_output=text,pytest_exit_code=completed.returncode)
    write_json(DEFAULT_OUTPUT/'pytest_result.json',{'command':command,'exit_code':completed.returncode})
    print(json.dumps({'day4a_infrastructure':verification['day4a_infrastructure'],
                     'live_ai_integration':verification['live_ai_integration'],
                     'untrusted_candidate_execution':verification['untrusted_candidate_execution'],
                     'artifacts':str(DEFAULT_OUTPUT)},indent=2))
    if verification['day4a_infrastructure']!='PASS':
        raise SystemExit(1)


if __name__=='__main__':
    main()
