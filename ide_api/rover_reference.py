"""Registered numeric rover reference, reusing the typed rover/ramp construction.

Developer-authored controller; no source/XML input. Native execution is implemented
but UNVERIFIED until a separately authorized primary + fresh replay completes.
"""
from __future__ import annotations
import copy, hashlib, math, threading, time
from pathlib import Path
import mujoco
import numpy as np
from core.simulation import ROOT
from engineering.actions import execute_copy
from engineering.project import new_project, validate as validate_project
from engineering.assembly_examples import rover_plan
from engineering.assembly_rover import structural
from ide_api import rail_sweeps as rail
from ide_api.ramp import operations as ramp_operations, geometry_check
from world.compiler import compile_world, initial_state
from world.simulation import poses

EXPERIMENT='rover_ramp_target_v1'
MODEL='bounded_rover_ramp_v1'
CONTROLLER='developer_rover_target_pd_v1'
CONFIRMATION='RUN TRUSTED ROVER QUALIFICATION'
BOUNDS={'chassis_mass_kg':(.1,1.2),'length_m':(.14,.30),'width_m':(.10,.20),
        'wheel_radius_m':(.025,.06),'angle_deg':(0.,15.),'friction':(.7,2.),
        'torque_nm':(.001,.02),'target_m':(.02,.12)}
UNITS=dict(zip(BOUNDS,['kg','m','m','m','degrees','coefficient','N*m','m']))
DEFAULTS=dict(zip(BOUNDS,[.15,.18,.12,.03,5.,.9,.012,.04]))
DEFAULT_CRITERIA={'minimumProgress':.005,'maximumTargetError':.035,'maximumFinalSpeed':.10,'minimumUpDot':math.cos(math.pi/4)}
POLICY={**rail.POLICY,'maximum_cases':4,'duration_s':1.,'primary_steps_per_case':200,
        'replay_steps_per_case':200,'samples_per_trajectory':201,'maximum_total_steps':1600,
        'maximum_case_bytes':8_000_000}
LIMITATIONS=['Nine ShapeSpecs and explicit small joint/mount bodies from the existing typed rover plan.',
 'One-second rigid proxies, limited wheel hinges; no steering, suspension, terrain navigation, sensors or autonomy.',
 'Uniform solid proxy inertia and MuJoCo contact friction; no tire/slip/material or electrical powertrain proof.',
 'Feedback controller uses native pose/velocity; no arbitrary edited controller source.',
 'IMPLEMENTED_AWAITING_NATIVE_VERIFICATION; no measured performance is claimed.']
_local=threading.local()
canonical=rail.canonical;digest=rail.digest
FIELDS=('time_s','signed_progress_m','linear_speed_mps','tangent_speed_mps','up_dot')

def parameters(value):
    rail.exact(value,BOUNDS)
    result={k:rail.number(value[k],*bounds) for k,bounds in BOUNDS.items()}
    if any(abs(n*1e6-round(n*1e6))>1e-7 for n in result.values()):raise ValueError('Use at most six decimals')
    if 2*result['wheel_radius_m']>.64*result['length_m']-.002+1e-12:raise ValueError('Wheel diameter must leave 2 mm clearance within the 0.64 x chassis-length wheelbase')
    return result

def criteria(value):
    rail.exact(value,DEFAULT_CRITERIA)
    bounds={'minimumProgress':(.005,.12),'maximumTargetError':(.001,.035),
            'maximumFinalSpeed':(.001,.10),'minimumUpDot':(DEFAULT_CRITERIA['minimumUpDot'],1.)}
    return {k:rail.number(value[k],*b) for k,b in bounds.items()}

def source_manifest():
    # Explicit trusted closure. Untrusted data never chooses module names or paths.
    from engineering.assembly import sources
    result=sources()
    for directory in ('core','hardware','devices','physics','robot'):
        for p in (ROOT/directory).rglob('*.py'):result[str(p.relative_to(ROOT))]=hashlib.sha256(p.read_bytes()).hexdigest()
    for p in [*(ROOT/'configs').glob('*.json'),*(ROOT/'robot').glob('*.xml'),ROOT/'workspace/data.py']:
        result[str(p.relative_to(ROOT))]=hashlib.sha256(p.read_bytes()).hexdigest()
    names=['ide_api/rover_reference.py','ide_api/native_models.py','ide_api/model_evidence.py',
           'ide_api/rail_sweeps.py','ide_api/server.py','ide_api/ramp.py','engineering/assembly_examples.py',
           'world/compiler.py','world/schema.py','world/simulation.py','requirements.txt']
    for name in names:result[name]=hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
    return dict(sorted(result.items()))

def source_identity():
    return digest({'files':source_manifest(),'engine':mujoco.__version__,'numpy':np.__version__,
                   'policy':POLICY,'controller':CONTROLLER,'criteria':DEFAULT_CRITERIA})

def validate(value):
    rail.exact(value,['experiment_id','controller_id','source_sha256','cases','criteria','nonce','confirmation'])
    if len(canonical(value))>POLICY['maximum_request_bytes']:raise ValueError('Request size limit')
    if value['experiment_id']!=EXPERIMENT or value['controller_id']!=CONTROLLER:raise ValueError('Registered rover/controller identity required')
    if value['source_sha256']!=source_identity():raise ValueError('Rover source identity changed')
    if value['confirmation']!=CONFIRMATION:raise ValueError('Explicit rover confirmation required')
    rail.identifier(value['nonce'])
    if not isinstance(value['cases'],list) or not 1<=len(value['cases'])<=POLICY['maximum_cases']:raise ValueError('One to four rover cases required')
    cases=[parameters(p) for p in value['cases']]
    if len({digest(p) for p in cases})!=len(cases):raise ValueError('Duplicate cases rejected')
    return {**copy.deepcopy(value),'cases':cases,'criteria':criteria(value['criteria'])}

def construction(value):
    p=parameters(value);project=new_project();project['world']['environment']['duration_s']=1.
    plan=rover_plan(length=p['length_m'],width=p['width_m'],wheel_diameter=2*p['wheel_radius_m'],label='native')
    for step in plan['steps']:
        ops=copy.deepcopy(step['operations'])
        for op in ops:
            if op['kind']=='create_parametric_part' and op['part']['family']=='chassis':op['part']['mass_kg']=p['chassis_mass_kg']
            if op['kind']=='set_actuator':op['actuator'].update(limit=p['torque_nm'],command=-p['torque_nm'])
        project=validate_project(execute_copy(project,ops))
    flat=structural(project,plan['roles']) # existing unchanged topology/mass/force envelope
    ramp={'angle_deg':p['angle_deg'],'length_m':1.,'width_m':.4,'thickness_m':.04,'friction':p['friction']}
    project=validate_project(execute_copy(project,ramp_operations(project,plan['roles'],ramp)))
    proof=geometry_check(project,ramp)
    return project,plan['roles'],{'flat_structure':flat,'ramp_geometry':proof,
                               'origin':'DEVELOPER_AUTHORED_TYPED_REFERENCE_NOT_AI','simulation':'NOT_RUN'}

def compiled(value):
    project,roles,proof=construction(value);model,xml,contract=compile_world(project['world'])
    return project,roles,proof,model,xml,contract

def controller_commands(error_m,speed_mps,radius_m,limit_nm,axis_projections):
    """PD target force (3 N/m, 0.8 N s/m), shared by two rear wheels.

    Sign comes from dot(axis cross ramp-normal, uphill tangent), not a preset
    wheel label. Commands remain clipped; orientation metadata is not slip proof.
    """
    if not all(type(x) in (int,float) and math.isfinite(x) for x in [error_m,speed_mps,radius_m,limit_nm,*axis_projections]):raise ValueError('Finite controller inputs required')
    if not .025<=radius_m<=.06 or not .001<=limit_nm<=.02 or len(axis_projections)!=2 or any(abs(x)>1+1e-10 for x in axis_projections):raise ValueError('Unsupported radius/authority/axis')
    force=3.*error_m-.8*speed_mps
    return [max(-limit_nm,min(limit_nm,force*radius_m/2*x)) for x in axis_projections]

def reference_controller(model,data,p,roles,origin,tangent,normal):
    context=getattr(_local,'context',None)
    if context:
        if context['cancel'].is_set():raise rail.Cancelled('Explicit cancellation')
        if time.monotonic()>=context['deadline']:raise rail.Deadline('Rover wall deadline reached')
        context['calls']+=1
        if context['calls']>402:raise rail.Deadline('Rover controller sample budget reached')
    root=model.body(roles['root_body_id']).id
    progress=float((data.xpos[root]-origin)@tangent)
    velocity=np.zeros(6);mujoco.mj_objectVelocity(model,data,mujoco.mjtObj.mjOBJ_BODY,root,velocity,0)
    rear=[roles['wheels'][k]['joint_body_id'] for k in ('rear_left','rear_right')]
    projections=[float(np.cross(data.xaxis[model.joint('joint_'+name).id],normal)@tangent) for name in rear]
    commands=controller_commands(p['target_m']-progress,float(velocity[3:]@tangent),p['wheel_radius_m'],p['torque_nm'],projections)
    for name,command in zip(rear,commands):data.ctrl[model.actuator('motor_'+name).id]=command

def snapshot(model,data,p,roles,origin,tangent):
    root=model.body(roles['root_body_id']).id;velocity=np.zeros(6)
    mujoco.mj_objectVelocity(model,data,mujoco.mjtObj.mjOBJ_BODY,root,velocity,0)
    contacts=[{'geom_ids':[int(c.geom1),int(c.geom2)]} for c in data.contact]
    chassis=next(s for s in roles['shape_specs'] if s['id']==roles['chassis_part_id']) if 'shape_specs' in roles else None
    chassis_id=model.body(chassis['body_id'] if chassis else roles['chassis_part_id']+'_body').id
    return {'time_s':float(data.time),'qpos':data.qpos.tolist(),'qvel':data.qvel.tolist(),
            'control':data.ctrl.tolist(),'generalized_force':data.qfrc_actuator.tolist(),'actuator_force':data.actuator_force.tolist(),
            'poses':poses(model,data,roles['world']), 'contacts':contacts,
            'root_position_m':data.xpos[root].tolist(),'root_quaternion_wxyz':data.xquat[root].tolist(),
            'linear_velocity_mps':velocity[3:].tolist(),'angular_velocity_radps':velocity[:3].tolist(),
            'linear_speed_mps':float(np.linalg.norm(velocity[3:])),'tangent_speed_mps':float(velocity[3:]@tangent),
            'signed_progress_m':float((data.xpos[root]-origin)@tangent),'up_dot':float(data.xmat[chassis_id].reshape(3,3)[2,2]),
            'wheel_angles_rad':{k:float(data.qpos[model.joint('joint_'+v['joint_body_id']).qposadr[0]]) for k,v in roles['wheels'].items()}}

def frame(p):
    a=math.radians(p['angle_deg']);return np.array([math.cos(a),0,math.sin(a)]),np.array([-math.sin(a),0,math.cos(a)])

def measure(samples,p,c,model,roles):
    if len(samples)!=201:raise ValueError('Complete 201 sample rover trajectory required')
    # All finite numeric state is checked; contacts/pose consistency is independently forwarded below.
    for i,s in enumerate(samples):
        if any(type(s.get(k)) not in (int,float) or not math.isfinite(s[k]) for k in FIELDS) or abs(s['time_s']-i*.005)>1e-9:raise ValueError('Invalid finite rover sample/time grid')
        for field in ['qpos','qvel','control','generalized_force','actuator_force','root_position_m','root_quaternion_wxyz','linear_velocity_mps','angular_velocity_radps']:
            if not isinstance(s[field],list) or any(type(v) not in (int,float) or not math.isfinite(v) for v in s[field]):raise ValueError('Invalid numeric state')
        for field,size in {'qpos':model.nq,'qvel':model.nv,'control':model.nu,'generalized_force':model.nv,'actuator_force':model.nu,'root_position_m':3,'root_quaternion_wxyz':4,'linear_velocity_mps':3,'angular_velocity_radps':3}.items():
            if len(s[field])!=size:raise ValueError('Incomplete native state vector')
        for pose in s['poses']:
            rail.exact(pose,['id','position_m','quaternion_wxyz'])
            if any(type(v) not in (int,float) or not math.isfinite(v) for v in pose['position_m']+pose['quaternion_wxyz']):raise ValueError('Invalid pose numeric fields')
        for contact in s['contacts']:
            rail.exact(contact,['geom_ids']);ids=contact['geom_ids']
            if not isinstance(ids,list) or len(ids)!=2 or len(set(ids))!=2 or any(type(v) is not int or not 0<=v<model.ngeom for v in ids):raise ValueError('Invalid contact identity')
    wheel_ids={model.geom('geom_'+v['part_id']+'_body').id:k for k,v in roles['wheels'].items()}
    surfaces={model.geom('geom_test_ramp').id,model.geom('geom_floor').id}
    counts={k:0 for k in roles['wheels']};unexpected=0
    for s in samples:
        for contact in s['contacts']:
            ids=set(contact['geom_ids']);w=ids&set(wheel_ids)
            if len(w)==1 and len(ids&surfaces)==1:counts[wheel_ids[next(iter(w))]]+=1
            else:unexpected+=1
    progress=samples[-1]['signed_progress_m'];speed=samples[-1]['linear_speed_mps'];error=abs(p['target_m']-progress)
    maximum=max(abs(v) for s in samples for v in s['actuator_force']);min_up=min(s['up_dot'] for s in samples)
    joint_ok=all(-math.pi-1e-6<=v<=math.pi+1e-6 for s in samples for v in s['wheel_angles_rad'].values())
    m={'signed_progress_m':progress,'target_error_m':error,'final_speed_mps':speed,'minimum_up_dot':min_up,
       'maximum_actuator_force_nm':maximum,'wheel_surface_observations':counts,'unexpected_contact_pairs':unexpected,
       'sample_count':len(samples),'duration_s':samples[-1]['time_s'],'joint_ranges_valid':joint_ok}
    checks={'minimum_progress':progress>=c['minimumProgress'],'target_error':error<=c['maximumTargetError'],
            'final_speed':speed<c['maximumFinalSpeed'],'upright':min_up>=c['minimumUpDot'],
            'all_wheels_surface_contact':all(counts.values()),'no_prohibited_contacts':unexpected==0,
            'bounded_actuator_forces':maximum<=p['torque_nm']+1e-12,'joint_ranges':joint_ok,'finite_complete_trajectory':True}
    return m,checks

def forward_audit(samples,p,roles,model,world):
    """Independent saved-state force, pose, contact and kinematic readback; no stepping."""
    data=initial_state(model,world);mujoco.mj_forward(model,data);root=model.body(roles['root_body_id']).id;origin=data.xpos[root].copy();tangent,normal=frame(p)
    local_roles={**roles,'world':world}
    for saved in samples:
        rail.exact(saved,['time_s','qpos','qvel','control','generalized_force','actuator_force','poses','contacts','root_position_m','root_quaternion_wxyz','linear_velocity_mps','angular_velocity_radps','linear_speed_mps','tangent_speed_mps','signed_progress_m','up_dot','wheel_angles_rad'])
        data.qpos[:]=saved['qpos'];data.qvel[:]=saved['qvel'];data.ctrl[:]=saved['control'];data.time=saved['time_s'];mujoco.mj_forward(model,data)
        actual=snapshot(model,data,p,local_roles,origin,tangent)
        # Kinematics/force reconstruction and controller arguments are independent of recorded claims.
        for field in ['qpos','qvel','generalized_force','actuator_force','root_position_m','root_quaternion_wxyz','linear_velocity_mps','angular_velocity_radps',*FIELDS]:
            np.testing.assert_allclose(actual[field],saved[field],rtol=0,atol=1e-10)
        if actual['poses']!=saved['poses'] or actual['contacts']!=saved['contacts'] or actual['wheel_angles_rad']!=saved['wheel_angles_rad']:raise ValueError('Saved native geometry/contact/joint mismatch')
        reference_controller(model,data,p,roles,origin,tangent,normal)
        np.testing.assert_allclose(data.ctrl,saved['control'],atol=1e-12,rtol=0)
        for aid in range(model.nu):
            jid=int(model.actuator_trnid[aid,0]);dof=int(model.jnt_dofadr[jid])
            if abs(data.qfrc_actuator[dof]-data.actuator_force[aid])>1e-12:raise ValueError('Generalized force transmission mismatch')
    return {'status':'FORWARD_STATE_FORCE_CONTACT_READBACK_PASS','new_steps':0}

def simulate_case(p,c,folder):
    """Only the existing serial job service invokes this after exact admission."""
    project,roles,proof,model,xml,contract=compiled(p);world=project['world'];tangent,normal=frame(p)
    def rollout(m,phase):
        d=initial_state(m,world);mujoco.mj_forward(m,d);origin=d.xpos[m.body(roles['root_body_id']).id].copy();out=[]
        completed=0
        try:
            for i in range(201):
                mujoco.mj_forward(m,d);reference_controller(m,d,p,roles,origin,tangent,normal);mujoco.mj_forward(m,d)
                out.append(snapshot(m,d,p,{**roles,'world':world},origin,tangent))
                if i<200:mujoco.mj_step(m,d);completed+=1
            if any(w.number for w in d.warning):raise ValueError('Native numerical warning')
        except Exception as exc:
            rail.write_once(folder/(digest(p)+'_'+phase+'_incomplete.json'),{'status':'INCOMPLETE_NOT_PHYSICAL_VERDICT','phase':phase,'actual_completed_steps':completed,'samples':out,'error_type':type(exc).__name__,'parameters':p,'model_sha256':hashlib.sha256(xml.encode()).hexdigest()},POLICY['maximum_case_bytes'])
            raise
        rail.write_once(folder/(digest(p)+'_'+phase+'_samples.json'),{'status':'ACTUAL_NATIVE_SAMPLES_NOT_YET_VERIFIED','phase':phase,'actual_completed_steps':completed,'samples':out,'model_sha256':hashlib.sha256(xml.encode()).hexdigest()},POLICY['maximum_case_bytes'])
        return out
    primary=rollout(model,'primary');fresh=mujoco.MjModel.from_xml_string(xml);replay=rollout(fresh,'fresh')
    if digest(primary)!=digest(replay):raise ValueError('Fresh native trajectory differs')
    # Audit does not call the controller cancellation counter after the 402 sampled controls.
    context=getattr(_local,'context',None);_local.context=None
    try:audit=forward_audit(primary,p,roles,fresh,world)
    finally:_local.context=context
    m,checks=measure(primary,p,c,model,roles);checks['fresh_replay']=True
    return {'execution_status':'MEASURED','verdict':'PASS' if all(checks.values()) else 'FAIL','metrics':m,'checks':checks,
            'failure_reasons':[k for k,v in checks.items() if not v],'comparison':{'meaning':'Target-relative rover requirements; no rail braking equation'},
            'samples':primary,'trajectory_sha256':digest(primary),'model_xml':xml,'effective_model_sha256':hashlib.sha256(xml.encode()).hexdigest(),
            'world':world,'roles':roles,'compiled_contract':contract,'construction_proof':proof,'independent_readback':audit,
            'replay':{'status':'PASS','primary_steps':200,'fresh_steps':200,'samples':replay,'trajectory_sha256':digest(replay)},
            'controller_contract':{'id':CONTROLLER,'runtime_controls':'Registered target PD feedback; compiler constant command is only the initial authoring/probe value','kp_n_per_m':3.,'kd_ns_per_m':.8},
            'engine_version':mujoco.__version__,'units':UNITS,'limitations':LIMITATIONS,'model_id':MODEL,'measurement_definition':'ROVER_TARGET_SAMPLED_V1'}
