"""Trusted developer baseline for joint-space target tracking (AI-assisted definition).

The legacy function name is the existing isolated-worker ABI for every family.
This baseline is not a genuine live-agent proposal.
"""
from __future__ import annotations
import math
import mujoco

POSITION_GAIN = 12.0
VELOCITY_GAIN = 1.8


def faulty_braking_controller(model: mujoco.MjModel, data: mujoco.MjData) -> None:
    """Apply bounded feedback toward the task's joint-space command."""
    for i in range(2):
        position = float(data.qpos[i])
        velocity = float(data.qvel[i])
        target = float(model.numeric_data[i])
        if not math.isfinite(position) or not math.isfinite(velocity):
            raise ValueError("Nonfinite arm state")
        requested = POSITION_GAIN * (target - position) + VELOCITY_GAIN * velocity
        data.ctrl[i] = min(float(model.actuator_ctrlrange[i, 1]),
                           max(float(model.actuator_ctrlrange[i, 0]), requested))
