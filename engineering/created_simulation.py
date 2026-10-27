"""Trusted control on the actual generated world, never a hidden finished plant."""
from pathlib import Path
from dataclasses import asdict
from xml.etree import ElementTree as ET
import hashlib,math
import mujoco
import numpy as np
from physics.contracts import digest
from robustness.contracts import write_once,file_hash
from world.compiler import compile_world,initial_state
from world.simulation import poses
from devices.controller import ReferenceLogic,Command
from devices.simulation import RaySensor,object_position,evaluate
from .project import validate,identity
from .device_bindings import check_binding

ROOT=Path(__file__).resolve().parents[1]
def compile_created(project):
    p=validate(project);spec,electrical=check_binding(p);roles=p['creation']['world_roles'];base,xml,compiled=compile_world(p['world'])
    root=ET.fromstring(xml);actor=root.find(f".//body[@name='{roles['target']}']");actor.set('mocap','true')
    # The generated target is explicitly an imposed kinematic trajectory; all
    # geometry, local transforms, mass, inertia and actuator limits stay authored.
    for role in ('sensor','board_mount'):
        root.find(f".//geom[@name='geom_{roles[role]}']").set('group','1')
    xml=ET.tostring(root,encoding='unicode');model=mujoco.MjModel.from_xml_string(xml);data=initial_state(model,p['world']);mujoco.mj_forward(model,data)
    if model.nv!=1 or model.nu!=1 or model.nmocap!=1 or not np.array_equal(model.opt.gravity,[0,0,-9.81]):raise ValueError('Generated barrier supports one scalar actuator and frozen gravity only')
    beam=model.body(roles['beam']);pivot=model.body(roles['pivot']);joint=model.joint('joint_'+roles['pivot']);motor=model.actuator('motor_'+roles['pivot'])
    np.testing.assert_allclose(beam.mass,[spec.mechanical.mass_kg],rtol=0,atol=1e-12)
    np.testing.assert_allclose(model.actuator_forcerange[motor.id],[-spec.mechanical.torque_limit_nm,spec.mechanical.torque_limit_nm],rtol=0,atol=1e-12)
    np.testing.assert_allclose(model.jnt_range[joint.id],[0,1.65],rtol=0,atol=1e-12)
    contract={'schema_version':1,'protocol':'day16_generated_barrier_v1','project_sha256':identity(p),'world_sha256':digest(p['world']),'circuit_sha256':digest(p['circuit']),'binding_sha256':digest(p['creation']),'device_spec_sha256':spec.identity,'controller_sha256':p['controller_sha256'],'model_sha256':hashlib.sha256(xml.encode()).hexdigest(),'duration_s':5.,'timestep_s':.005,'requirements':asdict(spec.requirements),'kinematic_target':'Trajectory from generated target initial XYZ and dimensions; fixed reviewed near/approach/departure settings.','electronic_mass':'Excluded; mounting metadata distinguishes visual-only placement and ray pose coupling.'}
    return p,spec,model,xml,{'contract':contract,'contract_sha256':digest(contract),'compiled':{'model_sha256':contract['model_sha256'],'mass_kg':float(beam.mass[0]),'length_m':spec.mechanical.length_m,'pivot_mass_kg':float(pivot.mass[0]),'inertia_kg_m2':beam.inertia.tolist(),'hinge_range_rad':joint.range.tolist(),'force_probes':compiled['force_probes'],'base_world_compilation':compiled},'electrical':electrical}

def rollout(p,spec,model):
    data=initial_state(model,p['world']);logic=ReferenceLogic(spec.logic);sensor=RaySensor(spec.sensor);command=Command('IDLE',0.,'Initial rest');next_control=0.;samples=[];roles=p['creation']['world_roles'];objects={o['id']:o for o in p['world']['objects']};target=objects[roles['target']];mocap_id=int(model.body_mocapid[model.body(roles['target']).id])
    jid=model.joint('joint_'+roles['pivot']).id;qadr=int(model.jnt_qposadr[jid]);vadr=int(model.jnt_dofadr[jid]);aid=model.actuator('motor_'+roles['pivot']).id
    for i in range(round(5/model.opt.timestep)+1):
        t=i*model.opt.timestep;data.mocap_pos[mocap_id]=[object_position(t,spec.environment),target['position_m'][1],target['position_m'][2]];mujoco.mj_forward(model,data)
        reading=sensor.update(model,data,t)
        if t+1e-10>=next_control:command=logic.update(t,reading,float(data.qpos[qadr]));next_control+=spec.logic.update_s
        request=(command.target_rad-data.qpos[qadr])*.45-data.qvel[vadr]*.11;data.ctrl[aid]=float(np.clip(request,-spec.mechanical.torque_limit_nm,spec.mechanical.torque_limit_nm));mujoco.mj_forward(model,data)
        if not np.isfinite(np.r_[data.qpos,data.qvel,data.qfrc_actuator]).all() or np.max(np.abs(data.qvel),initial=0)>1e4:raise ValueError('Native generated dynamics exceeded finite numerical envelope')
        samples.append({'time_s':float(t),'q_rad':float(data.qpos[qadr]),'qvel_rad_s':float(data.qvel[vadr]),'qpos':data.qpos.tolist(),'qvel':data.qvel.tolist(),'requested_torque_nm':float(request),'generalized_torque_nm':float(data.qfrc_actuator[vadr]),'actuator_force':data.actuator_force.tolist(),'contacts':int(data.ncon),'distance_m':reading.distance_m if reading else None,'state':command.state,'target_rad':command.target_rad,'reason':command.reason,'object_position_m':data.mocap_pos[mocap_id].tolist(),'poses':poses(model,data,p['world'])})
        if i<round(5/model.opt.timestep):mujoco.mj_step(model,data)
    return samples,sensor.history

def verify(result):
    p,spec,model,xml,checks=compile_created(result['project'])
    if xml!=result['model_xml'] or checks['contract_sha256']!=result['contract_sha256'] or digest(result['samples'])!=result['trajectory_sha256']:raise ValueError('Generated result identity mismatch')
    samples,readings=rollout(p,spec,model)
    for actual,saved in zip(samples,result['samples'],strict=True):
        for key in ('time_s','q_rad','qvel_rad_s','requested_torque_nm','generalized_torque_nm','qpos','qvel','actuator_force','object_position_m'):np.testing.assert_allclose(actual[key],saved[key],rtol=0,atol=1e-12)
        for key in ('state','target_rad','distance_m','contacts','poses'):
            if digest(actual[key])!=digest(saved[key]):raise ValueError('Independent generated state/geometry/sensor mismatch')
    if readings!=result['sensor_readings'] or evaluate(samples,spec)!=result['acceptance']:raise ValueError('Independent sensor/acceptance mismatch')
    return {'status':'PASS','fresh_native_integration_steps':len(samples)-1,'tolerance':1e-12,'scope':'Fresh closed-loop sensor/control/native integration and world compilation; shares MuJoCo and trusted controller, no second-engine or real hardware proof.'}

def render(result,path):
    from PIL import Image
    p,spec,model,_,_=compile_created(result['project']);data=initial_state(model,p['world']);sample=max(result['samples'],key=lambda s:s['q_rad']);data.qpos[:]=sample['qpos'];data.mocap_pos[0]=sample['object_position_m'];mujoco.mj_forward(model,data)
    camera=mujoco.MjvCamera();camera.lookat[:]=[.25,-.03,.15];camera.distance=1.3;camera.azimuth=125;camera.elevation=-25
    with mujoco.Renderer(model,480,640) as renderer:renderer.update_scene(data,camera=camera);Image.fromarray(renderer.render()).save(path)
    return {'status':'PASS','path':str(path),'sha256':file_hash(path),'source':'Native generated MuJoCo model at measured maximum opening'}

def run(project,output,render_image=True):
    out=Path(output);out.mkdir(parents=True,exist_ok=False);p,spec,model,xml,checks=compile_created(project);samples,readings=rollout(p,spec,model)
    result={'schema_version':1,'project':p,'base_project_sha256':identity(p),'world':p['world'],'generated_world_binding':True,'device_spec':spec.to_dict(),'device_spec_sha256':spec.identity,'assembly':p['circuit'],'assembly_sha256':digest(p['circuit']),'execution':'COMPLETED','origin':'DETERMINISTIC_TRUSTED_GENERATED_WORLD; not live model output','samples':samples,'sensor_readings':readings,'acceptance':evaluate(samples,spec),'trajectory_sha256':digest(samples),'model_xml':xml,**checks,'model_requests':0,'vm_launches':0,'source_sha256':{str(f.relative_to(ROOT)):file_hash(f) for f in [Path(__file__),ROOT/'world/compiler.py',ROOT/'devices/controller.py',ROOT/'devices/simulation.py',ROOT/'engineering/device_bindings.py',ROOT/'engineering/generated_contract.py']}}
    result['status']=result['acceptance']['status'];result['independent_verification']=verify(result)
    if render_image:
        try:result['native_render']=render(result,out/'native.png')
        except (RuntimeError,ImportError,ValueError) as exc:result['native_render']={'status':'UNVERIFIED','reason':str(exc)[:300]}
    write_once(out/'result.json',result);(out/'model.xml').write_text(xml);return result
