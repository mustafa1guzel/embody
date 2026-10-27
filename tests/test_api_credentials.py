"""Dummy credentials and mocked HTTP only; never read the developer's .env."""
import json
import logging
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip('dotenv', reason='Optional API dependencies are not installed')

from core.agent import credentials
from core.agent.credentials import (CredentialConfigurationError, CredentialsMissing,
                                    ModelRequestError, read_openai_api_key)
from core.agent.models import OpenAIResponsesAdapter
from core.agent.orchestration import AgentOrchestrator
from core.agent.trace import ExecutionTrace
from tools import openai_connectivity


def private_env(tmp_path, content):
    path = tmp_path / '.env'
    path.write_text(content)
    path.chmod(0o600)
    return path


@pytest.mark.parametrize('assignment', [
    'OPENAI_API_KEY=dummy-key', 'OPENAI_API_KEY="dummy-key"',
    "export OPENAI_API_KEY='dummy-key' # comment",
])
def test_loads_private_file_without_exporting_environment(tmp_path, assignment):
    path = private_env(tmp_path, assignment + '\nOPENAI_BASE_URL=https://example.invalid\n')
    before = dict(os.environ)
    assert read_openai_api_key(path) == 'dummy-key'
    assert dict(os.environ) == before


def test_environment_takes_precedence_without_reading_file(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'dummy-environment-key')
    assert read_openai_api_key(tmp_path / 'absent.env') == 'dummy-environment-key'


def test_no_interpolation_or_shell_evaluation(tmp_path, monkeypatch):
    monkeypatch.setenv('OTHER_SECRET', 'do-not-expand')
    path = private_env(tmp_path, "OPENAI_API_KEY='${OTHER_SECRET}'\nUNRELATED=$(false)\n")
    assert read_openai_api_key(path) == '${OTHER_SECRET}'


@pytest.mark.parametrize('content', [
    '', 'OTHER_KEY=ignored', 'OPENAI_API_KEY=',
])
def test_missing_or_empty_key_does_not_make_request(tmp_path, content):
    with pytest.raises(CredentialsMissing):
        read_openai_api_key(private_env(tmp_path, content))


@pytest.mark.parametrize('content', [
    'OPENAI_API_KEY=one\nOPENAI_API_KEY=two',
    'OPENAI_API_KEY="unterminated',
    'OPENAI_API_KEY="first\nsecond"',
    'OPENAI_API_KEY="contains space"',
    'OPENAI_API_KEY=' + 'x' * credentials.MAX_ENV_BYTES,
])
def test_invalid_file_is_rejected_without_exposing_values(tmp_path, content, caplog):
    with pytest.raises(CredentialConfigurationError) as error:
        read_openai_api_key(private_env(tmp_path, content))
    assert content not in str(error.value)
    assert not caplog.text


def test_symlinks_and_shared_permissions_are_rejected(tmp_path):
    original = private_env(tmp_path, 'OPENAI_API_KEY=dummy-private-key')
    link = tmp_path / 'linked.env'
    link.symlink_to(original)
    with pytest.raises(CredentialConfigurationError):
        read_openai_api_key(link)
    original.chmod(0o644)
    with pytest.raises(CredentialConfigurationError, match='0600'):
        read_openai_api_key(original)


def test_no_parent_directory_discovery(tmp_path, monkeypatch):
    private_env(tmp_path, 'OPENAI_API_KEY=dummy-parent-key')
    child = tmp_path / 'child'
    child.mkdir()
    monkeypatch.chdir(child)
    monkeypatch.setattr(credentials, 'PROJECT_ENV_PATH', child / '.env')
    with pytest.raises(CredentialsMissing):
        read_openai_api_key()


def test_factory_loads_project_file_pins_host_and_disables_retries(tmp_path, monkeypatch):
    openai = pytest.importorskip('openai')
    path = private_env(tmp_path, 'OPENAI_API_KEY=dummy-file-key')
    monkeypatch.setattr(credentials, 'PROJECT_ENV_PATH', path)
    monkeypatch.setenv('OPENAI_BASE_URL', 'https://untrusted.invalid')
    monkeypatch.setenv('HTTPS_PROXY', 'https://untrusted.invalid')
    calls = []

    class Transport:
        def __init__(self, **kwargs):
            calls.append(('transport', kwargs))

    def client(**kwargs):
        calls.append(('client', kwargs))
        return SimpleNamespace()

    monkeypatch.setattr(openai, 'DefaultHttpxClient', Transport)
    monkeypatch.setattr(openai, 'OpenAI', client)
    model = OpenAIResponsesAdapter.from_environment('explicit-model')
    assert model.requests_made == 0
    transport, client = calls[0][1], calls[1][1]
    assert transport['trust_env'] is False and transport['follow_redirects'] is False
    assert transport['verify'].check_hostname is True
    assert client['api_key'] == 'dummy-file-key'
    assert client['base_url'] == 'https://api.openai.com/v1'
    assert client['max_retries'] == 0 and client['timeout'] == 15.0
    assert 'OPENAI_API_KEY' not in os.environ


def test_provider_exception_never_reaches_agent_trace(tmp_path, capsys):
    secret = 'dummy-provider-echoed-key'

    def fail(**kwargs):
        raise RuntimeError('Incorrect API key provided: ' + secret)

    model = OpenAIResponsesAdapter(SimpleNamespace(responses=SimpleNamespace(create=fail)),
                                   'test-model', mock_transport=True)
    path = tmp_path / 'trace.jsonl'
    result = AgentOrchestrator(model, SimpleNamespace(schemas=()),
                               ExecutionTrace(path, model_mode=model.mode)).run('Dummy test')
    assert result['orchestration_status'] == 'ERROR'
    assert 'ModelRequestError' in path.read_text()
    assert secret not in path.read_text()
    assert secret not in repr(capsys.readouterr())


@pytest.mark.parametrize('status', [200, 401, 429])
def test_connectivity_makes_exactly_one_http_request_without_generation(monkeypatch, status, caplog):
    openai = pytest.importorskip('openai')
    # Use the transport bundled with the pinned SDK, rather than invoking a server.
    import httpx2 as httpx
    secret = 'dummy-api-key-for-mock-http'
    requests = []

    def serve(request):
        requests.append(request)
        assert request.headers['authorization'] == 'Bearer ' + secret
        assert request.method == 'GET' and request.url.path == '/v1/models'
        body = {'object': 'list', 'data': []} if status == 200 else {
            'error': {'message': 'Incorrect API key provided: ' + secret,
                      'type': 'authentication_error', 'code': 'invalid_api_key'}}
        return httpx.Response(status, json=body)

    credentials._disable_transport_logging()
    client = openai.OpenAI(api_key=secret, max_retries=0,
                           http_client=httpx.Client(transport=httpx.MockTransport(serve)))
    monkeypatch.setattr(openai_connectivity, 'create_openai_client', lambda: client)
    with caplog.at_level(logging.DEBUG):
        result = openai_connectivity.check_connectivity()
    assert len(requests) == result['requests_attempted'] == 1
    assert result['http_status'] == status
    assert result['status'] == ('PASS' if status == 200 else 'FAIL')
    assert result['generation_requests'] == 0 and result['agent_experiment_started'] is False
    assert secret not in json.dumps(result) and secret not in caplog.text
    assert client.is_closed


def test_transport_logs_suppressed_even_for_late_created_children(caplog):
    credentials._disable_transport_logging()
    with caplog.at_level(logging.DEBUG):
        logging.getLogger('openai.late_created_test_child').error('dummy-secret')
        logging.getLogger('httpx2.late_created_test_child').error('dummy-secret')
    assert 'dummy-secret' not in caplog.text


def test_no_secret_file_exposed_by_read_project():
    from core.agent.patching import read_project_file
    root = Path(__file__).resolve().parents[1]
    with pytest.raises(ValueError):
        read_project_file(root, '.env')
    ignore = (root / '.gitignore').read_text().splitlines()
    assert '.env' in ignore and '.env.*' in ignore
