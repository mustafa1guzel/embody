"""Independent arithmetic on actual stored samples; never native stepping."""
import math
from ide_api import rail_sweeps as rail

DEFINITION='RAIL_SAMPLED_MEASUREMENTS_V1'

def metrics(samples,criteria,simulation):
 if not isinstance(samples,list) or len(samples)!=601:raise ValueError('Complete601sample saved trajectory required')
 required=('time','position','velocity','wall_clearance','generalized_actuator_force')
 for s in samples:
  if any(type(s.get(k)) not in (int,float) or not math.isfinite(s[k]) for k in required) or type(s.get('wall_collision')) is not bool:raise ValueError('Invalid finite saved sample/contact flag')
 dt=simulation['timestep_s'];duration=simulation['duration_s']
 if not math.isclose(dt,.005,abs_tol=1e-15) or not math.isclose(duration,3.,abs_tol=1e-12):raise ValueError('Unsupported measurement horizon/grid')
 if any(abs(s['time']-i*dt)>1e-9 for i,s in enumerate(samples)):raise ValueError('Timestamp grid mismatch')
 speed=criteria['maximumFinalSpeed'];settled_index=None
 for i in range(len(samples)-1,-1,-1):
  if abs(samples[i]['velocity'])>=speed:break
  settled_index=i
 first=next((s['time'] for s in samples if abs(s['velocity'])<speed),None)
 impulse=work=0.
 for a,b in zip(samples,samples[1:]):
  elapsed=b['time']-a['time'];impulse+=elapsed*(abs(a['generalized_actuator_force'])+abs(b['generalized_actuator_force']))/2
  work+=elapsed*(a['generalized_actuator_force']*a['velocity']+b['generalized_actuator_force']*b['velocity'])/2
 result={'minimum_clearance_m':min(s['wall_clearance'] for s in samples),'final_speed_mps':abs(samples[-1]['velocity']),'maximum_speed_mps':max(abs(s['velocity']) for s in samples),'wall_contact_samples':sum(s['wall_collision'] for s in samples),'wall_contact_episodes':sum(s['wall_collision'] and (i==0 or not samples[i-1]['wall_collision']) for i,s in enumerate(samples)),'maximum_actuator_force_n':max(abs(s['generalized_actuator_force']) for s in samples),'sample_count':len(samples),'duration_s':samples[-1]['time'],'sampled_settling_time_s':None if settled_index is None else samples[settled_index]['time'],'sampled_settling_travel_m':None if settled_index is None else samples[settled_index]['position']-samples[0]['position'],'absolute_impulse_ns':impulse,'signed_work_j':work}
 return {'definition':DEFINITION,'metrics':result,'first_speed_threshold_entry_s':first,'sustained_sampled_suffix_start_s':result['sampled_settling_time_s'],'native_integration_steps':0,'limitations':['First entry, final sampled suffix and continuous ideal stop are distinct.','Force integral is impulse magnitude(N s), signed Fv integral is mechanical work(J); not battery energy.']}

def compare(record,samples):
 result=metrics(samples,record['criteria'],record['simulation']);mismatches=[]
 for name,actual in result['metrics'].items():
  expected=record['metrics'].get(name)
  equal=actual is None and expected is None or type(actual) in (int,float) and type(expected) in (int,float) and math.isfinite(expected) and math.isclose(actual,expected,rel_tol=1e-12,abs_tol=1e-12)
  if not equal:mismatches.append(name)
 if mismatches:raise ValueError('Saved metric readback differs: '+', '.join(mismatches))
 return {**result,'status':'READBACK_MATCH','case_id':record['id'],'stored_result_sha256':record['result_sha256'],'trajectory_sha256':record['trajectory_sha256']}

def native_replay(result):
 if rail.digest(result['samples'])!=result['trajectory_sha256'] or rail.digest(result['replay']['samples'])!=result['replay']['trajectory_sha256']:raise ValueError('Primary/replay trajectory hash mismatch')
 primary=result['samples'];replay=result['replay']['samples']
 if type(result['replay'].get('primary_steps')) is not int or type(result['replay'].get('fresh_steps')) is not int or result['replay']['primary_steps']!=600 or result['replay']['fresh_steps']!=600:raise ValueError('Exact600primary/600fresh replay steps required')
 if len(primary)!=601 or len(replay)!=601 or result['replay']['status']!='PASS':raise ValueError('Required fresh replay missing')
 for a,b in zip(primary,replay):
  for field in rail.FIELDS:
   if type(a.get(field)) not in (int,float) or type(b.get(field)) not in (int,float) or not math.isfinite(a[field]) or not math.isfinite(b[field]) or abs(a[field]-b[field])>1e-9:raise ValueError('Saved replay state/action differs')
  if a['contacts']!=b['contacts'] or a['wall_collision']!=b['wall_collision']:raise ValueError('Saved replay contacts differ')
 return {'status':'SAVED_FRESH_REPLAY_MATCH','primary_steps_recorded':result['replay']['primary_steps'],'fresh_steps_recorded':result['replay']['fresh_steps'],'new_steps':0}
