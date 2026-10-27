"""Local startup checks never install, run physics, load credentials or call GPT."""
import json
from pathlib import Path
import subprocess
import sys
import pytest
from ide_api.startup import check
from core.simulation import ROOT

def test_installed_environment_and_actual_production_assets_pass(monkeypatch):
    monkeypatch.setattr('core.agent.credentials.create_openai_client',lambda:pytest.fail('No client'))
    monkeypatch.setattr('world.simulation.run',lambda *a,**k:pytest.fail('No simulation'))
    result=check();assert result['status']=='READY' and result['model_requests']==result['native_runs']==0
    assert result['dependencies']['mujoco']=='3.16.0'

@pytest.mark.parametrize('issue',['missing','wrong','old_numpy','old_pillow','build','asset','escape'])
def test_startup_errors_are_actionable_without_install(tmp_path,monkeypatch,issue):
    from importlib import metadata
    original=metadata.version
    def version(name):
        if issue=='missing' and name=='mujoco':raise metadata.PackageNotFoundError(name)
        if issue=='wrong' and name=='mujoco':return '0.0.0'
        if issue=='old_numpy' and name=='numpy':return '1.0.0'
        if issue=='old_pillow' and name=='Pillow':return '9.0.0'
        return original(name)
    monkeypatch.setattr('ide_api.startup.metadata.version',version)
    if issue in ('build','asset','escape'):
        root=tmp_path;folder=root/'frontend/dist';folder.mkdir(parents=True)
        if issue!='build':(folder/'index.html').write_text('<script src="/assets/'+('../secret' if issue=='escape' else 'missing.js')+'"></script>')
    else:root=ROOT
    with pytest.raises(ValueError,match='environment|build|dependencies|minimum|Missing'):check(root)

def test_check_only_entrypoint_exits_without_service_or_credentials():
    run=subprocess.run([sys.executable,'-m','tools.start','--check'],cwd=ROOT,capture_output=True,text=True,timeout=30)
    assert run.returncode==0,run.stderr
    result=json.loads(run.stdout);assert result['status']=='READY' and result['model_requests']==0

def test_health_is_read_only_same_origin_and_not_an_execution_gate(http):
    client,server=http
    before=server.jobs.copy();response=client.get('/api/health');assert response.status_code==200,response.text
    assert response.json()['model_requests']==0 and response.json()['native_runs']==0
    assert client.get('/api/health',params={'extra':'bad'}).status_code==400
    assert client.post('/api/health',json={}).status_code==404
    assert client.get('/api/health',headers={'Host':'attacker'}).status_code==403
    assert server.jobs==before

from tests.test_ide_api import service,http
