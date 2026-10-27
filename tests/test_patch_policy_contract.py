"""Real validator/discovery alignment. Fixtures are developer edits, not AI repairs."""
import ast
import json

import pytest

from core.agent.patching import (ALLOWED_METHODS, FORBIDDEN_CALLS, RULES, CandidateStore,
                                 TARGET, read_project_file, source_errors, source_policy,
                                 source_violations)
from core.agent.tools import AgentTools, CONTRACTS
from core.agent.trace import ExecutionTrace
from core.simulation import ROOT


@pytest.fixture
def original():
    return read_project_file(ROOT, TARGET)


def test_discovery_contains_authoritative_policy_without_new_tool(tmp_path, original):
    tools = AgentTools(tmp_path, ExecutionTrace(tmp_path/'trace', model_mode='offline_policy_test'))
    schemas = {s['name']: s for s in tools.schemas}
    assert set(schemas) == set(CONTRACTS)
    patch = schemas['propose_patch']
    policy = json.loads(patch['parameters']['properties']['proposed_source']['description'])
    assert policy == source_policy(original['content'])
    assert policy['additional_top_level_helpers_allowed'] is False
    assert policy['top_level_function_count'] == 1
    assert policy['entrypoint'] == {'name': 'faulty_braking_controller',
                                    'arguments': 'model: mujoco.MjModel, data: mujoco.MjData',
                                    'return_annotation': 'None', 'decorators': []}
    assert policy['required_imports_in_order'] == [ast.unparse(n) for n in ast.parse(original['content']).body
                                                  if isinstance(n, (ast.Import, ast.ImportFrom))]
    assert policy['forbidden_bare_name_calls'] == sorted(FORBIDDEN_CALLS)
    assert policy['allowed_attribute_calls'] == {k: sorted(v) for k, v in ALLOWED_METHODS.items()}
    assert policy['original_sha256'] == original['sha256']
    assert policy['authorized_target'] == TARGET and not policy['other_files_modifiable']
    assert set(policy['rules']) == set(RULES)
    assert patch['parameters']['additionalProperties'] is False
    assert set(patch) == {'type', 'name', 'description', 'parameters', 'strict'}
    json.dumps(list(schemas.values()), allow_nan=False)


def test_helper_rejection_has_exact_rule_and_location(tmp_path, original):
    source = original['content'] + '\ndef extra_helper():\n    return 1\n'
    result = CandidateStore(ROOT, tmp_path).propose(target_path=TARGET,
        expected_original_sha256=original['sha256'], proposed_source=source, explanation='Offline negative fixture')
    assert result['validation_status'] == 'REJECTED' and result['candidate_id'] is None
    assert result['violations'] == source_violations(original['content'], source)
    entry = next(v for v in result['violations'] if v['rule_id'] == 'single_entrypoint')
    assert entry['location']['line'] == source.splitlines().index('def extra_helper():') + 1
    assert 'additional top-level helpers are forbidden' in entry['explanation']
    assert result['source_policy']['top_level_function_count'] == 1
    assert 'compliant' in result['revision_request']
    assert result['execution_authorized'] is False
    assert not list(tmp_path.rglob('controller.py'))
    assert read_project_file(ROOT, TARGET) == original


@pytest.mark.parametrize('operation', sorted(FORBIDDEN_CALLS))
def test_each_advertised_forbidden_operation_is_rejected(operation, original):
    source = original['content'].replace('    joint =', f'    {operation}()\n    joint =', 1)
    found = [v for v in source_violations(original['content'], source) if v['rule_id'] == 'runtime_call']
    assert found and found[0]['message'] == f'Forbidden runtime operation: {operation}'
    assert found[0]['location']['line'] == source.splitlines().index(f'    {operation}()') + 1


@pytest.mark.parametrize('receiver,method', [(r, m) for r, methods in ALLOWED_METHODS.items() for m in methods])
def test_each_advertised_method_remains_supported(receiver, method, original):
    # Only syntax/policy inspection: no fixture is executed or physically endorsed.
    source = original['content'].replace('    joint =', f'    {receiver}.{method}()\n    joint =', 1)
    assert not source_errors(original['content'], source)


def test_valid_single_entrypoint_and_policy_derived_from_changed_original(tmp_path, original):
    source = original['content'] + '\n# Harmless developer fixture: preserve baseline behavior.\n'
    record = CandidateStore(ROOT, tmp_path).propose(target_path=TARGET,
        expected_original_sha256=original['sha256'], proposed_source=source, explanation='Offline syntax fixture')
    assert record['validation_status'] == 'VALID'
    assert record['execution_authorized'] is False
    assert (next(tmp_path.rglob('controller.py'))).read_text() == source
    renamed = original['content'].replace('faulty_braking_controller', 'another_entry')
    assert source_policy(renamed)['entrypoint']['name'] == 'another_entry'
    assert source_policy(renamed)['original_sha256'] != original['sha256']
    assert not source_errors(renamed, renamed+'\n# fixture\n')


@pytest.mark.parametrize('change,rule', [
    ('import os\n', 'imports_unchanged'),
    ('class Extra: pass\n', 'module_structure'),
    ('FLAG = True\n', 'module_structure'),
    ('COUNT: int = 1\n', 'module_structure'),
])
def test_module_restrictions_are_unchanged(change, rule, original):
    found = source_violations(original['content'], original['content']+'\n'+change)
    assert rule in {v['rule_id'] for v in found}
    assert all(v['rule_id'] in source_policy(original['content'])['rules'] for v in found)


@pytest.mark.parametrize('statement,rule', [
    ('import os', 'nested_effects'), ('global hidden', 'nested_effects'),
    ('model.opt.timestep = 1', 'state_writes'), ('data.qvel[0] = 0', 'state_writes'),
    ('model.__class__', 'public_attributes'), ('data.reset()', 'method_call'),
])
def test_ast_restrictions_report_precise_rules(statement, rule, original):
    source = original['content'].replace('    joint =', f'    {statement}\n    joint =', 1)
    assert rule in {v['rule_id'] for v in source_violations(original['content'], source)}


def test_metadata_does_not_invent_blanket_bare_call_or_nested_helper_ban(original):
    source = original['content'].replace('    joint =', '    def local_helper():\n        return 1\n    local_helper()\n    joint =', 1)
    assert not source_errors(original['content'], source)


def test_file_boundaries_and_isolation_are_not_relaxed(tmp_path, original):
    tools = AgentTools(tmp_path, ExecutionTrace(tmp_path/'trace', model_mode='offline_policy_test'))
    for path in ('core/simulation.py', 'configs/bodybase.json', 'tests/test_candidate_validation.py',
                 '.env', '/etc/passwd', '../robot/controller.py'):
        record = tools.dispatch('propose_patch', {'target_path': path,
            'expected_original_sha256': original['sha256'], 'proposed_source': original['content']+'\n# fixture\n',
            'explanation': 'Offline forbidden path fixture'})
        assert record['ok'] is False
        assert record['error']['violations'][0]['rule_id'] == 'patch_target'
    assert not list(tmp_path.rglob('controller.py'))
    assert read_project_file(ROOT, TARGET) == original


def test_stale_hash_and_no_change_feedback(tmp_path, original):
    result = CandidateStore(ROOT, tmp_path).propose(target_path=TARGET,
        expected_original_sha256='0'*64, proposed_source=original['content'], explanation='Offline stale fixture')
    assert {v['rule_id'] for v in result['violations']} == {'original_hash', 'source_changed'}
