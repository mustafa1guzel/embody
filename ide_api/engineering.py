"""Trusted local project transactions. Model tool facade has no commit capability."""
import copy,json,os,threading,fcntl
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4
from engineering.project import validate,identity,identities,new_project,device_contract
from engineering.actions import execute_copy,CLASSIFICATIONS,OPERATIONS
from engineering.store import Store
from engineering.changes import validate_changeset
from engineering.plans import create_plan,review_plan,compile_plan,validate_plan
from engineering.diagnosis import diagnose
from hardware.advanced import advanced_inspect,schematic,functional_interfaces
from hardware.library import catalog
from hardware.assemblies import identity as circuit_identity
from world.objects import LIBRARY
from world.compiler import compile_world
from world.schema import identity as world_identity
from world.simulation import run as run_world
from devices.contracts import DeviceSpec
from devices.simulation import run as run_device
from physics.contracts import digest,canonical
from shapebase.geometry import library as shape_library
from core.simulation import ROOT

class EngineeringService:
    def __init__(self,root=None,*,initial_project=None):
        self.root=Path(root) if root else ROOT/'artifacts/day13_15/workspaces'
        Store(self.root);self.projects=Store(self.root/'projects');self.proposals=Store(self.root/'proposals');self.plans=Store(self.root/'plans');self.events=Store(self.root/'events');self.measured=Store(self.root/'measured');self.commits=Store(self.root/'commits');self.lock=threading.RLock()
        with self.transaction():
            if not (self.root/'head.json').exists():self._commit(initial_project if initial_project is not None else new_project())
            elif initial_project is not None:raise ValueError('Cannot overwrite an existing project with an initial state')
    @contextmanager
    def transaction(self):
        with self.lock:
            fd=os.open(self.root/'project.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
            try:
                fcntl.flock(fd,fcntl.LOCK_EX);yield
            finally:fcntl.flock(fd,fcntl.LOCK_UN);os.close(fd)
    def _current(self):
        fd=os.open(self.root/'head.json',os.O_RDONLY|os.O_NOFOLLOW)
        with os.fdopen(fd,'r') as f:v=json.load(f)
        if 'commit_sha256' in v and self.commits.get(v['commit_sha256'])['result_sha256']!=v['sha256']:raise ValueError('Atomic project head/commit mismatch')
        return validate(self.projects.get(v['sha256']))
    def _commit(self,p,authorization=None):
        p=validate(p);key=self.projects.put(p);head=self.root/'head.json'
        if head.is_symlink():raise ValueError('Symlink head rejected')
        previous={}
        if head.exists():
            fd=os.open(head,os.O_RDONLY|os.O_NOFOLLOW)
            with os.fdopen(fd,'r') as f:previous=json.load(f)
        commit_key=self.commits.put({'schema_version':1,'base_sha256':previous.get('sha256'),'parent_commit_sha256':previous.get('commit_sha256'),'result_sha256':key,'authorization_event_sha256':authorization,'meaning':'Applied only when reachable from atomic head; orphan records are uncommitted.'})
        temp=self.root/('head_'+uuid4().hex+'.tmp');fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'w') as f:json.dump({'sha256':key,'commit_sha256':commit_key},f);f.flush();os.fsync(f.fileno())
        os.replace(temp,head);return p
    def current(self):
        with self.transaction():return self._current()
    def _precondition(self,sha,revision):
        p=self._current()
        if type(revision) is not int or revision!=p['revision'] or sha!=identity(p):raise ValueError('Stale project hash/revision; inspect current state')
        return p
    def preview(self,p,operations):
        candidate=validate(execute_copy(p,operations));_,_,compiled=compile_world(candidate['world']);electrical=advanced_inspect(candidate['circuit'])
        result={'world':'VALID_COMPILED','world_contract_sha256':compiled['contract_sha256'],'electrical':electrical,'interfaces':'VALID_TYPED_MAPPINGS','simulation':'NOT_RUN; no dynamic expected outcome inferred'}
        if 'shape_specs' in candidate:
            from shapebase.geometry import library
            result['shapes']=library(candidate)
        return candidate,result
    def bootstrap(self):
        p=self.current();return {'project':p,'identities':identities(p),'primitives':list(LIBRARY),'catalog':catalog(),'functional_interfaces':functional_interfaces(),'action_contracts':CLASSIFICATIONS,'operation_schema':OPERATIONS,'shapebase':shape_library(p),'schematic':schematic(p['circuit']),'electrical':advanced_inspect(p['circuit']),'live_model':'PENDING_APPROVAL; new live experiment not authorized','plan_author':'DETERMINISTIC_DEVELOPER_AUTHORED; not live AI','day16':'BOUNDED_CREATION_ENGINE; not unrestricted synthesis'}
    def edit(self,sha,revision,operations):
        from engineering.actions import check_operations
        check_operations(operations)
        if any(CLASSIFICATIONS[o['kind']]['subsystem']=='shapes' for o in operations):raise ValueError('SHAPEBASE changes require a review proposal and explicit decision')
        with self.transaction():
            p=self._precondition(sha,revision);candidate,checks=self.preview(p,operations);self.events.put({'kind':'EXPLICIT_LOCAL_USER_EDIT','base':sha,'operations':operations,'result':identity(candidate),'checks':checks});return self._commit(candidate)
    def replace_circuit(self,sha,revision,assembly):
        from hardware.assemblies import validate as validate_circuit
        with self.transaction():
            p=self._precondition(sha,revision);p['circuit']=validate_circuit(assembly);p['revision']+=1
            if p.get('creation',{}).get('state')=='BUILT':
                from engineering.device_bindings import synchronize
                synchronize(p,circuit_source=True)
            validate(p)
            self.events.put({'kind':'EXPLICIT_HARDWARE_STUDIO_EDIT','base':sha,'result':identity(p)});return self._commit(p)
    def propose(self,sha,revision,operations,explanation,origin='MODEL_TOOL_UNTRUSTED_PROPOSAL'):
        if not isinstance(explanation,str) or not 1<=len(explanation)<=2000:raise ValueError('Bounded proposal explanation required')
        with self.transaction():
            p=self._precondition(sha,revision);candidate,checks=self.preview(p,operations)
            value={'schema_version':1,'base_project_sha256':sha,'base_revision':revision,'operations':copy.deepcopy(operations),'dependency_order':list(range(len(operations))),'affected_subsystems':sorted(set(CLASSIFICATIONS[o['kind']]['subsystem'] for o in operations)),'preconditions':['Exact current project hash/revision; valid targets; all dependent operations in order.'],'validation':checks,'expected_outcomes':['Typed data and native compiled values match proposed changes.'],'unknown_consequences':['Dynamics NOT_RUN; electrical UNKNOWNs remain; no full system safety proof.'],'approval_status':'PROPOSED_NOT_APPLIED' if checks['electrical']['errors']==0 else 'INVALID_REVIEW_ONLY','proposed_project':candidate,'resulting_project_sha256':identity(candidate),'resulting_revision':candidate['revision'],'explanation':explanation,'origin':origin,'model_application_authority':False,'installation_effect':'NONE'}
            validate_changeset(value);return {**value,'proposal_id':self.proposals.put(value)}
    def decide(self,sha,revision,proposal_id,decision,confirmation):
        with self.transaction():
            p=self._precondition(sha,revision);proposal=validate_changeset(self.proposals.get(proposal_id))
            if proposal['base_project_sha256']!=sha or proposal['base_revision']!=revision:raise ValueError('Stale proposal')
            terminal=self.root/'decisions'/proposal_id
            Store(terminal.parent)
            if terminal.exists() or terminal.is_symlink():raise ValueError('Proposal already decided')
            if decision=='reject':
                if confirmation!='REJECT ENGINEERING CHANGE':raise ValueError('Explicit rejection required')
                event={'decision':'REJECTED','proposal_id':proposal_id,'project_sha256':sha}
            elif decision=='apply':
                if confirmation!='APPLY REVIEWED ENGINEERING CHANGE':raise ValueError('Explicit local application approval required')
                candidate,checks=self.preview(p,proposal['operations'])
                if checks.get('shapes')!=proposal['validation'].get('shapes'):raise ValueError('Shape geometry/source identity changed; prepare a fresh review')
                if proposal['approval_status']!='PROPOSED_NOT_APPLIED' or checks['electrical']['errors'] or digest(candidate)!=proposal['resulting_project_sha256'] or digest(candidate)!=digest(proposal['proposed_project']):raise ValueError('Invalid or tampered changeset; no commit')
                event={'decision':'APPROVED_FOR_DATA_COMMIT','proposal_id':proposal_id,'base':sha,'result':identity(candidate)}
            else:raise ValueError('Unknown review decision')
            # Reserve the immutable decision before committing; failure never creates
            # a partially edited project, and a decision is never silently retried.
            fd=os.open(terminal,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            with os.fdopen(fd,'w') as f:f.write(canonical(event))
            authorization=self.events.put(event)
            if decision=='apply':
                p=self._commit(candidate,authorization=authorization)
                event={**event,'decision':'APPROVED_AND_APPLIED_DATA_ONLY','authorization_event_sha256':authorization}
            return {'project':p,'decision':event}
    def restore(self,sha,revision,key):
        with self.transaction():
            current=self._precondition(sha,revision);p=validate(self.projects.get(key));p['revision']=current['revision']+1;p['world']['revision']=current['world']['revision']+1;p['circuit']['revision']=current['circuit']['revision']+1
            self.events.put({'kind':'EXPLICIT_USER_SAFE_REVISION_RESTORE','base':sha,'saved_revision':key,'result':identity(p)});return self._commit(p)
    def save(self,sha,revision):
        with self.transaction():p=self._precondition(sha,revision);return {'key':self.projects.put(p),'identities':identities(p)}
    def load_evidence(self,key):
        p=self.current();reference=next((r for r in p['evidence_refs'] if r['sha256']==key),None)
        if reference is None:raise PermissionError('Evidence must be referenced by the current project')
        result=self.measured.get(key)
        if result.get('base_project_sha256')!=reference['base_project_sha256']:raise ValueError('Evidence input identity mismatch')
        return {'result':result,'evidence':reference,'origin':'RECORDED_PROJECT_RUN; no new simulation','current_project_sha256':identity(p)}
    def preview_shapes(self,sha,revision,proposal_id):
        """Explicit trusted native proxy run; no head/evidence-reference commit."""
        from shapebase.preview import run_preview
        return run_preview(self,sha,revision,proposal_id)
    def physics_preflight(self):
        from engineering.barrier_repair import preflight_project
        return preflight_project(self.current())
    def propose_physics_repair(self,sha,revision,*,max_native_previews=8,max_candidates=100,render_image=True):
        """Explicit local bounded search; keep the authoritative head unchanged."""
        from engineering.barrier_repair import propose_repair
        with self.transaction():p=self._precondition(sha,revision)
        result=propose_repair(p,self.root/'physics_repairs'/('repair_'+uuid4().hex),max_native_previews=max_native_previews,max_candidates=max_candidates,source_evidence=p['evidence_refs'][-1] if p['evidence_refs'] else None,render_image=render_image)
        with self.transaction():
            self._precondition(sha,revision)
            if result['engineering_changeset'] is not None:result['proposal_id']=self.proposals.put(result['engineering_changeset'])
        return result
    def _save_plan_ref(self,project,plan):
        key=self.plans.put(plan);project['design_plans']=[r for r in project['design_plans'] if r['id']!=plan['id']]+[{'id':plan['id'],'revision':plan['revision'],'sha256':key}];project['revision']+=1;self._commit(project);return {'plan':plan,'plan_id':key}
    def plan(self,goal):
        with self.transaction():
            project=self._current();p=create_plan(goal,project)
            previous=next((r for r in project['design_plans'] if r['id']==p['id']),None)
            if previous:p['revision']=previous['revision']+1
            return self._save_plan_ref(project,p)
    def review_plan(self,key):
        with self.transaction():
            project=self._current()
            if not any(r['sha256']==key for r in project['design_plans']):raise ValueError('Only current project plan revisions can be reviewed')
            p=review_plan(self.plans.get(key));return self._save_plan_ref(project,p)
    def compile_plan(self,key):
        p=self.plans.get(key);return compile_plan(p,self.current())
    def simulate(self,sha,revision,kind):
        with self.transaction():p=self._precondition(sha,revision)
        folder=self.root/'runs'/('run_'+uuid4().hex)
        if kind=='world':result=run_world(p['world'],folder)
        elif kind=='device':
            if 'creation' in p:
                from engineering.created_simulation import run as run_created
                result=run_created(p,folder)
            else:result=run_device(p['circuit'],DeviceSpec.from_dict(p['device_spec']),folder,render=True)
        else:raise ValueError('Unsupported trusted simulation kind')
        result['base_project_sha256']=sha;key=self.measured.put(result);e={'id':'run_'+uuid4().hex,'kind':kind,'sha256':key,'base_project_sha256':sha}
        self.events.put({'kind':'TRUSTED_SIMULATION','evidence':e,'artifact_path':str(folder)})
        with self.transaction():
            current=self._current()
            if identity(current)==sha:
                current['evidence_refs']=[*current['evidence_refs'][-31:],e];current['revision']+=1;self._commit(current)
        return {'project':self.current(),'result':result,'evidence':e,'evidence_path':str(folder.relative_to(ROOT)) if ROOT in folder.parents else str(folder)}
    def inspect_context(self):
        p=self.current();electrical=advanced_inspect(p['circuit']);last=next((e for e in reversed(p['evidence_refs']) if e['kind']=='device'),None);measurement=self.measured.get(last['sha256']) if last else None
        if measurement and (measurement['device_spec_sha256']!=device_contract(p).identity or measurement['assembly_sha256']!=circuit_identity(p['circuit']) or measurement.get('generated_world_binding') and measurement['world']!=p['world']):measurement=None
        return {'identities':identities(p),'world_objects':p['world']['objects'][:8],'device_spec':p['device_spec'],'electrical':{'errors':electrical['errors'],'unknowns':electrical['unknowns'],'diagnostics':electrical['diagnostics'][:12]},'interfaces':p['interfaces'],'design_plans':p['design_plans'],'controller':{'sha256':p['controller_sha256'],'origin':'NONE_GEOMETRY_ONLY' if p.get('creation',{}).get('family')=='smart_glasses' else 'TRUSTED_REFERENCE','behavior':'No active controller for concept envelopes.' if p.get('creation',{}).get('family')=='smart_glasses' else 'Sampled ray -> debounce -> opening/hold/closing; bounded PD torque. No source sent.'},'diagnosis':diagnose(p,measurement),'evidence_reference':last if measurement else None,'permissions':'Inspection and review-only proposals; no execution/apply/model spending authority.',**({'shape_specs':p['shape_specs'],'shapebase':shape_library(p)} if 'shape_specs' in p else {})}
