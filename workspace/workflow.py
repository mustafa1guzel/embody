"""Explicit local review/VM verification and recoverable controller-only install.

The managed controller is NEVER imported by the host. The original trusted
baseline is never replaced. UI actions and verification are distinct approvals.
"""
from contextlib import contextmanager
from datetime import datetime,timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
from uuid import uuid4

from core.agent.patching import CandidateStore, READ_ALLOWLIST, TARGET, read_project_file
from core.agent.trace import ExecutionTrace
from core.agent.verification import CandidateVerifier
from core.agent.vm_backend import AppleVMBackend
from core.day3 import load_scenarios
from core.simulation import ROOT, sha256
from workspace.data import EvidenceError, bounded_read, decode_json

MANAGED_TARGET='robot/approved_controller.py'
DEFAULT_SESSIONS=ROOT/'artifacts/day6/workflows'


class WorkflowBlocked(ValueError):
    pass


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def atomic_json(path,value):
    temporary=path.parent/('.state-'+uuid4().hex)
    raw=json.dumps(value,indent=2,allow_nan=False).encode()+b'\n'
    with temporary.open('xb') as stream:
        os.chmod(temporary,0o600);stream.write(raw);stream.flush();os.fsync(stream.fileno())
    os.replace(temporary,path)
    directory=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(directory)
    finally:os.close(directory)


def durable_backup(path,raw):
    with path.open('xb') as stream:
        os.chmod(path,0o600);stream.write(raw);stream.flush();os.fsync(stream.fileno())


class Workflow:
    def __init__(self,root=ROOT,sessions=DEFAULT_SESSIONS,*,family='rail',evaluation=True):
        from core.robots.registry import get_family
        self.root,self.sessions=Path(root),Path(sessions)
        self.family_id=family;self.evaluation=evaluation
        self.family=get_family(family,root=self.root,evaluation=evaluation)
        self.target=self.family.target if self.family else TARGET
        self.read_allowlist=self.family.read_allowlist if self.family else READ_ALLOWLIST
        self.managed_target=self.family.managed_target if self.family else MANAGED_TARGET
        self.managed_name=self.family.managed_name if self.family else 'approved_controller.py'
        self.scenarios=self.family.scenarios if self.family else load_scenarios()

    def _folder(self,review_id):
        if not isinstance(review_id,str) or len(review_id)!=32 or any(c not in '0123456789abcdef' for c in review_id):
            raise WorkflowBlocked('Invalid review identifier')
        folder=self.sessions/review_id
        if folder.is_symlink() or not folder.is_dir():
            raise WorkflowBlocked('Review is missing or is a symlink')
        return folder

    @contextmanager
    def _lock(self,review_id):
        folder=self._folder(review_id)
        fd=os.open(folder/'action.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
        try:
            try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError as exc:raise WorkflowBlocked('Another action owns this review') from exc
            yield folder
        finally:os.close(fd)

    def _save(self,folder,state,event):
        state['updated_utc']=datetime.now(timezone.utc).isoformat()
        state['events'].append({'event':event,'status':state['status'],'timestamp_utc':state['updated_utc']})
        atomic_json(folder/'state.json',state)

    def get(self,review_id):
        folder=self._folder(review_id)
        state=decode_json(bounded_read(folder,'state.json'))
        if state['review_id']!=review_id or digest(bounded_read(folder,'proposed_source.txt'))!=state['source_sha256']:
            raise WorkflowBlocked('Review identity or source integrity mismatch')
        if state.get('robot_family','rail')!=self.family_id or state['apply_target']!=self.managed_target:
            raise WorkflowBlocked('Review family or managed target mismatch')
        return state

    def _fingerprint(self):
        paths=set(self.read_allowlist)
        if self.family:
            paths.add('configs/arm_evaluation.json')
            paths.update(str(p.relative_to(self.root)) for p in (self.root/'physics').glob('*.py'))
        for name in ('workspace/workflow.py','workspace/data.py'):
            if (self.root/name).is_file():paths.add(name)
        paths.update(str(p.relative_to(self.root)) for p in (self.root/'core').rglob('*.py'))
        return {p:sha256(self.root/p) for p in sorted(paths)}

    @contextmanager
    def _managed(self):
        root_fd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:directory=os.open('robot',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=root_fd)
        finally:os.close(root_fd)
        lock=None
        try:
            # Cooperative project-wide install/rollback serialization.
            lock=os.open('.approved-controller.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600,dir_fd=directory)
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError as exc:raise WorkflowBlocked('Another controller transaction is active') from exc
            yield directory
        finally:
            if lock is not None:os.close(lock)
            os.close(directory)

    def _current(self,directory):
        name=self.managed_name
        try:info=os.stat(name,dir_fd=directory,follow_symlinks=False)
        except FileNotFoundError:return None
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1:
            raise WorkflowBlocked('Managed controller must be a regular file, not a link')
        fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory)
        with os.fdopen(fd,'rb') as stream:
            raw=stream.read(100001)
        if len(raw)>100000:raise WorkflowBlocked('Managed source exceeds policy size')
        return raw

    def _replace(self,directory,raw):
        name='.approved-'+uuid4().hex
        fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=directory)
        try:
            with os.fdopen(fd,'wb') as stream:
                stream.write(raw);stream.flush();os.fsync(stream.fileno())
            os.replace(name,self.managed_name,src_dir_fd=directory,dst_dir_fd=directory)
            os.fsync(directory)
        finally:
            try:os.unlink(name,dir_fd=directory)
            except FileNotFoundError:pass

    def create(self,*,source,explanation,expected_original_sha256,provenance):
        self.sessions.mkdir(parents=True,exist_ok=True)
        review_id=uuid4().hex;folder=self.sessions/review_id;folder.mkdir(mode=0o700)
        original=read_project_file(self.root,self.target,{self.target})
        store=CandidateStore(self.root,folder/'candidates',target=self.target)
        validation=store.propose(target_path=self.target,expected_original_sha256=expected_original_sha256,
                                 proposed_source=source,explanation=explanation)
        durable_backup(folder/'proposed_source.txt',source.encode())
        durable_backup(folder/'original_source.txt',original['content'].encode())
        with self._managed() as directory:
            prior=self._current(directory)
        state={'review_id':review_id,'status':'REVIEWED' if validation['validation_status']=='VALID' else 'INVALID',
            'source_sha256':digest(source.encode()),'original_sha256':original['sha256'],
            'original_backup_sha256':digest(original['content'].encode()),'validation':validation,
            'explanation':explanation,'provenance':provenance,'verification':None,'verification_inventory':{},
            'fingerprint':self._fingerprint(),'managed_before_sha256':digest(prior) if prior is not None else None,
            'apply_target':self.managed_target,'robot_family':self.family_id,
            'verification_scope':'full' if self.evaluation else 'development',
            'permanent_application_approved':False,'events':[]}
        self._save(folder,state,'candidate_reviewed')
        return review_id

    def _unchanged(self,folder,state):
        if read_project_file(self.root,self.target,{self.target})['sha256']!=state['original_sha256']:
            raise WorkflowBlocked('Original source hash changed; create a fresh review')
        if self._fingerprint()!=state['fingerprint']:
            raise WorkflowBlocked('Project/context changed; previous verification is stale')
        if digest(bounded_read(folder,'original_source.txt'))!=state['original_backup_sha256']:
            raise WorkflowBlocked('Original backup integrity mismatch')

    def reject(self,review_id):
        with self._lock(review_id) as folder:
            state=self.get(review_id)
            if state['status'] in ('APPLIED','APPLYING','REVERTING'):
                raise WorkflowBlocked('Use explicit rollback for an applied transaction')
            state['status']='REJECTED';self._save(folder,state,'candidate_rejected')

    def verify(self,review_id,*,approved=False,backend=None):
        if approved is not True:raise WorkflowBlocked('Explicit verification approval is required')
        with self._lock(review_id) as folder:
            state=self.get(review_id)
            if state['status'] not in ('REVIEWED','BLOCKED'):
                raise WorkflowBlocked('Create a fresh review for this candidate state')
            state['verification']=None;state['verification_inventory']={}
            try:
                self._unchanged(folder,state)
                backend=backend if backend is not None else AppleVMBackend()
                if type(backend) is not AppleVMBackend:
                    raise WorkflowBlocked('Only the qualified AppleVMBackend may execute candidates')
                proof=backend.preflight()
                if self.family:
                    from core.robots.qualification import require_qualification
                    require_qualification(backend,self.family)
                if any(proof['identity']['files'].get(path)!=value for path,value in state['fingerprint'].items()):
                    raise WorkflowBlocked('Reviewed project differs from the qualified simulation sources')
                state['status']='VERIFYING';self._save(folder,state,'isolated_verification_approved')
                attempt=folder/('execution_'+uuid4().hex);attempt.mkdir()
                atomic_json(attempt/'qualification.json',proof)
                store=CandidateStore(self.root,folder/'candidates',target=self.target)
                v=state['validation'];candidate=v['candidate_id']
                source_path=folder/'candidates'/candidate.removeprefix('candidate_')/'controller.py'
                store.records[candidate]={**v,'source_path':source_path}
                trace=ExecutionTrace(attempt/'trace.jsonl',model_mode='user_approved_vm_verification_no_model')
                verifier=CandidateVerifier(store,self.scenarios,attempt/'verifications',trace,backend=backend,family=self.family)
                result=verifier.verify(candidate)
                self._unchanged(folder,state)
                state['verification']=result
                state['execution_directory']=str(attempt.relative_to(folder))
                state['qualification_identity']=proof['identity']
                state['verification_inventory']={str(p.relative_to(folder)):sha256(p) for p in attempt.rglob('*') if p.is_file()}
                state['status']=('VERIFIED' if result['verification_execution']=='PASS' and result['physical_safety_status']=='PASS'
                                 else 'BLOCKED' if result['verification_execution']=='BLOCKED' else 'FAILED')
                state['reason']=result.get('reason','')
                self._save(folder,state,'isolated_verification_finished')
            except (ValueError,OSError,RuntimeError) as exc:
                state['status']='BLOCKED';state['reason']=str(exc)
                self._save(folder,state,'isolated_verification_blocked')
            return state

    def checked_verification(self,review_id):
        folder=self._folder(review_id);state=self.get(review_id)
        self._unchanged(folder,state)
        for relative,expected in state['verification_inventory'].items():
            if digest(bounded_read(folder,relative))!=expected:
                raise WorkflowBlocked('Verification artifact integrity mismatch')
        if not state['verification_inventory'] or not state['verification']:
            raise WorkflowBlocked('No fresh verification measurements exist')
        result=state['verification']
        # Also bind the persisted result to its authoritative file, not just mutable UI state.
        result_path=state['execution_directory']+'/verifications/'+state['validation']['candidate_id']+'.json'
        if decode_json(bounded_read(folder,result_path))!=result:
            raise WorkflowBlocked('Verification result differs from its evidence')
        return state

    def apply(self,review_id,*,confirmation):
        if self.family and not self.evaluation:
            raise WorkflowBlocked('Development-only verification cannot authorize permanent installation')
        with self._lock(review_id) as folder:
            state=self.checked_verification(review_id)
            if confirmation!='APPLY '+state['source_sha256']:
                raise WorkflowBlocked('Separate explicit permanent application confirmation is required')
            if state['status']!='VERIFIED':raise WorkflowBlocked('Only a fresh physically verified candidate may be applied')
            result=state['verification']
            if (result['source_sha256']!=state['source_sha256'] or result['verification_execution']!='PASS'
                    or result['physical_safety_status']!='PASS' or set(result['scenario_results'])!=set(self.scenarios)):
                raise WorkflowBlocked('Candidate is not independently verified across A/B/C')
            proof=AppleVMBackend().preflight()
            if proof['identity']!=state['qualification_identity']:
                raise WorkflowBlocked('VM qualification changed; new verification is required')
            with self._managed() as directory:
                prior=self._current(directory);current_hash=digest(prior) if prior is not None else None
                if current_hash!=state['managed_before_sha256']:
                    raise WorkflowBlocked('Managed source changed since review; refusing overwrite')
                raw=bounded_read(folder,'proposed_source.txt')
                if prior is not None:
                    durable_backup(folder/'previous_controller.backup',prior)
                state['status']='APPLYING';state['permanent_application_approved']=True
                self._save(folder,state,'permanent_application_approved_backup_ready')
                self._unchanged(folder,state)
                self._replace(directory,raw)
                state['status']='APPLIED';self._save(folder,state,'managed_controller_atomically_applied')
            return state

    def rollback(self,review_id,*,confirmation):
        with self._lock(review_id) as folder:
            state=self.get(review_id)
            if confirmation!='REVERT '+review_id:raise WorkflowBlocked('Explicit rollback confirmation is required')
            if state['status'] not in ('APPLIED','APPLYING','REVERTING'):
                raise WorkflowBlocked('No applied transaction to revert')
            with self._managed() as directory:
                raw=self._current(directory);current_hash=digest(raw) if raw is not None else None
                before=state['managed_before_sha256']
                if current_hash not in (state['source_sha256'],before):
                    raise WorkflowBlocked('Installed source changed externally; rollback will not overwrite it')
                previous=bounded_read(folder,'previous_controller.backup') if before is not None else None
                if previous is not None and digest(previous)!=before:
                    raise WorkflowBlocked('Recoverable backup hash mismatch')
                state['status']='REVERTING';self._save(folder,state,'rollback_approved')
                if current_hash!=before:
                    if previous is None:
                        os.unlink(self.managed_name,dir_fd=directory);os.fsync(directory)
                    else:self._replace(directory,previous)
                state['status']='REVERTED';self._save(folder,state,'previous_controller_restored')
            return state
