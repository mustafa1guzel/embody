"""Adapters over existing verified readers. No imported JSON becomes evidence."""
import copy,hashlib
from ide_api import rail_sweeps as rail
from ide_api.experiment_designer import evidence_summary
from .registry import METRICS

def integrals(samples):
 impulse=work=0.
 for a,b in zip(samples,samples[1:]):
  dt=b['time']-a['time']
  if dt<=0:raise ValueError('Invalid saved timestamp order')
  impulse+=dt*(abs(a['generalized_actuator_force'])+abs(b['generalized_actuator_force']))/2
  work+=dt*(a['generalized_actuator_force']*a['velocity']+b['generalized_actuator_force']*b['velocity'])/2
 return {'absolute_impulse_ns':impulse,'signed_work_j':work}

def native_records(designer,key):
 summary=designer.summary(key);state=designer.rail.read(key);request=state['request'];records=[]
 for row in state['cases']:
  common={'id':row['case_id'],'status':row['execution_status'],'verified':False,'parameters':row['parameters'],'controller_id':request['controller_id'],'source_sha256':request['source_sha256'],'source_current':summary['source_current'],'provenance_kind':'GENUINE_SAVED_NATIVE','compatibility':{'physics':'rail_native_template_v1','source':request['source_sha256'],'controller':request['controller_id'],'criteria':rail.digest(request['criteria']),'simulation':rail.digest({'duration_s':3.,'timestep_s':.005,'initial_position_m':0.})}}
  if row['execution_status']=='MEASURED':
   result=designer.rail.case(key,row['case_id']);s=next(v for v in summary['cases'] if v['case_id']==row['case_id'])
   common.update(verified=True,metrics={**s['metrics'],**integrals(result['samples'])},verdict=s['verdict'],comparison=s['comparison'],criteria=copy.deepcopy(result['criteria']),trajectory_sha256=result['trajectory_sha256'],result_sha256=rail.digest(result),model_sha256=result['effective_model_sha256'],replay=result['replay']['status'],simulation=result['simulation_configuration'],checks=result['checks'])
  records.append(common)
 return records,state['status'],request

def recorded_records():
 from physics.reports import recorded_report
 from workspace.data import default_recording
 recording=default_recording();records=[]
 for scenario in ('A','B','C'):
  for variant in ('original','attempt_1','attempt_2'):
   report=recorded_report(scenario,variant,recording=recording);c=report['physics_contract'];t=recording.trajectory(scenario,variant);samples=t['samples'];criteria={'minimumClearance':c['minimum_clearance_m'],'maximumFinalSpeed':c['final_speed_tolerance_mps'],'maximumSettlingTime':c['deadline_s'],'maximumContactEpisodes':0}
   metrics,selected=rail.measure(samples,criteria);metrics.update(integrals(samples));p={'mass_kg':c['mass_kg'],'speed_mps':c['initial_velocity_mps'],'force_n':c['braking_force_n'],'gap_m':c['initial_clearance_m']}
   gap=metrics['minimum_clearance_m']-(p['gap_m']-p['mass_kg']*p['speed_mps']**2/(2*p['force_n']))
   simulation={'duration_s':c['duration_s'],'timestep_s':c['timestep_s'],'initial_position_m':c['initial_position_m']}
   records.append({'id':rail.digest({'inventory':recording.inventory_sha256,'scenario':scenario,'variant':variant}),'status':'MEASURED','verified':True,'parameters':p,'controller_id':'recorded_'+variant,'source_sha256':rail.digest(dict(c['source_hashes'])),'source_current':False,'provenance_kind':'GENUINE_PINNED_HISTORICAL_RECORDING','compatibility':{'physics':'pinned_rail_recording_v1','source':rail.digest(dict(c['source_hashes'])),'controller':c['controller_sha256'],'criteria':rail.digest(criteria),'simulation':rail.digest(simulation)},'metrics':metrics,'verdict':report['observed_physics']['safety_status'],'comparison':{'measured_minus_ideal_clearance_m':gap},'criteria':criteria,'trajectory_sha256':report['provenance']['telemetry_sha256'],'result_sha256':report['report_sha256'],'model_sha256':c['model_sha256'],'replay':report['recorded_independent_verification'],'simulation':simulation,'checks':report['observed_physics']['checks'],'recorded_selection':{'scenario':scenario,'variant':variant}})
 return records,'HISTORICAL_RECORDED',None

def load(designer,kind,key):
 if kind=='native':records,status,request=native_records(designer,key)
 elif kind=='recorded' and key=='portable_rail_study':records,status,request=recorded_records()
 else:raise ValueError('Only registered local evidence readers permitted')
 facts=[]
 for r in records:
  if r['verified']:
   for metric,value in {**r['metrics'],**r['comparison']}.items():
    unit=METRICS.get(metric,{}).get('unit','m/s' if metric.endswith('_mps') else 'm' if metric.endswith('_m') else 's' if metric.endswith('_s') else 'N' if metric.endswith('_n') else 'count')
    facts.append({'id':r['id']+':'+metric,'case_id':r['id'],'metric':metric,'value':value,'unit':unit})
 counts={k:0 for k in ('planned','measured','physical_pass','physical_fail','execution_error','cancelled','unexecuted','running')};counts['planned']=len(request['cases']) if request else len(records)
 for r in records:
  if r['verified']:counts['measured']+=1;counts['physical_pass' if r['verdict']=='PASS' else 'physical_fail']+=1
  elif r['status']=='EXECUTION_ERROR':counts['execution_error']+=1
  elif r['status']=='CANCELLED':counts['cancelled']+=1
  elif r['status']=='RUNNING':counts['running']+=1
  else:counts['unexecuted']+=1
 counts['unexecuted']+=max(0,counts['planned']-len(records))
 out={'kind':kind,'id':key,'status':status,'records':records,'facts':facts,'counts':counts,'request':request,'limitations':['Verified existing saved measurements only; no new native execution.','Source drift is retained. Imported or external references do not grant execution authority.','Fresh replay shares MuJoCo; finite sample coverage is not hardware safety.']}
 out['summary_sha256']=rail.digest(out);return out
