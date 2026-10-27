"""AI-assisted developer benchmark, excluded from agent reads; never an AI repair."""


def reference_controller(model, data):
    """Velocity-limited tracking, only to demonstrate nominal achievability."""
    for i in range(2):
        error = float(model.numeric_data[i])-float(data.qpos[i])
        desired_speed = max(-1.5,min(1.5,4.0*error))
        requested = 2.0*(desired_speed-float(data.qvel[i]))
        data.ctrl[i] = min(float(model.actuator_ctrlrange[i,1]),max(float(model.actuator_ctrlrange[i,0]),requested))


def pd_reference_controller(model, data):
    """Earlier developer benchmark; preserved even if its peak speed fails."""
    for i in range(2):
        requested = 12.0*(float(model.numeric_data[i])-float(data.qpos[i]))-3.0*float(data.qvel[i])
        data.ctrl[i] = min(float(model.actuator_ctrlrange[i,1]),max(float(model.actuator_ctrlrange[i,0]),requested))
