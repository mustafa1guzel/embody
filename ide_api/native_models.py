"""Fixed model capabilities; project data cannot name code, paths or executors."""
import copy,inspect,hashlib
from ide_api import rail_sweeps as rail
from ide_api import rover_reference as rover

RAIL='rail_carriage'
ROVER=rover.MODEL

def implementation(experiment_id):
    if experiment_id==rail.EXPERIMENT:return rail
    if experiment_id==rover.EXPERIMENT:return rover
    raise ValueError('Unsupported registered native experiment')

def for_model(model_id):
    if model_id==RAIL:return rail
    if model_id==ROVER:return rover
    raise ValueError('Unsupported model identifier; imports cannot register executable code')

def validate_request(value):
    if not isinstance(value,dict) or not isinstance(value.get('experiment_id'),str):raise ValueError('Registered experiment required')
    module=implementation(value['experiment_id']);return module.validate(value)

def descriptors():
    out=[]
    for identifier,module,title,defaults in [(RAIL,rail,'Rail braking',{'mass_kg':2.,'speed_mps':.4,'force_n':4.,'gap_m':1.77}),
                                           (ROVER,rover,'Rover / inclined surface',rover.DEFAULTS)]:
        is_rail=identifier==RAIL
        controller=(inspect.getsource(rover.controller_commands)+'\n' if not is_rail else '')+inspect.getsource(module.reference_controller)
        out.append({'id':identifier,'version':1,'name':title,'experiment_id':module.EXPERIMENT,
                    'fields':{k:{'bounds':list(b),'unit':module.UNITS[k]} for k,b in module.BOUNDS.items()},
                    'coupled_constraints':[] if is_rail else ['2 * wheel_radius_m <= 0.64 * length_m - 0.002 m; four equal wheels must not overlap'],
                    'defaults':copy.deepcopy(defaults),'controller_id':module.CONTROLLER,
                    'controller':{'id':module.CONTROLLER,'content':controller,'sha256':hashlib.sha256(controller.encode()).hexdigest(),'editable':False},
                    'requirements':copy.deepcopy(module.DEFAULT_CRITERIA),'environment':'rigid_rail_wall' if is_rail else 'finite_planar_ramp_and_floor',
                    'source_sha256':module.source_identity(),'execution':'IMPLEMENTED_REQUIRES_SEPARATE_EXACT_APPROVAL',
                    'verification':'CURRENT_SOURCE_NATIVE_QUALIFICATION_PENDING','policy':module.POLICY,
                    'trajectory_fields':list(module.FIELDS)+(['wall_collision','contacts'] if is_rail else ['qpos','qvel','poses','root_position_m','root_quaternion_wxyz','linear_velocity_mps','angular_velocity_radps','wheel_angles_rad','control','actuator_force','generalized_force','contacts']),
                    'measurement_definition':'RAIL_SAMPLED_MEASUREMENTS_V1' if is_rail else 'ROVER_TARGET_SAMPLED_V1',
                    'measurements':{'minimum_clearance_m':{'unit':'m','evaluation':'Minimum sampled wall surface separation'},'final_speed_mps':{'unit':'m/s','evaluation':'Absolute final joint speed'},'sampled_settling_time_s':{'unit':'s','evaluation':'Start of final low-speed sampled suffix'},'wall_contact_episodes':{'unit':'episodes','evaluation':'False-to-true wall collision transitions'},'maximum_actuator_force_n':{'unit':'N','evaluation':'Peak absolute sampled generalized force'}} if is_rail else {'signed_progress_m':{'unit':'m','evaluation':'Final root displacement projected on the fixed uphill tangent'},'target_error_m':{'unit':'m','evaluation':'Absolute target minus final signed progress'},'final_speed_mps':{'unit':'m/s','evaluation':'Norm of final native root linear velocity'},'minimum_up_dot':{'unit':'dimensionless','evaluation':'Minimum chassis up dot world Z over all samples'},'maximum_actuator_force_nm':{'unit':'N*m','evaluation':'Maximum absolute native scalar motor force; independently checked against generalized force'},'wheel_surface_observations':{'unit':'contact pairs','evaluation':'Per-wheel native ramp/floor contact observations'},'unexpected_contact_pairs':{'unit':'contact pairs','evaluation':'Any pair other than wheel/ramp or wheel/floor'}},
                    'analytical':['ideal_constant_braking_v1'] if is_rail else [],
                    'diagnostics':['clearance','final_speed','contacts','force','settling'] if is_rail else ['progress','target_error','speed','orientation','contacts','force','joint_ranges'],
                    'limitations':module.LIMITATIONS})
    return out

def descriptor(model_id):
    for value in descriptors():
        if value['id']==model_id:return value
    raise ValueError('Unsupported registered model')
