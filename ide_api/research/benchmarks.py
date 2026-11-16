"""Bounded offline strategy evaluation. Oracle outputs are NEVER native evidence."""
import math,random,hashlib
from pathlib import Path
from .contracts import obj,NUM,validate,data_digest
from .artifacts import ArtifactStore,canonical,finite_json,now
from .sampling import evenly
from . import analysis

ENVIRONMENTS=('analytical_rail','single_transition','multiple_transitions','narrow_failure','all_pass','all_fail','two_dimensional')
STRATEGIES=('uniform','seeded_stratified','adaptive')
SCHEMA=obj({'environment':{'enum':list(ENVIRONMENTS)},'budget':{'type':'integer','minimum':3,'maximum':25},'seed':{'type':'integer','minimum':0,'maximum':2147483647},'resolution':{'type':'number','minimum':.000001,'maximum':.1}})


def config(value):return validate(SCHEMA,value)
def environment(name):
 if name not in ENVIRONMENTS:raise ValueError('Unknown offline environment')
 return {'id':name,'dimension':2 if name=='two_dimensional' else 1,'domain':[[1.4,1.6]] if name=='analytical_rail' else [[0.,1.],[0.,1.]] if name=='two_dimensional' else [[0.,1.]],'provenance':'ANALYTICAL_ORACLE_NOT_MUJOCO' if name=='analytical_rail' else 'SYNTHETIC_ALGORITHM_FIXTURE','initial_information':'Domain, budget, seed and target only; zero free observations. Adaptive first endpoints/corners count as queries.','definition':{'analytical_rail':'gap - 4*1.2^2/(2*2) >= .05; ideal continuous clearance only','single_transition':'u >= .37','multiple_transitions':'u < .25 or u >= .75','narrow_failure':'outside [.47,.495)','all_pass':'always oracle PASS','all_fail':'always oracle FAIL','two_dimensional':'u+v >=1'}[name]}

def classify(name,point):
 # Kept inside driver: selectors receive history, never this oracle or hidden transition values.
 x=point[0]
 return (x-4*1.2**2/(2*2)>=.05 if name=='analytical_rail' else x>=.37 if name=='single_transition' else x<.25 or x>=.75 if name=='multiple_transitions' else not .47<=x<.495 if name=='narrow_failure' else True if name=='all_pass' else False if name=='all_fail' else x+point[1]>=1.)

def brackets(history):
 ordered=sorted(history,key=lambda v:v['point'][0]);out=[]
 for left,right in zip(ordered,ordered[1:]):
  if left['outcome']!=right['outcome']:out.append({'lower':left['point'][0],'upper':right['point'][0],'width':right['point'][0]-left['point'][0],'query_indices':[left['query'],right['query']]})
 return out

def baseline(strategy,domain,budget,seed):
 d=len(domain);rng=random.Random(seed)
 if strategy=='uniform':
  if d==1:return [[x] for x in evenly(*domain[0],budget)]
  side=math.ceil(math.sqrt(budget));pool=[[x,y] for y in evenly(*domain[1],side) for x in evenly(*domain[0],side)];selected=[pool.pop(0)]
  # Outcome-blind maximin ordering prevents a truncated final grid row from omitting an edge.
  while len(selected)<budget:
   next_point=max(pool,key=lambda p:(min(sum(((a-b)/(hi-lo))**2 for a,b,(lo,hi) in zip(p,q,domain)) for q in selected),tuple(-v for v in p)));pool.remove(next_point);selected.append(next_point)
  return selected
 columns=[]
 for lo,hi in domain:
  values=[round(lo+(hi-lo)*(i+rng.random())/budget,6) for i in range(budget)];rng.shuffle(values);columns.append(values)
 return [list(p) for p in zip(*columns)]

def choose_adaptive(domain,history):
 """History-only policy. No environment name, threshold or oracle handle."""
 d=len(domain);used={tuple(r['point']) for r in history}
 if d==1:
  lo,hi=domain[0]
  if not history:return [lo],1,'Counted initial lower endpoint'
  if len(history)==1:return [hi],1,'Counted initial upper endpoint'
  intervals=brackets(history)
  gaps=intervals if intervals else [{'lower':a,'upper':b,'width':b-a} for a,b in zip(sorted(r['point'][0] for r in history),sorted(r['point'][0] for r in history)[1:])]
  for gap in sorted(gaps,key=lambda v:(-v['width'],v['lower'])):
   p=[round((gap['lower']+gap['upper'])/2,6)]
   if tuple(p) not in used:return p,len(gaps),'Observed opposite-oracle midpoint' if intervals else 'Coverage midpoint; no observed transition'
  return None,len(gaps),'NO_DISTINCT_POINT'
 corners=[[a,b] for a in domain[0] for b in domain[1]]
 for p in corners:
  if tuple(p) not in used:return p,1,'Counted initial domain corner'
 candidates=[];cost=0
 def distance(a,b):return math.sqrt(sum(((x-y)/(hi-lo))**2 for x,y,(lo,hi) in zip(a,b,domain)))
 for y in evenly(*domain[1],9):
  for x in evenly(*domain[0],9):
   p=[x,y]
   if tuple(p) in used:continue
   cost+=1;near=sorted(history,key=lambda h:(distance(p,h['point']),h['query']))[:4];disagree=len({h['outcome'] for h in near})>1;nearest=distance(p,near[0]['point']);candidates.append((4*int(disagree)+nearest,p))
 if not candidates:return None,cost,'NO_DISTINCT_POINT'
 score,p=sorted(candidates,key=lambda v:(-v[0],v[1]))[0];return p,cost,'Local oracle-outcome disagreement plus normalized coverage; not probability'

def known_transitions(name):return [1.49] if name=='analytical_rail' else [.37] if name=='single_transition' else [.25,.75] if name=='multiple_transitions' else [.47,.495] if name=='narrow_failure' else []

def evaluate(value):
 config(value);env=environment(value['environment']);budget=value['budget'];runs=[]
 for strategy in STRATEGIES:
  fixed=baseline(strategy,env['domain'],budget,value['seed']) if strategy!='adaptive' else None
  history=[];rounds=[];duplicates=0;cost=0;reached=None;reason='QUERY_BUDGET_EXHAUSTED'
  for index in range(budget):
   point,assessed,rationale=choose_adaptive(env['domain'],history) if strategy=='adaptive' else (fixed[index],1,'Fixed outcome-blind '+strategy+' sequence')
   cost+=assessed
   if point is None:reason='NO_VALID_DISTINCT_POINT';break
   if tuple(point) in {tuple(r['point']) for r in history}:duplicates+=1;reason='DUPLICATE_QUERY_REJECTED';break
   outcome='ORACLE_PASS' if classify(env['id'],point) else 'ORACLE_FAIL';history.append({'query':index+1,'point':point,'outcome':outcome,'rationale':rationale,'provenance':env['provenance']})
   intervals=brackets(history) if env['dimension']==1 else []
   rounds.append({'queries':len(history),'intervals':intervals,'smallest_observed_width':min((b['width'] for b in intervals),default=None),'executed_native':False})
   if intervals and all(b['width']<=value['resolution']+1e-12 for b in intervals):
    reached=len(history);reason='OBSERVED_INTERVAL_TARGET_REACHED';break
  intervals=brackets(history) if env['dimension']==1 else []
  truth=known_transitions(env['id']) # Evaluated only AFTER selection, never passed to a selector.
  detected=[t for t in truth if any(b['lower']<=t<=b['upper'] for b in intervals)]
  metrics={'evaluated_points':len(history),'observed_transition_count':len(intervals),'bracket_widths':[b['width'] for b in intervals],'smallest_observed_bracket_width':min((b['width'] for b in intervals),default=None),'queries_to_target':reached,'duplicate_queries':duplicates,'known_transitions_covered':len(detected),'known_transitions_missed':len(truth)-len(detected),'candidate_scores_evaluated':cost,'termination':reason if intervals or env['dimension']==2 else reason+'_NO_TRANSITION_OBSERVED'}
  if env['dimension']==2:
   points=[h['point'] for h in history];distance=lambda a,b:math.hypot(a[0]-b[0],a[1]-b[1]);lattice=[[i/8,j/8] for i in range(9) for j in range(9)];metrics.update(normalized_fill_distance=max(min(distance(p,s) for s in points) for p in lattice),queried_points_near_known_line=sum(abs(p[0]+p[1]-1)<=.05 for p in points),opposite_outcome_neighbor_pairs=sum(a['outcome']!=b['outcome'] and distance(a['point'],b['point'])<=.4 for i,a in enumerate(history) for b in history[i+1:]))
  runs.append({'strategy':strategy,'version':1,'seed':value['seed'],'maximum_queries':budget,'history':history,'rounds':rounds,'metrics':metrics,'known_truth_used_for_selection':False})
 out={'format':'EMBODY_OFFLINE_STRATEGY_BENCHMARK_V1','config':value,'environment':env,'runs':runs,'implementation_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'native_cases':0,'native_rollouts':0,'native_integration_steps':0,'paid_calls':0,'limitations':['Analytical/synthetic classifications are not MuJoCo measurements.','Equal maximum query budgets, zero free initial observations, common stopping rule. Actual queries may differ after target reached.','A narrow region may be missed; observed bracket resolution does not prove all transitions found.','Candidate cost counts evaluated scores, not elapsed runtime or physical efficiency.','No claim that adaptive sampling outperforms uniform in real physics.']};out['id']=data_digest(out)[:32];return out

class Benchmarks:
 def __init__(self,root):self.store=ArtifactStore(root)
 def run(self,value,project_id=None,campaign_id=None):
  config(value)
  if len(list(self.store.root.glob('benchmarks/*.json')))>=32:raise ValueError('Benchmark retention quota; no automatic deletion')
  result=evaluate(value);self.store.write_once('benchmarks/'+result['id']+'.json',canonical(result),500000)
  if project_id is not None:
   from .artifacts import identifier
   identifier(project_id);identifier(campaign_id)
   if len(list(self.store.root.glob('benchmark_links/'+project_id+'_'+campaign_id+'/*.json')))>=8:raise ValueError('Campaign benchmark link quota')
   self.store.write_once('benchmark_links/'+project_id+'_'+campaign_id+'/'+result['id']+'.json',canonical({'id':result['id']}),1000)
  return result
 def read(self,key):
  from .artifacts import identifier
  value=finite_json(self.store.read('benchmarks/'+identifier(key)+'.json',500000),500000)
  if value.get('id')!=key or data_digest({k:v for k,v in value.items() if k!='id'})[:32]!=key:raise ValueError('Saved benchmark identity differs')
  if value['implementation_sha256']==hashlib.sha256(Path(__file__).read_bytes()).hexdigest() and evaluate(value['config'])!=value:raise ValueError('Current deterministic benchmark differs')
  return value
 def for_campaign(self,project_id,campaign_id):return [self.read(p.stem) for p in sorted(self.store.root.glob('benchmark_links/'+project_id+'_'+campaign_id+'/*.json'))]
 def catalog(self):return {'environments':[environment(n) for n in ENVIRONMENTS],'strategies':list(STRATEGIES),'maximum_queries':25,'runs':[p.stem for p in sorted(self.store.root.glob('benchmarks/*.json'))],'native_execution':False}

def retrospective(records):
 groups={}
 for r in records:
  if not analysis.is_measured(r):continue
  key=data_digest(r['compatibility']);groups.setdefault(key,[]).append(r)
 return {'status':'INSUFFICIENT_COMPARABLE_MEASURED_DATA_FOR_STRATEGY_BENCHMARK','eligible_cohorts':[{'source_controller_contract':k,'available_case_ids':[r['id'] for r in rows],'count':len(rows)} for k,rows in sorted(groups.items())],'query_count':0,'reason':'Pinned historical cohorts are sparse and do not supply a common uniform/adaptive oracle over unsampled points. No interpolation or hidden outcomes are substituted.','provenance':'RETROSPECTIVE_MEASURED_DATA_AVAILABILITY_NOT_NEW_NATIVE_BENCHMARK'}
