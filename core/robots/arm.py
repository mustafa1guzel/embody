"""Authoritative planar-arm provider; analytical kinematics is separate from dynamics."""
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET
import mujoco
import numpy as np
from core.simulation import ROOT
from physics.contracts import canonical, digest
from physics.multidof import JointLimit, MultiDOFContract
from physics.planar import forward, assess

TARGET = 'robot/arm_controller.py'
MODEL = 'robot/planar_arm.xml'
CONFIG = 'configs/arm_tasks.json'
EVALUATION = 'configs/arm_evaluation.json'
READS = frozenset({TARGET, MODEL, CONFIG})


class ArmFamily:
    name = 'arm'
    target = TARGET
    managed_target = 'robot/approved_arm_controller.py'
    managed_name = 'approved_arm_controller.py'
    read_allowlist = READS

    def __init__(self, *, root=ROOT, evaluation=False):
        self.root = Path(root)
        self.definition = json.loads((self.root/CONFIG).read_text())
        self.scenarios = self.definition['development'].copy()
        if evaluation: self.scenarios.update(json.loads((self.root/EVALUATION).read_text()))

    def compile(self, scenario, controller_sha=None):
        if scenario not in self.scenarios: raise ValueError('Unknown arm scenario')
        task = self.scenarios[scenario]; tree = ET.parse(self.root/MODEL); root = tree.getroot()
        lengths = (float(root.find(".//body[@name='link2']").get('pos').split()[0]),
                   float(root.find(".//site[@name='end_effector']").get('pos').split()[0]))
        goal = task.get('goal_q', [0.7, -1.0])
        xy = task.get('target_xy_m', forward(lengths, goal))
        root.find('./custom/numeric').set('data', ' '.join(format(v,'.17g') for v in goal))
        for node in (root.find(".//geom[@name='target_marker']"), root.find(".//site[@name='target']")):
            node.set('pos', ' '.join(format(v,'.17g') for v in (*xy,.25)))
        root.find('./option').set('timestep', str(self.definition['requirements']['timestep_s']))
        xml = ET.tostring(root, encoding='unicode'); model = mujoco.MjModel.from_xml_string(xml)
        data = mujoco.MjData(model);data.qpos[:]=task['q0'];data.qvel[:]=task['v0'];mujoco.mj_forward(model,data)
        if (model.nq,model.nv,model.nu,model.njnt)!=(2,2,2,2): raise ValueError('Unexpected arm dimension')
        if any(model.jnt_type!=mujoco.mjtJoint.mjJNT_HINGE) or not np.allclose(data.xaxis,[[0,0,1],[0,0,1]],atol=1e-12):
            raise ValueError('Unsupported arm joint/frame')
        if not (np.all(model.actuator_trntype==0) and np.all(model.actuator_trnid[:,0]==[0,1])
                and np.all(model.actuator_gear==[[1,0,0,0,0,0]]*2)
                and np.all(model.actuator_gaintype==0) and np.all(model.actuator_gainprm[:,0]==1)
                and np.all(model.actuator_biastype==0) and np.all(model.actuator_dyntype==0)
                and np.all(model.actuator_ctrllimited) and np.all(model.actuator_forcelimited)
                and np.all(model.jnt_limited) and not np.any(model.jnt_actfrclimited)):
            raise ValueError('Unsupported actuator transmission/force/limit model')
        if data.ncon: raise ValueError('Initial arm contacts are unsupported')
        if not (np.allclose(model.body('link1').pos,[0,0,.25],atol=1e-12)
                and np.allclose(model.body('link2').pos,[lengths[0],0,0],atol=1e-12)
                and np.allclose(model.site('end_effector').pos,[lengths[1],0,0],atol=1e-12)
                and np.allclose(model.body('link1').quat,[1,0,0,0],atol=1e-12)
                and np.allclose(model.body('link2').quat,[1,0,0,0],atol=1e-12)
                and np.allclose(model.jnt_pos,0,atol=1e-12)):
            raise ValueError('Unsupported planar link frames')
        ee = data.site_xpos[model.site('end_effector').id]
        if not np.allclose(ee[:2],forward(lengths,task['q0']),rtol=0,atol=1e-12) or abs(ee[2]-.25)>1e-12:
            raise ValueError('Compiled arm geometry disagrees with planar kinematics')
        # Derive torque authority from both compiled clamps; gear-one revolute
        # mapping is checked above, not assumed from an input variable name.
        joints = tuple(JointLimit(model.joint(i).name,'revolute','rad','N*m',
                       tuple(float(v) for v in model.jnt_range[i]),
                       (float(max(model.actuator_ctrlrange[i,0],model.actuator_forcerange[i,0])),
                        float(min(model.actuator_ctrlrange[i,1],model.actuator_forcerange[i,1])))) for i in range(2))
        req=self.definition['requirements']; target=tuple(float(v) for v in model.site('target').pos)
        contract=MultiDOFContract(family='arm',robot_id=self.definition['robot_id'],scenario_id=scenario,
            model_sha256=hashlib.sha256(xml.encode()).hexdigest(),
            controller_sha256=controller_sha or hashlib.sha256((self.root/TARGET).read_bytes()).hexdigest(),
            context_sha256=digest({'task':task,'requirements':req,'model_source_sha256':hashlib.sha256((self.root/MODEL).read_bytes()).hexdigest()}),
            joints=joints,q0=tuple(task['q0']),v0=tuple(task['v0']),target_m=target,end_effector_site='end_effector',
            gravity_mps2=tuple(float(v) for v in model.opt.gravity), assumptions=(
                'Horizontal planar two-link chain; joint axes world z; fixed link heights.',
                'Vertical gravity has zero in-plane gravitational torque; inertial coupling and Coriolis forces remain.',
                'Direct gear-one stateless unit motors; actual torque clamps checked independently.',
                'IK proves only a kinematic witness; dynamics, contacts and source behavior require measurements.'),
            body_masses_kg=tuple((model.body(i).name,float(model.body_mass[i])) for i in range(1,model.nbody)),
            joint_axes_world=tuple(tuple(float(v) for v in axis) for axis in data.xaxis),**req)
        mass=np.empty((2,2));mujoco.mj_fullM(model,data,mass)
        bodybase={'robot_id':contract.robot_id,'joint_count':2,'joints':[asdict(j) for j in joints],
                  'link_lengths_m':list(lengths),'body_masses_kg':dict(contract.body_masses_kg),
                  'body_inertias_kg_m2':{model.body(i).name:model.body_inertia[i].tolist() for i in range(1,model.nbody)},
                  'generalized_inertia_at_initial_kg_m2':mass.tolist(),
                  'transmission':'direct joint, gear=1, fixed gain=1, no bias or activation',
                  'damping_nm_s_per_rad':model.dof_damping.tolist(),'geometry':'compiled boxes and marker spheres'}
        worldbase={'scenario_id':scenario,'q0_rad':list(contract.q0),'v0_rad_s':list(contract.v0),
                   'target_m':list(target),'joint_space_command_rad':list(goal),
                   'gravity_mps2':list(contract.gravity_mps2),'requirements':req,
                   'target_site_id':model.site('target').id,'goal_q_numeric_address':int(model.numeric_adr[0])}
        return model,xml,contract,bodybase,worldbase,lengths

    def context(self, scenario):
        _,_,c,b,w,lengths=self.compile(scenario)
        return {'scenario_id':scenario,'robot_family':'arm','bodybase':b,'worldbase':w,
                'physics_contract':c.to_dict(),'contract_sha256':c.identity,
                'effective_mjcf_sha256':c.model_sha256,'analytical_guard':assess(c,lengths)}

    def baseline(self):
        from robot.arm_controller import faulty_braking_controller
        return faulty_braking_controller

    def executor(self, candidate, scenarios, backend, output, names=None):
        from core.robots.execution import execute_candidate
        return execute_candidate(self,candidate,scenarios,backend,output,names=names)

    def trusted(self, scenario, output):
        from core.robots.execution import execute_trusted
        return execute_trusted(self,scenario,output)

    def diagnostic(self, record):
        from workspace.data import decode_json,bounded_read
        if any(hashlib.sha256(bounded_read(record['directory'],name)).hexdigest()!=sha for name,sha in record['inventory'].items()):
            raise ValueError('Arm diagnostic artifact integrity mismatch')
        return decode_json(bounded_read(record['directory'],'diagnostics.json'))
