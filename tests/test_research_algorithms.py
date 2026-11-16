"""Synthetic mathematics/provenance fixtures; NOT MuJoCo evidence."""
import copy,math
import pytest
from ide_api import rail_sweeps as rail
from ide_api.research import contracts as c,sampling,analysis,graph,registry

@pytest.fixture
def cfg():return {'experiment_id':rail.EXPERIMENT,'controller_id':rail.CONTROLLER,'objective':'Study bounded clearance','type':'adaptive_1d','axes':[{'parameter':'gap_m','minimum':.35,'maximum':2.2}],'fixed_parameters':{'mass_kg':4.,'speed_mps':1.2,'force_n':2.,'gap_m':1.49},'criteria':copy.deepcopy(rail.DEFAULT_CRITERIA),'strategy':'uniform','count':3,'seed':12,'minimum_spacing':.001,'proposal_budget':12,'hypothesis_ids':[]}

def record(x,y=None,verdict=None,**params):
 p={'mass_kg':4.,'speed_mps':1.2,'force_n':2.,'gap_m':x,**params};y=x if y is None else y
 return {'id':rail.digest({'synthetic_point':p,'y':y}),'status':'MEASURED','verified':True,'parameters':p,'verdict':verdict or ('PASS' if y>=.05 else 'FAIL'),'metrics':{'minimum_clearance_m':y,'maximum_actuator_force_n':2.},'controller_id':rail.CONTROLLER,'source_current':False,'comparison':{'measured_minus_ideal_clearance_m':.003},'compatibility':{'physics':'SYNTHETIC_ALGORITHM_ONLY','experiment':'synthetic','model':'synthetic','measurements':'synthetic','source':'test_source','controller':'test_controller','criteria':'test_criteria','simulation':'test_simulation'}}

@pytest.mark.parametrize('strategy,n,dimension',[('uniform',3,1),('uniform',9,2),('endpoints',4,2),('space_filling',7,2),('near_threshold',3,1)])
def test_initial_reproducible_bounded(cfg,strategy,n,dimension):
 cfg.update(strategy=strategy,count=n)
 if dimension==2:cfg['axes'].append({'parameter':'mass_kg','minimum':1.,'maximum':4.})
 a=sampling.initial(cfg);assert a==sampling.initial(cfg);assert 1<=len(a['points'])<=n
 assert len({rail.digest(x['parameters']) for x in a['points']})==len(a['points'])
 for x in a['points']:c.point_allowed(x['parameters'],cfg)
 assert all('not measured' in x['reason'] for x in a['points'])

def test_space_filling_seed(cfg):
 cfg.update(strategy='space_filling',count=5);cfg['axes'].append({'parameter':'mass_kg','minimum':1.,'maximum':4.})
 a=sampling.initial(cfg);cfg['seed']+=1;assert a!=sampling.initial(cfg)

def test_threshold_expected(cfg):
 cfg['strategy']='near_threshold';points=sampling.initial(cfg)['points'];assert points[1]['parameters']['gap_m']==1.49

def test_invalid_threshold_and_endpoint_budget(cfg):
 cfg.update(strategy='endpoints',count=1)
 with pytest.raises(ValueError):sampling.initial(cfg)
 cfg.update(strategy='near_threshold');cfg['axes'][0].update(minimum=.35,maximum=.5)
 with pytest.raises(ValueError):sampling.initial(cfg)

def test_midpoint_refinement_and_no_automatic_run(cfg):
 rows=[record(1.,.01),record(2.,.2)];a=sampling.adaptive(cfg,rows,[],2)
 assert a['points'][0]['parameters']['gap_m']==1.5;assert set(a['points'][0]['neighbors'])=={r['id'] for r in rows};assert a['algorithm']=='midpoint_v1'
 assert len(a['points'])==1

def test_resolution_budget_and_duplicates(cfg):
 rows=[record(1.,.01),record(2.,.2)]
 assert sampling.adaptive(cfg,rows,[],0)['termination']=='PROPOSAL_BUDGET_EXHAUSTED'
 cfg['minimum_spacing']=.4;assert not sampling.adaptive(cfg,rows,[],2)['points']
 cfg['minimum_spacing']=.001;assert not sampling.adaptive(cfg,rows,[{**cfg['fixed_parameters'],'gap_m':1.5}],2)['points']

@pytest.mark.parametrize('outcomes,status',[([True,True],'No measured PASS/FAIL transition'),([False,False],'No measured passing case')])
def test_no_fabricated_boundary(outcomes,status):
 rows=[record(1.,verdict='PASS' if outcomes[0] else 'FAIL'),record(2.,verdict='PASS' if outcomes[1] else 'FAIL')];b=analysis.boundaries(rows,['gap_m']);assert not b['intervals'];assert status in b['status']

def test_multiple_intervals():
 rows=[record(.5,.1),record(1.,.01),record(1.5,.2)];b=analysis.boundaries(rows,['gap_m']);assert len(b['intervals'])==2;assert all(v['width']==.5 for v in b['intervals'])

@pytest.mark.parametrize('field',['controller','source','criteria','simulation','physics'])
def test_incompatible_boundaries_excluded(field,cfg):
 rows=[record(1.,.01),record(2.,.2)];rows[1]['compatibility'][field]='different';assert not analysis.boundaries(rows,['gap_m'])['intervals'];assert not sampling.adaptive(cfg,rows,[],2)['points']

@pytest.mark.parametrize('status',['CANCELLED','EXECUTION_ERROR','NOT_EXECUTED','RUNNING'])
def test_intermediate_unexecuted_prevents_bracket(status):
 rows=[record(1.,.01),record(2.,.2),record(1.5,.1)];rows[-1].update(status=status,verified=False);b=analysis.boundaries(rows,['gap_m']);assert b['excluded_unverified_or_unexecuted']==1;assert not b['intervals']

def test_fixed_parameter_difference_excluded():
 assert not analysis.boundaries([record(1.,.01),record(2.,.2,mass_kg=3.)],['gap_m'])['intervals']

def test_adaptive_two_dimensional_scores_determinism(cfg):
 cfg.update(type='adaptive_2d',count=4);cfg['axes'].append({'parameter':'mass_kg','minimum':1.,'maximum':4.})
 rows=[record(.5,.01),record(2.,.2)];a=sampling.adaptive(cfg,rows,[],4);assert a==sampling.adaptive(cfg,rows,[],4);assert len(a['points'])==4
 assert all('not calibrated uncertainty' in x['reason'] and x['neighbors'] for x in a['points'])

@pytest.mark.parametrize('key,expected',[('mass_kg',.36),('speed_mps',2.4),('force_n',-.72),('gap_m',0)])
def test_derivatives_independently_derived(key,expected):
 a=analysis.analytical({'mass_kg':4.,'speed_mps':1.2,'force_n':2.,'gap_m':1.49});assert a['derivatives'][key]==pytest.approx(expected)
 assert a['stopping_distance_m']==1.44;assert a['elasticities']['speed_mps']==2.

def test_zero_output_elasticities():
 a=analysis.analytical({'mass_kg':2.,'speed_mps':0.,'force_n':4.,'gap_m':1.});assert all(v is None for v in a['elasticities'].values());assert a['derivatives']['speed_mps']==0.

def test_irregular_central_difference_quadratic():
 rows=[record(x,x*x) for x in [1.,1.5,2.2]];d=analysis.finite_differences(rows,rows[1]['id'])['estimates'][0];assert d['derivative']==pytest.approx(3.);assert d['method']=='THREE_POINT_IRREGULAR_CENTRAL';assert d['spacings']==pytest.approx([.5,.7]);assert len(d['case_ids'])==3

def test_one_sided_and_missing_neighbors():
 rows=[record(1.,2.),record(2.,4.)];a=analysis.finite_differences(rows,rows[0]['id']);assert a['estimates'][0]['derivative']==2.;assert a['estimates'][0]['method']=='ONE_SIDED_SECANT'
 rows[1]['compatibility']['source']='different';assert not analysis.finite_differences(rows,rows[0]['id'])['estimates']
 with pytest.raises(ValueError):analysis.finite_differences(rows,'unknown')

def test_pareto_safety_constraints_fairness_and_equal_values():
 a=record(1.,.1);b=copy.deepcopy(a);b.update(id='b',controller_id='second');b['compatibility']['controller']='second';b['metrics']={'minimum_clearance_m':.2,'maximum_actuator_force_n':1.}
 unsafe=copy.deepcopy(b);unsafe.update(id='unsafe',verdict='FAIL');result=analysis.pareto([a,b,unsafe]);assert result['status']=='CONTROLLED_SAMPLED_COMPARISON';assert result['excluded']==1;assert [r['non_dominated'] for r in result['rows']]==[False,True]
 b['parameters']['mass_kg']=3.;assert analysis.pareto([a,b])['status']=='INSUFFICIENT_MATCHED_CONTROLLER_PAIRS'
 b['parameters']=copy.deepcopy(a['parameters']);b['metrics']=copy.deepcopy(a['metrics']);assert all(r['non_dominated'] for r in analysis.pareto([a,b])['rows'])
 with pytest.raises(ValueError):analysis.pareto([a],{'minimum_clearance_m':'min'})

def test_registry_mathematics_never_executes():
 assert registry.candidate_force('candidate_velocity_damping',1.,2.,2.,1.,k=3.)==-2.
 assert registry.candidate_force('candidate_distance_aware',1.,2.,2.,.2)==-2.
 assert registry.candidate_force('candidate_fixed_distance',-1.,2.,2.,.2)==2.
 assert registry.candidate_force('candidate_fixed_distance',1.,2.,2.,1.)==0.
 with pytest.raises(ValueError):registry.candidate_force('arbitrary',1.,2.,2.,1.)

def test_graph_dangling_cycle_duplicate_and_prediction_laundering():
 nodes=[{'id':'a','type':'proposal','label':'synthetic','reference':None},{'id':'b','type':'proposal','label':'synthetic','reference':None}];g={'version':1,'nodes':nodes,'edges':[{'from':'a','to':'b','type':'derived_from'}]};assert graph.validate_graph(g)==g
 g['edges'].append({'from':'b','to':'a','type':'derived_from'})
 with pytest.raises(ValueError):graph.validate_graph(g)
 g['edges']=[{'from':'a','to':'missing','type':'references'}]
 with pytest.raises(ValueError):graph.validate_graph(g)
 g['edges']=[{'from':'a','to':'b','type':'derived_from'}];nodes[0]['type']='finding'
 with pytest.raises(ValueError):graph.validate_graph(g)
 g['edges']=[];nodes.append(copy.deepcopy(nodes[0]))
 with pytest.raises(ValueError):graph.validate_graph(g)

def test_invalid_graph_size():
 nodes=[{'id':str(i),'type':'prediction','label':'Synthetic','reference':None} for i in range(513)]
 with pytest.raises(ValueError):graph.validate_graph({'version':1,'nodes':nodes,'edges':[]})

def test_missing_metrics_and_pareto_no_false_optimum():
 a=record(1.,.1);a['metrics']['maximum_actuator_force_n']=None;assert not analysis.pareto([a])['rows']
 b=record(2.,.2);b['verified']=False;assert analysis.boundaries([b],['gap_m'])['status']=='INSUFFICIENT_COMPARABLE_EVIDENCE'

@pytest.mark.parametrize('bad',[0,-1,float('inf'),True])
def test_analytical_rejects_invalid_force(bad):
 with pytest.raises(ValueError):analysis.analytical({'mass_kg':2.,'speed_mps':.6,'force_n':bad,'gap_m':1.})


def test_conflicting_duplicate_outcomes_do_not_form_a_boundary():
 rows=[record(1.,.01),record(1.,.2),record(2.,.3)];assert not analysis.boundaries(rows,['gap_m'])['intervals']

def test_missing_or_nonfinite_metric_and_derivative_unit():
 rows=[record(1.,.1),record(2.,.2)];rows[0]['metrics']['minimum_clearance_m']=float('nan');assert not analysis.boundaries(rows,['gap_m'])['intervals'];assert not analysis.finite_differences(rows,rows[0]['id'])['estimates']
 rows=[record(1.,y,speed_mps=x) for x,y in [(1.,.2),(1.2,.3)]];d=analysis.finite_differences(rows,rows[0]['id'])['estimates'][0];assert d['unit']=='m/(m/s)';assert d['derivative']==pytest.approx(.5)
