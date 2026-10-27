"""No live VM. Search/statistical fixtures are explicitly synthetic test records."""
import copy
import hashlib
from collections import Counter
import pytest
import numpy as np
from robustness.builder import freeze,approval_report
from robustness.contracts import frozen_sources,Experiment
from robustness.sampling import sample,scenario
from robustness.parameters import nominal,validate
from robustness.perturbation import compile_scenario
from robustness.statistics import summary,wilson
from robustness.classification import classify,violations
from robustness.counterexamples import search
from robustness.minimization import minimize
from robustness.ablation import diagnostic_ablation
from robustness.qualification import require
from robustness.batch import run
from robustness.reporting import offline_report
from core.agent.vm_backend import IsolationBlocked,AppleVMBackend
from robustness.evaluator import evaluate


@pytest.fixture(scope='module')
def frozen(tmp_path_factory):
    folder=tmp_path_factory.mktemp('frozen-robustness')/'experiment';e=freeze(folder);return folder,e


@pytest.mark.parametrize('family',['rail','arm'])
def test_fixed_deterministic_strata_and_seed_variations(family):
    rows=sample(family);assert rows==sample(family) and rows!=sample(family,123)
    assert len({r['id'] for r in rows})==40
    assert Counter(r['stratum'] for r in rows)=={'anchor':1,'nominal_uniform':15,'wide_uniform':16,'boundary':8}
    for row in rows:validate(family,row['parameters'])


def test_all_80_real_compiled_perturbations_and_consistent_inertias(frozen):
    folder,e=frozen
    for row in e.data['matrix']:
        p=compile_scenario(row,e.data['sources'][row['family']]['repair']['sha256']);m=p['model'];v=row['parameters']
        assert hashlib.sha256(p['xml'].encode()).hexdigest()==row['model_sha256']
        if row['family']=='rail':
            assert m.body('carriage').mass[0]==pytest.approx(v['mass_kg'])
            assert p['contract'].initial_position_m==v['initial_position_m']
            assert p['contract'].initial_clearance_m==pytest.approx(v['gap_m'])
            assert m.actuator_forcerange[0,1]==v['force_n']
        else:
            assert m.body('link1').mass[0]==v['link1_mass_kg'] and m.body('link2').mass[0]==v['link2_mass_kg']
            np.testing.assert_allclose(m.dof_damping,v['damping_nm_s_per_rad'])
            assert np.all(m.body('link1').inertia>0)
    assert len(e.data['matrix'])==80


def test_frozen_source_provenance_is_exact_historical_gpt(frozen):
    folder,e=frozen;sources=frozen_sources()
    for family in ('rail','arm'):
        raw=(folder/'controllers'/(family+'_repair.py')).read_bytes()
        assert hashlib.sha256(raw).hexdigest()==sources[family]['repair']['sha256']
        assert raw.decode()==sources[family]['repair']['source']
        assert sources[family]['repair']['origin']=='genuine_historical_gpt_proposal'
    assert e.data['sources']['arm']['repair']['sha256']=='106a02808f3c89a71d2e632ca268b581579d05eef65b00aeee1d7c0adce2a5b4'
    assert Experiment.load(folder).identity==e.identity


def test_exact_new_approval_required_before_any_vm_preflight(frozen,monkeypatch):
    folder,e=frozen
    def forbidden(*a,**kw):raise AssertionError('No VM operation authorized')
    monkeypatch.setattr(AppleVMBackend,'preflight',forbidden)
    for approval in (None,'DAY9_APPROVED','0'*64):
        with pytest.raises(IsolationBlocked):run(folder,approved_sha=approval)
    with pytest.raises(IsolationBlocked):require(e,None,{},e.identity)
    assert not (folder/'evaluation').exists()
    request=approval_report(e);assert request['api_requests']==0 and request['installation'] is False
    assert request['runtime_limits']['one_vm_at_a_time']


def test_offline_reporting_does_not_invent_measurements(frozen):
    folder,e=frozen;r=offline_report(folder)
    assert r['status']=='PARTIAL' and r['measured_pairs']==0 and r['candidate_evaluations']==0
    assert r['counterexample_search']=='NOT_EXECUTED'
    assert r['statistics']['groups']==[] and r['diagnostic_ablation']['rows']==[]
    assert sum(r['guard_counts']['rail'].values())==40


def test_real_nonzero_initial_rail_independent_decisions_tolerate_only_last_bit(frozen,tmp_path):
    folder,e=frozen;row=e.data['matrix'][4]
    r=evaluate(e,folder,row,'baseline',tmp_path/'nonzero-rail')
    assert row['parameters']['initial_position_m']!=0
    assert r['execution']=='PASS' and r['independent_verification']=='PASS'
    assert r['classification']=='CONTROLLER_SAFETY_VIOLATION'


def fixture_outcome(variant,passed=True,*,stratum='nominal_uniform',execution='PASS',scenario_id='fixture'):
    """Synthetic orchestration fixture, never saved as physical experiment evidence."""
    r={'family':'rail','variant':variant,'scenario':{'id':scenario_id,'stratum':stratum},'guard':{'status':'UNKNOWN'},
       'execution':execution,'independent_verification':'PASS','physical_safety_status':'PASS' if passed else 'FAIL',
       'margins':{'clearance_m':.01 if passed else -.01}}
    r['classification']=classify(r['guard'],execution,'PASS',r['margins'],passed);r['violations']=violations(r)
    return r


def test_paired_statistics_exclude_absent_infeasible_and_execution_failures():
    rows=[]
    for i,(a,b) in enumerate([(True,True),(False,False),(False,True),(True,False)]):
        rows += [fixture_outcome('baseline',a,scenario_id=str(i)),fixture_outcome('repair',b,scenario_id=str(i))]
    rows.append(fixture_outcome('baseline',scenario_id='missing'))
    result=summary(rows);pair=result['paired'][0]
    assert all(pair[k]==1 for k in ('both_pass','both_fail','baseline_fails_repair_passes','baseline_passes_repair_fails','unavailable_or_task_infeasible'))
    assert 0<wilson(2,4)[0]<.5<wilson(2,4)[1]<1
    assert wilson(0,0) is None
    blocked=fixture_outcome('repair',False,execution='BLOCKED');assert blocked['classification']=='EXECUTION_BLOCKED' and not blocked['violations']
    assert classify({'status':'PROVEN_INFEASIBLE'},'NOT_RUN','NOT_RUN',{},False)=='TASK_INFEASIBLE'


def test_ablation_cannot_change_frozen_physical_results():
    rows=[fixture_outcome('repair',False)];original=copy.deepcopy(rows);a=diagnostic_ablation(rows)
    assert len(a['rows'])==4 and rows==original
    assert len({r['physical_outcome_unchanged'] for r in a['rows']})==1
    assert a['search_changes_benchmark_outcomes'] is False
    assert a['repair_generation_ablation'].startswith('NOT_EXECUTED')


def test_bounded_deterministic_search_and_minimization_reproduction():
    calls=[]
    def explicitly_synthetic_evaluator(row):
        calls.append(row);r=fixture_outcome('repair',False,scenario_id=row['id']);r['scenario']=row
        failure=row['parameters']['mass_kg']>2.2;r['margins']={'clearance_m':-.01 if failure else .01}
        r['classification']=classify(r['guard'],'PASS','PASS',r['margins'],not failure);r['violations']=violations(r);return r
    row=scenario('rail',{**nominal('rail'),'mass_kg':4.},'boundary',0,123)
    initial=explicitly_synthetic_evaluator(row)
    a=search('rail',[initial],explicitly_synthetic_evaluator,budget=6,seed=12)
    b=search('rail',[initial],explicitly_synthetic_evaluator,budget=6,seed=12)
    assert [r['scenario'] for r in a['trials']]==[r['scenario'] for r in b['trials']]
    m=minimize(a['selected'],explicitly_synthetic_evaluator,budget=6)
    assert m['status']=='REPRODUCED' and len(m['trials'])<=6
    assert m['simplicity_after']<=m['simplicity_before']
    assert m['confirmation']['scenario']['stratum']=='reproduction'
    with pytest.raises(ValueError):search('rail',[],explicitly_synthetic_evaluator,budget=7)
