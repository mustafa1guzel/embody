"""Real same-origin HTTP and deterministic device workflow, no model or VM."""
import pytest
from test_ide_api import http,finish
from ide_api.service import IDE
from ide_api.hardware import HardwareService
from hardware.template import barrier
from hardware.assemblies import identity,endpoint
from hardware.agent import HardwareTools
from core.agent.tools import AgentTools
from core.agent.trace import ExecutionTrace
from devices.contracts import DeviceSpec
from core.agent.vm_backend import AppleVMBackend


@pytest.fixture
def service(tmp_path):
    value=IDE();value._hardware=HardwareService(tmp_path/'hardware');return value


def test_hardware_startup_inspection_never_calls_model_or_vm(http,monkeypatch):
    client,server=http
    def forbidden(*a,**kw):raise AssertionError('No model/VM authorized')
    monkeypatch.setattr('ide_api.server.run_live',forbidden);monkeypatch.setattr(AppleVMBackend,'preflight',forbidden)
    b=client.get('/api/hardware/bootstrap');assert b.status_code==200
    assert b.json()['planner_origin'].startswith('HUMAN_DEFINED_TEMPLATE')
    d=client.post('/api/hardware/validate',json={'assembly':b.json()['template']})
    assert d.status_code==200 and d.json()['errors']==0 and server.jobs=={}


def test_graph_edit_save_load_and_device_run_share_actual_assembly(http):
    client,_=http;a=barrier()
    r=client.post('/api/hardware/edit',json={'assembly':a,'operation':{'kind':'transform','component':'sensor','position_m':[.1,.2,.3],'rotation_rad':[0,.1,.2]}})
    assert r.status_code==200;a=r.json()
    saved=client.post('/api/hardware/save',json={'assembly':a});assert saved.status_code==200
    restored=client.get('/api/hardware/load',params={'key':saved.json()['key']}).json();assert restored==a
    result=finish(client,client.post('/api/device/run',json={'assembly':restored,'spec':DeviceSpec().to_dict()}))
    assert result['status']=='COMPLETED'
    r=result['result'];assert r['status']=='VERIFIED_IN_SIMULATION' and r['assembly_sha256']==identity(a)
    assert len(r['samples'])==4001 and r['evidence_path']


def test_hardware_csrf_source_injection_and_path_attacks(http):
    client,_=http
    assert client.post('/api/hardware/save',json={'assembly':barrier()},headers={'X-EMBODY-Token':''}).status_code==403
    assert client.post('/api/hardware/save',json={'assembly':barrier()},headers={'Origin':'https://evil.invalid'}).status_code==403
    assert client.get('/api/hardware/load',params={'key':'../secret'}).status_code==400
    assert client.post('/api/device/run',json={'assembly':barrier(),'spec':DeviceSpec().to_dict(),'source':'untrusted'}).status_code==400
    assert client.post('/api/hardware/edit',json={'assembly':barrier(),'operation':{'kind':'write','path':'robot/controller.py'}}).status_code==400


def test_hardware_agent_extends_traced_tools_without_mutation_or_authority(tmp_path):
    a=barrier();base=AgentTools(tmp_path/'tools',ExecutionTrace(tmp_path/'trace.jsonl',model_mode='mock'))
    tools=HardwareTools(base,a,DeviceSpec().to_dict())
    assert len(base.schemas)==6 and len(tools.schemas)==8
    assert tools.verifier is base.verifier and tools.candidates is base.candidates
    inspected=tools.dispatch('inspect_hardware',{});assert inspected['ok']
    assert inspected['result']['electrical']['errors']==0
    import json
    proposed=tools.dispatch('propose_hardware_change',{'expected_sha256':identity(a),'expected_revision':a['revision'],'operations':[{'kind':'connect','a':endpoint('sensor','ECHO'),'b':endpoint('board','IO19')}],'explanation':'Explicitly simulated model-tool fixture; no live GPT request.'})
    assert proposed['ok'] and proposed['result']['status']=='PROPOSED_NOT_APPLIED'
    assert tools.assembly==a and proposed['result']['diagnostics']['errors']>0
    blocked=tools.dispatch('propose_hardware_change',{'expected_sha256':identity(a),'expected_revision':a['revision'],'operations':[{'kind':'exec','source':'bad'}],'explanation':'Negative fixture'})
    assert not blocked['ok'] and tools.assembly==a
    assert tools.dispatch('read_project',{'path':'robot/controller.py'})['ok']


def test_hardware_adapter_uses_existing_orchestrator_with_explicit_mock_only(tmp_path):
    from core.agent.orchestration import AgentOrchestrator
    from core.agent.models import MockModelAdapter,ModelTurn,ToolCall
    trace=ExecutionTrace(tmp_path/'trace.jsonl',model_mode='deterministic_mock')
    base=AgentTools(tmp_path/'tools',trace);tools=HardwareTools(base,barrier(),DeviceSpec().to_dict())
    model=MockModelAdapter([ModelTurn(tool_calls=(ToolCall('inspect','inspect_hardware',{}),)),ModelTurn(text='Explicit mock: inspect diagnostics and request review; no live model action occurred.')])
    report=AgentOrchestrator(model,tools,trace,max_turns=2,max_tool_calls=1).run('Inspect supported hardware')
    assert report['orchestration_status']=='COMPLETED' and report['model_mode']=='deterministic_mock'
    assert report['tool_calls']==1 and not report['repair_verified']
