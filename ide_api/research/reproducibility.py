"""Portable inert manifests; review/execution authority never survives import."""
import copy
from ide_api import rail_sweeps as rail
from . import contracts as c
from .store import uid,now

FORMAT='EMBODY_RESEARCH_MANIFEST_V1'

def export(service,key):
 p=service.read(key)['project'];refs=[]
 for campaign in p['campaigns']:
  records,_,errors=service._records(campaign)
  refs.append({'campaign_id':campaign['id'],'verification':'UNVERIFIED' if errors else 'LOCALLY_RECHECKED','errors':errors,'cases':[{k:r[k] for k in ('id','result_sha256','trajectory_sha256','source_sha256','source_current','model_sha256','controller_id','metrics','simulation')} for r in records if r['verified']]})
 body={'format':FORMAT,'project':p,'descriptors':service.context()['descriptors'],'evidence_identities':refs,'limitations':['Imported measurements are claims until independently verified locally.','Review, native authority and provider approvals are not portable.','Historical/current source differences must be retained.']}
 body['manifest_sha256']=c.data_digest(body)
 if len(rail.canonical(body))>c.LIMITS['bytes']:raise ValueError('Export exceeds bounded manifest capacity; reduce campaign scope')
 return body

def validate_manifest(service,value):
 rail.exact(value,['format','project','descriptors','evidence_identities','limitations','manifest_sha256'])
 if value['format']!=FORMAT or len(rail.canonical(value))>c.LIMITS['bytes']:raise ValueError('Unsupported manifest/version/size')
 if value['manifest_sha256']!=c.data_digest({k:v for k,v in value.items() if k!='manifest_sha256'}):raise ValueError('Manifest identity mismatch')
 c.validate_project(value['project'],service.context()['catalog'])
 # Reconstruct all descriptor/evidence metadata; never accept opaque imported code or file paths.
 def walk(v):
  if isinstance(v,str):c.text(v)
  elif isinstance(v,dict):
   for x in v.values():walk(x)
  elif isinstance(v,list):
   for x in v:walk(x)
 walk(value)
 current={d['id']:d for d in service.context()['descriptors']}
 for d in value['descriptors']:
  if not isinstance(d,dict) or d.get('id') not in current:raise ValueError('Unregistered imported descriptor')
  if any(c.data_digest(d.get(k))!=c.data_digest(v) for k,v in current[d['id']].items() if k!='source_sha256'):raise ValueError('Unsupported imported descriptor contract; no controller or parameter registration by import')
 if len({d['id'] for d in value['descriptors']})!=2:raise ValueError('Duplicate descriptor identity')
 expected=export_shape(value)
 if not expected:raise ValueError('Invalid manifest descriptor/evidence shape')
 return value

def export_shape(value):
 # These are inert export metadata. Exact per-record fields/size and registered IDs prevent covert execution descriptors.
 if not isinstance(value['descriptors'],list) or len(value['descriptors'])!=2:return False
 for d in value['descriptors']:
  rail.exact(d,['id','version','name','domain','parameters','controllers','analytical_models','metrics','criteria','execution','source_sha256','limits','limitations'])
  if d['id'] not in (rail.EXPERIMENT,'rover_ramp_reference_descriptor_v1') or d['version']!=1:return False
 for ref in value['evidence_identities']:
  rail.exact(ref,['campaign_id','verification','errors','cases'])
  if ref['campaign_id'] not in [c['id'] for c in value['project']['campaigns']]:return False
  if len(ref['cases'])>100:return False
  for r in ref['cases']:
   rail.exact(r,['id','result_sha256','trajectory_sha256','source_sha256','source_current','model_sha256','controller_id','metrics','simulation'])
 return True

def import_manifest(service,value,accept_stale=False):
 validate_manifest(service,value);p=copy.deepcopy(value['project']);stale=p['context_sha256']!=service.context()['context_sha256']
 if stale and accept_stale is not True:raise ValueError('Stale context requires explicit archival-import acknowledgement; no execution or automatic migration')
 with service.lock:
  if len(service.listing())>=c.LIMITS['projects']:raise ValueError('Research retention quota reached')
  old=p['id'];p['id']=uid();p['status']='ACTIVE';p['title']='Imported '+p['title'][:180];p['created_at']=now();p['updated_at']=now();p['events']=[]
  # Existing historical IDs within this independent research copy are retained as provenance. All approval states are reset.
  for campaign in p['campaigns']:
   campaign['status']='AWAITING_REVIEW' if campaign['batches'] else 'DRAFT'
   for b in campaign['batches']:b['status']='AWAITING_REVIEW'
   for ref in campaign['evidence']:ref['association']='EXTERNAL_REFERENCE';ref['batch_id']=None
  service._event(p,'IMPORTED_DATA_NO_AUTHORITY',old);service._save(p)
  return service.read(p['id'])

def compare(service,a,b):
 validate_manifest(service,a);validate_manifest(service,b)
 def projection(v):return {'descriptors':v['descriptors'],'context':v['project']['context_sha256'],'campaigns':[c['config'] for c in v['project']['campaigns']],'evidence':v['evidence_identities']}
 left,right=projection(a),projection(b);diffs=[]
 def walk(x,y,path):
  if c.data_digest(x)==c.data_digest(y):return
  if type(x)!=type(y):diffs.append(path)
  elif isinstance(x,dict):
   for k in sorted(set(x)|set(y)):
    if k not in x or k not in y:diffs.append(path+'.'+k)
    else:walk(x[k],y[k],path+'.'+k)
  elif isinstance(x,list):
   if len(x)!=len(y):diffs.append(path+'.length')
   for i,(v,w) in enumerate(zip(x,y)):walk(v,w,path+'.'+str(i))
  elif x!=y:diffs.append(path)
 walk(left,right,'research')
 return {'status':'IDENTICAL_CONFIGURATION_AND_EVIDENCE' if not diffs else 'DIFFERENT_SOURCE_IDENTITY' if any('source_sha256' in d or d=='research.context' for d in diffs) else 'DIFFERENT_CONFIGURATION_OR_EVIDENCE','differences':diffs[:128],'meaning':'Configuration comparison is not fresh physical reproduction.'}
