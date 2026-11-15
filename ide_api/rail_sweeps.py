"""Fixed developer-authored rail reference; never a candidate-source executor.

Only the local guarded HTTP adapter can admit numeric sweeps. No model/controller
path, source, XML, command, import name or output path is accepted in a request.
"""
from __future__ import annotations
import copy, hashlib, json, math, re, threading, time
from dataclasses import replace
from pathlib import Path
from uuid import uuid4
import mujoco
import numpy as np
from core.simulation import ROOT, DEFAULT_MODEL_PATH, run_simulation
from core.bodybase import BodyBase
from core.worldbase import WorldBase
from core.diagnostics import evaluate_safety
from workspace.data import bounded_read, decode_json

EXPERIMENT = 'rail_velocity_brake_v1'
CONTROLLER = 'developer_velocity_brake_v1'
CONFIRMATION = 'RUN TRUSTED RAIL SWEEP'
BOUNDS = {'mass_kg': (1., 4.), 'speed_mps': (0., 1.2), 'force_n': (2., 6.), 'gap_m': (.35, 2.2)}
UNITS = dict(zip(BOUNDS, ['kg', 'm/s', 'N', 'm']))
POLICY = {'maximum_cases': 25, 'duration_s': 3., 'timestep_s': .005, 'primary_steps_per_case': 600,
          'replay_steps_per_case': 600, 'samples_per_trajectory': 601, 'maximum_total_steps': 30000,
          'wall_seconds': 60., 'retained_jobs': 16, 'maximum_request_bytes': 16384,
          'maximum_case_bytes': 1500000, 'maximum_overview_bytes': 65536}
DEFAULT_CRITERIA = {'minimumClearance': .05, 'maximumFinalSpeed': .03, 'maximumSettlingTime': 3., 'maximumContactEpisodes': 0}
LIMITATIONS = ['Developer-authored immediate velocity-opposing reference; not a historical GPT repair.',
 'Frictionless one-axis rigid proxy; no material, hardware or universal safety certification.',
 'Sampled low-speed suffix is not exact continuous stopping time.',
 'Physical verdict requires original fixed rail safety checks AND selected criteria AND fresh replay/force/contact audit.',
 'Cancellation and wall deadline are cooperative between fixed native steps; no arbitrary code is run.']
_local = threading.local()


def canonical(v): return json.dumps(v, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
def digest(v): return hashlib.sha256(canonical(v)).hexdigest()
def exact(v, keys):
    if not isinstance(v, dict) or set(v) != set(keys): raise ValueError('Exact trusted sweep fields required')
def number(v, lo, hi):
    if type(v) not in (int, float) or not math.isfinite(v) or not lo <= v <= hi: raise ValueError('Numeric value outside trusted sweep bounds')
    return float(v)
def identifier(v):
    if not isinstance(v, str) or re.fullmatch('[a-f0-9]{32}', v) is None: raise ValueError('Invalid sweep identifier')
    return v

def source_identity():
    files = [Path(__file__), ROOT/'ide_api/server.py', ROOT/'core/simulation.py', ROOT/'core/bodybase.py',
             ROOT/'core/worldbase.py', ROOT/'core/diagnostics.py', ROOT/'core/context_validation.py',
             ROOT/'configs/bodybase.json', ROOT/'configs/worldbase.json', DEFAULT_MODEL_PATH]
    return digest({'files': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
                   'engine': mujoco.__version__, 'numpy': np.__version__, 'policy': POLICY, 'controller': CONTROLLER})

def catalog():
    return {'experiment_id': EXPERIMENT, 'controller_id': CONTROLLER, 'source_sha256': source_identity(),
            'model_id': 'rail_carriage', 'model_template_sha256': hashlib.sha256(DEFAULT_MODEL_PATH.read_bytes()).hexdigest(),
            'bounds': BOUNDS, 'units': UNITS, 'policy': POLICY, 'defaults': DEFAULT_CRITERIA,
            'confirmation': CONFIRMATION, 'limitations': LIMITATIONS, 'execution': 'TRUSTED_DEVELOPER_REFERENCE_ONLY'}

def parameters(v):
    exact(v, BOUNDS); out = {k: number(v[k], *bound) for k, bound in BOUNDS.items()}
    if any(abs(n*1e6-round(n*1e6)) > 1e-7 for n in out.values()): raise ValueError('Use at most six decimals')
    return out

def criteria(v):
    exact(v, DEFAULT_CRITERIA)
    out = {k: number(v[k], *b) for k, b in {'minimumClearance':(0,2.2), 'maximumFinalSpeed':(0,1.2),
            'maximumSettlingTime':(0,3), 'maximumContactEpisodes':(0,600)}.items()}
    if out['maximumFinalSpeed'] <= 0 or type(v['maximumContactEpisodes']) is not int: raise ValueError('Positive speed and integer contact limit required')
    out['maximumContactEpisodes']=int(out['maximumContactEpisodes'])
    return out

def validate(v):
    exact(v, ['experiment_id','controller_id','source_sha256','cases','criteria','nonce','confirmation'])
    if len(canonical(v)) > POLICY['maximum_request_bytes']: raise ValueError('Sweep request exceeds size limit')
    if v['experiment_id'] != EXPERIMENT or v['controller_id'] != CONTROLLER: raise ValueError('Only the registered developer rail reference may execute')
    if v['source_sha256'] != source_identity(): raise ValueError('Trusted source/configuration identity changed; prepare a new confirmation')
    if v['confirmation'] != CONFIRMATION: raise ValueError('Explicit trusted sweep confirmation required')
    identifier(v['nonce']); c=criteria(v['criteria'])
    if not isinstance(v['cases'], list) or not 1 <= len(v['cases']) <= 25: raise ValueError('One to 25 cases required')
    cases=[parameters(p) for p in v['cases']]
    if len({digest(p) for p in cases}) != len(cases): raise ValueError('Duplicate cases rejected')
    return {**copy.deepcopy(v), 'cases':cases, 'criteria':c}

class Cancelled(RuntimeError): pass
class Deadline(RuntimeError): pass

def reference_controller(model, data):
    """Known developer logic: bounded opposing force; clip the last braking step.

    No wall-distance trigger or imported repair; immediate ideal-model reference.
    The cancellation/deadline state is set only by the local serial service.
    """
    context=getattr(_local, 'context', None)
    if context:
        if context['cancel'].is_set(): raise Cancelled('Explicit cancellation')
        if time.monotonic() >= context['deadline']: raise Deadline('Sweep wall deadline reached')
        context['calls'] += 1
        if context['calls'] > 1202: raise Deadline('Controller sample budget reached')
    motor=model.actuator('x_motor').id
    requested=-float(model.body('carriage').mass[0])*float(data.qvel[0])/float(model.opt.timestep)
    data.ctrl[motor]=min(float(model.actuator_ctrlrange[motor,1]), max(float(model.actuator_ctrlrange[motor,0]), requested))


def contexts(p):
    body=replace(BodyBase.from_json(), mass_kg=p['mass_kg'], max_force_n=p['force_n'])
    base=WorldBase.from_json()
    bumper=body.collision_geometry.bumper_center_x_m+body.collision_geometry.bumper_half_size_m[0]
    world=replace(base, initial_position_x_m=0., initial_velocity_ms=p['speed_mps'],
                  wall_position_x_m=bumper+p['gap_m']+base.wall_half_size_m[0],
                  simulation_duration_s=3., simulation_timestep_s=.005,
                  minimum_clearance_m=.05, max_final_speed_ms=.03, completion_deadline_s=3.)
    return body,world

FIELDS=('time','position','velocity','wall_clearance','control','generalized_actuator_force','scalar_actuator_force')
def snapshot(model, data):
    wall,bumper=model.geom('wall').id,model.geom('front_bumper').id
    gap=float(mujoco.mj_geomDistance(model,data,bumper,wall,100.,None))
    contacts=[{'geom_ids':[int(c.geom1),int(c.geom2)]} for c in data.contact[:data.ncon]]
    return {'time':float(data.time),'position':float(data.qpos[0]),'velocity':float(data.qvel[0]),'wall_clearance':gap,
            'control':float(data.ctrl[0]),'generalized_actuator_force':float(data.qfrc_actuator[0]),
            'scalar_actuator_force':float(data.actuator_force[0]),'wall_collision':any(wall in c['geom_ids'] for c in contacts),'contacts':contacts}

def measure(samples, c):
    if len(samples) != 601 or any(not math.isfinite(s[k]) for s in samples for k in FIELDS): raise ValueError('Invalid native trajectory')
    settled=None
    for s in reversed(samples):
        if abs(s['velocity']) >= c['maximumFinalSpeed']: break
        settled=s['time']
    events=sum(s['wall_collision'] and (i==0 or not samples[i-1]['wall_collision']) for i,s in enumerate(samples))
    m={'minimum_clearance_m':min(s['wall_clearance'] for s in samples),'final_speed_mps':abs(samples[-1]['velocity']),
       'maximum_speed_mps':max(abs(s['velocity']) for s in samples),'wall_contact_episodes':events,
       'wall_contact_samples':sum(s['wall_collision'] for s in samples),'sampled_settling_time_s':settled,
       'sampled_settling_travel_m':None if settled is None else next(s['position'] for s in samples if s['time']==settled)-samples[0]['position'],
       'duration_s':samples[-1]['time'],'sample_count':len(samples),'maximum_actuator_force_n':max(abs(s['generalized_actuator_force']) for s in samples)}
    checks={'selected_clearance':m['minimum_clearance_m']>=c['minimumClearance']-1e-12,
            'selected_final_speed':m['final_speed_mps']<c['maximumFinalSpeed'],
            'selected_settling_time':settled is not None and settled<=c['maximumSettlingTime']+1e-12,
            'selected_contact_episodes':events<=c['maximumContactEpisodes']}
    return m,checks

def simulate_case(p, c, folder):
    """One fixed primary rollout and one fresh direct native replay, no other code."""
    body,world=contexts(p)
    run=run_simulation(bodybase=body,worldbase=world,controller=reference_controller,
                       save_telemetry=False,save_render=False,artifacts_dir=folder/'primary')
    if run['metadata']['actual_steps']!=600 or run['metadata']['warnings']: raise ValueError('Primary step/warning check failed')
    xml=run['effective_model_xml'];m=mujoco.MjModel.from_xml_string(xml);d=mujoco.MjData(m)
    d.qvel[0]=p['speed_mps'];wall=m.geom('wall').id;bumper=m.geom('front_bumper').id
    if not (math.isclose(float(m.body('carriage').mass[0]),p['mass_kg'],abs_tol=1e-12)
            and np.allclose(m.actuator_ctrlrange[0],[-p['force_n'],p['force_n']],atol=1e-12,rtol=0)
            and np.allclose(m.actuator_forcerange[0],[-p['force_n'],p['force_n']],atol=1e-12,rtol=0)
            and m.actuator_gear[0,0]==1 and m.opt.timestep==.005): raise ValueError('Compiled parameter mismatch')
    replay=[]
    for i in range(601):
        mujoco.mj_forward(m,d);reference_controller(m,d);mujoco.mj_forward(m,d);replay.append(snapshot(m,d))
        if i<600:mujoco.mj_step(m,d)
    if any(w.number for w in d.warning):raise ValueError('Replay numerical warning')
    primary=[{k:s[k] for k in (*FIELDS,'wall_collision','contacts')} for s in run['telemetry']]
    differences={k:max(abs(a[k]-b[k]) for a,b in zip(primary,replay)) for k in FIELDS}
    contacts_match=all([x['geom_ids'] for x in a['contacts']]==[x['geom_ids'] for x in b['contacts']] for a,b in zip(primary,replay))
    initial_ok=abs(primary[0]['wall_clearance']-p['gap_m'])<=1e-12 and primary[0]['velocity']==p['speed_mps']
    replay_ok=len(primary)==601 and max(differences.values())<=1e-9 and contacts_match and initial_ok
    if not replay_ok:raise ValueError('Fresh native replay/state/geometry mismatch')
    metrics,selected=measure(primary,c); original=evaluate_safety(primary,world,wall)
    forces=metrics['maximum_actuator_force_n']<=p['force_n']+1e-12
    unexpected=any(set(contact['geom_ids'])!={wall,bumper} for s in primary for contact in s['contacts'])
    checks={**{k:v=='PASS' for k,v in original['checks'].items()},**selected,'bounded_actuator_force':forces,'no_unexpected_contacts':not unexpected,'fresh_replay':replay_ok}
    verdict='PASS' if all(checks.values()) else 'FAIL'
    a=p['force_n']/p['mass_kg'];distance=p['speed_mps']**2/(2*a);remaining=p['gap_m']-distance
    return {'execution_status':'MEASURED','verdict':verdict,'metrics':metrics,'checks':checks,
            'failure_reasons':[k.replace('_',' ') for k,v in checks.items() if not v], 'original_reference_acceptance':original,
            'analytical_prediction':{'kind':'ANALYTICAL_PREDICTION','stopping_distance_m':distance,'stopping_time_s':p['speed_mps']/a,'remaining_clearance_m':remaining},
            'comparison':{'measured_minus_ideal_clearance_m':metrics['minimum_clearance_m']-remaining,
               'sampled_travel_minus_ideal_stop_m':None if metrics['sampled_settling_travel_m'] is None else metrics['sampled_settling_travel_m']-distance},
            'samples':primary,'trajectory_sha256':digest(primary),'model_xml':xml,'effective_model_sha256':hashlib.sha256(xml.encode()).hexdigest(),
            'replay':{'status':'PASS','primary_steps':600,'fresh_steps':600,'max_abs_differences':differences,'contact_ids_match':contacts_match,
                      'method':'Fresh MjModel/MjData, direct native stepping, mj_geomDistance and force/contact checks','samples':replay,'trajectory_sha256':digest(replay)},
            'engine_version':mujoco.__version__,'units':UNITS,'limitations':LIMITATIONS}


def write_once(path, value, maximum):
    raw=canonical(value)
    if len(raw)>maximum:raise ValueError('Bounded result size exceeded')
    with path.open('xb') as f:f.write(raw)

def read_json(root, name):return decode_json(bounded_read(root,name))

class RailSweeps:
    def __init__(self, root=None):
        self.root=Path(root) if root is not None else ROOT/'.runtime/rail_sweeps'
        self.guard=threading.RLock();self.controls={};self.active=set()
    def catalog(self):
        recent=[]
        if self.root.exists():
            for folder in sorted(self.root.iterdir()):
                if re.fullmatch('[a-f0-9]{32}',folder.name):
                    try:recent.append({'id':folder.name,'status':self.read(folder.name)['status']})
                    except (ValueError,OSError,KeyError):continue
        return {**catalog(),'recent':recent[:16]}
    def _folder(self, key):return self.root/identifier(key)
    def start(self, value, submit):
        request=validate(value);key=request['nonce'];folder=self._folder(key)
        with self.guard:
            if folder.exists():
                if read_json(folder,'request.json')!=request:raise ValueError('Consumed nonce belongs to different inputs')
                return {'sweep_id':key,'reused':True}
            self.root.mkdir(parents=True,exist_ok=True)
            if len(list(self.root.iterdir()))>=POLICY['retained_jobs']:raise ValueError('Local retained-job quota reached; preserve/export results before operator maintenance')
            folder.mkdir();write_once(folder/'request.json',request,POLICY['maximum_request_bytes'])
            self.controls[key]={'cancel':threading.Event()};self._state(key,'QUEUED',[])
            try:job=submit(lambda:self.execute(key))
            except Exception:
                self._state(key,'EXECUTION_ERROR',[], 'Job admission failed; no implicit retry');raise
        return {'sweep_id':key,'reused':False,**job}
    def _state(self,key,status,cases,error=None):
        value={'sweep_id':key,'status':status,'cases':cases,'error':error}
        raw=canonical(value)
        if len(raw)>POLICY['maximum_overview_bytes']:raise ValueError('Overview size exceeded')
        folder=self._folder(key);temporary=folder/('state_'+uuid4().hex+'.tmp')
        with temporary.open('xb') as f:f.write(raw)
        temporary.replace(folder/'state.json')
    def read(self,key):
        folder=self._folder(key);request=read_json(folder,'request.json');state=read_json(folder,'state.json')
        with self.guard:
            if state['status'] in ('QUEUED','RUNNING') and key not in self.controls:
                state={**state,'status':'INTERRUPTED','error':'Previous process stopped; scope is consumed and will not retry'}
        return {**state,'request':request,'policy':POLICY,'catalog_identity':request['source_sha256'],'limitations':LIMITATIONS}
    def case(self,key,case_id):
        if not isinstance(case_id,str) or re.fullmatch('[a-f0-9]{64}',case_id) is None:raise ValueError('Invalid case identity')
        result=read_json(self._folder(key),case_id+'.json');state=self.read(key)
        entry=next((c for c in state['cases'] if c['case_id']==case_id),None)
        if entry is None or entry.get('result_sha256')!=digest(result):raise ValueError('Saved case integrity mismatch')
        if result['case_id']!=case_id or digest(result['samples'])!=result['trajectory_sha256'] or hashlib.sha256(result['model_xml'].encode()).hexdigest()!=result['effective_model_sha256'] or digest(result['replay']['samples'])!=result['replay']['trajectory_sha256']:raise ValueError('Saved trajectory/model integrity mismatch')
        return result
    def cancel(self,key):
        with self.guard:
            state=self.read(key)
            if state['status'] in ('QUEUED','RUNNING') and key in self.controls:
                self.controls[key]['cancel'].set()
        return self.read(key)
    def execute(self,key):
        folder=self._folder(key)
        with self.guard:
            if key in self.active or key not in self.controls:raise ValueError('Scope already consumed or unavailable')
            if self.read(key)['status']!='QUEUED':raise ValueError('Scope already started')
            self.active.add(key);control=self.controls[key];self._state(key,'RUNNING',[])
        records=[];status='COMPLETED';error=None;request=read_json(folder,'request.json');deadline=time.monotonic()+60
        try:
            validate(request)
            for p in request['cases']:
                case_id=digest({'source':request['source_sha256'],'experiment':EXPERIMENT,'controller':CONTROLLER,'parameters':p,'criteria':request['criteria']})
                item={'case_id':case_id,'parameters':p,'execution_status':'QUEUED'};records.append(item)
            self._state(key,'RUNNING',records)
            for index,item in enumerate(records):
                if control['cancel'].is_set():status='CANCELLED';break
                if time.monotonic()>=deadline:status='EXECUTION_ERROR';error='Wall deadline reached before next case';break
                if request['source_sha256']!=source_identity():raise ValueError('Source identity changed before case')
                item['execution_status']='RUNNING';self._state(key,'RUNNING',records)
                _local.context={'cancel':control['cancel'],'deadline':deadline,'calls':0}
                try:
                    result=simulate_case(item['parameters'],request['criteria'],folder)
                    if request['source_sha256']!=source_identity():raise ValueError('Source identity changed during case')
                    result={**result,'case_id':item['case_id'],'experiment_id':EXPERIMENT,'controller_id':CONTROLLER,
                            'source_sha256':request['source_sha256'],'parameters':item['parameters'],'criteria':request['criteria'],
                            'simulation_configuration':{'duration_s':3.,'timestep_s':.005,'initial_position_m':0.}}
                    write_once(folder/(item['case_id']+'.json'),result,POLICY['maximum_case_bytes'])
                    item['result_sha256']=digest(result)
                    item.update({k:result[k] for k in ['execution_status','verdict','metrics','checks','failure_reasons','comparison','effective_model_sha256']})
                except Cancelled:
                    item['execution_status']='CANCELLED';status='CANCELLED';break
                except Exception as exc:
                    item.update(execution_status='EXECUTION_ERROR',error='Native execution/verification failed: '+type(exc).__name__)
                    status='PARTIAL';error='A case failed execution; remaining cases were not run. No retry.';break
                finally:_local.context=None
                self._state(key,'RUNNING',records)
        except Exception:
            status='EXECUTION_ERROR';error='Admission/source integrity failed; no further execution'
        finally:
            for item in records:
                if item['execution_status']=='QUEUED':item['execution_status']='CANCELLED' if status=='CANCELLED' else 'NOT_EXECUTED'
            self._state(key,status,records,error)
            with self.guard:self.active.discard(key);self.controls.pop(key,None)
        return {'sweep_id':key,'status':status}
