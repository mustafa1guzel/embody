"""Deterministic bounded sampling and explainable selection, never execution."""
import itertools,math,random
from ide_api import rail_sweeps as rail
from .contracts import PARAMS,point_allowed
from .analysis import boundaries,compatible,is_measured

def ideal(p,criteria):
 m,v,f,g=(p[k] for k in PARAMS);d=m*v*v/(2*f);t=m*v/f
 return {'kind':'ANALYTICAL_PREDICTION','stopping_distance_m':d,'stopping_time_s':t,'remaining_clearance_m':g-d,'clearance_margin_m':g-d-criteria['minimumClearance'],'time_margin_s':criteria['maximumSettlingTime']-t}

def evenly(a,b,n):return [round(a+(b-a)*i/(n-1),6) for i in range(n)] if n>1 else [round((a+b)/2,6)]
def pack(cfg,values,reason):
 points=[];seen=set()
 for coords in values:
  p={**cfg['fixed_parameters'],**{a['parameter']:round(v,6) for a,v in zip(cfg['axes'],coords)}};point_allowed(p,cfg)
  if rail.digest(p) not in seen:points.append({'parameters':p,'reason':reason,'neighbors':[],'score':None});seen.add(rail.digest(p))
 return points

def initial(cfg):
 axes=cfg['axes'];n=cfg['count'];d=len(axes);strategy=cfg['strategy']
 if strategy=='endpoints':
  if n<2**d:raise ValueError('Endpoint strategy needs at least one point at each corner')
  values=itertools.product(*[[a['minimum'],a['maximum']] for a in axes])
 elif strategy=='uniform':
  side=n if d==1 else math.isqrt(n)
  values=itertools.product(*[evenly(a['minimum'],a['maximum'],side) for a in axes])
 elif strategy=='space_filling':
  rng=random.Random(cfg['seed']);columns=[]
  for a in axes:
   values=evenly(a['minimum'],a['maximum'],n);rng.shuffle(values);columns.append(values)
  values=zip(*columns)
 else:
  if d!=1:raise ValueError('Near-threshold analytical sampling requires one axis')
  a=axes[0];p=cfg['fixed_parameters'];m,v,f,g=(p[k] for k in PARAMS);clear=cfg['criteria']['minimumClearance']
  threshold={'gap_m':clear+m*v*v/(2*f),'speed_mps':math.sqrt(max(0,2*f*(g-clear)/m)), 'mass_kg':None if v==0 else 2*f*(g-clear)/(v*v),'force_n':None if g<=clear else m*v*v/(2*(g-clear))}[a['parameter']]
  if threshold is None or not a['minimum']<=threshold<=a['maximum']:raise ValueError('No ideal clearance threshold in this domain; choose uniform sampling')
  width=(a['maximum']-a['minimum'])/4;lo=max(a['minimum'],threshold-width);hi=min(a['maximum'],threshold+width)
  values=([v] for v in evenly(lo,hi,n))
 points=pack(cfg,values,'Deterministic '+strategy+' v1; analytical expectation, not measured evidence')
 if len(points)>n or not points:raise ValueError('Invalid sample budget')
 return {'algorithm':'initial_v1','seed':cfg['seed'],'points':points,'termination':'BATCH_READY','origin':'DETERMINISTIC_ANALYTICAL_NOT_AI'}

def adaptive(cfg,records,previous,remaining):
 axes=cfg['axes'];spacing=cfg['minimum_spacing'];d=len(axes);used={rail.digest(p) for p in previous};limit=min(cfg['count'],25,remaining)
 if limit<=0:return {'algorithm':'adaptive_v1','points':[],'termination':'PROPOSAL_BUDGET_EXHAUSTED'}
 valid=[r for r in records if is_measured(r) and all(a['minimum']<=r['parameters'][a['parameter']]<=a['maximum'] for a in axes) and all(r['parameters'][k]==cfg['fixed_parameters'][k] for k in PARAMS if k not in [a['parameter'] for a in axes])]
 if not valid:return {'algorithm':'adaptive_v1','points':[],'termination':'INSUFFICIENT_COMPARABLE_EVIDENCE'}
 groups={rail.digest(r['compatibility']) for r in valid}
 if len(groups)>1:return {'algorithm':'adaptive_v1','points':[],'termination':'MIXED_IDENTITIES_SELECT_ONE_COMPATIBLE_EVIDENCE_GROUP'}
 def distance(p,q):return math.sqrt(sum(((p[a['parameter']]-q[a['parameter']])/(a['maximum']-a['minimum']))**2 for a in axes))
 def available(p):return rail.digest(p) not in used and all(distance(p,r['parameters'])>=spacing-1e-12 for r in valid) and all(distance(p,q)>=spacing-1e-12 for q in previous)
 candidates=[]
 if d==1:
  axis=axes[0];name=axis['parameter'];brackets=boundaries(valid,[name])['intervals']
  for b in brackets:
   if b['width']/(axis['maximum']-axis['minimum'])<=2*spacing:continue
   p={**cfg['fixed_parameters'],name:round((b['lower']+b['upper'])/2,6)}
   if available(p):candidates.append({'parameters':p,'score':b['width']/(axis['maximum']-axis['minimum']),'reason':'Midpoint of verified adjacent sampled PASS/FAIL interval; not an exact boundary','neighbors':b['case_ids']})
  if brackets and not candidates:return {'algorithm':'midpoint_v1','points':[],'termination':'RESOLUTION_REACHED_OR_NO_NEW_VALID_MIDPOINT'}
  if not brackets:
   xs=sorted({axis['minimum'],axis['maximum'],*[r['parameters'][name] for r in valid]})
   for lo,hi in zip(xs,xs[1:]):
    p={**cfg['fixed_parameters'],name:round((lo+hi)/2,6)}
    if available(p):candidates.append({'parameters':p,'score':(hi-lo)/(axis['maximum']-axis['minimum']),'reason':'Coverage midpoint; no measured transition exists','neighbors':[]})
 else:
  pool=pack(cfg,itertools.product(*[evenly(a['minimum'],a['maximum'],9) for a in axes]),'')
  for item in pool:
   p=item['parameters']
   if not available(p):continue
   neighbors=sorted(valid,key=lambda r:(distance(p,r['parameters']),r['id']))[:4]
   nearest=distance(p,neighbors[0]['parameters']);disagreement=len({r['verdict'] for r in neighbors})>1
   # Dimensionless scales: clearance by selected clearance (minimum1mm), discrepancy by gap domain width or1m.
   margin=min(abs(r['metrics']['minimum_clearance_m']-cfg['criteria']['minimumClearance']) for r in neighbors)/max(.001,cfg['criteria']['minimumClearance'])
   discrepancy=max(abs(r['comparison']['measured_minus_ideal_clearance_m']) for r in neighbors)/max(.001,next((a['maximum']-a['minimum'] for a in axes if a['parameter']=='gap_m'),1.))
   components={'outcome_disagreement':4*int(disagreement),'clearance_proximity':2/(1+margin),'normalized_discrepancy':min(1,discrepancy),'normalized_coverage_distance':nearest}
   candidates.append({'parameters':p,'score':sum(components.values()),'reason':'Heuristic v1 '+str(components)+'; not calibrated uncertainty','neighbors':[r['id'] for r in neighbors]})
 candidates.sort(key=lambda r:(-r['score'],rail.digest(r['parameters'])))
 selected=[]
 for item in candidates:
  point_allowed(item['parameters'],cfg)
  if all(distance(item['parameters'],s['parameters'])>=spacing-1e-12 for s in selected):selected.append(item)
  if len(selected)==limit:break
 return {'algorithm':'midpoint_v1' if d==1 else 'normalized_local_rank_v1','points':selected,'termination':'BATCH_READY' if selected else 'NO_INFORMATIVE_NEW_POINT','origin':'DETERMINISTIC_MEASURED_GUIDANCE_NOT_AI'}
