"""Real native repair integration. No fabricated production physics callback."""
from dataclasses import replace
from pathlib import Path
import copy,json
import mujoco
import pytest
from engineering.barrier_repair import preflight_project,propose_repair,_candidate,FROZEN_CHECK_NAMES
from engineering.phase17_repair import BarrierParameters,candidate_designs,find_verified_repair,NativeOutcome
from engineering.mujoco_contact_probe import all_initial_contacts,forbidden_initial_contacts
from engineering.changes import validate_changeset
from engineering.project import identity
from engineering.creation import CreationManager
from engineering.creation_experiment import CreationExperimentTools,preview_measurements
from engineering.diagnosis import diagnose
from core.agent.trace import ExecutionTrace

ROOT=Path(__file__).resolve().parents[1]
FAILED=ROOT/'artifacts/phase17_live_creation/20261024/live_execution/previews/primary/result.json'

@pytest.fixture
def original():return json.loads(FAILED.read_text())['project']

def test_native_preflight_identifies_both_original_failures_without_mutation(original):
    before=copy.deepcopy(original);pf=preflight_project(original)
    assert pf['status']=='BLOCKED_PHYSICS_PREFLIGHT' and original==before
    assert 'INSUFFICIENT_STATIC_TORQUE' in {f['code'] for f in pf['findings']}
    assert len(pf['native']['initial_contacts'])==8
    distances={round(c['signed_distance_m'],6) for c in pf['native']['initial_contacts']}
    assert distances=={-.008,-.0025} and pf['native']['initial_bias_torque_nm'][0]==pytest.approx(.247212)
    findings=diagnose(original,json.loads(FAILED.read_text()))['findings']
    assert {'FORBIDDEN_CONTACT','ACTUATOR_CAPABILITY'}<={x['category'] for x in findings}

def test_mass_only_and_height_only_each_leave_a_distinct_physical_problem(original):
    d=BarrierParameters(**preflight_project(original)['design'])
    light=preflight_project(_candidate(original,replace(d,mass_kg=.035,torque_nm=.12)))
    clear=preflight_project(_candidate(original,replace(d,pivot_height_m=.18)))
    assert 'FORBIDDEN_CONTACT' in {f['code'] for f in light['findings']} and 'INSUFFICIENT_STATIC_TORQUE' not in {f['code'] for f in light['findings']}
    assert 'INSUFFICIENT_STATIC_TORQUE' in {f['code'] for f in clear['findings']} and not clear['native']['initial_contacts']

def test_real_bounded_search_requires_all_nine_and_fresh_independent_native_replay(original,tmp_path):
    before=identity(original);answer=propose_repair(original,tmp_path/'repair',max_native_previews=2,render_image=False)
    assert answer['status']=='VERIFIED_PROPOSAL_NOT_APPLIED' and not answer['proposal_applied']
    assert answer['native_previews']<=2 and identity(original)==before
    changeset=validate_changeset(answer['engineering_changeset']);assert changeset['base_project_sha256']==before
    result=json.loads(Path(answer['evidence']['new']['path']).read_text())
    assert set(FROZEN_CHECK_NAMES)==set(json.loads(FAILED.read_text())['acceptance']['checks'])==set(result['acceptance']['checks'])
    assert all(v is True for v in result['acceptance']['checks'].values())
    assert result['independent_verification']['status']=='PASS' and result['independent_verification']['fresh_native_integration_steps']==1000
    assert result['project']['circuit']==original['circuit'] and result['project']['controller_sha256']==original['controller_sha256']
    assert not any(s['contacts'] for s in result['samples']) and result['contract']['requirements']==json.loads(FAILED.read_text())['contract']['requirements']

def test_repository_envelopes_reject_attachment_high_torque_and_no_model_changes(original):
    d=BarrierParameters(**preflight_project(original)['design'])
    assert any(c.torque_nm>.17 for c in candidate_designs(d))
    with pytest.raises(ValueError,match='existing Day16'):_candidate(original,replace(d,torque_nm=.25))
    with pytest.raises(ValueError,match='only mass'):_candidate(original,replace(d,span_m=.2))
    with pytest.raises(ValueError):replace(d,mass_kg=True).validate()
    for value in (0,False,101):
        with pytest.raises(ValueError):candidate_designs(d,max_candidates=value)

def test_zero_budget_never_integrates(original,tmp_path,monkeypatch):
    def forbidden(*a,**k):raise AssertionError('No native preview budget')
    monkeypatch.setattr('engineering.barrier_repair.run',forbidden)
    a=propose_repair(original,tmp_path/'no_run',max_native_previews=0,render_image=False)
    assert a['status']=='NOT_RUN' and a['native_previews']==0 and a['engineering_changeset'] is None

def test_actual_native_margin_contacts_and_exact_pair_names():
    model=mujoco.MjModel.from_xml_string('<mujoco><worldbody><geom name="floor" type="plane" size="1 1 .1"/><body pos="0 0 .15"><freejoint/><geom name="box" type="box" size=".1 .1 .1" mass="1" margin=".1"/></body></worldbody></mujoco>')
    data=mujoco.MjData(model);contacts=all_initial_contacts(model,data)
    assert contacts and all(c[2]>0 for c in contacts)
    assert not forbidden_initial_contacts(model,data,[('floor','box')])
    assert forbidden_initial_contacts(model,data,[('floor','box')],include_margin_contacts=True)
    with pytest.raises(ValueError,match='exist'):forbidden_initial_contacts(model,data,[('floor','wrong_box')])

def test_new_model_proposal_preflight_blocks_bad_preview_and_preserves_empty_head(tmp_path,monkeypatch):
    from test_phase17_creation import mock_arguments
    m=CreationManager(tmp_path/'registry');t=CreationExperimentTools(m,ExecutionTrace(tmp_path/'mock.jsonl',model_mode='deterministic_mock'))
    a=copy.deepcopy(mock_arguments());a['mechanical']={'span_m':.28,'mass_kg':.18,'torque_nm':.11,'height_m':.16}
    selected=t.dispatch('propose_barrier_from_template',a)['result']
    assert selected['physics_preflight']['status']=='BLOCKED_PHYSICS_PREFLIGHT'
    def forbidden(*a,**k):raise AssertionError('Bad preflight must block simulation')
    monkeypatch.setattr('engineering.created_simulation.run',forbidden)
    result=preview_measurements(selected,m,tmp_path/'blocked')
    assert result['simulation_scenarios']==0 and result['primary_status']=='BLOCKED_PHYSICS_PREFLIGHT'
    assert m.project(selected['construction_proposal']['project_id']).current()['creation']['state']=='EMPTY'

def test_existing_service_produces_real_review_changeset_without_committing(tmp_path):
    m=CreationManager(tmp_path/'registry');p=m.start('Build a barrier.',{'span_m':.28,'mass_kg':.18,'torque_nm':.11,'height_m':.16})
    # Explicit deterministic test build, not a model proposal or real user head.
    built=m.decide(p['proposal_id'],p['base_sha256'],0,'build','BUILD REVIEWED SUPPORTED PROJECT')['project'];s=m.project(built['id'])
    before=s.current();r=s.propose_physics_repair(identity(before),before['revision'],max_native_previews=1,render_image=False)
    assert r['engineering_changeset'] and s.current()==before and s.proposals.get(r['proposal_id'])['approval_status']=='PROPOSED_NOT_APPLIED'
    with pytest.raises(ValueError,match='Stale'):s.propose_physics_repair('f'*64,before['revision'],max_native_previews=0)

def test_incomplete_or_non_boolean_independence_never_accepted():
    d=BarrierParameters(.28,.18,.11,.16)
    for flag in (False,1,'yes'):
        # Explicit unit double tests protocol rejection; not simulation evidence.
        result=find_verified_repair(d,trusted_native_preview=lambda c:NativeOutcome(dict.fromkeys(FROZEN_CHECK_NAMES,True),flag,evidence_path='UNIT_ONLY'),frozen_check_names=FROZEN_CHECK_NAMES,max_native_previews=1)
        assert result.accepted_candidate is None
