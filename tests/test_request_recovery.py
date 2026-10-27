"""Interrupted request representation is distinct from an unexecuted scope."""
import time
from pathlib import Path
from ide_api.engineering_ai import EngineeringAI
from engineering.project import identity
from robustness.contracts import write_once

def test_consumed_scope_without_completion_never_claims_no_model_request(tmp_path):
    s=EngineeringAI(tmp_path/'ai');p=s.draft(create=True).current()
    r=s.prepare(workflow='assembly',task='Create a simple four-wheel rover',expected_sha256=identity(p),expected_revision=0,selection='')
    key=r['request_id'];approval={'manifest_sha256':r['manifest_sha256'],'request_id':key,'decision':'EXPLICIT_APPROVE','authority':'CURRENT_USER_EXPLICIT_APPROVAL','approved_unix':time.time()}
    # Explicit hypothetical crash fixture, no provider or execution call.
    write_once(s._folder(key)/'consumed.json',{'started_unix':time.time(),'approval':approval,'origin':'GENUINE_PROVIDER_RESPONSE'})
    unknown=s.read(key)
    assert unknown['status']=='EXECUTION_RESERVED_OR_INTERRUPTED'
    assert unknown['origin']=='PROVIDER_EXECUTION_OUTCOME_UNKNOWN'
    assert unknown['execution_approval_recorded'] and unknown['execution_consumed']
    assert unknown['proposal'] is None and unknown['native'] is None
    import pytest
    with pytest.raises(ValueError,match='consumed'):s.gate(key,approval)
    with pytest.raises(ValueError):s.cancel(key)

def test_unknown_cost_reservation_is_shown_but_not_released(tmp_path):
    from core.agent.api_budget import ApiBudget,GPT54_POLICY
    s=EngineeringAI(tmp_path/'ai');p=s.draft(create=True).current()
    r=s.prepare(workflow='assembly',task='Create a compact four-wheel rover',expected_sha256=identity(p),expected_revision=0,selection='')
    key=r['request_id'];folder=s._folder(key)
    write_once(folder/'consumed.json',{'started_unix':time.time(),'approval':{},'origin':'GENUINE_PROVIDER_RESPONSE'})
    budget=ApiBudget(folder/'api_cost_ledger.json',policy=GPT54_POLICY,limit='1.24',max_requests=3,input_token_bound=114688,max_output_tokens=8192)
    budget.begin(r['manifest']['definition']['first_request'])
    value=s.read(key)
    assert value['usage']['requests'][0]['state']=='PENDING'
    assert float(value['usage']['accounted_cost_usd'])>0
    assert not value['execution_approval_recorded']
