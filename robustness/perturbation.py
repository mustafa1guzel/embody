"""Trusted bounded model construction; historical model/configuration stays untouched."""
from dataclasses import replace,asdict
from functools import lru_cache
import hashlib
import xml.etree.ElementTree as ET
import mujoco
import numpy as np
from core.simulation import ROOT,DEFAULT_MODEL_PATH,compile_context_model,collision_surfaces
from core.day3 import load_scenarios
from core.robots.arm import ArmFamily
from physics.extraction import extract_contract
from physics.guard import assess_task
from physics.planar import forward,assess
from physics.contracts import digest
from .parameters import validate


@lru_cache(maxsize=1)
def rail_reference():return extract_contract('A')


def compile_rail(row,source_hash):
    p=validate('rail',row['parameters']);base,world=load_scenarios()['A']
    body=replace(base,mass_kg=p['mass_kg'],max_force_n=p['force_n'])
    offset=base.collision_geometry.bumper_center_x_m+base.collision_geometry.bumper_half_size_m[0]
    world=replace(world,scenario=row['id'],initial_velocity_ms=p['speed_mps'],initial_position_x_m=p['initial_position_m'],
                  wall_position_x_m=p['initial_position_m']+offset+world.wall_half_size_m[0]+p['gap_m'])
    model,xml=compile_context_model(DEFAULT_MODEL_PATH,body,world);data=mujoco.MjData(model)
    data.qpos[0]=world.initial_position_x_m;data.qvel[0]=world.initial_velocity_ms;mujoco.mj_forward(model,data)
    ref=rail_reference();base_model=mujoco.MjModel.from_xml_path(str(DEFAULT_MODEL_PATH))
    # The compiler is the existing allowlisted BodyBase/WorldBase application.
    # Check all nonperturbed transmission, force-model and geometry premises.
    for name in ('jnt_type','jnt_axis','dof_damping','dof_frictionloss','actuator_gear','actuator_gainprm',
                 'actuator_biasprm','actuator_gaintype','actuator_biastype','actuator_dyntype','geom_size','geom_friction','geom_margin','geom_gap'):
        if not np.array_equal(getattr(model,name),getattr(base_model,name)):raise ValueError('Unsupported changed rail premise: '+name)
    if (model.nq,model.nv,model.nu)!=(1,1,1) or not all(v for _,v in ref.checks):raise ValueError('Unsupported rail model')
    ratio=p['mass_kg']/float(base_model.body('carriage').mass[0])
    np.testing.assert_allclose(model.body('carriage').inertia,base_model.body('carriage').inertia*ratio,rtol=0,atol=1e-12)
    surface=collision_surfaces(model,data);probes=[]
    for offset in (0.,max(0.,p['gap_m']-.05)*.25,max(0.,p['gap_m']-.05)*.5):
        for velocity in (0.,world.initial_velocity_ms,-world.initial_velocity_ms):
            for command in (-1000.,0.,1000.):
                d=mujoco.MjData(model);d.qpos[0]=world.initial_position_x_m+offset;d.qvel[0]=velocity;d.ctrl[0]=command;mujoco.mj_forward(model,d)
                expected=float(np.clip(command,-p['force_n'],p['force_n']))
                if (d.ncon or not np.allclose([d.M[0],d.actuator_force[0],d.qfrc_actuator[0],d.qacc[0]],
                    [p['mass_kg'],expected,expected,expected/p['mass_kg']],rtol=0,atol=1e-11)
                    or not np.allclose(d.qfrc_bias+d.qfrc_passive,0,rtol=0,atol=1e-12)):
                    raise ValueError('Compiled rail authority/inertia probe failed')
                probes.append(tuple(map(float,(d.qpos[0],d.qvel[0],command,d.actuator_force[0],d.qfrc_actuator[0],d.M[0],d.qacc[0],d.ncon))))
    c=replace(ref,scenario_id=row['id'],model_sha256=hashlib.sha256(xml.encode()).hexdigest(),controller_sha256=source_hash,
        context_sha256=digest({'bodybase':body.to_dict(),'worldbase':world.to_dict()}),mass_kg=p['mass_kg'],generalized_inertia_kg=float(data.M[0]),
        body_masses_kg=((body.robot_id,p['mass_kg']),),control_range=tuple(map(float,model.actuator_ctrlrange[0])),
        scalar_force_range_n=tuple(map(float,model.actuator_forcerange[0])),braking_force_n=p['force_n'],
        wall_center_m=tuple(map(float,data.geom_xpos[model.geom('wall').id])),wall_near_x_m=surface['wall_near_x'],
        initial_position_m=world.initial_position_x_m,initial_velocity_mps=world.initial_velocity_ms,
        initial_clearance_m=surface['wall_clearance'],force_probe_evidence=tuple(probes),
        provenance_kind='compiled_project')
    return {'model':model,'xml':xml,'contract':c,'body':body,'world':world,'guard':assess_task(c),
            'parameters':p,'scenario':row}


class ArmPlant:
    def __init__(self,row):self.row=row;self.scenarios={row['id']:row};self.reference=ArmFamily()
    def baseline(self):return self.reference.baseline()
    def compile(self,name,controller_sha=None):
        if name!=self.row['id']:raise ValueError('Unknown perturbed arm scenario')
        p=validate('arm',self.row['parameters']);base,xml,c,_,world,lengths=self.reference.compile('arm_nominal',controller_sha)
        tree=ET.fromstring(xml)
        for i in (1,2):
            node=tree.find(f".//body[@name='link{i}']/inertial");mass=p[f'link{i}_mass_kg'];ratio=mass/float(node.get('mass'))
            node.set('mass',format(mass,'.17g'));node.set('diaginertia',' '.join(format(float(x)*ratio,'.17g') for x in node.get('diaginertia').split()))
        for node in tree.findall('.//joint'):
            if node.get('name') in ('shoulder','elbow'):node.set('damping',format(p['damping_nm_s_per_rad'],'.17g'))
        for node,key in zip(tree.findall('./actuator/motor'),('shoulder_torque_nm','elbow_torque_nm')):
            for attr in ('ctrlrange','forcerange'):node.set(attr,f'{-p[key]:.17g} {p[key]:.17g}')
        q=(p['q0_shoulder_rad'],p['q0_elbow_rad']);goal=(p['goal_shoulder_rad'],p['goal_elbow_rad']);xy=forward(lengths,goal)
        tree.find('./custom/numeric').set('data',' '.join(format(v,'.17g') for v in goal))
        for node in (tree.find(".//site[@name='target']"),tree.find(".//geom[@name='target_marker']")):
            node.set('pos',f'{xy[0]:.17g} {xy[1]:.17g} .25')
        xml=ET.tostring(tree,encoding='unicode');model=mujoco.MjModel.from_xml_string(xml);data=mujoco.MjData(model)
        data.qpos[:]=q;mujoco.mj_forward(model,data)
        if data.ncon or (model.nq,model.nv,model.nu)!=(2,2,2):raise ValueError('Invalid arm state/dimensions')
        for i in (1,2):
            name=f'link{i}';ratio=p[f'link{i}_mass_kg']/float(base.body(name).mass[0])
            np.testing.assert_allclose(model.body(name).inertia,base.body(name).inertia*ratio,rtol=0,atol=1e-12)
        np.testing.assert_allclose(model.dof_damping,p['damping_nm_s_per_rad'],rtol=0,atol=1e-12)
        np.testing.assert_allclose(data.site_xpos[model.site('end_effector').id],(*forward(lengths,q),.25),rtol=0,atol=1e-12)
        limits=[p['shoulder_torque_nm'],p['elbow_torque_nm']]
        for command in (-1000.,1000.):
            data.ctrl[:]=command;mujoco.mj_forward(model,data)
            np.testing.assert_allclose(data.qfrc_actuator,np.sign(command)*np.array(limits),rtol=0,atol=1e-12)
        joints=tuple(replace(j,effort_range=(-limits[i],limits[i])) for i,j in enumerate(c.joints))
        c=replace(c,scenario_id=self.row['id'],model_sha256=hashlib.sha256(xml.encode()).hexdigest(),
            context_sha256=digest({'parameters':p,'base_context':c.context_sha256}),q0=q,v0=(0.,0.),target_m=(*xy,.25),joints=joints,
            body_masses_kg=tuple((model.body(i).name,float(model.body_mass[i])) for i in range(1,model.nbody)))
        mass=np.empty((2,2));mujoco.mj_fullM(model,data,mass)
        if np.linalg.eigvalsh(mass).min()<=0:raise ValueError('Invalid generalized inertia')
        body={'robot_id':c.robot_id,'joints':[asdict(j) for j in joints],'body_masses_kg':dict(c.body_masses_kg),
              'body_inertias_kg_m2':{f'link{i}':model.body(f'link{i}').inertia.tolist() for i in (1,2)},
              'damping_nm_s_per_rad':model.dof_damping.tolist(),'generalized_inertia_at_initial_kg_m2':mass.tolist(),'link_lengths_m':list(lengths)}
        world={**world,'scenario_id':self.row['id'],'q0_rad':list(q),'v0_rad_s':[0.,0.],'target_m':list(c.target_m),'joint_space_command_rad':list(goal)}
        return model,xml,c,body,world,lengths


def compile_scenario(row,source_hash):
    if row['family']=='rail':return compile_rail(row,source_hash)
    if row['family']!='arm':raise ValueError('Unknown robot family')
    family=ArmPlant(row);model,xml,c,b,w,lengths=family.compile(row['id'],source_hash)
    return {'model':model,'xml':xml,'contract':c,'bodybase':b,'worldbase':w,'lengths':lengths,
            'guard':assess(c,lengths),'parameters':dict(row['parameters']),'scenario':row,'family':family}


def contract_dict(c):return c.to_dict()
