"""Comparability-first analysis. No interpolation is a measured observation."""
import math
from ide_api import rail_sweeps as rail
from .contracts import PARAMS
from .registry import METRICS

def compatible(a,b,vary=(),benchmark=False):
 if not a.get('verified') or not b.get('verified') or a['status']!='MEASURED' or b['status']!='MEASURED':return False
 keys=['physics','source','criteria','simulation']+([] if benchmark else ['controller'])
 return all(a['compatibility'][k]==b['compatibility'][k] for k in keys) and all(a['parameters'][k]==b['parameters'][k] for k in PARAMS if k not in vary)

def is_measured(r):
 return bool(r.get('verified') and r.get('status')=='MEASURED' and r.get('verdict') in ('PASS','FAIL') and all(type(r.get('parameters',{}).get(k)) in (int,float) and math.isfinite(r['parameters'][k]) for k in PARAMS) and type(r.get('metrics',{}).get('minimum_clearance_m')) in (int,float) and math.isfinite(r['metrics']['minimum_clearance_m']))

def boundaries(records,axes):
 valid=[r for r in records if is_measured(r)];intervals=[];excluded=len(records)-len(valid)
 for key in axes:
  groups={}
  for r in valid:
   cohort=rail.digest({'compatibility':r['compatibility'],'fixed':{k:v for k,v in r['parameters'].items() if k!=key}})
   groups.setdefault(cohort,[]).append(r)
  for group in groups.values():
   ordered=sorted(group,key=lambda r:(r['parameters'][key],r['id']));values={}
   for r in ordered:values.setdefault(r['parameters'][key],[]).append(r)
   if any(len({r['verdict'] for r in same})>1 for same in values.values()):continue
   ordered=[values[x][0] for x in sorted(values)]
   for left,right in zip(ordered,ordered[1:]):
    lo,hi=left['parameters'][key],right['parameters'][key]
    if left['verdict']==right['verdict']:continue
    if any(compatible(left,{**x,'verified':True,'status':'MEASURED'},[key]) and lo<x['parameters'][key]<hi for x in records):continue
    intervals.append({'parameter':key,'lower':lo,'upper':hi,'width':hi-lo,'unit':rail.UNITS[key],'case_ids':[left['id'],right['id']],'outcomes':[left['verdict'],right['verdict']],'fixed_parameters':{k:v for k,v in left['parameters'].items() if k!=key},'compatibility':left['compatibility'],'kind':'OBSERVED_SAMPLED_TRANSITION_INTERVAL'})
 outcomes={r['verdict'] for r in valid}
 reason='OBSERVED_INTERVALS' if intervals else 'No measured PASS/FAIL transition has been observed.' if outcomes=={'PASS'} else 'No measured passing case has been observed in the sampled domain.' if outcomes=={'FAIL'} else 'INSUFFICIENT_COMPARABLE_EVIDENCE'
 return {'status':reason,'intervals':intervals,'excluded_unverified_or_unexecuted':excluded,'limitations':['Intervals are local sampled brackets, never exact/global failure boundaries.','Different sources, controllers, criteria, configuration or fixed parameters cannot form a bracket.']}

def analytical(p):
 p=rail.parameters(p);m,v,f,g=(p[k] for k in PARAMS);d=m*v*v/(2*f)
 derivatives={'mass_kg':v*v/(2*f),'speed_mps':m*v/f,'force_n':-m*v*v/(2*f*f),'gap_m':0.}
 elasticities={k:None if d==0 else derivatives[k]*p[k]/d for k in PARAMS}
 perturbations={}
 for k in PARAMS:
  lo,hi=rail.BOUNDS[k];x=min(hi,max(lo,round(p[k]*1.01 if p[k] else .001,6)));q={**p,k:x};dd=q['mass_kg']*q['speed_mps']**2/(2*q['force_n'])
  perturbations[k]={'parameter_value':x,'delta_stopping_distance_m':dd-d,'actual_delta_parameter':x-p[k]}
 return {'kind':'ANALYTICAL_IDEAL_BRAKING','reference':p,'stopping_distance_m':d,'derivatives':derivatives,'units':{'mass_kg':'m/kg','speed_mps':'s','force_n':'m/N','gap_m':'m/m'},'elasticities':elasticities,'perturbations':perturbations,'influence_rank':sorted(PARAMS,key=lambda k:-(abs(elasticities[k]) if elasticities[k] is not None else -1)),'limitations':['Ideal immediate constant braking only. Elasticities undefined at zero output. Not measured controller behavior.']}

def finite_differences(records,reference,metric='minimum_clearance_m'):
 if metric not in METRICS:raise ValueError('Unknown measured metric')
 center=next((r for r in records if r['id']==reference and r.get('verified') and r['status']=='MEASURED'),None)
 if center is None:raise ValueError('Verified reference case required')
 if type(center['metrics'].get(metric)) not in (int,float) or not math.isfinite(center['metrics'][metric]):return {'status':'INSUFFICIENT_COMPARABLE_NEIGHBORS','estimates':[],'limitations':['Reference metric missing/nonfinite; no analytical substitute.']}
 out=[]
 for key in PARAMS:
  group=[r for r in records if compatible(center,r,[key]) and type(r['metrics'].get(metric)) in (int,float) and math.isfinite(r['metrics'][metric])]
  x=center['parameters'][key];left=sorted((r for r in group if r['parameters'][key]<x),key=lambda r:r['parameters'][key]);right=sorted((r for r in group if r['parameters'][key]>x),key=lambda r:r['parameters'][key])
  if center['metrics'].get(metric) is None or not left and not right:continue
  if left and right:
   a,b=left[-1],right[0];h=x-a['parameters'][key];j=b['parameters'][key]-x;y=center['metrics'][metric]
   derivative=-j/(h*(h+j))*a['metrics'][metric]+(j-h)/(h*j)*y+h/(j*(h+j))*b['metrics'][metric];ids=[a['id'],center['id'],b['id']];method='THREE_POINT_IRREGULAR_CENTRAL';spacings=[h,j]
  else:
   other=left[-1] if left else right[0];dx=other['parameters'][key]-x;derivative=(other['metrics'][metric]-center['metrics'][metric])/dx;ids=[center['id'],other['id']];method='ONE_SIDED_SECANT';spacings=[abs(dx)]
  out.append({'parameter':key,'metric':metric,'derivative':derivative,'unit':METRICS[metric]['unit']+'/('+rail.UNITS[key]+')','case_ids':ids,'spacings':spacings,'method':method})
 return {'status':'AVAILABLE' if out else 'INSUFFICIENT_COMPARABLE_NEIGHBORS','estimates':out,'limitations':['Finite sampled estimates; no continuous derivative or global ranking is established.']}

def pareto(records,objectives=None):
 objectives=objectives or {'minimum_clearance_m':'max','maximum_actuator_force_n':'min'}
 if not objectives or len(objectives)>4 or any(k not in METRICS or v not in ('min','max') or METRICS[k]['direction']!=v for k,v in objectives.items()):raise ValueError('Supported objective directions required')
 eligible=[r for r in records if r.get('verified') and r['status']=='MEASURED' and r['verdict']=='PASS' and all(type(r['metrics'].get(k)) in (int,float) and math.isfinite(r['metrics'][k]) for k in objectives)]
 rows=[]
 for a in eligible:
  peers=[b for b in eligible if compatible(a,b,benchmark=True)]
  def dominates(b):
   diffs=[(b['metrics'][k]-a['metrics'][k])*(1 if direction=='max' else -1) for k,direction in objectives.items()]
   return all(d>=0 for d in diffs) and any(d>0 for d in diffs)
  controllers={b['controller_id'] for b in peers}
  rows.append({'case_id':a['id'],'controller_id':a['controller_id'],'objectives':{k:a['metrics'][k] for k in objectives},'non_dominated':not any(dominates(b) for b in peers),'comparable_cases':[b['id'] for b in peers],'distinct_controllers':len(controllers),'source_current':a['source_current']})
 return {'status':'CONTROLLED_SAMPLED_COMPARISON' if any(r['distinct_controllers']>1 for r in rows) else 'INSUFFICIENT_MATCHED_CONTROLLER_PAIRS','objectives':objectives,'rows':rows,'excluded':len(records)-len(eligible),'limitations':['Safety is a constraint: failed/unverified/missing-metric points excluded.','Non-dominated only within eligible identical-configuration set; not global optimum.','Source and physical contract differences prevent fair comparison.']}
