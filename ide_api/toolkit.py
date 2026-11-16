"""Multi-model product composition. Numeric declarations, not engineering apply."""
import copy,hashlib,os,re,threading
from pathlib import Path
from uuid import uuid4
from core.simulation import ROOT
from engineering.store import Store
from ide_api import native_models as models,rail_sweeps as rail,rover_reference as rover
from ide_api import robot_import
from ide_api.model_evidence import diagnose
from workspace.data import bounded_read,decode_json
MAX_PROJECTS=16

class Toolkit:
    def __init__(self,root=None):
        self.root=Path(root) if root else ROOT/'.runtime/model_projects';self.lock=threading.RLock()
    def catalog(self):return {'version':1,'models':models.descriptors(),'projects':self.listing(),'declarative_format':robot_import.FORMAT,'native_runs':0,'execution_authorized':False}
    def _folder(self,key):return self.root/rail.identifier(key)
    def listing(self):
        if not self.root.exists():return []
        rows=[]
        for p in sorted(self.root.iterdir()):
            if re.fullmatch('[a-f0-9]{32}',p.name):
                v=self.read(p.name);rows.append({'id':v['id'],'title':v['declaration']['title'],'model_id':v['declaration']['model_id'],'revision':v['revision'],'verification':v['verification'],'stale':v['stale']})
        return rows
    def _write(self,key,payload):
        folder=self._folder(key);store=Store(folder/'snapshots');h=store.put(payload)
        # Atomic pointer only for an explicitly created/saved numeric project. Never a World head.
        if folder.is_symlink() or (folder/'head.json').is_symlink():raise ValueError('Symlink project pointer refused')
        tmp=folder/(uuid4().hex+'.tmp');rail.write_once(tmp,{'sha256':h},1024);os.replace(tmp,folder/'head.json')
        return self.read(key)
    def create(self,declaration):
        d=robot_import.validate(declaration)
        with self.lock:
            self.root.mkdir(parents=True,exist_ok=True)
            if len(list(self.root.iterdir()))>=MAX_PROJECTS:raise ValueError('Project quota reached; no automatic deletion')
            return self._write(uuid4().hex,{'revision':0,'declaration':d,'source_sha256':models.for_model(d['model_id']).source_identity()})
    def read(self,key):
        folder=self._folder(key);pointer=decode_json(bounded_read(folder,'head.json'));rail.exact(pointer,['sha256'])
        # Existing Store enforces O_NOFOLLOW and content hashes; refuse symlink directories as well.
        for p in [folder,self.root,folder/'snapshots']:
            if p.is_symlink():raise ValueError('Symlink robot project refused')
        if not (folder/'snapshots').is_dir():raise ValueError('Missing immutable project snapshots')
        value=Store(folder/'snapshots').get(pointer['sha256']);rail.exact(value,['revision','declaration','source_sha256'])
        declaration=robot_import.validate(value['declaration'])
        if type(value['revision']) is not int or not 0<=value['revision']<=999999:raise ValueError('Invalid project revision')
        return {'id':key,'sha256':pointer['sha256'],**value,'declaration':declaration,'verification':'NOT_VERIFIED','stale':value['source_sha256']!=models.for_model(declaration['model_id']).source_identity(),'kind':'NUMERIC_MODEL_PROJECT_NOT_APPLIED_WORLD'}
    def save(self,key,expected,declaration):
        d=robot_import.validate(declaration)
        with self.lock:
            p=self.read(key)
            if p['sha256']!=expected or p['stale']:raise ValueError('Stale project/source; inspect and create an explicit new declaration')
            if d['model_id']!=p['declaration']['model_id'] or d['controller_id']!=p['declaration']['controller_id']:raise ValueError('Project model/controller cannot change on save')
            return self._write(key,{'revision':p['revision']+1,'declaration':d,'source_sha256':p['source_sha256']})
    def export(self,key):return self.read(key)['declaration']
    def prepare(self,declaration):
        d=robot_import.validate(declaration);module=models.for_model(d['model_id'])
        request=module.validate({'experiment_id':module.EXPERIMENT,'controller_id':module.CONTROLLER,'source_sha256':module.source_identity(),'cases':[d['parameters']],'criteria':d['requirements'],'nonce':uuid4().hex,'confirmation':module.CONFIRMATION})
        return {'request':request,'status':'PENDING_SEPARATE_EXPLICIT_APPROVAL','execution_authorized':False,'native_steps':0,'primary_steps':module.POLICY['primary_steps_per_case'],'fresh_replay_steps':module.POLICY['replay_steps_per_case'],'requirements':d['requirements'],'qualification':'CURRENT_SOURCE_NATIVE_VERIFICATION_PENDING','shared_job_service':'RailSweeps + Server.job; no separate executor','model_id':d['model_id']}
    def design(self,declaration):
        d=robot_import.validate(declaration)
        if d['model_id']==models.RAIL:
            from core.simulation import compile_context_model,DEFAULT_MODEL_PATH
            from ide_api.product_alpha import scene
            import mujoco
            p=d['parameters'];body,world=rail.contexts(p);m,xml=compile_context_model(DEFAULT_MODEL_PATH,body,world);data=mujoco.MjData(m);data.qvel[0]=p['speed_mps'];mujoco.mj_forward(m,data)
            initial=rail.snapshot(m,data)
            return {'scene':scene({'model_xml':xml,'samples':[initial]}),'initial_state':initial,'simulation':'NOT_RUN','verification':'COMPILED_NOT_PHYSICALLY_VERIFIED','origin':'COMPILED_INITIAL_CONFIGURATION_NOT_RECORDED_TRAJECTORY','diagnosis':{'status':'UNVERIFIED_NO_MEASUREMENTS','issues':[]}}

        project,roles,proof,model,xml,contract=rover.compiled(d['parameters'])
        from shapebase.geometry import library
        return {'shape_parts':library(project)['parts'],'world':project['world'],'roles':roles,'compiled_contract':contract,'model_xml_sha256':hashlib.sha256(xml.encode()).hexdigest(),'total_dynamic_mass_kg':float(model.body_mass.sum()),'proof':proof,'simulation':'NOT_RUN','verification':'COMPILED_NOT_PHYSICALLY_VERIFIED','diagnosis':diagnose(None),'selection_ids':[o['id'] for o in project['world']['objects']],'origin':'DEVELOPER_AUTHORED_TYPED_PROXY_NOT_AI','limitations':rover.LIMITATIONS}

    def results(self,key):
        p=self.read(key);d=p['declaration'];module=models.for_model(d['model_id']);rows=[]
        service=rail.RailSweeps()
        if service.root.exists():
            for folder in sorted(service.root.iterdir()):
                if not re.fullmatch('[a-f0-9]{32}',folder.name):continue
                state=service.read(folder.name);r=state['request']
                if r['experiment_id']!=module.EXPERIMENT or r['controller_id']!=module.CONTROLLER or r['source_sha256']!=module.source_identity() or r['criteria']!=d['requirements']:continue
                for case in state['cases']:
                    if case['parameters']==d['parameters'] and case.get('execution_status')=='MEASURED':rows.append({'sweep_id':folder.name,'case_id':case['case_id'],'verdict':case['verdict']})
        return {'results':rows,'verification':'NOT_VERIFIED' if not rows else 'EXACT_CURRENT_INPUT_RECORDS_AVAILABLE'}
    def result(self,key,sweep,case):
        matches=self.results(key)['results']
        if not any(v['sweep_id']==sweep and v['case_id']==case for v in matches):raise ValueError('Result does not belong to exact current project configuration/source')
        value=rail.RailSweeps().case(sweep,case)
        if value['experiment_id']!=rover.EXPERIMENT:raise ValueError('Use historical rail reader for rail trajectories')
        from ide_api.model_evidence import verify_result,diagnose
        checked=verify_result(value)
        return {**checked,'diagnosis':diagnose(value)}
