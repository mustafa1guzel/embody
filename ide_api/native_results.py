"""Bounded read-only product adapters over registered saved jobs. Never execution.

Source/base metadata is not approval. Hashes/readback do not prove external origin.
No request may supply a path, module, controller source or an evidence payload.
"""
import copy,hashlib,math,re,threading
from itertools import islice
from collections import OrderedDict
from datetime import datetime,timezone
from pathlib import Path
import mujoco
import numpy as np
from core.simulation import ROOT,compile_context_model,DEFAULT_MODEL_PATH
from core.diagnostics import evaluate_safety
from ide_api import rail_sweeps as rail,rover_reference as rover,native_models as models
from ide_api.research import readback
from ide_api.research.artifacts import ArtifactStore,finite_json,validate_manifest
from workspace.data import bounded_read

MAX_JOBS=16
MAX_RESULTS=64
MAX_CACHE=8


def locator(job,case):
    rail.identifier(job)
    if not isinstance(case,str) or not re.fullmatch('[a-f0-9]{64}',case):raise ValueError('Invalid saved case identity')
    return 'native_'+job+'_'+case


def split_locator(value):
    m=re.fullmatch(r'native_([a-f0-9]{32})_([a-f0-9]{64})',value) if isinstance(value,str) else None
    if not m:raise ValueError('Invalid bounded native result locator')
    return m.groups()


def qualification(records):
    """Evidence availability is not physical success or universal model qualification."""
    measured=[r for r in records if r.get('verified')]
    current=[r for r in measured if r['source_current']]
    app=[r for r in current if r['provenance'].get('application_source_compatible') is True]
    status='CURRENT_SOURCE_QUALIFICATION_AVAILABLE' if app else 'VERIFIED_RECORDED_SOURCE' if current else 'VERIFIED_HISTORICAL_EVIDENCE' if measured else 'NO_QUALIFYING_EVIDENCE'
    return {'status':status,'verified_cases':len(measured),'native_compatible_cases':len(current),'application_compatible_cases':len(app),'physical_pass':sum(r['verdict']=='PASS' for r in measured),'physical_fail':sum(r['verdict']=='FAIL' for r in measured),'scope':'Exact recorded configurations only; saved physical FAIL is not an execution error. Native compatibility does not qualify changed application code.'}


class NativeResults:
    def __init__(self,service=None,store=None):
        self.service=service if service is not None else rail.RailSweeps()
        self.store=store if store is not None else ArtifactStore(ROOT/'.runtime/evidence_store')
        self._cache=OrderedDict();self._cache_guard=threading.RLock()

    def _root(self):
        root=self.service.root.absolute()
        if root.resolve()!=root:raise ValueError('Symlinked saved-job root refused')
        return root

    def _metadata(self,job,request):
        """Existing immutable binding declaration only, never execution authority.

        Native results do not retain execution UTC or Git base. The matching
        canonical binding supplies a *declared* base; preparation time is NOT run time.
        """
        out={'recorded_git_base':None,'base_origin':None,'recorded_at':None,'application_source_compatible':None,'application_binding_available':False,'execution_authority':False}
        root=self.store.root/'model_qualifications'/job
        if not root.exists():return out
        if root.resolve()!=root:raise ValueError('Unsafe source-binding directory')
        candidates=['consent.json']
        children=list(islice(root.iterdir(),9))
        if len(children)>8:raise ValueError('Source binding enumeration limit')
        candidates += [p.name+'/consent.json' for p in sorted(children) if re.fullmatch('base_[a-f0-9]{12}',p.name)]
        matches=[]
        for name in candidates:
            try:v=finite_json(self.store.read('model_qualifications/'+job+'/'+name,180000),180000)
            except FileNotFoundError:continue
            definition=v.get('definition',{})
            if v.get('sha256')!=rail.digest(definition) or definition.get('request')!=request or not re.fullmatch('[a-f0-9]{40}',str(definition.get('base_commit',''))):continue
            if name.startswith('base_') and not definition['base_commit'].startswith(name[5:17]):raise ValueError('Source-binding base identity mismatch')
            matches.append(definition)
        if not matches:return out
        # A legitimate reviewed base-only amendment may coexist with its original.
        # Prefer the current base if present; never infer approval from this choice.
        from ide_api.research.bundles import repo_base
        from tools.model_qualification import sources
        base=repo_base();chosen=next((x for x in matches if x['base_commit']==base),matches[-1])
        out.update(recorded_git_base=chosen['base_commit'],base_origin='MATCHING_CANONICAL_SOURCE_BINDING_NOT_EXECUTION_ATTESTATION',application_source_compatible=chosen.get('source_manifest')==sources() and chosen['base_commit']==base,application_binding_available=True)
        return out

    def _package(self,job,cid,result):
        """Associate only an existing exact reader capture/package, never a path input."""
        digest=rail.digest(result)
        if result['experiment_id']==rover.EXPERIMENT:
            from ide_api.model_evidence import FORMAT,MAX_BYTES
            name='model_native/'+job+'/'+cid+'.json'
            try:raw=self.store.read(name,MAX_BYTES)
            except FileNotFoundError:return None
            value=finite_json(raw,MAX_BYTES);rail.exact(value,['format','sha256','result'])
            # The identical result has already passed the existing strict V2
            # reader above. Do not rerun its costly forward audit a second time.
            if value['format']!=FORMAT or value['sha256']!=digest or value['result']!=result:raise ValueError('Durable rover package/result mismatch')
            return {'identity':hashlib.sha256(raw).hexdigest(),'format':FORMAT,'origin_attestation':'EXTERNAL_ORIGIN_NOT_ESTABLISHED_BY_HASH','captured_at':None,'recorded_git_base':None}
        root=self.store.root/'bundles'
        if not root.exists():return None
        if root.resolve()!=root:raise ValueError('Unsafe durable bundle directory')
        paths=list(islice(root.iterdir(),17))
        if len(paths)>16:raise ValueError('Durable bundle enumeration limit')
        for p in sorted(paths):
            if not re.fullmatch(r'[a-f0-9]{32}\.json',p.name):continue
            manifest=validate_manifest(finite_json(self.store.read('bundles/'+p.name,120000),120000))
            meta=manifest['metadata']
            if meta['evidence_kind']!='native' or meta['evidence_id']!=job:continue
            artifact=next((a for a in manifest['artifacts'] if a['name']=='cases/'+cid+'/native.json'),None)
            if artifact is None:continue
            if artifact['sha256']!=digest or meta['source_identity']!=result['source_sha256']:raise ValueError('Durable rail bundle/result mismatch')
            verified=self.store.verify(manifest['id'])
            if not verified['verified_local']:raise ValueError('Durable rail capture is missing, altered or unattested')
            return {'identity':manifest['manifest_sha256'],'format':manifest['format'],'origin_attestation':'LOCAL_VERIFIED_READER_CAPTURE_NOT_REMOTE_SIGNATURE','captured_at':manifest['created_utc'],'recorded_git_base':meta['base_commit']}
        return None

    def _rail(self,result,request):
        rail.exact(result,['execution_status','verdict','metrics','checks','failure_reasons','original_reference_acceptance','analytical_prediction','comparison','samples','trajectory_sha256','model_xml','effective_model_sha256','replay','engine_version','units','limitations','case_id','experiment_id','controller_id','source_sha256','parameters','criteria','simulation_configuration'])
        p=rail.parameters(result['parameters']);c=rail.criteria(result['criteria'])
        if result['experiment_id']!=rail.EXPERIMENT or result['controller_id']!=rail.CONTROLLER or result['engine_version']!=mujoco.__version__:raise ValueError('Unsupported saved rail contract')
        if result['simulation_configuration']!={'duration_s':3.,'timestep_s':.005,'initial_position_m':0.}:raise ValueError('Unsupported rail horizon')
        # Compile only the registered numeric construction, never arbitrary saved XML.
        body,world=rail.contexts(p);m,xml=compile_context_model(DEFAULT_MODEL_PATH,body,world)
        if xml!=result['model_xml'] or hashlib.sha256(xml.encode()).hexdigest()!=result['effective_model_sha256']:raise ValueError('Saved rail geometry differs from registered numeric model')
        readback.native_replay(result)
        met=readback.metrics(result['samples'],c,result['simulation_configuration'])['metrics']
        native_metrics,_=rail.measure(result['samples'],c)
        if set(result['metrics'])!=set(native_metrics):raise ValueError('Incomplete or unsupported saved rail metrics')
        if any(not math.isclose(v,result['metrics'][k],rel_tol=0,abs_tol=1e-12) if type(v) in (float,int) else v!=result['metrics'][k] for k,v in met.items() if k in result['metrics']):raise ValueError('Saved rail metrics differ')
        data=mujoco.MjData(m);wall=m.geom('wall').id;bumper=m.geom('front_bumper').id
        for s in result['samples']:
            data.qpos[0]=s['position'];data.qvel[0]=s['velocity'];data.ctrl[0]=s['control'];mujoco.mj_forward(m,data)
            expected=float(np.clip(-p['mass_kg']*s['velocity']/.005,-p['force_n'],p['force_n']))
            if any(abs(a-b)>1e-12 for a,b in [(expected,s['control']),(data.qfrc_actuator[0],s['generalized_actuator_force']),(data.actuator_force[0],s['scalar_actuator_force']),(mujoco.mj_geomDistance(m,data,bumper,wall,100.,None),s['wall_clearance'])]):raise ValueError('Saved rail native force/geometry/control mismatch')
            ids=[[int(v.geom1),int(v.geom2)] for v in data.contact[:data.ncon]]
            if ids!=[v['geom_ids'] for v in s['contacts']] or s['wall_collision']!=any(wall in v for v in ids):raise ValueError('Saved rail contact mismatch')
        if abs(result['samples'][0]['wall_clearance']-p['gap_m'])>1e-12 or result['samples'][0]['position']!=0 or result['samples'][0]['velocity']!=p['speed_mps']:raise ValueError('Saved rail initial state mismatch')
        original=evaluate_safety(result['samples'],world,wall)
        _,selected=rail.measure(result['samples'],c)
        checks={**{k:v=='PASS' for k,v in original['checks'].items()},**selected,'bounded_actuator_force':met['maximum_actuator_force_n']<=p['force_n']+1e-12,'no_unexpected_contacts':all(set(v['geom_ids'])=={wall,bumper} for s in result['samples'] for v in s['contacts']),'fresh_replay':True}
        if result['checks']!=checks or result['original_reference_acceptance']!=original or result['verdict']!=('PASS' if all(checks.values()) else 'FAIL'):raise ValueError('Saved rail acceptance mismatch')

    def load(self,value):
        job,cid=split_locator(value);self._root()
        state=self.service.read(job);request=state['request'];module=models.implementation(request['experiment_id'])
        # Read a bounded byte snapshot first. A warm hit still hashes actual
        # bytes + request/state + native source; mtime alone is never trusted.
        raw=bounded_read(self._root(),job+'/'+cid+'.json')
        snapshot=finite_json(raw,module.POLICY['maximum_case_bytes'])
        key=(value,hashlib.sha256(raw).hexdigest(),rail.digest({'request':request,'cases':state['cases'],'status':state['status']}),module.source_identity())
        with self._cache_guard:
            if key in self._cache:
                result=copy.deepcopy(self._cache[key]);self._cache.move_to_end(key)
            else:
                # Existing strict service owns source/model/result/replay hashes;
                # rover also performs its native forward/acceptance audit here.
                result=self.service.case(job,cid)
                if result!=snapshot:raise ValueError('Saved evidence changed during read')
                if module is rail:self._rail(result,request)
                self._cache[key]=copy.deepcopy(result)
                while len(self._cache)>MAX_CACHE:self._cache.popitem(last=False)
        if result['parameters'] not in request['cases'] or result['criteria']!=request['criteria'] or result['controller_id']!=module.CONTROLLER or request['controller_id']!=module.CONTROLLER or result['source_sha256']!=request['source_sha256'] or not re.fullmatch('[a-f0-9]{64}',result['source_sha256']):raise ValueError('Saved job/result association mismatch')
        expected=rail.digest({'source':result['source_sha256'],'experiment':module.EXPERIMENT,'controller':module.CONTROLLER,'parameters':result['parameters'],'criteria':result['criteria']})
        if expected!=cid or result['execution_status']!='MEASURED':raise ValueError('Saved case identity/status mismatch')
        provenance=self._metadata(job,request);package=self._package(job,cid,result)
        if package and package['recorded_git_base'] is not None:
            provenance.update(recorded_git_base=package['recorded_git_base'],base_origin='DURABLE_LOCAL_READER_CAPTURE')
        record={'id':value,'case_id':cid,'sweep_id':job,'model_id':models.RAIL if module is rail else models.ROVER,'controller_id':module.CONTROLLER,'source_sha256':result['source_sha256'],'parameters':copy.deepcopy(result['parameters']),'criteria':copy.deepcopy(result['criteria']),'metrics':copy.deepcopy(result['metrics']),'checks':copy.deepcopy(result['checks']),'status':'MEASURED','execution_status':'MEASURED','verdict':result['verdict'],'verified':True,'source_current':result['source_sha256']==module.source_identity(),'trajectory_sha256':result['trajectory_sha256'],'result_sha256':rail.digest(result),'model_sha256':result['effective_model_sha256'],'replay_status':'PASS','independent_verification':'SAVED_STATE_READBACK_PASS','trajectory_available':True,'origin':'LOCAL_SAVED_REGISTERED_JOB','provenance':provenance,'compatibility':{'model':models.RAIL if module is rail else models.ROVER,'controller':module.CONTROLLER,'source':result['source_sha256'],'criteria':rail.digest(result['criteria']),'simulation':rail.digest(result['simulation_configuration']),'measurement':'RAIL_SAMPLED_MEASUREMENTS_V1' if module is rail else 'ROVER_TARGET_SAMPLED_V1'},'evidence_package_identity':package['identity'] if package else None,'evidence_package':package,'recording_timestamp':None,'limitations':['Exact saved samples and fresh replay independently checked without integration.','Local job storage/readback is not an external origin signature or execution approval.','No recorded execution timestamp/package reference is invented.']}
        return record,result

    def discover(self,model_id):
        models.for_model(model_id);root=self._root();records=[];unavailable=[];truncated=False
        if not root.exists():return {'records':[],'unavailable':[],'bounded':True,'truncated':False,'limits':{'jobs':MAX_JOBS,'results':MAX_RESULTS},'qualification':qualification([])}
        folders=sorted(islice(root.iterdir(),MAX_JOBS+1))
        if len(folders)>MAX_JOBS:raise ValueError('Saved job enumeration exceeds supported retention; no unbounded scan')
        for folder in folders:
            if len(records)+len(unavailable)>=MAX_RESULTS:truncated=True;break
            if not re.fullmatch('[a-f0-9]{32}',folder.name):continue
            try:
                state=self.service.read(folder.name);module=models.implementation(state['request']['experiment_id'])
                if module is not models.for_model(model_id):continue
                if not isinstance(state['cases'],list) or len(state['cases'])>module.POLICY['maximum_cases']:raise ValueError('Saved case count exceeds bound')
                for item in state['cases']:
                    if len(records)+len(unavailable)>=MAX_RESULTS:truncated=True;break
                    try:
                        identifier=locator(folder.name,item['case_id'])
                        if item['execution_status']!='MEASURED':unavailable.append({'id':identifier,'status':item['execution_status'],'message':'No measured physical verdict; execution incomplete or unavailable.'});continue
                        r,_=self.load(identifier);records.append(r)
                    except (ValueError,OSError,KeyError,TypeError,AssertionError):unavailable.append({'status':'INVALID_OR_MISSING_EVIDENCE','id':item.get('case_id'),'message':'Saved evidence failed bounded integrity/source/readback checks; no physical verdict asserted.'})
            except (ValueError,OSError,KeyError,TypeError,AssertionError):unavailable.append({'status':'INVALID_OR_MISSING_EVIDENCE','id':folder.name,'message':'Saved job metadata unavailable or invalid; no fallback evidence substituted.'})
        return {'records':records,'unavailable':unavailable,'bounded':True,'truncated':truncated,'limits':{'jobs':MAX_JOBS,'results':MAX_RESULTS},'qualification':qualification(records)}


def compare_records(a,b):
    if a['id']==b['id'] or a['compatibility']!=b['compatibility']:raise ValueError('Select distinct exact model/controller/source/criteria/simulation cohorts')
    metrics={k:{'before':v,'after':b['metrics'][k],'delta':b['metrics'][k]-v} for k,v in a['metrics'].items() if type(v) in (int,float) and type(b['metrics'].get(k)) in (int,float)}
    return {'status':'COMPATIBLE_SAVED_RESULTS','baseline':a['id'],'candidate':b['id'],'changed_parameters':{k:{'before':v,'after':b['parameters'][k]} for k,v in a['parameters'].items() if v!=b['parameters'][k]},'verdicts':[a['verdict'],b['verdict']],'metrics':metrics,'minimum_clearance_delta_m':metrics.get('minimum_clearance_m',{}).get('delta'),'meaning':'Measured physical parameter comparison; conditions differ. Not a controller-only benchmark or verification of a modified draft.'}
