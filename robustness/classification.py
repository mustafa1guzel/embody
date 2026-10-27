"""Physical failures, impossible tasks and execution failures never collapse together."""
EPSILON=1e-8
SAFETY={'clearance_m','contacts','joint_limit_rad','peak_speed_rad_s','torque_nm'}


def classify(guard,execution,independent,margins,accepted):
    if execution=='BLOCKED':return 'EXECUTION_BLOCKED'
    if execution=='UNSUPPORTED':return 'UNSUPPORTED_MODEL'
    if guard.get('status')=='PROVEN_INFEASIBLE':return 'TASK_INFEASIBLE'
    if execution!='PASS' or independent!='PASS':return 'SIMULATION_OR_NUMERICAL_FAILURE'
    if accepted:return 'VERIFIED_WITHIN_TESTED_CONDITIONS'
    if any(k in SAFETY and v<0 for k,v in margins.items()):return 'CONTROLLER_SAFETY_VIOLATION'
    return 'CONTROLLER_REQUIREMENT_FAILURE'


def violations(result):
    if result['classification'] not in ('CONTROLLER_SAFETY_VIOLATION','CONTROLLER_REQUIREMENT_FAILURE'):return {}
    # Exact acceptance stays unchanged; this band filters fragile CE nominations.
    return {k:-v for k,v in result['margins'].items() if v < -EPSILON}


def objective(result):
    scales={'clearance_m':.05,'target_error_m':.02,'final_speed_mps':.03,'final_speed_rad_s':.03,
            'settling_speed_rad_s':.03,'settling_error_m':.02,'joint_limit_rad':.002,'peak_speed_rad_s':5.,'torque_nm':1.}
    return max((v/scales.get(k,1.) for k,v in violations(result).items()),default=0.)
