"""Real bounded native dynamics; rendering consumes measured poses only."""
from pathlib import Path
import hashlib
import mujoco
import numpy as np
from .schema import validate,identity
from .compiler import compile_world,initial_state
from physics.contracts import digest
from robustness.contracts import write_once


def poses(model,data,w):
    result=[]
    for o in w['objects']:
        gid=model.geom('geom_'+o['id']).id;q=np.empty(4);mujoco.mju_mat2Quat(q,data.geom_xmat[gid])
        result.append({'id':o['id'],'position_m':data.geom_xpos[gid].tolist(),'quaternion_wxyz':q.tolist()})
    return result


def run(world,output=None):
    w=validate(world);model,xml,compiled=compile_world(w);data=initial_state(model,w);samples=[]
    for o in w['objects']:
        if o['actuator']:data.ctrl[model.actuator('motor_'+o['id']).id]=o['actuator']['command']
    steps=round(w['environment']['duration_s']/model.opt.timestep)
    for index in range(steps+1):
        mujoco.mj_forward(model,data)
        if not np.isfinite(np.r_[data.qpos,data.qvel,data.qfrc_actuator]).all() or np.max(np.abs(data.qvel),initial=0)>1e4:raise ValueError('Native state exceeded supported finite numerical envelope')
        samples.append({'time_s':float(data.time),'qpos':data.qpos.tolist(),'qvel':data.qvel.tolist(),'generalized_force':data.qfrc_actuator.tolist(),'actuator_force':data.actuator_force.tolist(),'sensor_data':data.sensordata.tolist(),'contacts':int(data.ncon),'poses':poses(model,data,w)})
        if index<steps:mujoco.mj_step(model,data)
    result={'schema_version':1,'world':w,'world_sha256':identity(w),'model_xml':xml,**compiled,'samples':samples,'trajectory_sha256':digest(samples),'execution':'REAL_MUJOCO_TRUSTED_COMPILER_CONSTANT_CONTROLS','origin':'DEVELOPER_AUTHORED_LOCAL_SIMULATION; not model output','model_requests':0,'vm_launches':0}
    result['independent_verification']=verify(result)
    if output:
        p=Path(output);p.mkdir(parents=True,exist_ok=False);write_once(p/'result.json',result);(p/'model.xml').write_text(xml);result['native_render']=render_native(result,p/'native.png');write_once(p/'render.json',result['native_render'])
    return result


def verify(result):
    w=result['world'];model,xml,compiled=compile_world(w)
    if xml!=result['model_xml'] or compiled['contract_sha256']!=result['contract_sha256'] or digest(result['samples'])!=result['trajectory_sha256']:raise ValueError('World evidence identity mismatch')
    data=initial_state(model,w)
    for o in w['objects']:
        if o['actuator']:data.ctrl[model.actuator('motor_'+o['id']).id]=o['actuator']['command']
    for i,s in enumerate(result['samples']):
        mujoco.mj_forward(model,data)
        for key,actual in [('qpos',data.qpos),('qvel',data.qvel),('generalized_force',data.qfrc_actuator),('actuator_force',data.actuator_force),('sensor_data',data.sensordata)]:np.testing.assert_allclose(actual,s[key],rtol=0,atol=1e-12)
        if abs(data.time-s['time_s'])>1e-12 or data.ncon!=s['contacts'] or digest(poses(model,data,w))!=digest(s['poses']):raise ValueError('Independent native state/geometry/contact mismatch')
        if i<len(result['samples'])-1:mujoco.mj_step(model,data)
    return {'status':'PASS','fresh_native_integration_steps':len(result['samples'])-1,'tolerance':1e-12,'scope':'Fresh rollout and native compiled/force/geometry checks; shared MuJoCo and compiler, not a second physics engine or real hardware.'}


def render_native(result,path):
    try:
        from PIL import Image
        model=mujoco.MjModel.from_xml_string(result['model_xml']);data=mujoco.MjData(model);data.qpos[:]=result['samples'][-1]['qpos'];mujoco.mj_forward(model,data)
        cam=mujoco.MjvCamera();cam.lookat[:]=[.25,0,.25];cam.distance=2.5;cam.azimuth=120;cam.elevation=-25
        with mujoco.Renderer(model,480,640) as renderer:renderer.update_scene(data,camera=cam);Image.fromarray(renderer.render()).save(path)
        return {'status':'PASS','path':str(path),'sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest(),'source':'Native MuJoCo render, final measured state'}
    except (RuntimeError,ImportError,ValueError) as exc:return {'status':'UNVERIFIED','reason':str(exc)[:300]}
