"""Offline idealized equations, never measured/native integration."""
from ide_api import rail_sweeps as rail

def predictions(p,criteria):
 p=rail.parameters(p);m,v,f,g=(p[k] for k in rail.BOUNDS);distance=m*v*v/(2*f);stop=m*v/f
 # Arithmetic Euler/force-clipping idealization of the registered controller only.
 velocity=v;travel=0.;dt=rail.POLICY['timestep_s']
 for _ in range(rail.POLICY['primary_steps_per_case']):
  velocity=max(0.,velocity-min(f/m*dt,velocity));travel+=velocity*dt
 return {'continuous':{'kind':'CONTINUOUS_IDEAL_PREDICTION','stopping_distance_m':distance,'stopping_time_s':stop,'remaining_gap_m':g-distance,'clearance_margin_m':g-distance-criteria['minimumClearance'],'braking_ratio':distance/g},'discrete':{'kind':'DISCRETE_ANALYTICAL_NOT_MUJOCO','predicted_travel_m':travel,'predicted_remaining_gap_m':g-travel,'predicted_final_speed_mps':velocity,'arithmetic_updates':600,'native_steps':0,'assumptions':['Semi-implicit Euler, immediate opposing bounded force, clipped final braking, no contact/delay/damping.','The arithmetic continues through possible overlap; invalid as a contact model.']}}

def residuals(record):
 predicted=predictions(record['parameters'],record['criteria']);measured=record['metrics']['minimum_clearance_m'];ideal=predicted['continuous']['remaining_gap_m'];signed=measured-ideal
 return {'case_id':record['id'],'measured_metric':'minimum_clearance_m','measured_value_m':measured,'analytical_quantity':'continuous_ideal_remaining_gap_m','analytical_value_m':ideal,'signed_residual_m':signed,'absolute_residual_m':abs(signed),'relative_residual':None if abs(ideal)<=1e-12 else signed/abs(ideal),'relative_status':'UNDEFINED_ZERO_PREDICTION' if abs(ideal)<=1e-12 else 'DEFINED','predictions':predicted,'discrete_comparison_applicable':record['controller_id']==rail.CONTROLLER and record['metrics']['wall_contact_samples']==0,'cause':'NOT_ESTABLISHED_BY_RESIDUAL','limitations':['Historical trigger controllers and sampled minima differ from immediate ideal braking.','Continuous stopping time is not the sampled low-speed suffix.','Discretization, timing or contact explanations require supporting force/state evidence, not this residual alone.']}
