"""Measured vector diagnostics. No electrical or global safety interpretation."""
import math


def profile(samples, contract):
    h=contract.timestep_s; n=len(contract.joints)
    if len(samples)<2:return {'status':'NOT_AVAILABLE','reason':'At least two measured states required'}
    required=('qpos_rad','qvel_rad_s','generalized_torque_nm','joint_limit_margin_rad')
    if any(any(k not in s or len(s[k])!=n for k in required) for s in samples):
        return {'status':'NOT_AVAILABLE','reason':'Missing vector measurement'}
    if any(not math.isfinite(v) for s in samples for k in required for v in s[k]):
        raise ValueError('Nonfinite vector telemetry')
    if any(abs(b['time']-a['time']-h)>1e-10 for a,b in zip(samples,samples[1:])):
        raise ValueError('Invalid measured timestamp grid')
    acceleration=[[(b['qvel_rad_s'][j]-a['qvel_rad_s'][j])/(b['time']-a['time']) for j in range(n)] for a,b in zip(samples,samples[1:])]
    jerk=[[(b[j]-a[j])/h for j in range(n)] for a,b in zip(acceleration,acceleration[1:])]
    work=[sum(a['generalized_torque_nm'][j]*(b['qpos_rad'][j]-a['qpos_rad'][j]) for a,b in zip(samples,samples[1:])) for j in range(n)]
    saturation=[sum(b['time']-a['time'] for a,b in zip(samples,samples[1:]) if
                    abs(a['generalized_torque_nm'][j]-contract.joints[j].effort_range[0])<1e-10 or
                    abs(a['generalized_torque_nm'][j]-contract.joints[j].effort_range[1])<1e-10) for j in range(n)]
    return {'status':'AVAILABLE','signed_actuator_work_j':work,'saturation_duration_s':saturation,
            'saturation_fraction':[t/contract.duration_s for t in saturation],
            'peak_abs_acceleration_rad_s2':[max(abs(a[j]) for a in acceleration) for j in range(n)],
            'peak_abs_jerk_rad_s3':[max(abs(a[j]) for a in jerk) for j in range(n)],
            'final_error_m':samples[-1]['target_error_m'],
            'maximum_abs_joint_velocity_rad_s':[max(abs(s['qvel_rad_s'][j]) for s in samples) for j in range(n)],
            'minimum_joint_margin_rad':[min(s['joint_limit_margin_rad'][j] for s in samples) for j in range(n)],
            'methods':{'acceleration':'Forward velocity differences on intervals, no endpoint padding.',
                       'jerk':'Difference of adjacent interval accelerations over timestep.',
                       'work':'Sum held generalized torque[k] * (q[k+1]-q[k]); mechanical only, not electrical.',
                       'saturation':'Measured torque at compiled clamp, integration intervals only.'},
            'electrical_energy':'NOT_AVAILABLE','damage_from_jerk':'UNKNOWN'}
