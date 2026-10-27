"""Explicit empty-head construction review using preserved Phase17 provenance.

This creates a NEW construction proposal. It never rebases or applies the old
changeset. Native previews and a separate human commit are distinct operations.
"""
from pathlib import Path
from uuid import uuid4
import copy,os,json,threading
from robustness.contracts import file_hash
from physics.contracts import digest,canonical
from core.simulation import ROOT
from .store import Store
from .project import identity,validate
from .creation import implementation_identity
from .synthesis import recipe,build_copy
from .plans import validate_plan
from .created_simulation import compile_created,run
from .barrier_repair import preflight_project,FROZEN_CHECK_NAMES

PHASE17=ROOT/'artifacts/phase17_live_creation/20261024/live_execution'
PHASE171=ROOT/'artifacts/phase17_1_physics_repair/20261025/formal_repair'

class VerifiedConstruction:
    def __init__(self,root=None,*,project_root=None):
        self.root=Path(root) if root else ROOT/'artifacts/phase17_2/workspaces/construction_review'
        self.reviews=Store(self.root/'reviews');self.measurements=Store(self.root/'measurements');Store(self.root/'decisions')
        self.lock=threading.RLock()
        selection=json.loads((PHASE17/'selection.json').read_text())
        project_id=selection['construction_proposal']['project_id']
        location=Path(project_root) if project_root else PHASE17/'review_registry/projects'/project_id
        if not (location/'head.json').is_file():raise ValueError('Original authoritative project head is unavailable; no replacement created')
        from ide_api.engineering import EngineeringService
        self.project=EngineeringService(location)

    def _sources(self):
        selection=json.loads((PHASE17/'selection.json').read_text())
        repair=json.loads((PHASE171/'result.json').read_text())
        prior=json.loads((PHASE171/'runs/000/result.json').read_text())
        for name,item in repair['source_evidence'].items():
            if file_hash(ROOT/item['path'])!=item['sha256']:
                archived=list((self.root/'decisions').glob('base_head_*.json')) if name=='authoritative_empty_head' else []
                if not any(file_hash(p)==item['sha256'] for p in archived):raise ValueError('Preserved Phase17 evidence identity mismatch')
        if file_hash(Path(repair['evidence']['new']['path']))!=repair['evidence']['new']['sha256']:raise ValueError('Phase17.1 measured repair identity mismatch')
        if not all(prior['acceptance']['checks'].values()) or prior['independent_verification']['status']!='PASS':raise ValueError('Verified Phase17.1 repair unavailable')
        return selection,repair,prior

    def _identity(self):
        result=implementation_identity()
        for name in ('devices/simulation.py','devices/contracts.py','ide_api/engineering.py'):
            result[name]=file_hash(ROOT/name)
        return result

    def bootstrap(self):
        initial=self.project.current();selection,repair,prior=self._sources()
        original=selection['construction_proposal']['proposed_project']
        failure=json.loads((PHASE17/'previews/primary/result.json').read_text())
        return {'project':initial,'project_sha256':identity(initial),'application_status':'EMPTY_NOT_COMMITTED' if initial['creation']['state']=='EMPTY' else 'COMMITTED_PROJECT',
            'original_proposal':original,'original_model_intent':selection['model_design_intent'],
            'original_parameters':selection['model_design_intent']['mechanical'],'repaired_parameters':repair['accepted_parameters'],
            'original_preflight':preflight_project(original),'original_failure':{'origin':'RECORDED_GENUINE_PHASE17_FAILURE','acceptance':failure['acceptance'],'source_sha256':file_hash(PHASE17/'previews/primary/result.json')},
            'recorded_repair':{'origin':'RECORDED_PHASE17_1; no fresh run in this response','acceptance':prior['acceptance'],'independent_verification':prior['independent_verification']},
            'authorship':'Original GPT intent is preserved. Repair and empty-head reconstruction are deterministic local engineering work, not a new model response.',
            'source_paths':{'phase17':str(PHASE17.relative_to(ROOT)),'phase17_1':str(PHASE171.relative_to(ROOT))},'automatic_commit':False}

    def _construct(self,initial):
        selection,repair,prior=self._sources();old=selection['construction_proposal']
        if initial['creation']['state']!='EMPTY' or initial['revision']!=0 or identity(initial)!=old['base_sha256']:raise ValueError('Exact original EMPTY revision-zero base required; no force/rebase')
        batches,metadata=recipe(old['requirements'],initial)
        if digest(batches)!=digest(old['batches']) or digest(metadata)!=digest(old['metadata']):raise ValueError('Original typed construction prefix no longer matches preserved model proposal')
        fixed=repair['accepted_parameters']
        if (fixed['mass_kg'],fixed['torque_nm'],fixed['pivot_height_m'],fixed['span_m'])!=(.035,.12,.18,.28):raise ValueError('Proven repair parameters changed')
        target=repair['engineering_changeset']['proposed_project'];roles=target['creation']['world_roles']
        pivot=next(o for o in target['world']['objects'] if o['id']==roles['pivot'])
        corrections=[{'kind':'set_mass','target':roles['beam'],'mass_kg':fixed['mass_kg']},
            {'kind':'set_actuator_limit','target':roles['pivot'],'limit':fixed['torque_nm']},
            {'kind':'move_object','target':roles['pivot'],'position_m':pivot['position_m']}]
        combined=[*batches,corrections]
        candidate,checks=build_copy(initial,combined,metadata)
        plan=copy.deepcopy(old['plan']);plan['revision']+=1;plan['construction_batches']=combined
        plan['physical_assumptions']=[*plan['physical_assumptions'],'Three explicit deterministic world-data corrections follow the unchanged original model construction prefix. Original model intent remains unchanged.']
        plan=validate_plan(plan);plan_sha=digest(plan)
        candidate['design_plans']=[{'id':plan['id'],'revision':plan['revision'],'sha256':plan_sha}];candidate=validate(candidate)
        _,spec,_,xml,compiled=compile_created(candidate)
        if xml!=prior['model_xml'] or spec.to_dict()!=prior['device_spec']:raise ValueError('Reconstruction changed proven native model, controller, sensor or criteria')
        if candidate['circuit']!=old['proposed_project']['circuit'] or candidate['controller_sha256']!=target['controller_sha256'] or candidate['interfaces']!=target['interfaces']:raise ValueError('Circuit/controller/interface preservation failed')
        return {'base_sha256':identity(initial),'base_revision':initial['revision'],'project_id':initial['id'],
            'status':'PROPOSED_NOT_APPLIED','batches':combined,'original_batch_count':len(batches),'repair_operations':corrections,
            'proposed_project':candidate,'resulting_sha256':identity(candidate),'plan':plan,'plan_sha256':plan_sha,
            'validation':checks,'physics_preflight':preflight_project(candidate),'native_model_sha256':compiled['compiled']['model_sha256'],
            'original_model_intent':selection['model_design_intent'],'original_model_intent_sha256':selection['model_design_intent_sha256'],
            'old_changeset_base_sha256':repair['engineering_changeset']['base_project_sha256'],
            'provenance':{'original_selection_sha256':file_hash(PHASE17/'selection.json'),'verified_repair_sha256':file_hash(PHASE171/'result.json'),'original_failed_experiment_status':'PARTIAL_PRESERVED','reconstruction_origin':'DETERMINISTIC_LOCAL; separate from original model authorship'},
            'implementation_sha256':self._identity(),'automatic_commit':False}

    def prepare(self,sha,revision):
        with self.project.transaction():initial=self.project._precondition(sha,revision)
        proposal=self._construct(initial);key=self.reviews.put(proposal)
        return {**proposal,'review_id':key}

    def _checked(self,key,sha,revision,initial=None):
        proposal=self.reviews.get(key)
        if initial is None:
            with self.project.transaction():initial=self.project._precondition(sha,revision)
        if proposal['base_sha256']!=sha or proposal['base_revision']!=revision or proposal['implementation_sha256']!=self._identity():raise ValueError('Stale construction review or implementation; inspect current head')
        rebuilt=self._construct(initial)
        if digest(rebuilt)!=digest(proposal):raise ValueError('Independent empty-head reconstruction mismatch')
        return proposal

    def latest(self,key):
        self.reviews.get(key)
        for index in (1,0):
            ref=self.root/f'{key}_preview_{index}.json'
            if ref.exists():
                item=json.loads(ref.read_text())
                if 'measurement_sha256' in item:return self.measurements.get(item['measurement_sha256'])
        return None

    def preview(self,key,sha,revision,*,render_image=True):
        with self.lock:
            proposal=self._checked(key,sha,revision)
            for index in (0,1):
                reservation=self.root/f'{key}_reservation_{index}'
                try:
                    with reservation.open('x') as f:f.write('Explicit trusted preview reserved; no project application.')
                    break
                except FileExistsError:continue
            else:raise ValueError('Two native previews already reserved for this exact review')
            folder=self.root/'runs'/('preview_'+uuid4().hex)
            result=run(proposal['proposed_project'],folder,render_image=render_image)
            if set(result['acceptance']['checks'])!=set(FROZEN_CHECK_NAMES):raise ValueError('Frozen acceptance names changed')
            value={'review_id':key,'candidate_sha256':proposal['resulting_sha256'],'result':result,'origin':'FRESH_NATIVE_PREVIEW; NOT_APPLIED','evidence_path':str(folder),'authoritative_project_sha256':identity(self.project.current())}
            stored=self.measurements.put(value)
            with (self.root/f'{key}_preview_{index}.json').open('x') as f:json.dump({'measurement_sha256':stored},f)
            return value

    def commit(self,key,sha,revision,confirmation):
        if confirmation!='COMMIT VERIFIED CONSTRUCTION '+key:raise ValueError('Separate explicit human construction confirmation required')
        with self.lock,self.project.transaction():
            initial=self.project._precondition(sha,revision);proposal=self._checked(key,sha,revision,initial)
            measurement=self.latest(key)
            if not measurement or measurement['candidate_sha256']!=proposal['resulting_sha256'] or measurement['result']['status']!='VERIFIED_IN_SIMULATION' or measurement['result']['independent_verification']['status']!='PASS':raise ValueError('Fresh passing native verification of this exact construction required')
            # Reserve a human decision before the atomic head swap. Neither a
            # model tool nor a preview invokes this method.
            decision={'kind':'EXPLICIT_HUMAN_VERIFIED_CONSTRUCTION','review_id':key,'base_sha256':sha,'result_sha256':proposal['resulting_sha256'],'measurement_sha256':digest(measurement)}
            with (self.root/'decisions'/('base_head_'+key+'.json')).open('xb') as f:f.write((self.project.root/'head.json').read_bytes())
            fd=os.open(self.root/'decisions'/key,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            with os.fdopen(fd,'w') as f:f.write(canonical(decision))
            if self.project.plans.put(proposal['plan'])!=proposal['plan_sha256']:raise ValueError('Construction plan identity mismatch')
            authorization=self.project.events.put(decision)
            built=self.project._commit(proposal['proposed_project'],authorization=authorization)
            return {'status':'COMMITTED_AFTER_EXPLICIT_HUMAN_DECISION','project':built,'project_sha256':identity(built),'review_id':key}
