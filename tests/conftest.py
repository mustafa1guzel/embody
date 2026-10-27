"""Offline tests must never consume a developer's real local API credentials."""
import pytest


@pytest.fixture(autouse=True)
def isolate_api_credentials(monkeypatch, tmp_path):
    from core.agent import credentials
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    monkeypatch.setattr(credentials, 'PROJECT_ENV_PATH', tmp_path / 'absent.env')
