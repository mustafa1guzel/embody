"""Metadata is not an executable allowlist. No dynamic imports or dispatch."""
from ide_api import rail_sweeps as rail
from .contracts import PARAMS

METRICS={'minimum_clearance_m':{'unit':'m','direction':'max','meaning':'Minimum sampled wall surface separation'},'final_speed_mps':{'unit':'m/s','direction':'min','meaning':'Absolute terminal sampled speed'},'sampled_settling_time_s':{'unit':'s','direction':'min','meaning':'Start of final sampled low-speed suffix'},'maximum_actuator_force_n':{'unit':'N','direction':'min','meaning':'Maximum absolute generalized actuator force'},'absolute_impulse_ns':{'unit':'N s','direction':'min','meaning':'Trapezoidal integral of absolute sampled force, not energy'},'signed_work_j':{'unit':'J','direction':'none','meaning':'Trapezoidal integral F times v, not electrical consumption'}}

def descriptors(ctx):
 c=ctx['catalog']
 rail_desc={'id':c['experiment_id'],'version':1,'name':'Rail braking reference','domain':'Rigid single-axis translation','parameters':{k:{'unit':c['units'][k],'bounds':c['bounds'][k]} for k in PARAMS},'controllers':[c['controller_id']],'analytical_models':['ideal_constant_braking_v1'],'metrics':METRICS,'criteria':c['defaults'],'execution':'EXISTING_EXPLICIT_TRUSTED_SWEEP_ONLY','source_sha256':c['source_sha256'],'limits':c['policy'],'limitations':c['limitations']}
 # Only actual public RampService parameters; no invented rover mass/torque sweep.
 from ide_api.ramp import BOUNDS,CONTRACT
 rover={'id':'rover_ramp_reference_descriptor_v1','version':1,'name':'Developer rover / ramp reference metadata','domain':'Rigid wheeled proxy on inclined surface','parameters':{k:{'unit':'degrees' if k=='angle_deg' else 'coefficient' if k=='friction' else 'm','bounds':list(v)} for k,v in BOUNDS.items()},'controllers':[],'analytical_models':[],'metrics':{'signed_progress_m':{'unit':'m','direction':'max','meaning':'Displacement projected on ramp tangent'}},'criteria':CONTRACT,'execution':'UNAVAILABLE_IN_RESEARCH','source_sha256':None,'limits':{},'limitations':['Existing RampService builds developer-authored typed geometry and native tests through a separate review workflow.','No public pinned ramp evidence reader or reviewed research execution descriptor.','Analytical or historical analysis only; no fresh construction or dynamics from Research.','No calibrated tire, slip, motor powertrain or flight model.']}
 return [rail_desc,rover]

def controllers(ctx):
 return [{'id':ctx['catalog']['controller_id'],'version':1,'name':'Immediate velocity-opposing brake','definition':'F = clip(-m v / dt, -Fmax, Fmax)','observations':['velocity'],'interface':'Bounded direct generalized rail force','source_sha256':ctx['catalog']['source_sha256'],'execution':'REGISTERED_TRUSTED_REFERENCE','limitations':['Developer authored, not a historical GPT repair.']},
 *[{'id':name,'version':1,'name':title,'definition':law,'observations':obs,'interface':'Mathematical metadata only','source_sha256':None,'execution':'OFFLINE_DEFINITION_NOT_REGISTERED','limitations':['Needs source/force/contact/trust review and separate native authorization.']} for name,title,law,obs in [
 ('candidate_velocity_damping','Proportional damping','F = clip(-k v, -Fmax, Fmax)',['velocity']),
 ('candidate_distance_aware','Distance-aware braking','Brake opposite v when v squared over twice maximum deceleration reaches available clearance',['velocity','clearance']),
 ('candidate_fixed_distance','Fixed-distance trigger','Brake opposite v when clearance is below a fixed threshold',['velocity','clearance'])]]]

def candidate_force(kind,velocity,mass,force,gap,k=2.,threshold=.4):
 """Offline scalar mathematics, never registered as controller code."""
 for v in [velocity,mass,force,gap,k,threshold]:rail.number(v,-100,100)
 if mass<=0 or force<=0 or k<0 or threshold<0:raise ValueError('Positive physical authority/mass required')
 active=kind=='candidate_velocity_damping' or kind=='candidate_distance_aware' and mass*velocity**2/(2*force)>=gap or kind=='candidate_fixed_distance' and gap<=threshold
 if kind not in ('candidate_velocity_damping','candidate_distance_aware','candidate_fixed_distance'):raise ValueError('Unknown offline definition')
 return max(-force,min(force,-k*velocity if kind=='candidate_velocity_damping' else -force if velocity>0 else force if velocity<0 else 0)) if active else 0.
