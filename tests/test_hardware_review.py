"""Bounded review uses deterministic fixtures, never live model claims."""
import copy
from decimal import Decimal
from types import SimpleNamespace
import pytest
from hardware.review import HardwareReviewTools,independently_validate_proposal
from hardware.assemblies import identity,connect,endpoint
from hardware.template import barrier
from devices.contracts import DeviceSpec
from core.agent.trace import ExecutionTrace
from core.agent.models import MockModelAdapter,ModelTurn,ToolCall
from core.agent.orchestration import AgentOrchestrator
from core.agent.api_budget import GPT54_POLICY,cost,ApiBudget,BudgetBlocked


def setup_review(tmp_path):
    a=connect(barrier(),endpoint('sensor','ECHO'),endpoint('board','IO19'))
    trace=ExecutionTrace(tmp_path/'trace.jsonl',model_mode='deterministic_mock')
    tools=HardwareReviewTools(trace,a,DeviceSpec().to_dict())
    args={'expected_sha256':identity(a),'expected_revision':a['revision'],'operations':[{'kind':'disconnect','wire_id':a['wires'][-1]['id']}],'explanation':'Explicit deterministic fixture; not a genuine model result.'}
    return a,tools,args,trace


def test_two_turn_fixture_proposes_then_independently_validates_without_application(tmp_path):
    a,tools,args,trace=setup_review(tmp_path)
    assert {s['name'] for s in tools.schemas}=={'inspect_hardware','propose_hardware_change'}
    model=MockModelAdapter([ModelTurn(tool_calls=(ToolCall('inspect','inspect_hardware',{}),)),ModelTurn(tool_calls=(ToolCall('propose','propose_hardware_change',args),))])
    report=AgentOrchestrator(model,tools,trace,max_turns=2,max_tool_calls=2).run('Deterministic contract fixture')
    assert report['orchestration_status']=='LIMIT_REACHED' and report['model_mode']=='deterministic_mock'
    assert report['tool_calls']==2 and report['candidate_verifications']==[]
    submission=tools.submission;assert submission['output']['ok']
    check=independently_validate_proposal(a,submission['arguments'],submission['output']['result'])
    assert check['status']=='PASS' and check['applied'] is False and check['vm_launches']==0
    assert identity(a)==args['expected_sha256']==identity(tools.assembly)
    assert len(a['wires'])==13


def test_review_allowlist_order_and_no_proposal_retry(tmp_path):
    _,tools,args,_=setup_review(tmp_path)
    for name in ('read_project','propose_patch','run_simulation','apply','inspect_device'):
        with pytest.raises(ValueError,match='Only hardware'):tools.dispatch(name,{})
    with pytest.raises(ValueError,match='after inspection'):tools.dispatch('propose_hardware_change',args)
    assert tools.dispatch('inspect_hardware',{})['ok']
    with pytest.raises(ValueError,match='One inspection'):tools.dispatch('inspect_hardware',{})
    bad={**args,'operations':[{'op':'remove_wire','wire_id':args['operations'][0]['wire_id']}]}
    assert not tools.dispatch('propose_hardware_change',bad)['ok']
    with pytest.raises(ValueError,match='no retry'):tools.dispatch('propose_hardware_change',args)


def test_focused_inspection_keeps_authoritative_electrical_values_and_entire_graph(tmp_path):
    from hardware.library import catalog
    a,tools,_,_=setup_review(tmp_path)
    value=tools.dispatch('inspect_hardware',{})['result'];parts=catalog()
    assert value['circuitbase']==a and value['assembly_sha256']==identity(a)
    assert set(value['catalog'])=={c['part'] for c in a['components']}
    for key,part in value['catalog'].items():
        for pin,original in zip(part['pins'],parts[key]['pins']):
            assert pin=={k:original[k] for k in pin}
        assert part['properties']==parts[key]['properties']
        assert part['sources']==parts[key]['sources']
        assert part['assumptions']==parts[key]['assumptions']
    assert 'omitted' in value['catalog_scope']


@pytest.mark.parametrize('field',['diagnostics','assembly','operations','status'])
def test_independent_check_rejects_tampering(tmp_path,field):
    a,tools,args,_=setup_review(tmp_path);tools.dispatch('inspect_hardware',{})
    p=tools.dispatch('propose_hardware_change',args)['result'];p=copy.deepcopy(p)
    if field=='diagnostics':p[field]['errors']=999
    elif field=='assembly':p[field]['components'][0]['name']='unreviewed';p['proposed_sha256']=identity(p[field])
    elif field=='operations':p[field]=[]
    else:p[field]='APPLIED'
    with pytest.raises(ValueError):independently_validate_proposal(a,args,p)


def test_two_request_worst_case_fits_fifteen_cent_cap_and_third_is_blocked(tmp_path):
    reservation=cost(24576,0,768,policy=GPT54_POLICY)
    assert reservation*2==Decimal('0.145920')<Decimal('.15')
    budget=ApiBudget(tmp_path/'budget.json',policy=GPT54_POLICY,limit='.15',input_token_bound=24576,max_output_tokens=768,max_requests=2)
    request={'input':[{'role':'user','content':'Explicit offline budget fixture'}],'tools':[]}
    for k in range(2):
        i=budget.begin(request)
        budget.settle(i,dict(input_tokens=1000,output_tokens=100,total_tokens=1100,input_tokens_details={'cached_tokens':0},output_tokens_details={'reasoning_tokens':0}),response_id='mock_fixture_'+str(k),returned_model='gpt-5.4',service_tier='default')
    with pytest.raises(BudgetBlocked,match='count'):budget.begin(request)
