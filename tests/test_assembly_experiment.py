"""Explicit OFFLINE mock protocol tests, not genuine GPT decisions or receipts."""
import copy
import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator

from core.agent.api_budget import ApiBudget, GPT54_POLICY, BudgetBlocked
from core.agent.live_model import BudgetedOpenAIAdapter
from core.agent.trace import ExecutionTrace
from engineering.assembly import AssemblyComposer
from engineering.assembly_examples import rover_plan
from engineering.assembly_experiment import (CAP, INPUT_BOUND, OUTPUT_BOUND, FEEDBACK_BYTES,
    TASK, audit_completed_protocol, check_manifest, continuation, feedback, forward_measurement, inspect,
    parse_call, policy, request_first, run_protocol, serialized_bounds)
from engineering.assembly_revision import proposal_schema
from engineering.project import new_project, identity
from ide_api.engineering import EngineeringService
from physics.contracts import digest

@pytest.fixture
def c(tmp_path):
    p=new_project();p['world']['environment']['duration_s']=1
    return AssemblyComposer(EngineeringService(tmp_path/'project',initial_project=p))

def plan(*,bad=False):
    p=rover_plan(label='offline_protocol')
    if bad:p['steps'][0]['operations'][0]['mass_kg']=2
    return p

def raw_call(index,name,args):
    return {'status':'completed','id':f'mock_resp_{index}','model':'gpt-5.4-2026-03-05','service_tier':'default',
        'output':[{'type':'function_call','name':name,'call_id':f'mock_call_{index}','arguments':json.dumps(args)}],
        'usage':{'input_tokens':1000,'output_tokens':100,'total_tokens':1100,
            'input_tokens_details':{'cached_tokens':0},'output_tokens_details':{'reasoning_tokens':20}}}

def mock_adapter(tmp_path,c,plans):
    requests=[];returned=[]
    def create(**body):
        index=len(requests);requests.append(copy.deepcopy(body))
        if index==0:name='inspect_assembly_capabilities';args={}
        else:
            last=json.loads(body['input'][0]['output'])
            args={'expected_sha256':identity(c.service.current()),'expected_revision':0,
                'revision_of':last.get('failure_id'),'plan':copy.deepcopy(plans[index-1])}
            name='propose_assembly_plan'
        r=raw_call(index,name,args);returned.append(r)
        return SimpleNamespace(model_dump=lambda **kw:copy.deepcopy(r))
    client=SimpleNamespace(max_retries=0,responses=SimpleNamespace(create=create))
    budget=ApiBudget(tmp_path/'offline_mock_ledger.json',policy=GPT54_POLICY,limit=CAP,max_requests=3,
        input_token_bound=INPUT_BOUND,max_output_tokens=OUTPUT_BOUND)
    trace=ExecutionTrace(tmp_path/'trace.jsonl',model_mode='OFFLINE_MOCK_PROTOCOL_NOT_LIVE')
    return BudgetedOpenAIAdapter(client,budget,tmp_path/'mock_api',trace),trace,requests,returned

def test_inspection_is_actual_and_typed_contracts_are_complete(c):
    p=c.service.current();obs=inspect(c)
    assert obs['project']['world']==p['world'] and obs['project']['sha256']==identity(p)
    assert obs['construction_defaults']['primitive_defaults']['rigid_link']['mass_kg']>0
    assert obs['limits']['native']['max_total_mass_kg']==2
    assert obs['experiment_contract']['forward_acceptance']['minimum_signed_displacement_m']==.005
    schema=proposal_schema()[0]['parameters'];Draft202012Validator.check_schema(schema)
    ops=schema['properties']['plan']['properties']['steps']['items']['properties']['operations']['items']['anyOf']
    kinds={o['properties']['kind']['enum'][0]:o for o in ops}
    root=kinds['create_free_root'];assert set(root['required'])=={'kind','id','mass_kg','position_m','dimensions_m'}
    assert 'dynamic_body' not in kinds['create_object']['properties']['primitive']['enum']
    assert kinds['create_joint']['properties']['joint']['anyOf'][0]['properties']['kind']['enum']==['revolute','prismatic']
    assert c.service.current()==p and max(serialized_bounds(obs))<=INPUT_BOUND

@pytest.mark.parametrize('revise',[False,True])
def test_budgeted_mock_continuation_and_author_arguments_are_preserved(c,tmp_path,revise):
    supplied=[plan(bad=True),plan()] if revise else [plan()]
    adapter,trace,requests,returned=mock_adapter(tmp_path,c,supplied);head=c.service.current()
    result=run_protocol(adapter,c,trace,tmp_path/'protocol',lambda:None)
    assert result['status']=='COMPILED_REVIEW_READY' and len(requests)==(3 if revise else 2)
    assert result['proposal']['assembly_plan']==supplied[-1] and c.service.current()==head
    for i,body in enumerate(requests):
        assert body['model']=='gpt-5.4' and body['reasoning']=={'effort':'low'} and body['max_output_tokens']==8192
        if i:
            assert body['previous_response_id']==returned[i-1]['id']
            assert body['input'][0]['call_id']==returned[i-1]['output'][0]['call_id']
    if revise:
        actual=json.loads(requests[2]['input'][0]['output'])
        assert actual==feedback(result['attempts'][1]['output'])
        assert 'TOTAL_MASS' in {d['code'] for d in actual['assessment']['diagnostics']}
        assert result['attempts'][2]['arguments']['revision_of']==actual['failure_id']
        assert len(list(c.failures.root.glob('*.json')))==1
    assert not (c.root/'assembly_decisions').exists() and not (c.root/'assembly_native').exists()
    receipt=adapter.budget.snapshot();assert all(r['state']=='SETTLED' for r in receipt['requests'])
    assert Decimal(receipt['accounted_cost_usd'])==Decimal(receipt['measured_cost_usd'])
    # Independently audit the same serialized fake wire format, labelled mock.
    audit_root=tmp_path/'audit';audit_root.mkdir();(tmp_path/'mock_api').rename(audit_root/'api')
    audit=audit_completed_protocol(c,result,audit_root,receipt)
    assert audit['status']=='PASS_COMPLETED_PROTOCOL_EVIDENCE' and audit['additional_integration_steps']==0
    original=json.loads((audit_root/'api/request_001.json').read_text())
    original['previous_response_id']='wrong'
    (audit_root/'api/request_001.json').write_text(json.dumps(original))
    with pytest.raises(ValueError,match='continuation'):audit_completed_protocol(c,result,audit_root,receipt)
    with pytest.raises(ValueError,match='review-only'):
        # Session is explicitly restricted in this fixture before exercising apply.
        from robustness.contracts import write_once
        write_once(c.root/'assembly_session.json',{'review_only':True,'task':TASK})
        c.decide(identity(head),0,result['proposal']['proposal_id'],'apply','APPLY REVIEWED ASSEMBLY')

def test_two_supplied_invalid_plans_are_final_and_never_applied(c,tmp_path):
    adapter,trace,requests,_=mock_adapter(tmp_path,c,[plan(bad=True),plan(bad=True)])
    result=run_protocol(adapter,c,trace,tmp_path/'protocol',lambda:None)
    assert result['status']=='FINAL_REJECTION' and result['proposal'] is None and len(requests)==3
    assert len(list(c.failures.root.glob('*.json')))==2
    assert not list(c.proposals.root.glob('*.json')) and c.service.current()['revision']==0

@pytest.mark.parametrize('mode',['mass','joint','mount','geometry','torque','revision'])
def test_invalid_plan_classes_remain_rejected_without_native(c,tmp_path,mode):
    p=plan();ops=[o for s in p['steps'] for o in s['operations']]
    if mode=='mass':ops[0]['mass_kg']=2
    if mode=='joint':next(o for o in ops if o['kind']=='create_joint' and o['joint'])['joint']['range']=[0,0]
    if mode=='mount':next(o for o in ops if o['kind']=='set_attachment_frame')['target']=p['roles']['root_body_id']
    if mode=='geometry':next(o for o in ops if o['kind']=='create_parametric_part')['part']['parameters']['corner_radius_m']=.09
    if mode=='torque':next(o for o in ops if o['kind']=='set_actuator')['actuator']['limit']=.09
    head=c.service.current()
    if mode=='revision':
        with pytest.raises(ValueError):c.assess(identity(head),1,p)
    else:
        assessment=c.assess(identity(head),0,p)
        assert assessment['status']=='REJECTED' and assessment['diagnostics'] and assessment['native']=='NOT_EXECUTED'
        with pytest.raises(ValueError):c.propose(identity(head),0,p)
    assert c.service.current()==head and not (c.root/'assembly_native').exists()

def test_unlinked_revision_and_head_change_are_terminal(c,tmp_path):
    from engineering.assembly_revision import AssemblyRevisionTools
    t=AssemblyRevisionTools(c,ExecutionTrace(tmp_path/'trace',model_mode='OFFLINE_MOCK'))
    assert t.dispatch('inspect_assembly_capabilities',{})['ok']
    result=t.dispatch('propose_assembly_plan',{'expected_sha256':identity(c.service.current()),'expected_revision':0,
        'revision_of':'f'*64,'plan':plan()})
    assert not result['ok'] and t.done and not list(c.proposals.root.glob('*.json'))
    t=AssemblyRevisionTools(c,ExecutionTrace(tmp_path/'trace2',model_mode='OFFLINE_MOCK'))
    changed=c.service.current();changed['revision']=1
    c.service.current=lambda:changed
    assert not t.dispatch('inspect_assembly_capabilities',{})['ok'] and t.done

@pytest.mark.parametrize('mode',['extra','wrong_tool','multiple','incomplete','duplicate_json','oversized_id'])
def test_malformed_protocol_output_is_not_a_revision_opportunity(mode):
    schema=request_first()['tools'][0];r=raw_call(0,schema['name'],{})
    if mode=='extra':r['output'][0]['arguments']='{"source_code":"no"}'
    if mode=='wrong_tool':r['output'][0]['name']='apply_assembly'
    if mode=='multiple':r['output']*=2
    if mode=='incomplete':r['status']='incomplete'
    if mode=='duplicate_json':r['output'][0]['arguments']='{"a":1,"a":2}'
    if mode=='oversized_id':r['id']='R'*129
    with pytest.raises(Exception):parse_call(r,schema)

def test_full_feedback_is_never_silently_truncated():
    result={'ok':False,'failure_id':'a'*64,'assessment':{'diagnostics':['x'*FEEDBACK_BYTES]},'revision_of':None}
    with pytest.raises(BudgetBlocked,match='without truncation'):feedback(result)

def test_budget_reserves_all_three_and_blocks_a_fourth(c,tmp_path):
    adapter,trace,requests,_=mock_adapter(tmp_path,c,[plan(bad=True),plan(bad=True)])
    run_protocol(adapter,c,trace,tmp_path/'protocol',lambda:None)
    assert Decimal(policy()['worst_case_reservation_usd'])==Decimal('1.2288')
    assert len(adapter.budget.snapshot()['requests'])==3
    with pytest.raises(BudgetBlocked,match='Maximum API request count'):adapter._request(**request_first())
    assert len(requests)==3

@pytest.mark.parametrize('direction',[-1,1])
def test_real_native_directional_check_does_not_call_backward_motion_forward(c,direction):
    p=plan()
    for s in p['steps']:
        for op in s['operations']:
            if op['kind']=='set_actuator':op['actuator']['command']*=direction
    q=c.propose(identity(c.service.current()),0,p)
    n=c.preview_native(q['base_project_sha256'],0,q['proposal_id']);r=forward_measurement(n)
    assert n['observations']['checks']['measurable_horizontal_movement']
    assert n['result']['independent_verification']['status']=='PASS'
    assert (r['signed_forward_displacement_m']>=.005)==(direction==-1)
    assert r['status']==('PASS' if direction==-1 else 'FAIL')
    assert c.service.current()['revision']==0 and r['extra_integration_steps']==0

def test_driver_without_approval_stops_before_manifest_client_or_effects(monkeypatch):
    from tools.phase18e4_live import main
    monkeypatch.setattr('sys.argv',['phase18e4_live.py'])
    with pytest.raises(SystemExit,match='fresh explicit'):main()

@pytest.mark.parametrize('drift',['none','source','input','approval','expiry','policy'])
def test_manifest_identity_guards_fail_closed_on_each_drift(tmp_path,monkeypatch,drift):
    # Small, explicitly mocked source inventory; real byte hashes/preflight logic.
    import engineering.assembly_experiment as e
    from robustness.contracts import file_hash
    source=tmp_path/'source.py';source.write_text('# data only; never executed\n')
    data=tmp_path/'input.json';data.write_text('{}')
    monkeypatch.setattr(e,'source_inventory',lambda root:{'source.py':file_hash(source)})
    d={**policy(),'frozen_unix':1000,'approval_validity_seconds':86400,
        'source_sha256':e.source_inventory(tmp_path),'input_files_sha256':{'input.json':file_hash(data)}}
    if drift=='policy':d['max_requests']=4
    m={'definition':d,'sha256':digest(d)};approval=m['sha256'];now=1001
    if drift=='source':source.write_text('# changed')
    if drift=='input':data.write_text('{"changed":true}')
    if drift=='approval':approval='0'*64
    if drift=='expiry':now=1000+86401
    if drift=='none':assert check_manifest(tmp_path,m,approval,now=now)==d
    else:
        with pytest.raises(ValueError):check_manifest(tmp_path,m,approval,now=now)

def test_transport_error_is_terminal_and_unknown_charge_is_reserved(c,tmp_path):
    adapter,trace,requests,_=mock_adapter(tmp_path,c,[plan()])
    original=adapter.client.responses.create
    def fail_second(**body):
        if len(requests)==1:
            requests.append(body);raise TimeoutError('OFFLINE mock timeout; no real request')
        return original(**body)
    adapter.client.responses.create=fail_second
    with pytest.raises(BudgetBlocked,match='no retry'):
        run_protocol(adapter,c,trace,tmp_path/'protocol',lambda:None)
    ledger=adapter.budget.snapshot();assert len(requests)==len(ledger['requests'])==2
    assert ledger['requests'][-1]['state']=='FAILED_USAGE_UNKNOWN'
    assert not list(c.proposals.root.glob('*.json'))
    assert (tmp_path/'mock_api/error_001.json').is_file()
