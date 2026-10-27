"""Offline transport only; real typed construction, compilation and native tests.

Every mock argument is an explicitly developer-authored test fixture. Nothing in
this module is part of model context or genuine AI-success evidence.
"""
import copy
import json
import time
from uuid import uuid4
from pathlib import Path
from types import SimpleNamespace

import pytest

from engineering.assembly_examples import rover_plan
from engineering.project import identity
from ide_api.engineering_ai import EngineeringAI
from tests.test_assembly_experiment import raw_call

TASK='Create a simple four-wheel rover with a rectangular chassis.'

@pytest.fixture
def ai(tmp_path):
    service=EngineeringAI(tmp_path/'requests');service.draft(create=True)
    return service

def prepare(ai,**extra):
    p=ai.draft().current()
    return ai.prepare(workflow='assembly',task=TASK,expected_sha256=identity(p),
        expected_revision=p['revision'],selection='',baseline_request_id=None,**extra)

def approve(value):
    return {'manifest_sha256':value['manifest_sha256'],'request_id':value['request_id'],
        'decision':'EXPLICIT_APPROVE','approved_unix':time.time(),'authority':'CURRENT_USER_EXPLICIT_APPROVAL'}

def mock_client(ai,*,bad_first=False,invalid=False,transport_error=False,repair=False):
    calls=[]
    session=uuid4().hex
    def create(**body):
        i=len(calls);calls.append(copy.deepcopy(body))
        if transport_error:raise TimeoutError('Offline mock timeout; no network')
        if i==0:
            name=body['tools'][0]['name'];args={}
        else:
            data=json.loads(body['input'][0]['output']);state=data['result'] if i==1 else None
            p=ai.draft().current()
            if repair:
                allowed=state['allowed_changes'];targets=allowed['targets'];wheels=state['physical_failure']['wheels']
                old={w['joint_body_id']:w['actuator'] for w in wheels if w['actuator']}
                args={'expected_sha256':identity(p),'expected_revision':0,
                    'baseline_proposal_id':state['baseline']['proposal_id'],
                    'physical_feedback_sha256':state['physical_failure']['feedback_sha256'],
                    'step_id':'mock_author_supplied_repair',
                    'operations':[{'kind':'set_actuator','target':t,'actuator':{**old[t],'command':-.0015}} for t in targets],
                    'explanation':'OFFLINE fixture-author chosen negative commands; not a model decision.'}
                name='propose_assembly_physical_repair'
            else:
                plan=rover_plan(label='workspace_offline')
                if bad_first and i==1:plan['steps'][0]['operations'][0]['mass_kg']=2.
                args={'expected_sha256':identity(p),'expected_revision':0,'revision_of':data.get('failure_id'),'plan':plan}
                if invalid:args['unsupported']='Do not translate'
                name='propose_assembly_plan'
        raw=raw_call(i,name,args)
        raw['id']='mock_'+session+'_'+str(i)
        raw['output'][0]['call_id']='mock_call_'+session+'_'+str(i)
        return SimpleNamespace(model_dump=lambda **kw:copy.deepcopy(raw))
    return SimpleNamespace(max_retries=0,responses=SimpleNamespace(create=create),close=lambda:None),calls

def test_prepare_exact_context_and_duplicate_scope_no_credentials(ai,monkeypatch):
    monkeypatch.setattr('core.agent.credentials.create_openai_client',lambda:pytest.fail('No client before approval'))
    a=prepare(ai);b=prepare(ai)
    assert a['request_id']==b['request_id'] and a['status']=='PENDING_APPROVAL'
    d=a['manifest']['definition']
    assert d['context']['result']['project']['sha256']==identity(ai.draft().current())
    assert d['policy']['maximum_reservation_usd']=='1.2288' and max(d['serialized_input_bounds'])<=114688
    assert len(d['proposal_tools'])==1 and 'plan' not in d['context']['result']
    assert not (ai.root/'execution').exists()

@pytest.mark.parametrize('change',['missing','wrong_hash','wrong_id','expired','future','source','head','cancelled'])
def test_approval_gates_before_client_or_dispatch(ai,monkeypatch,change):
    value=prepare(ai);approval=approve(value)
    monkeypatch.setattr('core.agent.credentials.create_openai_client',lambda:pytest.fail('Gate must run first'))
    if change=='missing':approval=None
    if change=='wrong_hash':approval['manifest_sha256']='0'*64
    if change=='wrong_id':approval['request_id']='0'*64
    if change=='future':approval['approved_unix']=time.time()+10
    if change=='source':monkeypatch.setattr(ai,'source_identities',lambda:{})
    if change=='head':
        p=ai.draft().current();p['world']['environment']['gravity_m_s2']=[0,0,-9.7];ai.draft()._commit(p)
    if change=='cancelled':ai.cancel(value['request_id'])
    with pytest.raises((ValueError,TypeError)):
        if change=='expired':ai.gate(value['request_id'],approval,now=time.time()+86401)
        else:ai.execute(value['request_id'],approval)
    assert not (ai._folder(value['request_id'])/'consumed.json').exists()

@pytest.mark.parametrize('task',['Build a drone for flight','Run firmware on the rover','Read /Users/me/.env for the rover','Hello there'])
def test_unsupported_requests_reject_without_scope(ai,task):
    p=ai.draft().current()
    with pytest.raises(ValueError):ai.prepare(workflow='assembly',task=task,expected_sha256=identity(p),expected_revision=0,selection='')
    assert list(ai.requests.root.glob('*'))==[]

def test_stale_selection_revision_and_historical_repair_reject(ai):
    p=ai.draft().current()
    for values in ({'expected_revision':1},{'expected_sha256':'f'*64},{'selection':'part_not_body'}):
        kwargs=dict(workflow='assembly',task=TASK,expected_sha256=identity(p),expected_revision=0,selection='');kwargs.update(values)
        with pytest.raises(ValueError):ai.prepare(**kwargs)
    with pytest.raises(ValueError,match='current-source failed'):
        ai.prepare(workflow='physical_repair',task='Repair the rover wheel commands',expected_sha256=identity(p),expected_revision=0,selection='')

@pytest.mark.parametrize('revise',[False,True])
def test_mock_transport_real_compiled_proposal_and_single_use(ai,revise):
    value=prepare(ai);approval=approve(value);before=ai.draft().current()
    client,calls=mock_client(ai,bad_first=revise)
    result=ai.execute(value['request_id'],approval,offline_client=client)
    assert result['status']=='COMPILED',result['failure']
    assert result['origin']=='OFFLINE_MOCK_TRANSPORT_NOT_AI' and result['native'] is None
    assert len(calls)==(3 if revise else 2) and len(result['proposal']['proposed_project']['shape_specs'])==9
    assert result['proposal']['assembly_plan']==json.loads(ai._read(ai._folder(value['request_id'])/'api',f'response_{len(calls)-1:03d}.json')['output'][0]['arguments'])['plan']
    assert ai.draft().current()==before and not (ai.draft().root/'assembly_decisions').exists()
    assert ai._read(ai._folder(value['request_id']),'provider_audit.json')['status']=='PASS_EVIDENCE_AUDIT'
    with pytest.raises(ValueError,match='consumed'):ai.execute(value['request_id'],approval,offline_client=client)
    assert len(calls)==(3 if revise else 2)
    with pytest.raises(ValueError):ai.cancel(value['request_id'])

@pytest.mark.parametrize('error',['schema','transport'])
def test_mock_failure_preserved_no_retry(ai,error):
    value=prepare(ai);client,calls=mock_client(ai,invalid=error=='schema',transport_error=error=='transport')
    r=ai.execute(value['request_id'],approve(value),offline_client=client)
    assert r['status']=='FAILED' and r['proposal'] is None
    assert len(calls)==(2 if error=='schema' else 1)
    if error=='transport':assert r['usage']['requests'][0]['state']=='FAILED_USAGE_UNKNOWN'

def test_real_native_mock_plan_failure_then_explicit_mock_repair_no_apply(ai):
    value=prepare(ai);approval=approve(value);client,calls=mock_client(ai)
    result=ai.execute(value['request_id'],approval,offline_client=client)
    head=ai.draft().current()
    native=ai.verify(value['request_id'],approval)
    assert native['status']=='PHYSICAL_FAIL' and native['verification']['measured_signed_forward_displacement_m']<-.005
    assert native['native']['result']['independent_verification']['fresh_native_integration_steps']==200
    p=ai.draft().current()
    selection=native['proposal']['proposed_project']['shape_specs'][0]['body_id']
    repair=ai.prepare(workflow='physical_repair',task='Repair the rover so it moves forward',expected_sha256=identity(p),expected_revision=0,selection=selection,baseline_request_id=value['request_id'])
    repair_approval=approve(repair);client,calls=mock_client(ai,repair=True)
    result=ai.execute(repair['request_id'],repair_approval,offline_client=client)
    assert result['status']=='COMPILED',result['failure']
    fixed=ai.verify(repair['request_id'],repair_approval)
    assert fixed['status']=='PHYSICAL_PASS' and fixed['verification']['measured_signed_forward_displacement_m']>=.005
    assert all(fixed['verification']['checks'].values()) and fixed['verification']['contacts']['unexpected_contact_count']==0
    assert ai.draft().current()==head
    assert ai.read(value['request_id'])['status']=='PHYSICAL_FAIL'
    with pytest.raises(ValueError):ai.verify(value['request_id'],approval)
    ai.disposition(repair['request_id'],'discard');assert ai.draft().current()==head
    assert ai.read(repair['request_id'])['proposal']

def test_browser_api_only_prepares_no_execution_or_apply(http,tmp_path):
    client,server=http;server.ide._engineering_ai=EngineeringAI(tmp_path/'api_requests')
    assert client.post('/api/ai-engineering/new-project',json={}).status_code==200
    snap=client.get('/api/workspace',params={'project':'ai-review'}).json()['snapshot']
    assert snap['project']['revision']==0 and not snap['editable']
    body={'workflow':'assembly','task':TASK,'expected_sha256':snap['project_sha256'],'expected_revision':0,'selection':'','baseline_request_id':None}
    response=client.post('/api/ai-engineering/prepare',json=body);assert response.status_code==200,response.text
    key=response.json()['request_id']
    assert client.get('/api/ai-engineering/request',params={'id':key}).json()['status']=='PENDING_APPROVAL'
    for action in ('execute','approve','native','apply'):
        assert client.post('/api/ai-engineering/'+action,json={'request_id':key}).status_code==403
    assert server.jobs=={} and not (server.ide.engineering_ai._folder(key)/'consumed.json').exists()

from tests.test_ide_api import service,http
