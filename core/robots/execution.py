"""Trusted vector MuJoCo stepping and fresh isolated candidate consistency checks."""
import hashlib
import math
from pathlib import Path
from uuid import uuid4
import mujoco
import numpy as np
from core.simulation import write_json,sha256
from physics.planar import assess,forward
from physics.vector_profiler import profile


def sample(model,data,c):
    ee=data.site_xpos[model.site(c.end_effector_site).id].tolist()
    poses=[]
    for i in range(model.ngeom):
        quat=np.empty(4);mujoco.mju_mat2Quat(quat,data.geom_xmat[i])
        poses.append({'position':data.geom_xpos[i].tolist(),'quaternion_wxyz':quat.tolist()})
    contacts=[{'geom_ids':[int(v.geom1),int(v.geom2)],'distance_m':float(v.dist)} for v in data.contact[:data.ncon]]
    return {'time':float(data.time),'qpos_rad':data.qpos.tolist(),'qvel_rad_s':data.qvel.tolist(),
            'command':data.ctrl.tolist(),'scalar_torque_nm':data.actuator_force.tolist(),
            'generalized_torque_nm':data.qfrc_actuator.tolist(),'end_effector_m':ee,
            'target_error_m':float(np.linalg.norm(np.array(ee)-c.target_m)),
            'joint_limit_margin_rad':[min(float(data.qpos[i])-j.position_range[0],j.position_range[1]-float(data.qpos[i])) for i,j in enumerate(c.joints)],
            'contacts':contacts,'geom_poses':poses}


def acceptance(samples,c):
    fields=('qpos_rad','qvel_rad_s','generalized_torque_nm','end_effector_m')
    finite=all(all(math.isfinite(x) for x in s[k]) and math.isfinite(s['time']) and math.isfinite(s['target_error_m']) for s in samples for k in fields)
    terminal=samples[-1];window=[s for s in samples if s['time']>=c.duration_s-c.settling_window_s-1e-10]
    checks={'target_error':terminal['target_error_m']<=c.target_tolerance_m,
            'final_velocity':max(map(abs,terminal['qvel_rad_s']))<c.final_velocity_limit,
            'settling_window':all(s['target_error_m']<=c.target_tolerance_m and max(map(abs,s['qvel_rad_s']))<c.final_velocity_limit for s in window),
            'maximum_velocity':max(abs(v) for s in samples for v in s['qvel_rad_s'])<=c.maximum_velocity,
            'joint_limits':all(v>=-c.joint_limit_tolerance for s in samples for v in s['joint_limit_margin_rad']),
            'torque_limits':all(j.effort_range[0]-1e-10<=v<=j.effort_range[1]+1e-10 for s in samples for j,v in zip(c.joints,s['generalized_torque_nm'])),
            'no_contact':not c.no_contact or not any(s['contacts'] for s in samples),
            'complete_horizon':len(samples)==round(c.duration_s/c.timestep_s)+1 and abs(terminal['time']-c.duration_s)<1e-10,
            'finite':finite}
    return {'status':'PASS' if all(checks.values()) else 'FAIL','checks':checks,
            'violations':[k for k,v in checks.items() if not v],'final_error_m':terminal['target_error_m'],
            'final_joint_velocity_rad_s':terminal['qvel_rad_s'],
            'maximum_abs_torque_nm':[max(abs(s['generalized_torque_nm'][j]) for s in samples) for j in range(len(c.joints))],
            'minimum_joint_limit_margin_rad':[min(s['joint_limit_margin_rad'][j] for s in samples) for j in range(len(c.joints))],
            'contact_samples':sum(bool(s['contacts']) for s in samples),'completion_time_s':terminal['time']}


def first_run(family,scenario,controller,source_hash):
    model,xml,c,body,world,lengths=family.compile(scenario,source_hash)
    data=mujoco.MjData(model);data.qpos[:]=c.q0;data.qvel[:]=c.v0;samples=[]
    for step in range(round(c.duration_s/c.timestep_s)+1):
        mujoco.mj_forward(model,data);controller(model,data)
        if not np.isfinite(data.ctrl).all():raise ValueError('Nonfinite requested torque')
        mujoco.mj_forward(model,data);samples.append({'step':step,**sample(model,data,c)})
        if step<round(c.duration_s/c.timestep_s):mujoco.mj_step(model,data)
    if any(w.number for w in data.warning):raise ValueError('MuJoCo warning prevents acceptance')
    return {'model':model,'xml':xml,'contract':c,'bodybase':body,'worldbase':world,'lengths':lengths,'samples':samples}


def independent(run,source,backend,first_exchanges=None,family=None,trusted_controller=None):
    """Separate fresh host loop + fresh VM; compare states/actions, not command replay."""
    from contextlib import nullcontext
    c=run['contract'];model=mujoco.MjModel.from_xml_string(run['xml']);data=mujoco.MjData(model)
    data.qpos[:]=c.q0;data.qvel[:]=c.v0
    context=backend.controller(source,run['xml']) if backend is not None else nullcontext((trusted_controller or family.baseline(),None,None))
    trace=[];state_diff=action_diff=trajectory_diff=fk_diff=0.0
    with context as (controller,exchanges,handshake):
        for k,expected in enumerate(run['samples']):
            mujoco.mj_forward(model,data)
            if first_exchanges is not None:
                state=np.empty(mujoco.mj_stateSize(model,mujoco.mjtState.mjSTATE_INTEGRATION))
                mujoco.mj_getState(model,data,state,mujoco.mjtState.mjSTATE_INTEGRATION)
                state_diff=max(state_diff,float(np.max(np.abs(state-np.array(first_exchanges[k]['state'])))))
            controller(model,data);mujoco.mj_forward(model,data)
            # Extract numeric state independently; compare FK to the compiled site.
            ee=data.site_xpos[model.site('end_effector').id]
            fk_diff=max(fk_diff,float(np.max(np.abs(np.array(forward(run['lengths'],data.qpos.tolist()))-ee[:2]))))
            row={'time':float(data.time),'qpos_rad':data.qpos.tolist(),'qvel_rad_s':data.qvel.tolist(),
                 'command':data.ctrl.tolist(),'generalized_torque_nm':data.qfrc_actuator.tolist(),
                 'end_effector_m':ee.tolist(),'target_error_m':float(np.linalg.norm(ee-c.target_m)),
                 'joint_limit_margin_rad':[min(float(data.qpos[i])-j.position_range[0],j.position_range[1]-float(data.qpos[i])) for i,j in enumerate(c.joints)],
                 'contacts':[{'geom_ids':[int(t.geom1),int(t.geom2)],'distance_m':float(t.dist)} for t in data.contact[:data.ncon]]}
            for key in ('qpos_rad','qvel_rad_s','generalized_torque_nm','end_effector_m'):
                trajectory_diff=max(trajectory_diff,float(np.max(np.abs(np.array(row[key])-expected[key]))))
            action_diff=max(action_diff,float(np.max(np.abs(data.ctrl-np.array(expected['command'])))))
            if [v['geom_ids'] for v in row['contacts']] != [v['geom_ids'] for v in expected['contacts']]:
                raise ValueError('Independent contacts differ')
            trace.append(row)
            if k<len(run['samples'])-1:mujoco.mj_step(model,data)
    finite=all(math.isfinite(s['target_error_m']) for s in trace)
    verified=finite and max(state_diff,action_diff,trajectory_diff,fk_diff)<=1e-10 and not any(w.number for w in data.warning)
    return {'verification_execution':'PASS' if verified else 'FAIL',
            'method':'Fresh isolated candidate and fresh trusted host stepping' if backend else 'Fresh trusted developer baseline stepping',
            'controller_consistency_checked':True,'max_precontrol_state_difference':state_diff,
            'max_action_difference':action_diff,'max_trajectory_difference':trajectory_diff,
            'max_independent_fk_difference_m':fk_diff,'handshake':handshake,
            'safety_acceptance':acceptance(trace,c),'trace':trace}


def save(family,scenario,run,check,directory,origin,exchanges=None):
    directory.mkdir(parents=True,exist_ok=False);c=run['contract'];samples=run['samples'];guard=assess(c,run['lengths'])
    measured=acceptance(samples,c)
    if measured!=check['safety_acceptance']:raise ValueError('Independent acceptance disagreement')
    metadata={'schema_version':1,'robot_family':'arm','scenario_id':scenario,'controller_origin':origin,
              'controller_sha256':c.controller_sha256,'effective_mjcf_sha256':c.model_sha256,
              'contract_sha256':c.identity,'mujoco_version':mujoco.__version__,
              'bodybase':run['bodybase'],'worldbase':run['worldbase'],'physics_contract':c.to_dict()}
    write_json(directory/'telemetry.json',{'metadata':metadata,'samples':samples})
    (directory/'effective_model.xml').write_text(run['xml']);write_json(directory/'independent.json',check)
    write_json(directory/'profile.json',profile(samples,c))
    diagnostics={'physical_configuration':metadata,'analytical_guard':guard,'measured_acceptance':measured,
                 'initial':samples[0],'final':{k:v for k,v in samples[-1].items() if k!='geom_poses'},
                 'profiler':profile(samples,c),'independent_verification':{k:v for k,v in check.items() if k!='trace'}}
    # Compact evidence, no prewritten corrective algorithm.
    diagnostics['initial']={k:v for k,v in diagnostics['initial'].items() if k!='geom_poses'}
    write_json(directory/'diagnostics.json',diagnostics)
    if exchanges is not None:write_json(directory/'worker_exchanges.json',exchanges)
    summary={'simulation_run_id':directory.name,'scenario_id':scenario,'robot_family':'arm',
             'controller_sha256':c.controller_sha256,'model_sha256':c.model_sha256,'contract_sha256':c.identity,
             'simulation_execution':'PASS','physical_safety_status':measured['status'] if check['verification_execution']=='PASS' else 'NOT_EVALUATED',
             'independent_verification':check['verification_execution'],'safety_acceptance':measured,
             'analytical_guard':guard,'profiler':profile(samples,c),
             'artifact_references':{p.name:str(p) for p in directory.iterdir() if p.is_file()}}
    write_json(directory/'summary.json',summary)
    return summary,{'directory':directory,'inventory':{p.name:sha256(p) for p in directory.iterdir() if p.is_file()}}


def execute_trusted(family,scenario,output):
    _,_,c,_,_,lengths=family.compile(scenario);guard=assess(c,lengths)
    if guard['status']=='PROVEN_INFEASIBLE':
        return {'scenario_id':scenario,'simulation_execution':'NOT_RUN','physical_safety_status':'NOT_APPLICABLE',
                'task_rejection_verified':True,'independent_verification':'NOT_APPLICABLE','analytical_guard':guard},None
    run=first_run(family,scenario,family.baseline(),c.controller_sha256)
    check=independent(run,None,None,family=family)
    return save(family,scenario,run,check,Path(output)/('simulation_'+uuid4().hex),'developer_definition_ai_assisted')


def execute_candidate(family,candidate,scenarios,backend,output,names=None):
    from core.agent.vm_backend import AppleVMBackend,IsolationBlocked
    from core.robots.qualification import require_qualification
    if type(backend) is not AppleVMBackend:raise IsolationBlocked('Arm candidates require AppleVMBackend')
    backend.preflight();require_qualification(backend,family)
    source=candidate['source_path'].read_text()
    if hashlib.sha256(source.encode()).hexdigest()!=candidate['proposed_sha256']:raise ValueError('Candidate source changed')
    results={};records={}
    for scenario in names or scenarios:
        _,xml,c,_,_,lengths=family.compile(scenario,candidate['proposed_sha256']);guard=assess(c,lengths)
        if guard['status']=='PROVEN_INFEASIBLE':
            results[scenario]={'scenario_id':scenario,'simulation_execution':'NOT_RUN','physical_safety_status':'NOT_APPLICABLE',
                'task_rejection_verified':True,'independent_verification':'NOT_APPLICABLE','analytical_guard':guard};continue
        with backend.controller(source,xml) as (controller,exchanges,handshake):
            run=first_run(family,scenario,controller,candidate['proposed_sha256'])
        check=independent(run,source,backend,exchanges)
        directory=Path(output)/('simulation_'+uuid4().hex)
        # Source authorship belongs to reviewed provenance, not the executor:
        # the same isolated path also supports explicitly submitted manual code.
        result,record=save(family,scenario,run,check,directory,'isolated_untrusted_candidate',
                           {'candidate_sha256':candidate['proposed_sha256'],'handshake':handshake,'exchanges':exchanges})
        results[scenario]=result;records[directory.name]=record
    return results,records
