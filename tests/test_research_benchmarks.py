"""Offline algorithm tests: synthetic/analytical queries are not physical measurements."""
import copy,inspect
import pytest
from ide_api.research import benchmarks as b,physical_math as pm,sampling,analysis
from test_research_algorithms import record,cfg

@pytest.mark.parametrize('env',b.ENVIRONMENTS)
def test_deterministic_fair_bounded_all_environments(env):
 config={'environment':env,'budget':12,'seed':19,'resolution':.005};out=b.evaluate(config);assert out==b.evaluate(config)
 assert out['native_integration_steps']==out['native_rollouts']==out['paid_calls']==0
 for run in out['runs']:
  assert run['maximum_queries']==12 and 0<len(run['history'])<=12
  assert not run['known_truth_used_for_selection'] and run['metrics']['duplicate_queries']==0
  assert len({tuple(h['point']) for h in run['history']})==len(run['history'])
  assert all(h['outcome'] in ('ORACLE_PASS','ORACLE_FAIL') for h in run['history'])
 assert all('not MuJoCo' in out['limitations'][0] for _ in [0])

def test_counted_endpoints_and_history_only_policy():
 assert list(inspect.signature(b.choose_adaptive).parameters)==['domain','history']
 out=b.evaluate({'environment':'single_transition','budget':12,'seed':1,'resolution':.005});adaptive=out['runs'][2]
 assert adaptive['history'][0]['point']==[0.] and adaptive['history'][1]['point']==[1.]
 assert adaptive['metrics']['queries_to_target']==10
 assert adaptive['metrics']['smallest_observed_bracket_width']==pytest.approx(.003906)
 assert out['runs'][0]['metrics']['queries_to_target'] is None

def test_no_transition_and_missed_narrow_region_are_honest():
 for name in ('all_pass','all_fail','narrow_failure'):
  out=b.evaluate({'environment':name,'budget':3,'seed':1,'resolution':.005})
  for run in out['runs']:
   assert run['metrics']['queries_to_target'] is None
  if name=='narrow_failure':assert out['runs'][2]['metrics']['known_transitions_missed']==2

def test_stratification_seed_and_no_native_physics():
 a=b.baseline('seeded_stratified',[[0.,1.],[0.,1.]],12,1)
 assert a!=b.baseline('seeded_stratified',[[0.,1.],[0.,1.]],12,2)
 for axis in range(2):assert sorted(int(p[axis]*12) for p in a)==list(range(12))

def test_multiple_transitions_and_two_dimensional_metrics():
 out=b.evaluate({'environment':'multiple_transitions','budget':25,'seed':1,'resolution':.01})
 assert out['runs'][2]['metrics']['known_transitions_covered']==2
 out=b.evaluate({'environment':'two_dimensional','budget':12,'seed':1,'resolution':.005})
 assert all(r['metrics']['normalized_fill_distance']>=0 for r in out['runs'])
 assert out['runs'][2]['metrics']['candidate_scores_evaluated']>12

@pytest.mark.parametrize('field,value',[('budget',26),('budget',True),('resolution',0),('environment','native'),('seed',-1)])
def test_invalid_config(field,value):
 config={'environment':'single_transition','budget':12,'seed':1,'resolution':.005};config[field]=value
 with pytest.raises(ValueError):b.evaluate(config)

def test_saved_benchmark_recomputation_and_corruption(tmp_path):
 service=b.Benchmarks(tmp_path);out=service.run({'environment':'single_transition','budget':12,'seed':1,'resolution':.005})
 assert service.read(out['id'])==out
 p=tmp_path/'benchmarks'/(out['id']+'.json');p.write_bytes(p.read_bytes()+b'x')
 with pytest.raises(ValueError):service.read(out['id'])

def test_resolution_fixed_conditions_conflicts_and_unexecuted_blockers(cfg):
 rows=[record(1.,.01),record(2.,.2)];cfg['resolution_target']=1.
 assert sampling.adaptive(cfg,rows,[],3)['termination']=='TARGET_INTERVAL_RESOLUTION_REACHED'
 cfg['resolution_target']=.01;bad=record(1.5,.1);bad.update(verified=False,status='NOT_EXECUTED')
 assert not analysis.boundaries(rows+[bad],['gap_m'])['intervals']
 changed=record(1.5,.1,mass_kg=3.)
 assert sampling.adaptive(cfg,rows+[changed],[],3)['points'][0]['parameters']['gap_m']==1.5
 assert sampling.adaptive(cfg,rows+[record(1.,.2)],[],3)['termination']=='CONFLICTING_REPEATED_OUTCOMES'

def test_residuals_do_not_infer_missing_native_or_efficiency():
 assert b.retrospective([])['status']=='INSUFFICIENT_COMPARABLE_MEASURED_DATA_FOR_STRATEGY_BENCHMARK'
 assert b.retrospective([])['query_count']==0


def test_uniform_two_dimensional_edges_not_lost_to_truncated_rows():
 points=b.baseline('uniform',[[0.,1.],[0.,1.]],12,1)
 assert all(corner in points for corner in [[0.,0.],[1.,0.],[0.,1.],[1.,1.]])

@pytest.mark.parametrize('p,expected',[
 ({'mass_kg':4.,'speed_mps':1.2,'force_n':2.,'gap_m':1.49},(1.44,2.4)),
 ({'mass_kg':2.,'speed_mps':0.,'force_n':4.,'gap_m':1.},(0.,0.)),
 ({'mass_kg':2.,'speed_mps':1.,'force_n':4.,'gap_m':1.},(.25,.5))])
def test_continuous_and_discrete_predictions_are_explicit_arithmetic(p,expected):
 from ide_api import rail_sweeps as rail
 result=pm.predictions(p,rail.DEFAULT_CRITERIA)
 assert result['continuous']['stopping_distance_m']==pytest.approx(expected[0])
 assert result['continuous']['stopping_time_s']==pytest.approx(expected[1])
 assert result['discrete']['native_steps']==0 and result['discrete']['arithmetic_updates']==600
 assert result['discrete']['predicted_travel_m']<=expected[0]+1e-12

@pytest.mark.parametrize('field,value',[('mass_kg',True),('speed_mps',float('nan')),('force_n',0),('gap_m',float('inf'))])
def test_math_never_admits_nonfinite_bool_or_invalid_physics(field,value):
 from ide_api import rail_sweeps as rail
 p={'mass_kg':4.,'speed_mps':1.2,'force_n':2.,'gap_m':1.49};p[field]=value
 with pytest.raises(ValueError):pm.predictions(p,rail.DEFAULT_CRITERIA)
