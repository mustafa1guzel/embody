"""Trusted compilation/probing only; no controller loading or arbitrary XML from UI."""
from __future__ import annotations
import hashlib
import mujoco
import numpy as np
from core.day3 import load_scenarios
from core.simulation import ROOT, DEFAULT_MODEL_PATH, compile_context_model, collision_surfaces
from .contracts import PhysicsContract, digest

CHECK_NAMES = ('single_x_slide', 'direct_stateless_unit_motor', 'force_clamps',
               'no_other_forces', 'semi_implicit_euler', 'aligned_contact_geometry',
               'constant_inertia', 'bodybase_matches', 'actual_force_probes')
ASSUMPTIONS = (
    'One horizontal x slide; world X forward, Y left, Z up; SI units.',
    'Constant generalized inertia; direct stateless unit-gain gear-one motor with bounded force.',
    'No longitudinal gravity, damping, friction loss, springs, external force or active constraints before contact.',
    'Aligned overlapping wall/bumper boxes; clearance is near wall face minus front bumper surface.',
    'Euler with no damping: velocity advances before position; commands held for one timestep.',
    'Predictive bounds apply only before contact and for forward non-reversing stopping; recovery is unsupported.',
    'No nonzero uncertainty is certified; sampled evidence does not prove continuous real-hardware safety.',
)


def extract_contract(scenario_id, controller_sha256=None, *, model_xml=None):
    """model_xml is a trusted test/analytical-fixture hook, never an API parameter."""
    scenarios = load_scenarios()
    if scenario_id not in scenarios:
        raise ValueError('Unknown physical scenario')
    body, world = scenarios[scenario_id]
    model, xml = compile_context_model(DEFAULT_MODEL_PATH, body, world)
    if model_xml is not None:
        xml = model_xml; model = mujoco.MjModel.from_xml_string(xml)
    if (model.nq, model.nv, model.nu) != (1, 1, 1):
        raise ValueError('Contract extraction requires the existing one-axis system; unsupported dimensions')
    if int(model.joint('x_slide').type[0]) != int(mujoco.mjtJoint.mjJNT_SLIDE):
        raise ValueError('Rotary inertia/torque units require a different contract extractor')
    data = mujoco.MjData(model)
    data.qpos[0], data.qvel[0] = world.initial_position_x_m, world.initial_velocity_ms
    mujoco.mj_forward(model, data)
    surfaces = collision_surfaces(model, data)
    carriage, bumper, wall = model.body('carriage').id, model.geom('front_bumper').id, model.geom('wall').id
    motor = model.actuator('x_motor').id
    inertia = float(data.M[0])  # MuJoCo 3.16 packed inertia, one DOF.
    close = lambda a, b: bool(np.allclose(a, b, rtol=0, atol=1e-12))
    direct = (int(model.actuator_trntype[motor]) == int(mujoco.mjtTrn.mjTRN_JOINT)
              and int(model.actuator_trnid[motor, 0]) == model.joint('x_slide').id
              and int(model.actuator_gaintype[motor]) == int(mujoco.mjtGain.mjGAIN_FIXED)
              and int(model.actuator_biastype[motor]) == int(mujoco.mjtBias.mjBIAS_NONE)
              and int(model.actuator_dyntype[motor]) == int(mujoco.mjtDyn.mjDYN_NONE)
              and close(model.actuator_gainprm[motor], [1]+[0]*9)
              and close(model.actuator_biasprm[motor], 0)
              and close(model.actuator_gear[motor], [1, 0, 0, 0, 0, 0]) and model.na == 0)
    clamps = bool(model.actuator_ctrllimited[motor] and model.actuator_forcelimited[motor]
                  and model.actuator_ctrlrange[motor, 0] <= 0 <= model.actuator_ctrlrange[motor, 1]
                  and model.actuator_forcerange[motor, 0] <= 0 <= model.actuator_forcerange[motor, 1])
    # Authority is the intersection of input and scalar-force clamps only AFTER
    # checking transmission/gain. Unsupported models retain numbers but no theorem.
    force = max(0.0, -max(float(model.actuator_ctrlrange[motor, 0]),
                          float(model.actuator_forcerange[motor, 0])))
    joint = model.joint('x_slide').id
    single = (model.njnt == 1 and int(model.jnt_type[joint]) == int(mujoco.mjtJoint.mjJNT_SLIDE)
              and close(model.jnt_axis[joint], [1, 0, 0]) and close(data.xaxis[joint], [1, 0, 0])
              and int(model.jnt_bodyid[joint]) == carriage
              and not model.jnt_limited[joint] and not model.jnt_actfrclimited[joint])
    no_other = (model.neq == model.ntendon == model.nplugin == model.nflex == 0
                and close(model.dof_damping, 0) and close(model.dof_frictionloss, 0)
                and close(model.dof_armature, 0) and close(model.jnt_stiffness, 0)
                and close(model.body_gravcomp, 0) and close(model.opt.gravity[:2], 0)
                and close(model.opt.wind, 0) and model.opt.viscosity == model.opt.density == 0
                and close(data.qfrc_bias, 0) and close(data.qfrc_passive, 0)
                and close(data.qfrc_constraint, 0) and data.ncon == 0)
    names = {mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, i) for i in range(model.ngeom)}
    geometry = (names == {'floor', 'rail_base', 'rail_track', 'carriage_box', 'front_bumper', 'wall'}
                and model.nbody == 4 and model.ngeom == 6 and model.npair == model.nexclude == model.nmocap == 0
                and int(model.geom_bodyid[bumper]) == int(model.geom_bodyid[model.geom('carriage_box').id]) == carriage
                and int(model.geom_bodyid[wall]) == model.body('obstacle').id
                and int(model.geom_type[bumper]) == int(mujoco.mjtGeom.mjGEOM_BOX)
                and int(model.geom_type[wall]) == int(mujoco.mjtGeom.mjGEOM_BOX)
                and close(data.geom_xmat[bumper], np.eye(3).ravel())
                and close(data.geom_xmat[wall], np.eye(3).ravel())
                and close(data.geom_xmat[model.geom('carriage_box').id], np.eye(3).ravel())
                and int(model.geom('floor').type[0]) == int(mujoco.mjtGeom.mjGEOM_PLANE)
                and close(data.geom_xmat[model.geom('floor').id], np.eye(3).ravel())
                and close(data.geom_xpos[model.geom('floor').id, 2], 0)
                and close(model.geom_friction, 0) and close(model.geom_margin, 0) and close(model.geom_gap, 0)
                and all(model.geom(n).contype[0] == model.geom(n).conaffinity[0] == 0
                        for n in ('rail_base', 'rail_track'))
                and all(abs(data.geom_xpos[bumper, i]-data.geom_xpos[wall, i]) < model.geom_size[bumper, i]+model.geom_size[wall, i]
                        for i in (1, 2))
                and surfaces['bumper_front_x'] > data.geom_xpos[model.geom('carriage_box').id, 0]+model.geom('carriage_box').size[0]
                and data.geom_xpos[bumper, 2]-model.geom_size[bumper, 2] > 0
                and data.geom_xpos[model.geom('carriage_box').id, 2]-model.geom('carriage_box').size[2] > 0)
    # Actual endpoint and interior probes corroborate the structural checks.
    probe_ok = True; constant = True; probes = []
    endpoint = surfaces['wall_clearance']-world.minimum_clearance_m
    for offset in (0.0, max(0, endpoint)/2, max(0, endpoint)):
        for velocity in (0.0, world.initial_velocity_ms, -world.initial_velocity_ms):
            for command in (-1000.0, 0.0, 1000.0):
                d = mujoco.MjData(model)
                d.qpos[0] = world.initial_position_x_m+offset; d.qvel[0] = velocity; d.ctrl[motor] = command
                mujoco.mj_forward(model, d)
                expected = float(np.clip(np.clip(command, *model.actuator_ctrlrange[motor]), *model.actuator_forcerange[motor]))
                constant &= close(d.M, [inertia])
                probes.append(tuple(float(v) for v in (d.qpos[0], d.qvel[0], d.ctrl[motor],
                              d.actuator_force[motor], d.qfrc_actuator[0], d.M[0], d.qacc[0], d.ncon)))
                probe_ok &= (close(d.actuator_moment, [1]) and close(d.actuator_force, [expected])
                             and close(d.qfrc_actuator, [expected]) and close(d.qacc, [expected/inertia])
                             and close(d.qfrc_bias, 0) and close(d.qfrc_passive, 0) and d.ncon == 0)
    checks = dict(zip(CHECK_NAMES, (single, direct, clamps, no_other,
                  int(model.opt.integrator) == int(mujoco.mjtIntegrator.mjINT_EULER)
                  and model.opt.disableflags == model.opt.enableflags == model.opt.disableactuator == 0,
                  geometry, constant, close(inertia, body.mass_kg) and close(force, body.max_force_n), probe_ok)))
    sources = tuple((p, hashlib.sha256((ROOT/p).read_bytes()).hexdigest()) for p in
                    ('robot/rail_carriage.xml', 'configs/bodybase.json', 'configs/worldbase.json',
                     'configs/scenarios.json', 'core/simulation.py', 'core/bodybase.py',
                     'core/worldbase.py', 'core/day3.py', 'core/context_validation.py'))
    return PhysicsContract(
        scenario_id=scenario_id, robot_id=body.robot_id, model_sha256=hashlib.sha256(xml.encode()).hexdigest(),
        controller_sha256=controller_sha256 or hashlib.sha256((ROOT/'robot/controller.py').read_bytes()).hexdigest(),
        context_sha256=digest({'bodybase': body.to_dict(), 'worldbase': world.to_dict()}), source_hashes=sources,
        mass_kg=float(model.body_mass[carriage]), generalized_inertia_kg=inertia,
        body_masses_kg=((body.robot_id, float(model.body_mass[carriage])),),
        joint_name='x_slide', joint_type='prismatic' if single else 'unsupported',
        axis_world=tuple(float(v) for v in data.xaxis[joint]), actuator_name='x_motor',
        transmission='joint_direct' if int(model.actuator_trntype[motor]) == 0 else 'unsupported',
        gain_type=str(int(model.actuator_gaintype[motor])), bias_type=str(int(model.actuator_biastype[motor])),
        dynamics_type=str(int(model.actuator_dyntype[motor])), gear=float(model.actuator_gear[motor, 0]),
        control_range=tuple(float(v) for v in model.actuator_ctrlrange[motor]),
        scalar_force_range_n=tuple(float(v) for v in model.actuator_forcerange[motor]), braking_force_n=force,
        frame='world_X_forward_Y_left_Z_up_SI', bumper_front_offset_m=surfaces['bumper_front_x']-world.initial_position_x_m,
        bumper_half_size_m=tuple(float(v) for v in model.geom_size[bumper]),
        wall_center_m=tuple(float(v) for v in data.geom_xpos[wall]),
        wall_half_size_m=tuple(float(v) for v in model.geom_size[wall]), wall_near_x_m=surfaces['wall_near_x'],
        initial_position_m=world.initial_position_x_m, initial_velocity_mps=world.initial_velocity_ms,
        initial_clearance_m=surfaces['wall_clearance'], maximum_speed_mps=body.max_velocity_ms,
        timestep_s=float(model.opt.timestep), duration_s=world.simulation_duration_s, deadline_s=world.completion_deadline_s,
        minimum_clearance_m=world.minimum_clearance_m, final_speed_tolerance_mps=world.max_final_speed_ms,
        gravity_mps2=tuple(float(v) for v in model.opt.gravity), integrator='Euler' if int(model.opt.integrator) == 0 else 'unsupported',
        checks=tuple((k, bool(v)) for k, v in checks.items()), assumptions=ASSUMPTIONS,
        force_probe_evidence=tuple(probes),
        provenance_kind='analytical_fixture' if model_xml is not None else 'compiled_project')
