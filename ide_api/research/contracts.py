"""Strict data contracts. Imported claims are never evidence authority."""
import math,re
from jsonschema import Draft202012Validator
from ide_api import rail_sweeps as rail
from ide_api.experiment_designer import text

LIMITS={'projects':8,'campaigns':12,'hypotheses':16,'findings':32,'events':128,'campaign_points':100,'batch':25,'graph_nodes':512,'graph_edges':1024,'bytes':120000}
PARAMS=tuple(rail.BOUNDS)
STRATEGIES=('uniform','endpoints','near_threshold','space_filling')
TYPES=('grid','adaptive_1d','adaptive_2d','sensitivity','benchmark','reproducibility')

def obj(fields):return {'type':'object','properties':fields,'required':list(fields),'additionalProperties':False}
def arr(items,n=25):return {'type':'array','items':items,'maxItems':n}
STRING={'type':'string','minLength':1,'maxLength':1200}
ID={'type':'string','pattern':'^[a-f0-9]{32}$'}
SHA={'type':'string','pattern':'^[a-f0-9]{64}$'}
NUM={'type':'number'}
CRITERIA=obj({k:NUM for k in rail.DEFAULT_CRITERIA})
CRITERIA['properties']['maximumContactEpisodes']={'type':'integer'}
PHYSICAL=obj({k:NUM for k in PARAMS})
AXIS=obj({'parameter':{'enum':list(PARAMS)},'minimum':NUM,'maximum':NUM})
CONFIG=obj({'experiment_id':{'const':rail.EXPERIMENT},'controller_id':{'const':rail.CONTROLLER},'objective':STRING,'type':{'enum':list(TYPES)},'axes':{**arr(AXIS,2),'minItems':1},'fixed_parameters':PHYSICAL,'criteria':CRITERIA,'strategy':{'enum':list(STRATEGIES)},'count':{'type':'integer','minimum':1,'maximum':25},'seed':{'type':'integer','minimum':0,'maximum':2147483647},'minimum_spacing':{'type':'number','minimum':.000001,'maximum':1},'proposal_budget':{'type':'integer','minimum':1,'maximum':100},'hypothesis_ids':arr(ID,16)})
HYPOTHESIS=obj({'statement':STRING,'relationship':STRING,'variables':{**arr({'enum':list(PARAMS)},4),'minItems':1,'uniqueItems':True},'direction':{'enum':['increase','decrease','unspecified']},'assumptions':arr(STRING,5),'evaluation':STRING})
BATCH=obj({'id':SHA,'cases':{**arr(PHYSICAL),'minItems':1},'rationales':arr(STRING),'strategy':STRING,'context_sha256':SHA,'parent_summary_sha256':{'anyOf':[SHA,{'type':'null'}]},'status':{'enum':['AWAITING_REVIEW','REVIEWED','REJECTED','TRANSFERRED']}})
REF=obj({'kind':{'enum':['native','recorded']},'id':{'type':'string','pattern':'^(?:[a-f0-9]{32}|portable_rail_study)$'},'summary_sha256':SHA,'association':{'enum':['EXTERNAL_REFERENCE','MATCHING_REVIEWED_BATCH']},'batch_id':{'anyOf':[SHA,{'type':'null'}]}})
CAMPAIGN=obj({'id':ID,'config':CONFIG,'context_sha256':SHA,'status':{'enum':['DRAFT','AWAITING_REVIEW','REVIEWED','TRANSFERRED','PARTIAL','MEASURED','COMPLETED','CANCELLED','ARCHIVED']},'batches':arr(BATCH,16),'evidence':arr(REF,8),'created_at':STRING})
HYP_STORED=obj({'id':ID,'content':HYPOTHESIS,'status':{'enum':['PROPOSED','UNDER_INVESTIGATION']}})
FINDING=obj({'id':ID,'campaign_id':ID,'summary_sha256':SHA,'fact_id':STRING})
EVENT=obj({'id':ID,'at':STRING,'kind':STRING,'subject':STRING})
PROJECT=obj({'version':{'const':1},'id':ID,'title':STRING,'question':STRING,'description':STRING,'experiment_id':{'enum':[rail.EXPERIMENT,'rover_ramp_reference_descriptor_v1']},'context_sha256':SHA,'status':{'enum':['ACTIVE','ARCHIVED']},'created_at':STRING,'updated_at':STRING,'hypotheses':arr(HYP_STORED,16),'campaigns':arr(CAMPAIGN,12),'findings':arr(FINDING,32),'open_questions':arr(STRING,16),'events':arr(EVENT,128)})

def validate(schema,value):
 if len(rail.canonical(value))>LIMITS['bytes']:raise ValueError('Research payload exceeds120000bytes')
 errors=list(Draft202012Validator(schema).iter_errors(value))
 if errors:raise ValueError('Research schema: '+str(errors[0].message)[:200])
 def walk(v):
  if isinstance(v,float) and not math.isfinite(v):raise ValueError('Nonfinite research value')
  if isinstance(v,str):text(v)
  elif isinstance(v,dict):
   for x in v.values():walk(x)
  elif isinstance(v,list):
   for x in v:walk(x)
 walk(value)
 return value

def config(v,catalog):
 validate(CONFIG,v);rail.parameters(v['fixed_parameters']);c=rail.criteria(v['criteria'])
 for k,mandatory in catalog['defaults'].items():
  if (k=='minimumClearance' and c[k]<mandatory) or (k!='minimumClearance' and c[k]>mandatory):raise ValueError('Mandatory acceptance cannot be weakened')
 axes=v['axes']
 if len({a['parameter'] for a in axes})!=len(axes):raise ValueError('Distinct axes required')
 for a in axes:
  lo,hi=catalog['bounds'][a['parameter']]
  if not lo<=a['minimum']<a['maximum']<=hi:raise ValueError('Ordered nondegenerate domain within catalog required')
  for n in [a['minimum'],a['maximum']]:rail.parameters({**v['fixed_parameters'],a['parameter']:n})
 if v['count']>v['proposal_budget']:raise ValueError('Initial count exceeds campaign proposal budget')
 if v['type']=='adaptive_1d' and len(axes)!=1:raise ValueError('One-dimensional campaign requires one axis')
 if v['type']=='adaptive_2d' and len(axes)!=2:raise ValueError('Two-dimensional campaign requires two axes')
 return v

def validate_project(p,catalog):
 validate(PROJECT,p)
 for key in ['hypotheses','campaigns','findings','events']:
  if len({x['id'] for x in p[key]})!=len(p[key]):raise ValueError('Duplicate research identities')
 hypotheses={h['id'] for h in p['hypotheses']};campaigns={c['id'] for c in p['campaigns']}
 for c in p['campaigns']:
  config(c['config'],catalog)
  if not set(c['config']['hypothesis_ids'])<=hypotheses:raise ValueError('Missing hypothesis reference')
  seen=set()
  for b in c['batches']:
   if len(b['cases'])!=len(b['rationales']):raise ValueError('Each point requires a rationale')
   ids=[rail.digest(x) for x in b['cases']]
   if len(set(ids))!=len(ids):raise ValueError('Duplicate batch point')
   for x in b['cases']:point_allowed(x,c['config'])
   if b['id']!=batch_id(b):raise ValueError('Batch identity differs')
   seen.update(ids)
  if len(seen)>c['config']['proposal_budget']:raise ValueError('Campaign proposed-point budget exceeded')
  if c['status']=='COMPLETED' and not c['evidence']:raise ValueError('Completion requires evidence references; reverified on reading')
 for f in p['findings']:
  if f['campaign_id'] not in campaigns:raise ValueError('Dangling finding campaign')
 return p

def data_digest(value):
 """Research-only semantic JSON identity. Native evidence digests are untouched.

 Numbers use finite IEEE754 doubles with normalized signed zero. Tagged values
 retain bool/string/object distinctions while surviving browser4.0-to-4 and
 exponent-format changes. All bounded integer fields are below2**53.
 """
 def tagged(v):
  if v is None:return ['null']
  if type(v) is bool:return ['bool',v]
  if type(v) in (int,float):
   f=float(v)
   if not math.isfinite(f):raise ValueError('Nonfinite research identity value')
   return ['number',(0. if f==0 else f).hex()]
  if isinstance(v,str):return ['string',v]
  if isinstance(v,(list,tuple)):return ['array',[tagged(x) for x in v]]
  if isinstance(v,dict):return ['object',[[k,tagged(v[k])] for k in sorted(v)]]
  raise ValueError('JSON data only')
 return rail.digest(tagged(value))

def batch_id(b):return data_digest({k:v for k,v in b.items() if k not in ('id','status')})
def point_allowed(p,cfg):
 rail.parameters(p)
 for k in PARAMS:
  axis=next((a for a in cfg['axes'] if a['parameter']==k),None)
  if axis:
   if not axis['minimum']<=p[k]<=axis['maximum']:raise ValueError('Point outside campaign domain')
  elif p[k]!=cfg['fixed_parameters'][k]:raise ValueError('Point changes fixed campaign condition')
 return p
