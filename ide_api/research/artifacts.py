"""Bounded content-addressed artifacts. Byte integrity never implies physics authenticity."""
import base64,hashlib,json,os,re,stat,threading
from pathlib import Path
from uuid import uuid4
from datetime import datetime,timezone
from ide_api.rail_sweeps import canonical,exact
from .contracts import data_digest

BUNDLE='EMBODY_RESEARCH_EVIDENCE_BUNDLE_V1'
PACKAGE='EMBODY_RESEARCH_EVIDENCE_PACKAGE_V1'
RECEIPT='EMBODY_VERIFICATION_RECEIPT_V1'
PROVENANCE=('ORIGINAL_MEASURED_EVIDENCE','DERIVED_MEASUREMENT_SUMMARY','ANALYTICAL_PREDICTION','SYNTHETIC_ALGORITHM_FIXTURE','TEST_LOG','BROWSER_QA','SCREENSHOT','USER_AUTHORED_RESEARCH','HISTORICAL_REPORTED_RESULT','MISSING_REFERENCE','EXTERNAL_UNVERIFIED_DATA')
MAX_ARTIFACT=2*1024*1024;MAX_BUNDLE=12*1024*1024;MAX_PACKAGE=18*1024*1024;MAX_STORE=128*1024*1024
LIMITS={'retained_bundles':16,'artifacts_per_bundle':48,'artifact_bytes':MAX_ARTIFACT,'bundle_bytes':MAX_BUNDLE,'package_bytes':MAX_PACKAGE,'store_bytes':MAX_STORE,'receipts':64}
def now():return datetime.now(timezone.utc).isoformat()
def byte_hash(raw):return hashlib.sha256(raw).hexdigest()
def identifier(v,n=32):
 if not isinstance(v,str) or re.fullmatch('[a-f0-9]{'+str(n)+'}',v) is None:raise ValueError('Invalid artifact identity')
 return v

def relative(v):
 if not isinstance(v,str) or len(v)>180 or re.fullmatch('[a-zA-Z0-9_./-]+',v) is None or v.startswith('/') or any(p in ('','.','..') for p in v.split('/')):raise ValueError('Unsafe evidence relative path')
 return v

def finite_json(raw,limit=MAX_ARTIFACT):
 if not isinstance(raw,bytes) or len(raw)>limit:raise ValueError('Artifact size limit')
 def pairs(items):
  out={}
  for k,v in items:
   if k in out:raise ValueError('Duplicate JSON key')
   out[k]=v
  return out
 def bad(v):raise ValueError('Nonfinite JSON')
 try:
  value=json.loads(raw,object_pairs_hook=pairs,parse_constant=bad)
  json.dumps(value,allow_nan=False)
  return value
 except (json.JSONDecodeError,UnicodeDecodeError,RecursionError):raise ValueError('Invalid bounded JSON') from None

def validate_manifest(m):
 exact(m,['format','id','created_utc','metadata','artifacts','manifest_sha256'])
 if m['format']!=BUNDLE:raise ValueError('Unsupported evidence bundle version')
 identifier(m['id']);identifier(m['manifest_sha256'],64)
 exact(m['metadata'],['base_commit','source_identity','source_manifest','project_id','campaign_id','experiment_id','controller_ids','evidence_kind','evidence_id','limitations'])
 metadata=m['metadata']
 identifier(metadata['source_identity'],64);identifier(metadata['base_commit'],40)
 for field in ('project_id','campaign_id'):
  if metadata[field] is not None:identifier(metadata[field])
 if metadata['evidence_kind'] not in ('native','recorded') or not isinstance(metadata['source_manifest'],dict) or not 1<=len(metadata['source_manifest'])<=80:raise ValueError('Unsupported evidence/source metadata')
 for name,h in metadata['source_manifest'].items():relative(name);identifier(h,64)
 for field in ('experiment_id','evidence_id'):
  if not isinstance(metadata[field],str) or re.fullmatch('[a-zA-Z0-9_]{1,100}',metadata[field]) is None:raise ValueError('Invalid declared evidence identity')
 if not isinstance(metadata['controller_ids'],list) or not 1<=len(metadata['controller_ids'])<=9 or len(set(metadata['controller_ids']))!=len(metadata['controller_ids']):raise ValueError('Controller metadata limit')
 if any(not isinstance(v,str) or re.fullmatch('[a-zA-Z0-9_]{1,100}',v) is None for v in metadata['controller_ids']):raise ValueError('Invalid controller metadata')
 if not isinstance(metadata['limitations'],list) or len(metadata['limitations'])>12 or any(not isinstance(v,str) or len(v)>1200 for v in metadata['limitations']):raise ValueError('Limitations size')
 try:datetime.fromisoformat(m['created_utc'])
 except (ValueError,TypeError):raise ValueError('Creation timestamp required') from None
 if not isinstance(m['artifacts'],list) or not 1<=len(m['artifacts'])<=48:raise ValueError('Bounded nonempty artifacts required')
 names=set();size=0
 for v in m['artifacts']:
  exact(v,['name','sha256','bytes','provenance','media_type']);relative(v['name']);identifier(v['sha256'],64)
  if v['name'] in names or v['provenance'] not in PROVENANCE or type(v['bytes']) is not int or not 0<=v['bytes']<=MAX_ARTIFACT or v['media_type'] not in ('application/json','text/plain','image/png','application/zip'):raise ValueError('Invalid/duplicate artifact descriptor')
  names.add(v['name']);size+=v['bytes']
 if size>MAX_BUNDLE:raise ValueError('Bundle aggregate limit')
 body={k:v for k,v in m.items() if k not in ('id','manifest_sha256')}
 if data_digest(body)!=m['manifest_sha256'] or m['id']!=m['manifest_sha256'][:32]:raise ValueError('Evidence manifest identity mismatch')
 if len(canonical(m))>120000:raise ValueError('Manifest limit')
 return m

class ArtifactStore:
 def __init__(self,root):self.root=Path(root).absolute();self.lock=threading.RLock()
 def _root_check(self):
  if self.root.resolve()!=self.root:raise ValueError('Symlinked evidence root refused')
 def read(self,name,maximum=MAX_ARTIFACT):
  relative(name);self._root_check();fd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
  try:
   parts=name.split('/')
   for part in parts[:-1]:
    new=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);os.close(fd);fd=new
   filefd=os.open(parts[-1],os.O_RDONLY|os.O_NOFOLLOW,dir_fd=fd)
   with os.fdopen(filefd,'rb') as f:
    if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):raise ValueError('Regular evidence file required')
    raw=f.read(maximum+1)
    if len(raw)>maximum:raise ValueError('Evidence read bound')
    return raw
  finally:os.close(fd)
 def write_once(self,name,raw,maximum=MAX_ARTIFACT):
  relative(name);self._root_check()
  if not isinstance(raw,bytes) or len(raw)>maximum:raise ValueError('Evidence write bound')
  self.root.mkdir(parents=True,exist_ok=True)
  rootfd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW);parentfd=os.dup(rootfd);pending='pending_'+uuid4().hex
  try:
   parts=name.split('/')
   for part in parts[:-1]:
    try:os.mkdir(part,dir_fd=parentfd)
    except FileExistsError:pass
    new=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parentfd);os.close(parentfd);parentfd=new
   try:
    existing=os.open(parts[-1],os.O_RDONLY|os.O_NOFOLLOW,dir_fd=parentfd)
   except FileNotFoundError:existing=None
   if existing is not None:
    with os.fdopen(existing,'rb') as f:
     if not stat.S_ISREG(os.fstat(f.fileno()).st_mode) or f.read(maximum+1)!=raw:raise ValueError('Finalized artifact cannot be replaced')
    return
   fd=os.open(pending,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=rootfd)
   with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
   try:os.link(pending,parts[-1],src_dir_fd=rootfd,dst_dir_fd=parentfd,follow_symlinks=False)
   finally:os.unlink(pending,dir_fd=rootfd) # only this invocation's staging inode
  finally:os.close(parentfd);os.close(rootfd)
 def _usage(self):
  return sum(p.stat().st_size for p in self.root.rglob('*') if p.is_file() and not p.is_symlink()) if self.root.exists() else 0
 def finalize(self,metadata,artifacts,*,trusted=False):
  with self.lock:
   self._root_check();descriptors=[];objects={}
   for name,raw,kind,media in artifacts:
    relative(name);h=byte_hash(raw);objects[h]=raw;descriptors.append({'name':name,'sha256':h,'bytes':len(raw),'provenance':kind,'media_type':media})
   body={'format':BUNDLE,'created_utc':now(),'metadata':metadata,'artifacts':sorted(descriptors,key=lambda v:v['name'])};key=data_digest(body);m={**body,'id':key[:32],'manifest_sha256':key};validate_manifest(m)
   folders=[*self.root.glob('bundles/*.json'),*self.root.glob('external/*.json')]
   if len(folders)>=16:raise ValueError('Bundle retention quota; export/maintenance required, no deletion')
   if self._usage()+sum(len(v) for h,v in objects.items() if not (self.root/'objects'/h).exists())+len(canonical(m))>MAX_STORE:raise ValueError('Evidence store quota')
   for h,raw in objects.items():self.write_once('objects/'+h,raw)
   self.write_once('bundles/'+m['id']+'.json',canonical(m),120000)
   if trusted:self.write_once('attestations/'+m['id']+'.json',canonical({'bundle_sha256':key,'method':'Existing local verified reader capture; not an external import','captured_utc':now()}),2000)
   return m
 def manifest(self,key,external=False):return validate_manifest(finite_json(self.read(('external/' if external else 'bundles/')+identifier(key)+'.json',120000),120000))
 def verify(self,key,current_source=None,external=False):
  try:m=self.manifest(key,external)
  except FileNotFoundError:return {'id':key,'availability':'MISSING','errors':['Bundle manifest missing'],'verified_local':False}
  except (ValueError,OSError):return {'id':key,'availability':'INTEGRITY_FAILED','errors':['Invalid bundle manifest or unsafe filesystem reference'],'verified_local':False}
  errors=[]
  for d in m['artifacts']:
   try:
    raw=self.read('objects/'+d['sha256'])
    if len(raw)!=d['bytes'] or byte_hash(raw)!=d['sha256']:errors.append(d['name']+': hash/size mismatch')
   except FileNotFoundError:errors.append(d['name']+': missing')
   except (OSError,ValueError):errors.append(d['name']+': unsafe/unreadable')
  trusted=False
  if not external:
   try:trusted=finite_json(self.read('attestations/'+key+'.json',2000))['bundle_sha256']==m['manifest_sha256']
   except (OSError,ValueError,KeyError):pass
  state='PARTIALLY_AVAILABLE' if errors and all(': missing' in s for s in errors) else 'INTEGRITY_FAILED' if errors else 'EXTERNAL_UNVERIFIED' if not trusted else 'VERIFIED_AVAILABLE' if current_source and m['metadata']['source_identity']==current_source else 'VERIFIED_HISTORICAL'
  return {'id':key,'availability':state,'verified_local':trusted and not errors,'errors':errors,'manifest':m,'source_compatible':m['metadata']['source_identity']==current_source,'limitations':['Local filesystem attestation is not a remote signature or universal physics proof.','Ignored persistent storage is not a backup.']}
 def artifact(self,m,name):
  d=next((v for v in m['artifacts'] if v['name']==name),None)
  if not d:raise ValueError('Required evidence artifact missing from manifest')
  raw=self.read('objects/'+d['sha256'])
  if byte_hash(raw)!=d['sha256'] or len(raw)!=d['bytes']:raise ValueError('Artifact integrity mismatch')
  return raw
 def package(self,key):
  v=self.verify(key)
  if not v['verified_local']:raise ValueError('Export requires complete locally verified evidence; no substitute for missing raw data')
  m=v['manifest'];artifacts=[]
  for d in m['artifacts']:
   # Logs/receipts may contain exact local executable paths. Never silently redact original bytes.
   if d['provenance'] in ('TEST_LOG','BROWSER_QA'):raise ValueError('Raw operator logs require separate privacy review; not portable by default')
   raw=self.artifact(m,d['name'])
   if re.search(rb'/Users/|/home/|/private/(?:tmp|var)/|sk-(?:proj-)?[A-Za-z0-9_-]{15,}|-----BEGIN [A-Z ]*PRIVATE KEY',raw):raise ValueError('Private content in export; preserve original, do not silently rewrite')
   artifacts.append({'name':d['name'],'data_base64':base64.b64encode(raw).decode()})
  value={'format':PACKAGE,'manifest':m,'artifacts':artifacts};value['package_sha256']=data_digest(value)
  if len(canonical(value))>MAX_PACKAGE:raise ValueError('Portable package limit; select fewer cases')
  return value
 @staticmethod
 def verify_package(value):
  exact(value,['format','manifest','artifacts','package_sha256'])
  if value['format']!=PACKAGE or len(canonical(value))>MAX_PACKAGE or value['package_sha256']!=data_digest({k:v for k,v in value.items() if k!='package_sha256'}):raise ValueError('Invalid package identity/version/size')
  m=validate_manifest(value['manifest']);expected={d['name']:d for d in m['artifacts']};seen=set();decoded={}
  if not isinstance(value['artifacts'],list) or len(value['artifacts'])!=len(expected):raise ValueError('Incomplete package')
  for row in value['artifacts']:
   exact(row,['name','data_base64']);name=relative(row['name'])
   if name not in expected or name in seen or not isinstance(row['data_base64'],str) or len(row['data_base64'])>MAX_ARTIFACT*4//3+4:raise ValueError('Invalid/duplicate package artifact')
   try:raw=base64.b64decode(row['data_base64'],validate=True)
   except (ValueError,TypeError):raise ValueError('Invalid base64 artifact') from None
   d=expected[name]
   if len(raw)!=d['bytes'] or byte_hash(raw)!=d['sha256']:raise ValueError('Package artifact hash mismatch')
   seen.add(name);decoded[name]=raw
  from .bundles import package_readback
  readback=package_readback(m,decoded)
  return {'status':'INTEGRITY_VALID_EXTERNAL_UNVERIFIED','measured_authenticity':'NOT_ESTABLISHED_BY_PACKAGE_HASH','manifest':m,'decoded':decoded,'readback':readback}
 def import_package(self,value):
  checked=self.verify_package(value);m=checked['manifest']
  with self.lock:
   if len([*self.root.glob('bundles/*.json'),*self.root.glob('external/*.json')])>=16:raise ValueError('Bundle quota')
   if self._usage()+sum(len(v) for v in checked['decoded'].values())>MAX_STORE:raise ValueError('Store quota')
   for name,raw in checked['decoded'].items():self.write_once('objects/'+byte_hash(raw),raw)
   self.write_once('external/'+m['id']+'.json',canonical(m),120000)
  return {'id':m['id'],'availability':'EXTERNAL_UNVERIFIED','execution_authorized':False,'local_attestation_created':False}
 def receipt(self,value,log):
  exact(value,['format','id','command','started_utc','completed_utc','source_identity','base_commit','versions','exit_status','counts','stage','status','guard_counters','limits','limitations','log_sha256'])
  if value['format']!=RECEIPT or value['log_sha256']!=byte_hash(log) or type(value['exit_status']) is not int or value['status'] not in ('PASS','FAIL','TIMEOUT'):raise ValueError('Invalid completed verification receipt')
  identifier(value['id']);identifier(value['source_identity'],64);identifier(value['base_commit'],40);canonical(value)
  if not isinstance(value['command'],list) or not 1<=len(value['command'])<=40 or any(not isinstance(v,str) or len(v)>1000 for v in value['command']):raise ValueError('Exact bounded command required')
  exact(value['counts'],['pass','fail','skip','deselected','errors'])
  if any(v is not None and (type(v) is not int or v<0) for v in value['counts'].values()):raise ValueError('Actual counts or explicit unavailable required')
  if datetime.fromisoformat(value['completed_utc'])<datetime.fromisoformat(value['started_utc']):raise ValueError('Receipt completion precedes execution')
  if value['status']=='PASS' and (value['exit_status']!=0 or any(value['counts'][k] not in (0,None) for k in ('fail','errors'))):raise ValueError('Nonzero completed command is not PASS')
  if len(list(self.root.glob('receipts/*.json')))>=64:raise ValueError('Receipt retention quota')
  if self._usage()+len(log)+len(canonical(value))>MAX_STORE:raise ValueError('Receipt store quota')
  self.write_once('objects/'+value['log_sha256'],log);self.write_once('receipts/'+value['id']+'.json',canonical(value),32000);return value
 def begin_upload(self,size,sha256,purpose):
  identifier(sha256,64)
  if type(size) is not int or not 1<=size<=MAX_PACKAGE or purpose not in ('verify','import'):raise ValueError('Bounded package upload required')
  with self.lock:
   if len(list((self.root/'uploads').glob('*/request.json')))>=8:raise ValueError('Upload quota; explicit operator maintenance required')
   key=uuid4().hex;self.write_once('uploads/'+key+'/request.json',canonical({'bytes':size,'sha256':sha256,'purpose':purpose,'chunk_bytes':49152}),1024)
   return {'id':key,'chunk_bytes':49152,'parts':(size+49151)//49152}
 def upload_chunk(self,key,index,data):
  identifier(key);request=finite_json(self.read('uploads/'+key+'/request.json',1024))
  if (self.root/'uploads'/key/'completed.json').exists():raise ValueError('Upload finalized; no automatic restart')
  if type(index) is not int or not 0<=index<(request['bytes']+49151)//49152 or not isinstance(data,str) or len(data)>65536:raise ValueError('Invalid chunk')
  try:raw=base64.b64decode(data,validate=True)
  except (ValueError,TypeError):raise ValueError('Invalid chunk encoding') from None
  if len(raw)!=min(49152,request['bytes']-index*49152) or self._usage()+len(raw)>MAX_STORE:raise ValueError('Chunk/store bound')
  self.write_once('uploads/'+key+'/part_'+str(index),raw,49152);return {'id':key,'part':index,'bytes':len(raw)}
 def finish_upload(self,key):
  identifier(key)
  with self.lock:
   request=finite_json(self.read('uploads/'+key+'/request.json',1024))
   if (self.root/'uploads'/key/'completed.json').exists():return finite_json(self.read('uploads/'+key+'/completed.json',2000))
   raw=b''.join(self.read('uploads/'+key+'/part_'+str(i),49152) for i in range((request['bytes']+49151)//49152))
   if len(raw)!=request['bytes'] or byte_hash(raw)!=request['sha256']:raise ValueError('Upload byte identity differs')
   value=finite_json(raw,MAX_PACKAGE);checked=self.verify_package(value)
   result=self.import_package(value) if request['purpose']=='import' else {'id':checked['manifest']['id'],'status':checked['status'],'measured_authenticity':checked['measured_authenticity'],'artifacts_checked':len(checked['decoded']),'readback':checked['readback']}
   self.write_once('uploads/'+key+'/completed.json',canonical(result),2000);return result
