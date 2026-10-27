"""Typed role bindings and pose coupling; no electronic mass or MCU fiction."""
import copy
import mujoco
import numpy as np
from hardware.library import CATALOG
from hardware.validation import inspect
from hardware.advanced import advanced_inspect
from .generated_contract import GeneratedSpec

PARTS={'board':'esp32_devkitc_v4_wroom32','sensor':'hcsr04_sen15569','servo':'towerpro_sg90_digital','supply':'regulated_dual_supply','upper':'resistor_2200','lower':'resistor_3300'}

def synchronize(p,operations=(),circuit_source=False):
    m=p.get('creation',{})
    if m.get('state')!='BUILT' or m['family']!='sensor_barrier':return p
    objects={o['id']:o for o in p['world']['objects']};components={o['id']:o for o in p['circuit']['components']}
    beam=objects.get(m['world_roles']['beam'])
    if beam and beam['dimensions_m'][0]!=p['device_spec']['mechanical']['length_m']:
        beam['position_m']=[beam['dimensions_m'][0]/2,0,0]
    for mount in m['mounts']:
        if mount['kind']!='GEOMETRIC_SENSOR':continue
        world=objects.get(mount['world_object']);component=components.get(mount['component'])
        if not world or not component:raise ValueError('Required sensor mount absent')
        from_circuit=circuit_source or any(o['kind']=='move_component' and o['target']==component['id'] for o in operations)
        if from_circuit:
            world['position_m']=list(component['position_m']);world['rotation_rad']=list(component['rotation_rad']);p['world']['revision']+=1
        elif component['position_m']!=world['position_m'] or component['rotation_rad']!=world['rotation_rad']:
            component['position_m']=list(world['position_m']);component['rotation_rad']=list(world['rotation_rad']);p['circuit']['revision']+=1
    p['device_spec']=derived_spec(p).to_dict();return p

def derived_spec(p):
    roles=p['creation']['world_roles'];objects={o['id']:o for o in p['world']['objects']}
    try:beam=objects[roles['beam']];pivot=objects[roles['pivot']];sensor=objects[roles['sensor']];target=objects[roles['target']]
    except KeyError:raise ValueError('Required generated mechanism role absent') from None
    d=copy.deepcopy(p['device_spec']);d['mechanical'].update(length_m=beam['dimensions_m'][0],mass_kg=beam['mass_kg'],torque_limit_nm=pivot['actuator']['limit'],damping_nm_s_rad=pivot['joint']['damping'])
    q=np.empty(4);mat=np.empty(9);mujoco.mju_euler2Quat(q,np.array(sensor['rotation_rad']), 'XYZ');mujoco.mju_quat2Mat(mat,q)
    d['sensor'].update(origin_m=list(sensor['position_m']),direction=(mat.reshape(3,3)@np.array([1.,0,0])).tolist());d['environment'].update(initial_object_x_m=target['position_m'][0],object_half_extent_m=target['dimensions_m'][0]/2)
    return GeneratedSpec.from_dict(d)

def check_binding(p):
    m=p.get('creation',{})
    if m.get('state')!='BUILT' or m.get('family')!='sensor_barrier' or m.get('controller_family')!='TRUSTED_BARRIER_V1':raise ValueError('No supported generated controller/plant binding')
    objects={o['id']:o for o in p['world']['objects']};r=m['world_roles'];c={c['id']:c for c in p['circuit']['components']};roles=m['component_roles']
    for role,part in PARTS.items():
        if c.get(roles.get(role),{}).get('part')!=part:raise ValueError('Catalog role mismatch: '+role)
    board=c[roles['board']]
    if board['roles']!={'IO18':'output','IO19':'input','IO23':'pwm'}:raise ValueError('Generated GPIO binding mismatch')
    electrical=inspect(p['circuit']);advanced=advanced_inspect(p['circuit'])
    if electrical['errors'] or advanced['errors']:raise ValueError('Electrical preconditions failed; no generated dynamics')
    membership={tuple(e):n for n,ends in electrical['netlist'].items() for e in ends}
    net=lambda role,pin:membership.get((roles[role],pin))
    if not net('board','IO18') or net('board','IO18')!=net('sensor','TRIG') or not net('board','IO23') or net('board','IO23')!=net('servo','SIGNAL'):raise ValueError('Generated signal path disconnected')
    if not any(v['input_net']==net('sensor','ECHO') and v['output_net']==net('board','IO19') for v in electrical['calculations']):raise ValueError('Supported divider missing')
    pivot,beam=objects[r['pivot']],objects[r['beam']]
    if pivot['geometry']!='box' or pivot['joint'] is None or pivot['joint']['kind']!='revolute' or pivot['joint']['axis']!=[0,-1,0] or pivot['joint']['range']!=[0,1.65] or pivot['joint']['initial_position'] or pivot['joint']['initial_velocity'] or not pivot['actuator'] or pivot['actuator']['unit']!='N*m':raise ValueError('Unsupported generated hinge binding')
    if beam['parent']!=pivot['id'] or beam['joint'] or beam['actuator'] or beam['geometry']!='box' or beam['rotation_rad']!=[0,0,0] or beam['position_m']!=[beam['dimensions_m'][0]/2,0,0] or beam['dimensions_m'][1:]!=[.02,.016]:raise ValueError('Unsupported generated beam geometry')
    if objects[r['sensor']]['parent'] is not None or objects[r['target']]['parent'] is not None or objects[r['target']]['kind'] not in ('static','obstacle') or objects[r['target']]['geometry']!='box':raise ValueError('Unsupported target/sensor transform')
    if p['world']['environment']['duration_s']!=5. or p['world']['environment']['timestep_s']!=.005:raise ValueError('Frozen generated protocol duration/timestep mismatch')
    spec=derived_spec(p)
    if spec.to_dict()!=p['device_spec']:raise ValueError('Stale generated device parameters')
    return spec,advanced
