"""Project-defined systems, typed quantities, requirements and discoverable contracts."""
import copy,re
from ide_api import rail_sweeps as rail
from ide_api.research.artifacts import finite_json
from physical_core import adapters,language
FORMAT='PHYSICAL_ENGINEERING_PROJECT_V1'
def req(id,expression,aggregation,operator,threshold,unit,band=None):return dict(id=id,expression=expression,aggregation=aggregation,operator=operator,threshold=threshold,unit=unit,band=band)
def floors(d):
 a=adapters.adapter(d['family']);limit=max(v['limit'] for v in a.actuators(d).values());unit=next(iter(a.actuators(d).values()))['unit']
 return [req(*v) for v in [('authority','actuator_peak','max','<=',limit,unit,None),('contacts','unexpected_contacts','max','<=',0.,'1',None),('completed','time_s','final','<=',a.steps*.005,'s',None),*a.mandatory(d)]]
def contract(d):
 a=adapters.adapter(d['family']);units={**a.units,**{k:v['unit'] for k,v in d['task']['constants'].items()}}
 return {'format':'PHYSICAL_CONTROL_CONTRACT_V1','family':d['family'],'observations':{k:v for k,v in units.items() if k!='actuator_peak'},'measurements':units,'actuators':a.actuators(d),'dt_s':.005,'steps':a.steps,'task':d['task'],'requirements':d['requirements']}
def template(family):
 a=adapters.adapter(family);v=copy.deepcopy(a.defaults);d={'format':FORMAT,'title':'Independent '+family,'family':family,'parameters':v['parameters'],'environment':v['environment'],'task':{'description':'Meet the declared physical requirements using the selected bounded source.','constants':v['constants']},'requirements':[]}
 d['requirements']=floors(d)+[req(*v) for v in a.extra(d)];return validate(d)
def validate(value):
 d=finite_json(rail.canonical(value),32768);rail.exact(d,['format','title','family','parameters','environment','task','requirements'])
 if d['format']!=FORMAT or not isinstance(d['title'],str) or not 1<=len(d['title'])<=100 or any(ord(c)<32 for c in d['title']):raise ValueError('Invalid versioned physical definition')
 a=adapters.adapter(d['family']);rail.exact(d['parameters'],a.parameter_bounds);rail.exact(d['environment'],a.environment_bounds)
 for values,bounds in [(d['parameters'],a.parameter_bounds),(d['environment'],a.environment_bounds)]:
  for k,(lo,hi) in bounds.items():values[k]=rail.number(values[k],lo,hi)
 rail.exact(d['task'],['description','constants']);desc=d['task']['description']
 if not isinstance(desc,str) or not 1<=len(desc)<=1000 or any(ord(c)<32 for c in desc):raise ValueError('Bounded task description required')
 constants=d['task']['constants']
 if not isinstance(constants,dict) or not 1<=len(constants)<=12:raise ValueError('One to12 explicit quantity constants required')
 for k,v in constants.items():
  if not re.fullmatch('[a-z][a-z0-9_]{0,47}',k) or k in a.units or k in a.actuators(d):raise ValueError('Constant conflicts with physical observation/action identity')
  rail.exact(v,['value','unit']);v['value']=rail.number(v['value'],-100,100)
  if v['unit'] not in language.DIMS:raise ValueError('Unsupported explicit SI unit')
 if d['family']=='differential_rover':
  if 'target_m' not in constants or constants['target_m']['unit']!='m' or not .02<=constants['target_m']['value']<=.12:raise ValueError('Supported target range .02–.12 m required')
  from ide_api.rover_reference import parameters
  parameters({**d['parameters'],'angle_deg':d['environment']['angle_deg'],'friction':d['environment']['friction'],'target_m':constants['target_m']['value']})
 requirements=d['requirements']
 if not isinstance(requirements,list) or not 1<=len(requirements)<=16:raise ValueError('One to16 project requirements required')
 seen=set();units={**a.units,**{k:v['unit'] for k,v in constants.items()}}
 for r in requirements:
  rail.exact(r,['id','expression','aggregation','operator','threshold','unit','band'])
  if not isinstance(r['id'],str) or not re.fullmatch('[a-z][a-z0-9_]{0,47}',r['id']) or r['id'] in seen:raise ValueError('Canonical unique requirement ID required')
  seen.add(r['id']);tree,u=language.expression(r['expression'],units)
  if r['unit'] not in language.DIMS or u=='bool' or r['operator'] not in ('<','<=','>','>=') or r['aggregation'] not in ('min','max','final','settling_time'):raise ValueError('Unsupported requirement quantity/evaluation')
  r['threshold']=rail.number(r['threshold'],-1000,1000)
  if r['aggregation']=='settling_time':
   if r['unit']!='s' or u!=language.DIMS['m/s']:raise ValueError('Settling requires a speed quantity and seconds result')
   r['band']=rail.number(r['band'],.0001,.1)
  elif r['band'] is not None or u is not None and u!=language.DIMS[r['unit']]:raise ValueError('Requirement unit/band mismatch')
 byid={r['id']:r for r in requirements}
 for minimum in floors(d):
  if minimum['id'] not in byid:raise ValueError('Missing mandatory physical requirement '+minimum['id'])
  r=byid[minimum['id']]
  if any(r[k]!=minimum[k] for k in ('expression','aggregation','operator','unit')):raise ValueError('Mandatory physical predicate cannot be replaced')
  if (r['operator'] in ('<','<=') and r['threshold']>minimum['threshold']) or (r['operator'] in ('>','>=') and r['threshold']<minimum['threshold']) or minimum['band'] is not None and r['band']>minimum['band']:raise ValueError('Mandatory physical requirement cannot be weakened')
 return d

def evaluate_requirements(d,samples):
 """One evaluator for every registered system and every supported project task."""
 units=contract(d)['measurements'];metrics={};checks={}
 for r in d['requirements']:
  tree,_=language.expression(r['expression'],units);values=[language.evaluate(tree,s['observations']) for s in samples];agg=r['aggregation']
  if agg=='min':value=min(values)
  elif agg=='max':value=max(values)
  elif agg=='final':value=values[-1]
  else:
   value=None
   for s,v in reversed(list(zip(samples,values))):
    if abs(v)>=r['band']:break
    value=s['time_s']
  metrics[r['id']]=value;t=r['threshold'];op=r['operator']
  checks[r['id']]=value is not None and {'<':lambda:value<t,'<=':lambda:value<=t+1e-12,'>':lambda:value>t,'>=':lambda:value>=t-1e-12}[op]()
 return metrics,checks
