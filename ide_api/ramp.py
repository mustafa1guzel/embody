"""Bounded, review-only ramp fixture on the existing typed engine/native runner.

Developer-authored reference rover; not live AI or electromechanical simulation.
Flat-ground assembly acceptance is never reused as a ramp verdict.
"""
import copy,hashlib,math,threading
from pathlib import Path
from uuid import uuid4
import mujoco
import numpy as np
from core.simulation import ROOT
from engineering.project import new_project,identity
from engineering.assembly_examples import rover_plan
from engineering.assembly_rover import structural
from engineering.assembly import sources
from engineering.store import Store
from ide_api.engineering import EngineeringService
from physics.contracts import digest
from robustness.contracts import write_once,file_hash
from workspace.data import bounded_read,decode_json
from world.compiler import compile_world,initial_state
from world.simulation import run as run_world

DEFAULT={'angle_deg':5.,'length_m':1.,'width_m':.4,'thickness_m':.04,'friction':.9}
BOUNDS={'angle_deg':(0.,30.),'length_m':(.6,2.),'width_m':(.25,1.),'thickness_m':(.02,.15),'friction':(.7,2.)}
CONTRACT={'id':'RAMP_PROXY_V1','duration_s':1.,'primary_steps':200,'fresh_replay_steps':200,'minimum_progress_m':.005,'minimum_height_gain_m':.0001,'minimum_up_z_dot':math.cos(math.pi/4),'force_tolerance':1e-12,'contacts':'Every wheel must have actual ramp contact; only wheel/ramp and wheel/floor pairs allowed.','meaning':'Separate finite ramp test, not flat-ground acceptance, wheel-slip proof, calibrated tire model, continuous climbing or real hardware safety.'}

def config(value):
 if not isinstance(value,dict) or set(value)!=set(BOUNDS):raise ValueError('Exact bounded ramp parameters required')
 for k,(lo,hi) in BOUNDS.items():
  if type(value[k]) not in (int,float) or not math.isfinite(value[k]) or not lo<=value[k]<=hi:raise ValueError(f'{k} must be finite {lo}–{hi}')
 return {k:float(v) for k,v in value.items()}

def source_identity():return {**sources(),'ide_api/ramp.py':file_hash(Path(__file__))}

def operations(p,roles,c):
 a=math.radians(c['angle_deg']);normal=np.array([-math.sin(a),0,math.cos(a)])
 center=np.array([0,0,c['length_m']/2*math.sin(a)+c['thickness_m']/2*math.cos(a)])
 root=next(o for o in p['world']['objects'] if o['id']==roles['root_body_id'])
 position=center+normal*(c['thickness_m']/2+root['position_m'][2])
 return [{'kind':'create_object','primitive':'box','id':'test_ramp','parent':None},
  {'kind':'rename_object','target':'test_ramp','name':'Inclined test ramp'},
  {'kind':'set_geometry','target':'test_ramp','dimensions_m':[c['length_m'],c['width_m'],c['thickness_m']]},
  {'kind':'move_object','target':'test_ramp','position_m':center.tolist()},
  {'kind':'rotate_object','target':'test_ramp','rotation_rad':[0,-a,0]},
  {'kind':'set_static_surface_friction','target':'test_ramp','friction':[c['friction'],.005,.0001]},
  {'kind':'move_object','target':root['id'],'position_m':position.tolist()},
  {'kind':'rotate_object','target':root['id'],'rotation_rad':[0,-a,0]}]

def geometry_check(project,c):
 m,xml,proof=compile_world(project['world']);d=initial_state(m,project['world']);mujoco.mj_forward(m,d)
 ramp=m.geom('geom_test_ramp');a=math.radians(c['angle_deg']);normal=np.array([-math.sin(a),0,math.cos(a)])
 np.testing.assert_allclose(d.geom_xmat[ramp.id].reshape(3,3)[:,2],normal,atol=1e-12,rtol=0)
 np.testing.assert_allclose(ramp.size,[c['length_m']/2,c['width_m']/2,c['thickness_m']/2],atol=1e-12,rtol=0)
 np.testing.assert_allclose(ramp.friction,[c['friction'],.005,.0001],atol=1e-12,rtol=0)
 assert int(ramp.contype[0])==1 and int(ramp.conaffinity[0])==1 and m.body('test_ramp').mass[0]==0
 return {'status':'REAL_STATIC_NATIVE_COLLIDER','normal_world':normal.tolist(),'tangent_world':[math.cos(a),0,math.sin(a)],'native_half_extents_m':ramp.size.tolist(),'native_friction':ramp.friction.tolist(),'native_model_sha256':proof['contract']['model_sha256'],'contact_mixing':'Default MuJoCo maximum of paired friction values; ramp range >= wheel sliding coefficient 0.7.','compiled':proof}

def measure(result,roles,c):
 """Fresh forward-force/contact checks on saved states; zero integration."""
 m,xml,proof=compile_world(result['world']);assert xml==result['model_xml'] and digest(result['samples'])==result['trajectory_sha256']
 d=initial_state(m,result['world']);objects={o['id']:o for o in result['world']['objects']}
 for o in objects.values():
  if o['actuator']:d.ctrl[m.actuator('motor_'+o['id']).id]=o['actuator']['command']
 wheel_ids={next(s['body_id'] for s in result['project_shapes'] if s['id']==w['part_id']) for w in roles['wheels'].values()}
 wheel_geoms={'geom_'+w for w in wheel_ids};ramp_contacts={w:0 for w in wheel_geoms};floor_contacts=0;unexpected=[];forces=True;up=1.;pairs_saved=[];peak_force=0.;frictions=[]
 chassis=next(s['body_id'] for s in result['project_shapes'] if s['id']==roles['chassis_part_id'])
 for i,s in enumerate(result['samples']):
  d.qpos[:]=s['qpos'];d.qvel[:]=s['qvel'];mujoco.mj_forward(m,d)
  np.testing.assert_allclose(d.qfrc_actuator,s['generalized_force'],rtol=0,atol=1e-12)
  np.testing.assert_allclose(d.actuator_force,s['actuator_force'],rtol=0,atol=1e-12)
  if d.ncon!=s['contacts']:raise ValueError('Actual ramp contact telemetry differs')
  pairs=[]
  for contact in d.contact:
   names={m.geom(int(contact.geom1)).name,m.geom(int(contact.geom2)).name};pairs.append(sorted(names));wheel=names&wheel_geoms
   if len(wheel)==1 and 'geom_test_ramp' in names:
    ramp_contacts[next(iter(wheel))]+=1;frictions.append(float(contact.friction[0]))
   elif len(wheel)==1 and 'geom_floor' in names:floor_contacts+=1
   else:unexpected.append({'sample':i,'pair':sorted(names)})
  pairs_saved.append({'sample':i,'time_s':s['time_s'],'pairs':pairs})
  up=min(up,float(d.geom_xmat[m.geom('geom_'+chassis).id].reshape(3,3)[2,2]))
  for o in objects.values():
   if o['actuator']:
    force=abs(float(d.actuator_force[m.actuator('motor_'+o['id']).id]));peak_force=max(peak_force,force);forces=forces and force<=o['actuator']['limit']+1e-12
 pos=lambda s:np.array(next(p['position_m'] for p in s['poses'] if p['id']==roles['root_body_id']))
 delta=pos(result['samples'][-1])-pos(result['samples'][0]);a=math.radians(c['angle_deg']);progress=float(delta@np.array([math.cos(a),0,math.sin(a)]));height=float(delta[2]);incline=c['angle_deg']>0
 checks={'finite_states':all(np.isfinite(s['qpos']+s['qvel']).all() for s in result['samples']),'all_wheels_contact_ramp':all(v>0 for v in ramp_contacts.values()),'no_unexpected_contacts':not unexpected,'upright':up>=CONTRACT['minimum_up_z_dot'],'bounded_actuator_forces':bool(forces),'signed_progress':progress>=CONTRACT['minimum_progress_m'],'height_gain':not incline or height>=CONTRACT['minimum_height_gain_m'],'fresh_replay':result['independent_verification']['status']=='PASS'}
 outcome='CLIMBED' if all(checks.values()) and incline else 'TRAVERSED_LEVEL_RAMP' if all(checks.values()) else 'COLLIDED' if unexpected else 'UNSTABLE' if not checks['upright'] else 'MOVED_DOWNHILL' if progress<=-.005 else 'INSUFFICIENT_PROGRESS' if not checks['signed_progress'] else 'REQUIREMENT_FAILURE'
 return {'contract':CONTRACT,'status':'PASS' if all(checks.values()) else 'FAIL','outcome':outcome,'signed_progress_m':progress,'height_change_m':height,'world_displacement_m':delta.tolist(),'minimum_up_z_dot':up,'maximum_actuator_force_nm':peak_force,'wheel_ramp_pair_observations':ramp_contacts,'wheel_floor_pair_observations':floor_contacts,'unexpected_contacts':unexpected,'measured_contact_sliding_friction_range':[min(frictions),max(frictions)] if frictions else None,'contact_telemetry':pairs_saved,'checks':checks,'additional_integration_steps':0,'slip_status':'Rolling versus tire slip unresolved; downhill motion alone does not identify slip.'}

class RampService:
 def __init__(self,root=None):self.root=Path(root) if root else ROOT/'artifacts/phase20a_4/20261026/studio_ramps';self.reviews=Store(self.root/'reviews');self.lock=threading.Lock()
 def create(self,parameters):
  c=config(parameters)
  if len(list(self.reviews.root.glob('*.json')))>=64:raise ValueError('Ramp review limit reached; preserve existing records')
  folder=self.root/'projects'/('ramp_'+uuid4().hex)
  empty=new_project();empty['world']['environment']['duration_s']=1.
  construction=EngineeringService(folder/'construction',initial_project=empty);p=construction.current();plan=rover_plan(label='ramp_reference');stages=[]
  for step in plan['steps']:
   for op in step['operations']:
    if op['kind']=='set_actuator':op['actuator']['command']=-.012
   sha=identity(p);p,validation=construction.preview(p,step['operations']);stages.append({'base_sha256':sha,'result_sha256':identity(p),'operations':step['operations'],'validation':validation})
  flat=structural(p,plan['roles']);service=EngineeringService(folder/'review',initial_project=p);head=identity(p)
  q=service.propose(head,p['revision'],operations(p,plan['roles'],c),'Explicit developer-authored rover/ramp fixture; review only, no application.','EXPLICIT_LOCAL_USER_REVIEW')
  geometry=geometry_check(q['proposed_project'],c)
  write_once(folder/'construction.json',{'origin':'DEVELOPER_AUTHORED_REFERENCE_NOT_AI','stages':stages,'flat_structural':flat,'construction_head_unchanged':identity(construction.current())==identity(empty)})
  record={'parameters':c,'folder':str(folder.relative_to(self.root)),'proposal':q,'roles':plan['roles'],'head_sha256':head,'head_revision':p['revision'],'geometry':geometry,'source_sha256':source_identity(),'contract':CONTRACT,'origin':'DEVELOPER_AUTHORED_REFERENCE_NOT_AI','application_allowed':False}
  key=self.reviews.put(record);return self.read(key)
 def read(self,key):
  v=self.reviews.get(key);folder=self.root/v['folder'];service=EngineeringService(folder/'review');q=v['proposal']
  if v['source_sha256']!=source_identity() or v['contract']!=CONTRACT:raise ValueError('Ramp source or verification contract changed; old evidence remains historical')
  if identity(service.current())!=v['head_sha256'] or service.current()['revision']!=v['head_revision']:raise ValueError('Ramp review head changed')
  p,checks=service.preview(service.current(),q['operations'])
  if p!=q['proposed_project'] or json_normal(checks)!=q['validation'] or q['operations']!=json_normal(operations(service.current(),v['roles'],v['parameters'])):raise ValueError('Ramp typed proposal identity mismatch')
  status='NOT_RUN';result=None
  if (folder/'result.json').exists():result=decode_json(bounded_read(folder,'result.json'));status=result['measurements']['status']
  elif (folder/'reserved.json').exists():status='RESERVED_OR_INTERRUPTED'
  return {**v,'id':key,'status':status,'result':result,'simulation':'NOT_RUN' if status=='NOT_RUN' else 'RECORDED' if result else 'UNKNOWN_OUTCOME'}
 def run(self,key):
  v=self.read(key);folder=self.root/v['folder']
  with self.lock:
   write_once(folder/'reserved.json',{'id':key,'contract':CONTRACT,'primary_steps':200,'fresh_replay_steps':200,'retries':0})
  result=run_world(v['proposal']['proposed_project']['world'],folder/'native');result['project_shapes']=v['proposal']['proposed_project']['shape_specs'];measurements=measure(result,v['roles'],v['parameters'])
  if identity(EngineeringService(folder/'review').current())!=v['head_sha256']:raise ValueError('Review head changed during ramp test')
  record={'native':result,'measurements':measurements,'proposal_id':v['proposal']['proposal_id'],'head_unchanged':True,'origin':v['origin'],'paid_requests':0,'VM_launches':0,'application_status':'PROPOSED_NOT_APPLIED'}
  write_once(folder/'result.json',record);return self.read(key)

def json_normal(v):
 import json
 return json.loads(json.dumps(v,allow_nan=False))
