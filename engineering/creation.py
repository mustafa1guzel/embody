"""Human-approved atomic creation, reusing the authoritative EngineeringService."""
from pathlib import Path
from contextlib import contextmanager
from uuid import uuid4
import copy,os,json,re,fcntl,threading
from .store import Store
from .project import identity
from .requirements import interpret
from .synthesis import empty_project,recipe,build_copy,design_plan
from physics.contracts import digest,canonical
from core.simulation import ROOT

def implementation_identity():
    from robustness.contracts import file_hash
    files=[*sorted((ROOT/'engineering').glob('*.py')),*sorted((ROOT/'shapebase').glob('*.py')),ROOT/'world/compiler.py',ROOT/'world/schema.py',ROOT/'devices/controller.py',ROOT/'hardware/library.py']
    return {str(p.relative_to(ROOT)):file_hash(p) for p in files}

class CreationManager:
    def __init__(self,root=None):
        self.root=Path(root) if root else ROOT/'artifacts/day16_device_creation/workspaces'
        Store(self.root);Store(self.root/'projects');self.proposals=Store(self.root/'proposals');self.manifests=Store(self.root/'manifests');self.lock=threading.RLock()
    @contextmanager
    def transaction(self):
        with self.lock:
            fd=os.open(self.root/'registry.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
            try:fcntl.flock(fd,fcntl.LOCK_EX);yield
            finally:fcntl.flock(fd,fcntl.LOCK_UN);os.close(fd)
    def project(self,project_id):
        from ide_api.engineering import EngineeringService
        if not isinstance(project_id,str) or not re.fullmatch(r'p_[0-9a-f]{32}',project_id):raise ValueError('Invalid creation project identity')
        path=self.root/'projects'/project_id
        if not path.is_dir() or path.is_symlink() or not (path/'head.json').is_file():raise ValueError('Unknown or incomplete project')
        return EngineeringService(path)
    def _activate(self,project_id,*,checked=False):
        if not checked:self.project(project_id)
        target=self.root/'active.json'
        if target.is_symlink():raise ValueError('Symlink active pointer rejected')
        temp=self.root/('active_'+uuid4().hex+'.tmp');fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'w') as f:json.dump({'project_id':project_id},f);f.flush();os.fsync(f.fileno())
        os.replace(temp,target)
    def active(self):
        path=self.root/'active.json'
        if not path.exists():return None
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
        with os.fdopen(fd) as f:
            raw=f.read(257)
        if len(raw)>256:raise ValueError('Active project pointer exceeds bound')
        p=json.loads(raw)
        if set(p)!={'project_id'}:raise ValueError('Invalid active project pointer')
        return None if p['project_id']=='engineering_project' else self.project(p['project_id'])
    def open(self,project_id,confirmation):
        if confirmation!='OPEN SUPPORTED PROJECT':raise ValueError('Explicit project selection required')
        with self.transaction():self._activate(project_id)
        return self.project(project_id).bootstrap()
    def capabilities(self):
        return {'families':{'sensor_barrier':'Full bounded generated-world sensor/control/native simulation','smart_glasses':'Primitive physical concept only; active electronics/optics/battery/RF/thermal unavailable'},'matching':'Explicit deterministic family matching and typed SI parameters; not unrestricted natural-language AI','max_projects':32,'max_batches':16,'max_operations_per_batch':16,'max_world_objects':48,'model_or_vm_authority':False,'controller':'Existing trusted versioned ReferenceLogic only; no generated source execution','new_api_requests':0}
    def list_projects(self):
        values=[]
        for path in sorted((self.root/'projects').iterdir()):
            if path.is_dir() and not path.is_symlink():
                p=self.project(path.name).current();values.append({'id':p['id'],'family':p['creation']['family'],'state':p['creation']['state'],'revision':p['revision'],'sha256':identity(p)})
        return values
    def start(self,request,parameters=None):
        from ide_api.engineering import EngineeringService
        requirements=interpret(request,parameters)
        if requirements['blocked']:raise ValueError('; '.join(requirements['blocked']))
        with self.transaction():
            if len(list((self.root/'projects').iterdir()))>=32:raise ValueError('Project count limit')
            initial=empty_project(requirements['family'],requirements['request_sha256']);service=EngineeringService(self.root/'projects'/initial['id'],initial_project=initial);initial=service.current()
            manifest={'schema_version':1,'project_id':initial['id'],'initial_project_sha256':identity(initial),'initial_world_objects':0,'initial_circuit_components':0,'request':request,'requirements':requirements,'origin':'EMPTY_PROJECT_CONSTRUCTION; no finished project clone'};manifest_id=self.manifests.put(manifest)
            try:
                batches,meta=recipe(requirements,initial);candidate,validation=build_copy(initial,batches,meta);plan=design_plan(requirements,initial,batches);plan_id=service.plans.put(plan)
                candidate['design_plans']=[{'id':plan['id'],'revision':plan['revision'],'sha256':plan_id}]
                from .project import validate
                candidate=validate(candidate)
                proposal={'schema_version':1,'status':'PROPOSED_NOT_APPLIED','project_id':initial['id'],'base_sha256':identity(initial),'base_revision':0,'manifest_id':manifest_id,'requirements':requirements,'plan_id':plan_id,'plan':plan,'batches':batches,'metadata':meta,'validation':validation,'proposed_project':candidate,'resulting_sha256':identity(candidate),'implementation_sha256':implementation_identity(),'human_approval_required':True,'model_application_authority':False}
                key=self.proposals.put(proposal);service.events.put({'kind':'CREATION_PROPOSED_NOT_APPLIED','proposal_id':key,'base':identity(initial),'result':identity(candidate)})
                return {**proposal,'proposal_id':key,'initial_project':initial,'stages':['REQUIREMENTS_PARSED','CAPABILITIES_RESOLVED','TYPED_BATCHES_CONSTRUCTED_IN_COPY','INDEPENDENT_STATIC_AND_NATIVE_COMPILATION_VALIDATION','AWAITING_EXPLICIT_HUMAN_BUILD']}
            except Exception as exc:
                service.events.put({'kind':'CREATION_PLANNING_FAILED','exception':type(exc).__name__,'project_state':'EMPTY_NOT_BUILT'});raise
    def validate_proposal(self,key,expected_sha256,expected_revision,*,service=None):
        proposal=self.proposals.get(key)
        if service is None:
            service=self.project(proposal['project_id'])
            with service.transaction():return self.validate_proposal(key,expected_sha256,expected_revision,service=service)
        initial=service._precondition(expected_sha256,expected_revision)
        if proposal['base_sha256']!=expected_sha256 or proposal['base_revision']!=expected_revision or proposal['implementation_sha256']!=implementation_identity():raise ValueError('Stale creation proposal or implementation')
        batches,meta=recipe(proposal['requirements'],initial)
        if batches!=proposal['batches'] or meta!=proposal['metadata']:raise ValueError('Creation recipe mismatch')
        candidate,checks=build_copy(initial,batches,meta);candidate['design_plans']=copy.deepcopy(proposal['proposed_project']['design_plans'])
        if candidate!=proposal['proposed_project'] or identity(candidate)!=proposal['resulting_sha256']:raise ValueError('Independent creation replay mismatch')
        return proposal,service,candidate
    def decide(self,key,expected_sha256,expected_revision,decision,confirmation):
        if decision not in ('build','reject') or confirmation!=('BUILD REVIEWED SUPPORTED PROJECT' if decision=='build' else 'REJECT DEVICE CREATION'):raise ValueError('Exact explicit creation confirmation required')
        proposal=self.proposals.get(key);service=self.project(proposal['project_id'])
        with self.transaction(),service.transaction():
            proposal,service,candidate=self.validate_proposal(key,expected_sha256,expected_revision,service=service)
            terminal=service.root/('creation_decision_'+key);event={'decision':'APPROVED_FOR_ATOMIC_BUILD' if decision=='build' else 'REJECTED','proposal_id':key,'base':expected_sha256,'result':identity(candidate)}
            fd=os.open(terminal,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            with os.fdopen(fd,'w') as f:f.write(canonical(event))
            authorization=service.events.put(event)
            if decision=='reject':return {'status':'REJECTED_NOT_BUILT','project':service._current()}
            try:built=service._commit(candidate,authorization=authorization)
            except Exception:
                service.events.put({'kind':'CREATION_COMMIT_INTERRUPTED','proposal_id':key,'meaning':'Inspect actual atomic head; approval is not a completion claim.'});raise ValueError('Atomic build interrupted; inspect project '+proposal['project_id']+'; no completion claimed') from None
            try:self._activate(built['id'],checked=True)
            except Exception:raise ValueError('Build committed but selection failed; explicitly open project '+built['id']) from None
            return {'status':'BUILT_NOT_YET_SIMULATED','project':built,'project_sha256':identity(built),'authorization_event_sha256':authorization,'simulation':'NOT_RUN'}
