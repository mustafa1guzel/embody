"""Stopping-distance-aware wall-braking controller."""
from __future__ import annotations

import math

import mujoco

from core.simulation import collision_surfaces

MIN_CLEARANCE_M = 0.05
TARGET_FINAL_SPEED_MPS = 0.02


def faulty_braking_controller(model: mujoco.MjModel, data: mujoco.MjData) -> None:
    """Brake from measured stopping distance instead of a fixed trigger gap."""
    joint = data.joint("x_slide")
    position = float(joint.qpos[0])
    velocity = float(joint.qvel[0])
    if not math.isfinite(position) or not math.isfinite(velocity):
        raise ValueError("Controller requires finite joint position and velocity")

    motor = model.actuator("x_motor").id
    ctrl_min = float(model.actuator_ctrlrange[motor, 0])
    force_min = float(model.actuator_forcerange[motor, 0])
    maximum_braking_command = min(ctrl_min, force_min)
    braking_force_n = -maximum_braking_command
    mass_kg = float(model.body("carriage").mass[0])
    timestep_s = float(model.opt.timestep)
    clearance = collision_surfaces(model, data)["wall_clearance"]

    command = 0.0
    if (math.isfinite(clearance) and math.isfinite(braking_force_n) and math.isfinite(mass_kg)
            and math.isfinite(timestep_s) and braking_force_n > 0.0 and mass_kg > 0.0 and timestep_s > 0.0):
        max_deceleration = braking_force_n / mass_kg
        speed = abs(velocity)
        if speed > TARGET_FINAL_SPEED_MPS:
            stopping_distance = (speed * speed - TARGET_FINAL_SPEED_MPS * TARGET_FINAL_SPEED_MPS) / (2.0 * max_deceleration)
            trigger_clearance = MIN_CLEARANCE_M + stopping_distance + speed * timestep_s
            if velocity < 0.0:
                command = -maximum_braking_command
            elif clearance <= trigger_clearance or math.isclose(clearance, trigger_clearance, rel_tol=0.0, abs_tol=1e-12):
                command = maximum_braking_command

    data.ctrl[motor] = command
