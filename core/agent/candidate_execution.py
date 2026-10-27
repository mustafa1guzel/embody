"""Trusted host-authoritative candidate runs and fresh closed-loop verification."""
import hashlib
import math
from pathlib import Path
from uuid import uuid4

import mujoco
import numpy as np

from core.diagnostics import evaluate_safety, physical_parameters
from core.simulation import DEFAULT_MODEL_PATH, compile_context_model, run_simulation, write_json

def verify_fresh(run, backend, source, exchanges):
    """Fresh VM reruns the actual candidate in a fresh direct MuJoCo loop.

    Checks pre-control state AND returned actions, geometry, contacts, and force.
    Recorded commands alone cannot make an inconsistent controller pass.
    """
    xml=run['effective_model_xml']
    if hashlib.sha256(xml.encode()).hexdigest()!=run['metadata']['effective_mjcf_sha256']:
        raise ValueError('Effective model snapshot hash mismatch')
    model=mujoco.MjModel.from_xml_string(xml)
    data=mujoco.MjData(model)
    world=run['worldbase'];body=run['bodybase']
    data.qpos[0]=world.initial_position_x_m;data.qvel[0]=world.initial_velocity_ms
    wall,bumper=model.geom('wall').id,model.geom('front_bumper').id
    trace=[];checks=[];maximum=0.0;action_difference=0.0;state_difference=0.0
    with backend.controller(source,xml) as (controller,second,handshake):
        for step,first in enumerate(run['telemetry']):
            mujoco.mj_forward(model,data)
            state=np.empty(mujoco.mj_stateSize(model,mujoco.mjtState.mjSTATE_INTEGRATION))
            mujoco.mj_getState(model,data,state,mujoco.mjtState.mjSTATE_INTEGRATION)
            state_difference=max(state_difference,float(np.max(np.abs(state-np.array(exchanges[step]['state'])))))
            controller(model,data)
            action_difference=max(action_difference,max(abs(float(a)-b) for a,b in zip(data.ctrl,exchanges[step]['ctrl'])))
            mujoco.mj_forward(model,data)
            contacts=[{'geom_ids':[int(c.geom1),int(c.geom2)],'distance_m':float(c.dist)} for c in data.contact[:data.ncon]]
            clearance=float(mujoco.mj_geomDistance(model,data,bumper,wall,100,None))
            row={'step':step,'time':float(data.time),'position':float(data.qpos[0]),'velocity':float(data.qvel[0]),
                 'control':float(data.ctrl[0]),'generalized_actuator_force':float(data.qfrc_actuator[0]),
                 'wall_clearance':clearance,'contacts':contacts}
            trace.append(row)
            maximum=max(maximum,max(abs(row[k]-first[k]) for k in ('time','position','velocity','control','generalized_actuator_force','wall_clearance')))
            checks.append([c['geom_ids'] for c in contacts]==[c['geom_ids'] for c in first['contacts']])
            if step<len(run['telemetry'])-1: mujoco.mj_step(model,data)
    params=physical_parameters(model)
    compiled=(params['mass_kg']==body.mass_kg and params['max_braking_force_n']==body.max_force_n
              and model.opt.timestep==world.simulation_timestep_s
              and float(model.body('obstacle').pos[0])==world.wall_position_x_m
              and np.array_equal(model.geom('wall').size,world.wall_half_size_m)
              and np.array_equal(model.geom('front_bumper').size,body.collision_geometry.bumper_half_size_m)
              and np.array_equal(model.geom('carriage_box').size,body.collision_geometry.carriage_half_size_m)
              and np.array_equal(model.jnt_axis[0],[1,0,0])
              and np.array_equal(model.actuator_forcerange[0],[-body.max_force_n,body.max_force_n])
              and np.array_equal(model.actuator_ctrlrange[0],[-body.max_force_n,body.max_force_n])
              and np.array_equal(model.opt.gravity,world.gravity_ms2))
    acceptance=evaluate_safety(trace,world,wall)
    complete=len(trace)==round(world.simulation_duration_s/world.simulation_timestep_s)+1
    finite=all(math.isfinite(s[k]) for s in trace for k in ('time','position','velocity','control','generalized_actuator_force','wall_clearance'))
    force_limits=all(abs(s['generalized_actuator_force'])<=body.max_force_n+1e-12 for s in trace)
    warnings=not run['metadata']['warnings'] and not any(w.number for w in data.warning)
    verified=(compiled and complete and finite and force_limits and warnings and all(checks) and maximum<=1e-12
              and action_difference<=1e-12 and state_difference<=1e-12)
    return {'verification_execution':'PASS' if verified else 'FAIL',
            'method':'Fresh isolated candidate VM; fresh trusted host MjModel/MjData; direct mj_step and mj_geomDistance',
            'controller_consistency_checked':True,'fresh_worker_handshake':handshake,
            'max_telemetry_difference':maximum,'max_action_difference':action_difference,
            'max_precontrol_state_difference':state_difference,'contact_ids_match':all(checks),
            'effective_context_matches':compiled,'finite_measurements':finite,'complete_horizon':complete,
            'measured_actuator_force_within_limits':force_limits,'no_engine_warnings':warnings,
            'safety_acceptance':acceptance,'trace':trace}

def execute_candidate(candidate, scenarios, backend, output, names=None):
    source=candidate['source_path'].read_text()
    if hashlib.sha256(source.encode()).hexdigest()!=candidate['proposed_sha256']:
        raise ValueError('Candidate changed before isolated execution')
    results={};records={}
    for name in (names or scenarios):
        body,world=scenarios[name]
        _,xml=compile_context_model(DEFAULT_MODEL_PATH,body,world)
        run_id='simulation_'+uuid4().hex
        directory=Path(output)/run_id
        with backend.controller(source,xml) as (controller,exchanges,ready):
            run=run_simulation(bodybase=body,worldbase=world,controller=controller,save_render=False,artifacts_dir=directory)
        run['metadata']['controller']={'name':'isolated_candidate.faulty_braking_controller',
            'source_path':'candidate/controller.py','source_sha256':candidate['proposed_sha256'],
            'candidate_id':candidate['candidate_id'],'execution_boundary':'Apple ARM64 Linux VM'}
        write_json(directory/'manifest.json',run['metadata'])
        write_json(directory/'telemetry.json',{'metadata':run['metadata'],'samples':run['telemetry']})
        write_json(directory/'worker_exchanges.json',{'candidate_sha256':candidate['proposed_sha256'],
                                                    'handshake':ready,'exchanges':exchanges})
        independent=verify_fresh(run,backend,source,exchanges)
        write_json(directory/'independent_safety_trace.json',independent)
        acceptance=independent['safety_acceptance']
        samples=run['telemetry']
        onset=next((s for s in samples if s['velocity']>0 and s['generalized_actuator_force']<0),None)
        contact=next((s for s in samples if s['wall_collision']),None)
        summary={'simulation_run_id':run_id,'scenario_id':name,'controller_variant':candidate['candidate_id'],
            'controller_sha256':candidate['proposed_sha256'],'simulation_execution':'PASS',
            'physical_safety_status':acceptance['status'] if independent['verification_execution']=='PASS' else 'NOT_EVALUATED',
            'braking_onset':onset,'first_wall_contact':contact,
            'contact_velocity_ms':contact['velocity'] if contact else None,
            'minimum_clearance_m':min(s['wall_clearance'] for s in samples),
            'final_speed_ms':abs(samples[-1]['velocity']),
            'applied_force_n':{'minimum':min(s['generalized_actuator_force'] for s in samples),
                               'maximum':max(s['generalized_actuator_force'] for s in samples)},
            'independent_verification':independent['verification_execution'],
            'controller_consistency_checked':True,'safety_acceptance':acceptance,
            'artifact_references':{p.name:str(p) for p in directory.iterdir() if p.is_file()}}
        # Diagnostics contain observations and host acceptance; no baseline-specific narrative.
        diagnostics={'physical_context':run['metadata']['context'],'robot_physical_parameters':physical_parameters(run['model']),
            'controller':run['metadata']['controller'],'analytical_prediction':{
                'initial_stopping_distance_m':body.stopping_distance_m(world.initial_velocity_ms)},
            'prediction_at_measured_braking_onset':({'stopping_distance_m':body.stopping_distance_m(onset['velocity'])} if onset else None),
            'actual_available_braking_distance_m':onset['wall_clearance'] if onset else None,
            'braking_initiation':onset,'first_wall_contact':contact,'minimum_observed_clearance_m':summary['minimum_clearance_m'],
            'final_state':samples[-1],'safety_acceptance':acceptance,
            'independent_safety_verification':{k:v for k,v in independent.items() if k!='trace'},
            'effective_mjcf_sha256':run['metadata']['effective_mjcf_sha256']}
        write_json(directory/'diagnostics.json',diagnostics)
        write_json(directory/'tool_summary.json',summary)
        results[name]=summary
        records[run_id]={'directory':directory,'inventory':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.iterdir() if p.is_file()}}
    return results,records
