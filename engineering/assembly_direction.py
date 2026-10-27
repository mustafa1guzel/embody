"""General native wheel-axis inspection and measured physical feedback.

No parameter correction, sign constraint, rollout or application occurs here.
The rolling relation is conditional kinematics, never a simulation verdict.
"""
import copy
import hashlib
import mujoco
import numpy as np
from physics.contracts import digest
from world.compiler import compile_world,initial_state

def contract():
    return {'positive_joint_rate':'Right-hand rotation about the ACTUAL native world joint axis; local +Z can point along either world lateral direction.',
        'forward':'Initial native chassis local +X, toward front_axle. Signed displacement is projected on this INITIAL world direction.',
        'ideal_rolling_relation':'For a rigid wheel on a flat plane with no slip: center velocity = radius * joint_rate * cross(axis_world, ground_normal_world). Project on initial chassis +X.',
        'torque_is_not_velocity':'Torque requests produce generalized force/acceleration, not a guaranteed rate or travel direction; initial velocity, contact, inertia, friction, slip and constraints matter.',
        'required_measurement':'Only real native dynamics plus independent replay can establish direction, contacts, force, upright and minimum travel. Compilation does not establish them.',
        'permissions':{'automatic_sign_reversal':False,'apply':False},
        'unsupported':['Detailed tire compliance','Bearing/drivetrain fidelity','Guaranteed no-slip behavior','Universal locomotion or hardware safety']}

def kinematics(project,roles):
    m,xml,compiled=compile_world(project['world']);d=initial_state(m,project['world']);mujoco.mj_forward(m,d)
    parts={s['id']:s for s in project['shape_specs']};objects={o['id']:o for o in project['world']['objects']}
    chassis=parts[roles['chassis_part_id']];gid=m.geom('geom_'+chassis['body_id']).id
    forward=d.geom_xmat[gid].reshape(3,3)[:,0].copy()
    floor=m.geom('geom_floor').id;normal=d.geom_xmat[floor].reshape(3,3)[:,2].copy();rows=[]
    for placement,r in roles['wheels'].items():
        shape=parts[r['part_id']];body=objects[r['joint_body_id']];j=m.joint('joint_'+body['id'])
        axis=d.xaxis[j.id].copy();radius=shape['parameters']['outer_diameter_m']/2
        cross=np.cross(axis,normal);projection=float(cross@forward)
        rows.append({'placement':placement,'part_id':shape['id'],'wheel_body_id':shape['body_id'],
            'joint_body_id':body['id'],'local_joint_axis':body['joint']['axis'],
            'initial_native_axis_world':axis.tolist(),'radius_m':radius,
            'initial_joint_rate_rad_s':float(d.qvel[int(m.jnt_dofadr[j.id])]),
            'actuator':copy.deepcopy(body['actuator']),
            'ideal_forward_m_per_positive_joint_rad':radius*projection,
            'ideal_forward_projection_per_positive_joint_rate':projection,
            'meaning':'Conditional no-slip rolling direction for POSITIVE JOINT RATE, not a predicted torque outcome or acceptance check.'})
    return {'status':'COMPILED_KINEMATICS_ONLY_NOT_SIMULATED','forward_axis_world':forward.tolist(),
        'ground_normal_world':normal.tolist(),'wheels':rows,'model_sha256':compiled['contract']['model_sha256'],
        'contract':contract(),'additional_integration_steps':0}

def physical_feedback(proposal,native):
    """Recompute saved-state checks and return source/identity-bound feedback."""
    from .assembly_rover import measured
    from .assembly_experiment import forward_measurement
    from .assembly import sources
    from .project import identity
    q=proposal;r=native['result'];candidate=q['proposed_project']
    if q['source_sha256']!=sources():raise ValueError('Physical feedback source identity is stale')
    if native['proposal_id']!=q['proposal_id'] or native['proposed_project_sha256']!=identity(candidate) or r['world']!=candidate['world']:
        raise ValueError('Physical feedback proposal/model identity differs')
    if native['structural']!=q['structural']:raise ValueError('Physical feedback structural proof differs')
    if not native['head_unchanged'] or native['head_sha256_after']!=q['base_project_sha256']:
        raise ValueError('Physical feedback cannot authorize a changed head')
    k=kinematics(candidate,q['assembly_plan']['roles'])
    if k['model_sha256']!=r['contract']['model_sha256'] or hashlib.sha256(r['model_xml'].encode()).hexdigest()!=k['model_sha256'] or digest(r['samples'])!=r['trajectory_sha256']:
        raise ValueError('Physical feedback native trajectory/model changed')
    observations=measured(r,native['structural'])
    if observations!=native['observations']:raise ValueError('Physical observations differ from actual saved states')
    direction=forward_measurement(native);all_checks={**observations['checks'],'signed_forward_displacement':direction['checks']['signed_forward_displacement']}
    wheels=copy.deepcopy(k['wheels']);m=mujoco.MjModel.from_xml_string(r['model_xml'])
    for w in wheels:
        j=m.joint('joint_'+w['joint_body_id']);dof=int(m.jnt_dofadr[j.id])
        w['final_joint_rate_rad_s']=r['samples'][-1]['qvel'][dof]
        if w['actuator']:
            aid=m.actuator('motor_'+w['joint_body_id']).id
            w['maximum_measured_abs_actuator_force_nm']=max(abs(s['actuator_force'][aid]) for s in r['samples'])
        else:w['maximum_measured_abs_actuator_force_nm']=None
        wheel='geom_'+w['wheel_body_id']
        w['measured_wheel_ground_pair_observations']=sum(sum(wheel in pair and 'geom_floor' in pair for pair in row['pairs']) for row in observations['contact_telemetry'])
    value={'schema_version':1,'detected_stage':'NATIVE_SIMULATION',
        'status':'PHYSICAL_FAILURE' if not all(all_checks.values()) else 'PHYSICAL_PASS',
        'construction_status':'VALID_COMPILED; distinct from measured physical acceptance',
        'proposal_id':q['proposal_id'],'proposed_project_sha256':q['resulting_project_sha256'],
        'base_project_sha256':q['base_project_sha256'],'base_revision':q['base_revision'],
        'model_sha256':r['contract']['model_sha256'],'trajectory_sha256':r['trajectory_sha256'],
        'source_sha256':copy.deepcopy(q['source_sha256']),
        'required_direction':copy.deepcopy(direction['contract']),
        'measured_signed_forward_displacement_m':direction['signed_forward_displacement_m'],
        'horizontal_displacement_m':observations['horizontal_displacement_m'],
        'forward_axis_world':direction['initial_forward_axis_world'],
        'checks':all_checks,'failed_checks':[n for n,v in all_checks.items() if not v],
        'contacts':{'wheel_ground_pair_observations':observations['wheel_ground_contact_events'],
            'unexpected_contact_count':len(observations['unexpected_contacts']),
            'meaning':'Sampled contact pairs, not distinct collision episodes or proof of no slip.'},
        'minimum_chassis_up_z_dot':observations['minimum_chassis_up_z_dot'],
        'wheels':wheels,'fresh_replay':r['independent_verification'],
        'direction_semantics':contract(),'additional_integration_steps':0,
        'repair_policy':'Feedback only. Author must supply new exact typed operations; no suggested corrected command, automatic reversal, retry or application.'}
    return {**value,'feedback_sha256':digest(value)}
