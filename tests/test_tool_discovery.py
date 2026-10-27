"""Expose existing capabilities without changing tool or execution permissions."""
import pytest

from core.agent.patching import READ_ALLOWLIST, TARGET
from core.agent.tools import AgentTools, CONTRACTS
from core.agent.trace import ExecutionTrace


@pytest.fixture
def tools(tmp_path):
    return AgentTools(tmp_path/'tools',ExecutionTrace(tmp_path/'trace',model_mode='offline_tool_metadata_test'))


def schemas(tools):
    return {s['name']: s['parameters']['properties'] for s in tools.schemas}


def test_all_authorized_source_paths_are_discoverable_and_secrets_excluded(tools):
    properties=schemas(tools)
    assert set(properties)==set(CONTRACTS)
    assert set(properties['read_project']['path']['enum'])==READ_ALLOWLIST
    assert 'robot/controller.py' in properties['read_project']['path']['enum']
    assert '.env' not in properties['read_project']['path']['enum']
    assert properties['propose_patch']['target_path']['enum']==[TARGET]
    assert tools.dispatch('read_project',{'path':'.env'})['ok'] is False


def test_scenario_and_existing_controller_identifiers_are_exposed(tools):
    properties=schemas(tools)
    for name in ('get_robot_context','get_world_context','run_simulation'):
        assert properties[name]['scenario_id']['enum']==['A','B','C']
    assert properties['run_simulation']['controller_variant']['enum']==['faulty']
    assert tools.dispatch('run_simulation',{'scenario_id':'A','controller_variant':'invented'})['ok'] is False


def test_only_validated_candidate_ids_enter_schema_and_execution_stays_blocked(tools):
    original=tools.read_project(TARGET)
    proposal=tools.propose_patch(TARGET,original['sha256'],original['content']+'\n# Metadata-only test fixture; no repair.\n',
                                 'Offline developer fixture; not a model repair')
    assert proposal['validation_status']=='VALID'
    assert schemas(tools)['run_simulation']['controller_variant']['enum']==['faulty',proposal['candidate_id']]
    result=tools.dispatch('run_simulation',{'scenario_id':'A','controller_variant':proposal['candidate_id']})
    assert result['result']['simulation_execution']=='BLOCKED'
    assert result['result']['candidate_verification']['candidate_code_executed'] is False
    assert tools.read_project(TARGET)==original


def test_registered_measured_simulation_ids_become_discoverable(tools):
    assert 'enum' not in schemas(tools)['inspect_failure']['simulation_run_id']
    run=tools.dispatch('run_simulation',{'scenario_id':'A','controller_variant':'faulty'})
    assert run['ok'] and run['result']['simulation_execution']=='PASS'
    run_id=run['result']['simulation_run_id']
    assert schemas(tools)['inspect_failure']['simulation_run_id']['enum']==[run_id]
    evidence=tools.dispatch('inspect_failure',{'simulation_run_id':run_id})
    assert evidence['ok'] and evidence['result']['simulation_run_id']==run_id
