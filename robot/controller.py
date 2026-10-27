"""Intentionally unsafe Day 2 baseline; no dynamic stopping-distance controller."""
from __future__ import annotations

import math

import mujoco

from core.simulation import collision_surfaces

BRAKING_THRESHOLD_M = 0.12


def faulty_braking_controller(model: mujoco.MjModel, data: mujoco.MjData) -> None:
    """Brake at a fixed surface gap, ignoring mass, speed and stopping distance.

    The simulator refreshes derived geometry before this call. The velocity guard
    releases braking after stopping/rebound; it does not repair the late trigger.
    """
    joint = data.joint("x_slide")
    position, velocity = float(joint.qpos[0]), float(joint.qvel[0])
    if not math.isfinite(position) or not math.isfinite(velocity):
        raise ValueError("Controller requires finite joint position and velocity")
    clearance = collision_surfaces(model, data)["wall_clearance"]
    motor = model.actuator("x_motor").id
    # This scene has a direct motor (gear=1); both compiled clamps are in N.
    maximum_braking_command = max(float(model.actuator_ctrlrange[motor, 0]),
                                  float(model.actuator_forcerange[motor, 0]))
    # INTENTIONAL DEFECT: 0.12 m is treated as enough at every forward speed.
    # Treat floating-point roundoff at the threshold as equality (1 picometer).
    threshold_reached = clearance <= BRAKING_THRESHOLD_M or math.isclose(
        clearance, BRAKING_THRESHOLD_M, rel_tol=0, abs_tol=1e-12)
    data.ctrl[motor] = maximum_braking_command if threshold_reached and velocity > 0 else 0.0
