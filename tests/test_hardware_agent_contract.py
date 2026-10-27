"""Strict operation grammar and real CIRCUITBASE changes; no paid model calls."""
import copy
from types import SimpleNamespace
import pytest
from jsonschema import Draft202012Validator
from hardware.agent import HardwareTools
from hardware.tool_contract import PROPOSAL_PARAMETERS
from hardware.assemblies import connect,endpoint,identity
from hardware.template import barrier
from hardware.validation import inspect
from devices.contracts import DeviceSpec


class Trace:
    def append(self,*args):pass


@pytest.fixture
def context():
    a=connect(barrier(),endpoint('sensor','ECHO'),endpoint('board','IO19'))
    tools=HardwareTools(SimpleNamespace(schemas=(),trace=Trace()),a,DeviceSpec().to_dict())
    args={'expected_sha256':identity(a),'expected_revision':a['revision'],
          'operations':[{'kind':'disconnect','wire_id':a['wires'][-1]['id']}],
          'explanation':'Remove the actual Echo bypass; retain the connected divider and electrical unknowns.'}
    return a,tools,args


def test_published_schema_and_local_validator_share_typed_bounded_contract(context):
    _,tools,_=context
    schema=next(s for s in tools.schemas if s['name']=='propose_hardware_change')
    assert schema['strict'] and schema['parameters']==PROPOSAL_PARAMETERS
    assert 'operations_json' not in schema['parameters']['properties']
    Draft202012Validator.check_schema(schema['parameters'])
    def check(node):
        if isinstance(node,dict):
            if node.get('type')=='object':
                assert node['additionalProperties'] is False
                assert set(node['required'])==set(node['properties'])
            for value in node.values():check(value)
        elif isinstance(node,list):
            for value in node:check(value)
    check(schema['parameters'])
    schema['parameters']['properties'].clear()
    assert next(s for s in tools.schemas if s['name']=='propose_hardware_change')['parameters']==PROPOSAL_PARAMETERS


@pytest.mark.parametrize('mutate',[
    lambda x:x.update(operations_json='[{"op":"remove_wire"}]'),
    lambda x:x['operations'][0].update(op='remove_wire'),
    lambda x:x.update(operations=[{'op':'remove_wire','wire_id':'wire_1'}]),
    lambda x:x['operations'][0].update(kind='remove_wire'),
    lambda x:x.update(operations='[{"kind":"disconnect","wire_id":"wire_1"}]'),
    lambda x:x.update(operations=[]),
    lambda x:x.update(operations=x['operations']*17),
    lambda x:x['operations'][0].pop('wire_id'),
    lambda x:x['operations'][0].update(wire_id='../secret'),
    lambda x:x['operations'][0].update(wire_id='a'*65),
    lambda x:x['operations'][0].update(source='untrusted'),
    lambda x:x.update(explanation=''),
    lambda x:x.update(explanation='a'*4001),
    lambda x:x.update(explanation='😀'*4001),
    lambda x:x.update(expected_sha256='X'*64),
    lambda x:x.update(expected_revision=-1),
    lambda x:x.update(expected_revision=1000000),
    lambda x:x.update(expected_revision=True),
    lambda x:x.update(expected_revision=13.0),
    lambda x:x.pop('expected_revision'),
    lambda x:x.update(operations=[{'kind':'connect','a':{'component':'board','pin':'IO19'},'b':{'component':'sensor'}}]),
    lambda x:x.update(operations=[{'kind':'connect','a':{'component':'board','pin':'IO19','extra':True},'b':{'component':'sensor','pin':'ECHO'}}]),
    lambda x:x.update(operations=[{'kind':'connect','a':{'component':'board','pin':'a'*65},'b':{'component':'sensor','pin':'ECHO'}}]),
])
def test_invalid_structured_operations_are_rejected_without_translation_or_mutation(context,mutate):
    a,tools,args=context;original=copy.deepcopy(a);mutate(args)
    rejected=tools.dispatch('propose_hardware_change',args)
    assert not rejected['ok'] and a==original and tools.assembly==original
    assert inspect(a)['errors']>0


@pytest.mark.parametrize('field,value',[
    ('expected_sha256','0'*64),('expected_revision',12),
    ('operations',[{'kind':'disconnect','wire_id':'wire_absent'}]),
    ('operations',[{'kind':'connect','a':{'component':'board','pin':'ABSENT'},'b':{'component':'sensor','pin':'ECHO'}}]),
    ('operations',[{'kind':'connect','a':{'component':'absent','pin':'IO19'},'b':{'component':'sensor','pin':'ECHO'}}]),
])
def test_valid_json_schema_does_not_bypass_identity_or_graph_rules(context,field,value):
    a,tools,args=context;args[field]=value
    Draft202012Validator(PROPOSAL_PARAMETERS).validate(args)
    assert not tools.dispatch('propose_hardware_change',args)['ok']
    assert inspect(a)['errors']>0


def test_exact_disconnect_proposal_restores_rules_but_never_applies(context):
    a,tools,args=context;base=identity(a)
    result=tools.dispatch('propose_hardware_change',args)
    assert result['ok'];p=result['result']
    assert p['operations']==args['operations'] and p['base_sha256']==base
    assert p['status']=='PROPOSED_NOT_APPLIED' and p['installation_effect']=='NONE'
    assert p['assembly']['revision']==a['revision']+1
    assert p['diagnostics']['errors']==0 and p['diagnostics']['status']=='UNKNOWN'
    assert p['diagnostics']['unknowns']==6
    assert identity(a)==identity(tools.assembly)==base and inspect(a)['errors']>0


def test_typed_connect_keeps_actual_electrical_failures_visible():
    a=barrier();base=identity(a)
    tools=HardwareTools(SimpleNamespace(schemas=(),trace=Trace()),a,DeviceSpec().to_dict())
    args={'expected_sha256':base,'expected_revision':a['revision'],
          'operations':[{'kind':'connect','a':endpoint('sensor','ECHO'),'b':endpoint('board','IO19')}],
          'explanation':'Deliberate deterministic test defect, never a live success.'}
    result=tools.dispatch('propose_hardware_change',args)
    assert result['ok'] and result['result']['diagnostics']['status']=='INVALID'
    assert identity(a)==base and inspect(a)['errors']==0


def test_total_request_byte_limit_is_enforced_before_graph_work(context):
    _,tools,args=context
    long='a'*64
    args.update(explanation='😀'*4000,operations=[{'kind':'connect','a':{'component':long,'pin':long},'b':{'component':long,'pin':long}}]*16)
    Draft202012Validator(PROPOSAL_PARAMETERS).validate(args)
    result=tools.dispatch('propose_hardware_change',args)
    assert not result['ok'] and '20000 bytes' in result['error']['message']
