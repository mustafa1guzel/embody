"""Real MuJoCo sensor→logic→bounded actuator integration for one reference device."""
from dataclasses import asdict
from pathlib import Path
import hashlib
import math
import mujoco
import numpy as np
from physics.contracts import digest
from hardware.assemblies import validate, identity
from hardware.validation import inspect
from hardware.library import CATALOG
from robustness.contracts import write_once
from .contracts import DeviceSpec
from .controller import Reading, ReferenceLogic, Command

ROOT=Path(__file__).resolve().parents[1]


def compile_model(spec):
    m=spec.mechanical
    xml=f'''<mujoco model="sensor_barrier"><compiler angle="radian"/><option timestep="{m.timestep_s}" gravity="0 0 -9.81" integrator="Euler"/>
      <visual><global offwidth="640" offheight="480"/></visual>
      <worldbody><light pos="0 -1 2"/><camera name="evidence" pos="1 -1 0.8" xyaxes="0.707 0.707 0 -0.408 0.408 0.816"/>
        <geom name="floor" type="plane" size="2 2 .05" rgba=".18 .22 .25 1"/>
        <geom name="base" type="box" pos="0 0 .08" size=".025 .025 .08" rgba=".2 .3 .4 1"/>
        <body name="barrier" pos="0 0 .18"><joint name="hinge" type="hinge" axis="0 -1 0" range="0 1.65" damping="{m.damping_nm_s_rad}"/>
          <geom name="beam" type="box" pos="{m.length_m/2} 0 0" size="{m.length_m/2} .01 .008" mass="{m.mass_kg}" rgba=".9 .6 .2 1"/>
        </body>
        <body name="object" mocap="true" pos=".8 -.12 .08"><geom name="detected_object" type="box" size=".04 .045 .06" rgba=".2 .7 .7 1"/></body>
        <geom name="sensor_marker" type="box" pos="0 -.12 .08" size=".012 .025 .012" contype="0" conaffinity="0" group="1" rgba=".25 .4 .8 1"/>
      </worldbody><actuator><motor name="ideal_servo" joint="hinge" gear="1" ctrllimited="true" ctrlrange="{-m.torque_limit_nm} {m.torque_limit_nm}" forcelimited="true" forcerange="{-m.torque_limit_nm} {m.torque_limit_nm}"/></actuator></mujoco>'''
    model=mujoco.MjModel.from_xml_string(xml);data=mujoco.MjData(model);mujoco.mj_forward(model,data)
    expected=np.array([m.mass_kg*(.02**2+.016**2)/12,m.mass_kg*(m.length_m**2+.016**2)/12,m.mass_kg*(m.length_m**2+.02**2)/12])
    # MuJoCo may permute principal axes; check the full sorted inertia spectrum.
    np.testing.assert_allclose(np.sort(model.body('barrier').inertia),np.sort(expected),rtol=1e-12,atol=1e-15)
    np.testing.assert_allclose(model.body('barrier').mass,[m.mass_kg],rtol=0,atol=1e-14)
    np.testing.assert_allclose(model.jnt_range[0],m.joint_range_rad,rtol=0,atol=1e-14)
    probes=[]
    for value in (-100.,0.,100.):
        data.ctrl[0]=value;mujoco.mj_forward(model,data)
        force=float(np.clip(value,-m.torque_limit_nm,m.torque_limit_nm))
        np.testing.assert_allclose([data.actuator_force[0],data.qfrc_actuator[0]],[force,force],rtol=0,atol=1e-14)
        probes.append({'requested_nm':value,'scalar_force_nm':float(data.actuator_force[0]),'generalized_torque_nm':float(data.qfrc_actuator[0])})
    return model,xml,{'mass_kg':float(model.body('barrier').mass[0]),'inertia_kg_m2':model.body('barrier').inertia.tolist(),
        'generalized_inertia_initial_kg_m2':float(data.M[0]),'hinge_range_rad':model.jnt_range[0].tolist(),
        'gravity_m_s2':model.opt.gravity.tolist(),'damping_nm_s_rad':model.dof_damping.tolist(),'force_probes':probes,'model_sha256':hashlib.sha256(xml.encode()).hexdigest()}


def bindings(a, electrical):
    """Require the actual reference signal paths, directions and component identities."""
    components={c['id']:c for c in a['components']}
    for key,part in [('board','esp32_devkitc_v4_wroom32'),('sensor','hcsr04_sen15569'),('servo','towerpro_sg90_digital')]:
        if key not in components or components[key]['part']!=part:raise ValueError('Supported device component binding missing: '+key)
    if components['board']['roles'].get('IO18')!='output' or components['board']['roles'].get('IO19')!='input' or components['board']['roles'].get('IO23')!='pwm':raise ValueError('Device GPIO roles do not match contract')
    nets=electrical['netlist'];membership={tuple(e):n for n,ends in nets.items() for e in ends}
    same=lambda x,y:membership.get(x) is not None and membership.get(x)==membership.get(y)
    if not same(('board','IO18'),('sensor','TRIG')) or not same(('board','IO23'),('servo','SIGNAL')):raise ValueError('Signal mapping not connected')
    echo_net=membership.get(('sensor','ECHO'));input_net=membership.get(('board','IO19'))
    if not any(d['input_net']==echo_net and d['output_net']==input_net for d in electrical['calculations']):raise ValueError('Supported Echo divider topology required')
    return [
        {'source':'MuJoCo geom state + contract sensor pose','destination':'sensor.ECHO virtual distance','unit':'m','interval_s':.07,'abstraction':'single ideal geometric ray with bounded range/latency'},
        {'source':'sensor.ECHO via explicit resistor divider → board.IO19','destination':'ReferenceLogic.Reading','unit':'m','abstraction':'decoded Echo duration represented directly as metres; no pulse/MCU emulation'},
        {'source':'ReferenceLogic.Command → board.IO23 → servo.SIGNAL','destination':'ideal_servo target','unit':'rad','interval_s':.02,'abstraction':'position request; PWM waveform not modeled'},
        {'source':'ideal bounded PD torque','destination':'MuJoCo hinge','unit':'N*m','interval_s':.002},
    ]


def analytical(spec):
    m=spec.mechanical;r=spec.requirements
    # From rest, before any target speed peak q<=q_open: gravity and viscous damping
    # oppose opening in [0,q_open]. Therefore q(T)<=tau*T²/(2I).
    inertia=m.mass_kg*(m.length_m*m.length_m/3+.016**2/12)
    required=2*inertia*r.open_angle_rad/r.opening_deadline_s**2
    return {'status':'UNKNOWN',
        'ideal_rigid_stop_deadline_bound_fails':m.torque_limit_nm<required-1e-12,
        'necessary_acceleration_torque_nm':required,'available_torque_nm':m.torque_limit_nm,
        'initial_gravity_torque_nm':m.mass_kg*9.81*m.length_m/2,
        'formula':'q(T) <= tau_max*T^2/(2*I_hinge), from rest while opening below required angle; opposing gravity/damping omitted gives optimistic bound.',
        'assumptions':['Uniform box inertia; hinge at end; initial rest; positive opening raises beam; q required < pi/2.',
                       'MuJoCo joint stops are compliant and can store/release energy after slight negative sag. The optimistic inertial formula alone does not prove infeasibility for this compiled model.',
                       'Static gravity demand above available torque shows a hold deficit without joint-stop support, not an arbitrary-program impossibility proof. Actual dynamic failure must be measured.']}


def object_position(t,e):
    if t<=e.approach_end_s:return e.initial_object_x_m+(e.near_object_x_m-e.initial_object_x_m)*t/e.approach_end_s
    if t<=e.departure_end_s:return e.near_object_x_m+(e.initial_object_x_m-e.near_object_x_m)*(t-e.approach_end_s)/(e.departure_end_s-e.approach_end_s)
    return e.initial_object_x_m


class RaySensor:
    def __init__(self,config):self.config=config;self.next_sample=0.;self.pending=[];self.sequence=0;self.latest=None;self.history=[]
    def update(self,model,data,t):
        c=self.config
        if t+1e-10>=self.next_sample:
            geom=np.array([-1],dtype=np.int32);groups=np.array([1,0,1,1,1,1],dtype=np.uint8)
            distance=float(mujoco.mj_ray(model,data,np.array(c.origin_m,dtype=float),np.array(c.direction,dtype=float),groups,1,-1,geom))
            valid=c.minimum_m<=distance<=c.maximum_m
            reading=Reading(self.sequence,t,t+c.latency_s,round(distance/c.quantization_m)*c.quantization_m if valid else None,int(geom[0]),'VALID_GEOMETRIC_RAY' if valid else 'NO_RETURN_OR_OUT_OF_RANGE')
            self.pending.append(reading);self.history.append(asdict(reading));self.sequence+=1;self.next_sample+=c.interval_s
        while self.pending and self.pending[0].delivered_s<=t+1e-10:self.latest=self.pending.pop(0)
        return self.latest


def evaluate(samples,spec):
    r=spec.requirements;m=spec.mechanical;l=spec.logic
    # Independent checks use raw sensor distance and joint/command observations,
    # rather than trusting the state machine's self-declared state.
    detected=next((s['time_s'] for s in samples if s['distance_m'] is not None and s['distance_m']<l.threshold_m),None)
    reached=next((s['time_s'] for s in samples if s['q_rad']>=r.open_angle_rad),None)
    unsafe=[s for s in samples if s['state']=='CLOSING' and s['distance_m'] is not None and s['distance_m']<l.threshold_m]
    max_torque=max(abs(s['generalized_torque_nm']) for s in samples)
    checks={'opening_deadline':detected is not None and reached is not None and reached-detected<=r.opening_deadline_s,
        'no_closing_on_near_object':not unsafe,'closed_after_clear':abs(samples[-1]['q_rad'])<=r.closed_tolerance_rad and abs(samples[-1]['qvel_rad_s'])<.05,
        'no_fault':all(s['state']!='FAULT' for s in samples),'torque_limit':max_torque<=m.torque_limit_nm+1e-12,
        'joint_limits':all(m.joint_range_rad[0]-r.joint_tolerance_rad<=s['q_rad']<=m.joint_range_rad[1]+r.joint_tolerance_rad for s in samples),
        'speed_limit':max(abs(s['qvel_rad_s']) for s in samples)<=r.max_speed_rad_s,
        'no_contacts':not any(s['contacts'] for s in samples),'finite':all(math.isfinite(s[k]) for s in samples for k in ('q_rad','qvel_rad_s','generalized_torque_nm'))}
    return {'status':'VERIFIED_IN_SIMULATION' if all(checks.values()) else 'MEASURED_REQUIREMENT_FAILURE','checks':checks,
        'failed_requirements':[k for k,v in checks.items() if not v],'first_detection_s':detected,'first_open_s':reached,
        'unsafe_closing_samples':len(unsafe),'final_angle_rad':samples[-1]['q_rad'],'peak_speed_rad_s':max(abs(s['qvel_rad_s']) for s in samples),
        'peak_measured_torque_nm':max_torque,'minimum_joint_margin_rad':min(min(s['q_rad']-m.joint_range_rad[0],m.joint_range_rad[1]-s['q_rad']) for s in samples),
        'saturation_fraction':sum(abs(s['generalized_torque_nm'])>=m.torque_limit_nm-1e-10 for s in samples[:-1])/max(1,len(samples)-1)}


def run(a,spec=None,output=None,*,render=False):
    if output:
        output=Path(output);output.mkdir(parents=True,exist_ok=False)
    spec=spec or DeviceSpec();a=validate(a);electrical=inspect(a)
    result={'schema_version':1,'device_spec':spec.to_dict(),'device_spec_sha256':spec.identity,'assembly':a,'assembly_sha256':identity(a),
        'electrical':electrical,'execution':'NOT_RUN','source_origin':'TRUSTED_DEVELOPER_REFERENCE_MODEL; AI-assisted implementation, not live model output',
        'model_api_requests':0,'vm_executions':0,'limitations':['Simplified ray sensor; no acoustics/noise/beam cone/multipath.',
          'Reference Python state machine; no ESP32 instruction execution, compilation, flashing or hardware testing.',
          'Ideal bounded torque servo; no electrical current, gearbox backlash, heating or SG90 transient model.',
          'Component layout does not define a manufacturable PCB or automatically move the explicit sensor pose in the mechanical contract.',
          'Electrical unknowns remain unknown; simulation assumes trigger/signal operation and adequate power.'],
        'source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for d in ('devices','hardware') for p in sorted((ROOT/d).glob('*.py'))}}
    if electrical['errors']:
        result.update(status='INVALID',blocked_reason='Electrical precondition failed; MuJoCo was not run.')
    else:
        try:mapping=bindings(a,electrical)
        except ValueError as exc:result.update(status='BLOCKED',blocked_reason=str(exc))
        else:
            model,xml,compiled=compile_model(spec);guard=analytical(spec)
            mapping[0]['interval_s']=spec.sensor.interval_s
            result.update(bindings=mapping,compiled=compiled,analytical_guard=guard,model_xml=xml)
            result['contract_sha256']=digest({'device':spec.to_dict(),'assembly':identity(a),'netlist':electrical['netlist_sha256'],
                'sources':result['source_sha256'],'model':compiled['model_sha256'],'bindings':mapping})
            if guard['status']=='PHYSICALLY_INFEASIBLE':result.update(status='PHYSICALLY_INFEASIBLE',blocked_reason='Necessary optimistic inertial deadline bound fails; code-only repair is insufficient.')
            else:
                data=mujoco.MjData(model);logic=ReferenceLogic(spec.logic);sensor=RaySensor(spec.sensor);samples=[];command=Command('IDLE',0.,'Initial rest');next_control=0.
                steps=round(spec.environment.duration_s/spec.mechanical.timestep_s)
                for index in range(steps+1):
                    t=index*spec.mechanical.timestep_s
                    data.mocap_pos[0]=[object_position(t,spec.environment),-.12,.08]
                    mujoco.mj_forward(model,data);reading=sensor.update(model,data,t)
                    if t+1e-10>=next_control:
                        command=logic.update(t,reading,float(data.qpos[0]));next_control+=spec.logic.update_s
                    requested=.45*(command.target_rad-float(data.qpos[0]))-.11*float(data.qvel[0])
                    data.ctrl[0]=np.clip(requested,-spec.mechanical.torque_limit_nm,spec.mechanical.torque_limit_nm);mujoco.mj_forward(model,data)
                    poses=[]
                    for i in range(model.ngeom):
                        quat=np.empty(4);mujoco.mju_mat2Quat(quat,data.geom_xmat[i]);poses.append({'position':data.geom_xpos[i].tolist(),'quaternion_wxyz':quat.tolist()})
                    samples.append({'time_s':t,'q_rad':float(data.qpos[0]),'qvel_rad_s':float(data.qvel[0]),'requested_torque_nm':requested,
                        'generalized_torque_nm':float(data.qfrc_actuator[0]),'target_rad':command.target_rad,'state':command.state,'reason':command.reason,
                        'distance_m':reading.distance_m if reading else None,'sensor_sequence':reading.sequence if reading else None,
                        'object_position_m':data.xpos[model.body('object').id].tolist(),'contacts':int(data.ncon),'geom_poses':poses})
                    if index<steps:mujoco.mj_step(model,data)
                warnings=[{'index':i,'number':int(w.number)} for i,w in enumerate(data.warning) if w.number]
                result.update(execution='COMPLETED',samples=samples,sensor_readings=sensor.history,acceptance=evaluate(samples,spec),warnings=warnings,
                    scene={'geoms':[{'id':f'geom:{i}','name':model.geom(i).name,'type':int(model.geom_type[i]),'size':model.geom_size[i].tolist(),'rgba':model.geom_rgba[i].tolist()} for i in range(model.ngeom)]})
                result['status']='SIMULATION_OR_NUMERICAL_FAILURE' if warnings else result['acceptance']['status']
                result['trajectory_sha256']=digest(samples)
                result['independent_reconstruction']=verify_reconstruction(result)
                result['independent_dynamics']=verify_dynamics(result)
                if render and output:
                    result['native_render']=native_render(result,Path(output)/'native.png')
    if output:
        write_once(output/'result.json',result)
    return result


def verify_reconstruction(result):
    """Fresh model verifies all recorded force, geometry, time and acceptance.

    This is independent measured-state reconstruction, not candidate VM execution
    or a second control rollout/physics engine.
    """
    spec=DeviceSpec.from_dict(result['device_spec']);model,xml,_=compile_model(spec);data=mujoco.MjData(model)
    for i,s in enumerate(result['samples']):
        if abs(s['time_s']-i*model.opt.timestep)>1e-10:raise ValueError('Playback time mismatch')
        data.qpos[0]=s['q_rad'];data.qvel[0]=s['qvel_rad_s'];data.ctrl[0]=np.clip(s['requested_torque_nm'],-spec.mechanical.torque_limit_nm,spec.mechanical.torque_limit_nm)
        data.mocap_pos[0]=s['object_position_m'];mujoco.mj_forward(model,data)
        np.testing.assert_allclose(data.qfrc_actuator[0],s['generalized_torque_nm'],atol=1e-12,rtol=0)
        if int(data.ncon)!=s['contacts']:raise ValueError('Recorded contact mismatch')
        for g,p in enumerate(s['geom_poses']):
            quat=np.empty(4);mujoco.mju_mat2Quat(quat,data.geom_xmat[g])
            np.testing.assert_allclose(data.geom_xpos[g],p['position'],atol=1e-12,rtol=0);np.testing.assert_allclose(quat,p['quaternion_wxyz'],atol=1e-12,rtol=0)
    if evaluate(result['samples'],spec)!=result['acceptance']:raise ValueError('Acceptance reconstruction mismatch')
    return {'status':'PASS','samples':len(result['samples']),'geometry_force_contact_tolerance':1e-12,'scope':'Fresh native state/force/geometry reconstruction and acceptance; not fresh independent controller execution.'}


def native_render(result,path):
    path.parent.mkdir(parents=True,exist_ok=True)
    try:
        from PIL import Image
        model=mujoco.MjModel.from_xml_string(result['model_xml']);data=mujoco.MjData(model)
        s=max(result['samples'],key=lambda s:s['q_rad']);data.qpos[0]=s['q_rad'];data.mocap_pos[0]=s['object_position_m'];mujoco.mj_forward(model,data)
        camera=mujoco.MjvCamera();camera.lookat[:]=[.25,-.03,.15];camera.distance=1.15;camera.azimuth=125;camera.elevation=-25
        with mujoco.Renderer(model,480,640) as renderer:
            renderer.update_scene(data,camera=camera);pixels=renderer.render();Image.fromarray(pixels).save(path)
        return {'status':'PASS','path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'time_s':s['time_s'],'q_rad':s['q_rad']}
    except (RuntimeError,ImportError,ValueError) as exc:return {'status':'UNVERIFIED','reason':str(exc)[:400]}


def verify_dynamics(result):
    """Fresh trusted control/sensor rollout with independent state/action checks.

    Shares MuJoCo, reference logic and ray sensor; not a second engine or source
    verification for untrusted code. No saved command replay or q-state reset.
    """
    spec=DeviceSpec.from_dict(result['device_spec']);model,_,_=compile_model(spec);data=mujoco.MjData(model)
    logic=ReferenceLogic(spec.logic);sensor=RaySensor(spec.sensor);next_control=0.;command=Command('IDLE',0.,'Initial rest')
    for index,s in enumerate(result['samples']):
        t=index*model.opt.timestep
        data.mocap_pos[0]=[object_position(t,spec.environment),-.12,.08];mujoco.mj_forward(model,data)
        reading=sensor.update(model,data,t)
        if t+1e-10>=next_control:
            command=logic.update(t,reading,float(data.qpos[0]));next_control+=spec.logic.update_s
        request=(command.target_rad-data.qpos[0])*.45-data.qvel[0]*.11
        if command.state!=s['state'] or command.target_rad!=s['target_rad'] or (reading.distance_m if reading else None)!=s['distance_m']:
            raise ValueError('Independent control/sensor mismatch')
        np.testing.assert_allclose([data.qpos[0],data.qvel[0],request],[s['q_rad'],s['qvel_rad_s'],s['requested_torque_nm']],rtol=0,atol=1e-12)
        data.ctrl[0]=max(-spec.mechanical.torque_limit_nm,min(spec.mechanical.torque_limit_nm,float(request)))
        mujoco.mj_forward(model,data)
        np.testing.assert_allclose(data.qfrc_actuator[0],s['generalized_torque_nm'],rtol=0,atol=1e-12)
        if index<len(result['samples'])-1:mujoco.mj_step(model,data)
    if sensor.history!=result['sensor_readings']:raise ValueError('Independent sensor trace mismatch')
    return {'status':'PASS','integration_steps':len(result['samples'])-1,'maximum_allowed_difference':1e-12,
        'scope':'Fresh trusted sensor/control/dynamics rollout, shares reference code and MuJoCo; no arbitrary-source or hardware proof.'}
