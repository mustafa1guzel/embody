"""Typed local data operations; no code, execution, paths, API calls or apply tool."""
import copy
from jsonschema import Draft202012Validator
from world.schema import obj,ID,num,vec,JOINT,MOTOR,validate as validate_world
from world.objects import primitive,LIBRARY
from hardware.assemblies import validate as validate_circuit,instance,connect,remove_wire
from hardware.library import CATALOG
from devices.contracts import DeviceSpec
from hardware.tool_contract import ENDPOINT
from .interfaces import INTERFACE


def action(name,fields):return obj({'kind':{'type':'string','enum':[name]},**fields})
TARGET={'target':ID}
SCHEMAS=[action('set_body_kind',{**TARGET,'behavior':{'enum':['static','dynamic','anchor','link','obstacle']}}),action('set_shape',{**TARGET,'geometry':{'enum':['box','sphere','cylinder','capsule','plane']}}),action('create_object',{'primitive':{'enum':list(LIBRARY)},'id':ID,'parent':{'anyOf':[ID,{'type':'null'}]}}),action('remove_object',TARGET),action('duplicate_object',{**TARGET,'id':ID}),action('rename_object',{**TARGET,'name':{'type':'string','minLength':1,'maxLength':80}}),action('move_object',{**TARGET,'position_m':vec(-10,10)}),action('rotate_object',{**TARGET,'rotation_rad':vec(-6.283185307179586,6.283185307179586)}),action('set_geometry',{**TARGET,'dimensions_m':vec(.005,5)}),action('set_mass',{**TARGET,'mass_kg':num(0,100)}),action('create_joint',{**TARGET,'joint':{'anyOf':[JOINT,{'type':'null'}]}}),action('set_joint_limit',{**TARGET,'range':{'type':'array','items':num(-10,10),'minItems':2,'maxItems':2}}),action('set_actuator',{**TARGET,'actuator':{'anyOf':[MOTOR,{'type':'null'}]}}),action('set_actuator_limit',{**TARGET,'limit':num(.001,100)}),action('reparent_object',{**TARGET,'parent':{'anyOf':[ID,{'type':'null'}]}}),action('add_component',{'part':{'enum':list(CATALOG)},'id':ID}),action('remove_component',TARGET),action('move_component',{**TARGET,'position_m':vec(-10,10),'rotation_rad':vec(-6.283185307179586,6.283185307179586)}),action('connect_pins',{'a':ENDPOINT,'b':ENDPOINT}),action('disconnect_pins',{'wire_id':{'type':'string','pattern':'^[A-Za-z][A-Za-z0-9_-]{0,63}$','maxLength':64}}),action('set_device_mass',{'mass_kg':num(.01,2)}),action('set_device_actuator_limit',{'torque_limit_nm':num(.005,.17)}),action('bind_interface',{'interface':INTERFACE})]
SCHEMAS.append(action('set_pin_role',{**TARGET,'pin':{'type':'string','minLength':1,'maxLength':64},'role':{'enum':['input','output','pwm']}}))
SCHEMAS.append(action('create_free_root',{'id':ID,'mass_kg':num(.001,2),'position_m':vec(-10,10),'dimensions_m':vec(.005,.6)}))
SCHEMAS.append(action('set_static_surface_friction',{**TARGET,'friction':vec(0,5)}))
from shapebase.operations import SCHEMAS as SHAPE_SCHEMAS,NAMES as SHAPE_NAMES,MOBILITY_SCHEMAS
SCHEMAS.extend(SHAPE_SCHEMAS+MOBILITY_SCHEMAS)
OPERATIONS={'type':'array','minItems':1,'maxItems':16,'items':{'anyOf':SCHEMAS}}
CLASSIFICATIONS={s['properties']['kind']['enum'][0]:{'permission':'REVIEW_ONLY_MODEL_PROPOSAL; explicit local user approval required to apply','units':'SI; metres, radians, kg, N, N*m','failure':'Reject entire batch without mutation; no alias translation','result':'Validated proposed project copy, diagnostics and revision/hash','subsystem':'circuit' if s['properties']['kind']['enum'][0] in ('add_component','remove_component','move_component','connect_pins','disconnect_pins','set_pin_role') else 'device' if s['properties']['kind']['enum'][0].startswith('set_device') else 'interfaces' if s['properties']['kind']['enum'][0]=='bind_interface' else 'shapes' if s['properties']['kind']['enum'][0] in SHAPE_NAMES else 'world'} for s in SCHEMAS}


def check_operations(operations):
    if not Draft202012Validator(OPERATIONS).is_valid(operations):raise ValueError('Invalid typed engineering operations or batch size (1..16)')
    return operations


def execute_copy(project,operations):
    check_operations(operations);p=copy.deepcopy(project)
    for op in operations:
        k=op['kind'];w=p['world'];c=p['circuit'];target=op.get('target')
        if CLASSIFICATIONS[k]['subsystem']=='shapes':
            from shapebase.operations import execute
            execute(p,op)
        elif CLASSIFICATIONS[k]['subsystem']=='world':
            governed={s['body_id'] for s in p.get('shape_specs',[])}
            constrained={m['body_id'] for s in p.get('shape_specs',[]) for m in s['mounted_bodies']}
            if target in governed and k not in ('rename_object',):raise ValueError('Parametric bodies require SHAPEBASE review operations')
            if target in constrained and k in ('move_object','rotate_object','reparent_object','remove_object'):raise ValueError('Body placement is constrained by a ShapeSpec attachment frame')
            o=next((o for o in w['objects'] if o['id']==target),None)
            if k=='create_free_root':
                if any(x['id']==op['id'] for x in w['objects']):raise ValueError('Object already exists')
                # Typed intent, existing valid defaults. No caller joint fields,
                # implicit mass or correction of a legacy create_joint operation.
                o=primitive('dynamic_body',op['id']);o.update(mass_kg=op['mass_kg'],position_m=op['position_m'],dimensions_m=op['dimensions_m']);w['objects'].append(o)
            elif k=='create_object':
                if any(o['id']==op['id'] for o in w['objects']):raise ValueError('Object already exists')
                o=primitive(op['primitive'],op['id']);o['parent']=op['parent'];w['objects'].append(o)
            elif o is None:raise ValueError('Object target absent')
            elif k=='remove_object':
                if any(x['parent']==target for x in w['objects']):raise ValueError('Remove children first')
                w['objects'].remove(o)
            elif k=='duplicate_object':
                if any(x['id']==op['id'] or x['parent']==target for x in w['objects']):raise ValueError('Duplicate requires new identity and leaf target')
                new=copy.deepcopy(o);new.update(id=op['id'],name=o['name'][:70]+' copy');w['objects'].append(new)
            elif k=='set_body_kind':o['kind']=op['behavior']
            elif k=='set_shape':o['geometry']=op['geometry']
            elif k=='rename_object':o['name']=op['name']
            elif k=='move_object':o['position_m']=op['position_m']
            elif k=='rotate_object':o['rotation_rad']=op['rotation_rad']
            elif k=='set_geometry':o['dimensions_m']=op['dimensions_m']
            elif k=='set_mass':o['mass_kg']=op['mass_kg']
            elif k=='set_static_surface_friction':
                if o['parent'] is not None or o['kind'] not in ('static','obstacle') or not o['contact']['enabled']:raise ValueError('Friction edit requires an enabled fixed world-root collision surface')
                o['contact']['friction']=op['friction']
            elif k=='create_joint':o['joint']=op['joint']
            elif k=='set_joint_limit':
                if not o['joint']:raise ValueError('Joint absent')
                o['joint']['range']=op['range']
            elif k=='set_actuator':o['actuator']=op['actuator']
            elif k=='set_actuator_limit':
                if not o['actuator']:raise ValueError('Actuator absent')
                o['actuator']['limit']=op['limit']
            elif k=='reparent_object':o['parent']=op['parent']
            w['revision']+=1
            # Validate final topology at batch end, enabling dependent assembly edits.
        elif CLASSIFICATIONS[k]['subsystem']=='circuit':
            if k=='set_pin_role':
                item=next((x for x in c['components'] if x['id']==target),None)
                pin=next((x for x in CATALOG[item['part']].pins if x.id==op['pin']),None) if item else None
                if not pin or pin.role!='configurable' or op['role'] not in pin.capabilities:raise ValueError('Unsupported configurable pin role')
                item['roles'][op['pin']]=op['role'];c['revision']+=1
            elif k=='connect_pins':p['circuit']=connect(c,op['a'],op['b'])
            elif k=='disconnect_pins':p['circuit']=remove_wire(c,op['wire_id'])
            elif k=='add_component':
                c['components'].append(instance(c,op['part'],identifier_=op['id']));c['revision']+=1
            elif k=='move_component':
                item=next((x for x in c['components'] if x['id']==target),None)
                if item is None:raise ValueError('Component absent')
                item['position_m']=op['position_m'];item['rotation_rad']=op['rotation_rad'];c['revision']+=1
            elif k=='remove_component':
                if not any(x['id']==target for x in c['components']):raise ValueError('Component absent')
                for wire in list(c['wires']):
                    if target in (wire['a']['component'],wire['b']['component']):c=remove_wire(c,wire['id'])
                c['components']=[x for x in c['components'] if x['id']!=target];c['revision']+=1;p['circuit']=c
            validate_circuit(p['circuit'])
        elif CLASSIFICATIONS[k]['subsystem']=='device':
            p['device_spec']['mechanical']['mass_kg' if k=='set_device_mass' else 'torque_limit_nm']=op.get('mass_kg',op.get('torque_limit_nm'))
            from .project import device_contract
            device_contract(p)
            if p.get('creation',{}).get('state')=='BUILT' and p['creation']['family']=='sensor_barrier':
                roles=p['creation']['world_roles'];objects={o['id']:o for o in p['world']['objects']}
                if k=='set_device_mass':objects[roles['beam']]['mass_kg']=op['mass_kg']
                else:
                    a=objects[roles['pivot']]['actuator'];a['limit']=op['torque_limit_nm'];a['command']=max(-a['limit'],min(a['limit'],a['command']))
                p['world']['revision']+=1
        else:
            i=op['interface']
            if any(x['id']==i['id'] for x in p['interfaces']):raise ValueError('Interface already exists')
            p['interfaces'].append(copy.deepcopy(i))
    # Stable new wire/net IDs make preview and independent replay identical.
    from physics.contracts import digest
    from hardware.assemblies import netlist
    old_wires={x['id'] for x in project['circuit']['wires']};old_nets={x['id'] for x in project['circuit']['nets']}
    mapping={n:'net_'+digest({'members':ends})[:32] for n,ends in netlist(p['circuit']).items() if n not in old_nets}
    for n in p['circuit']['nets']:
        if n['id'] in mapping:n.update(id=mapping[n['id']],name=mapping[n['id']])
    for index,wire in enumerate(p['circuit']['wires']):
        if wire['net'] in mapping:wire['net']=mapping[wire['net']]
        if wire['id'] not in old_wires:wire['id']='wire_'+digest({'index':index,'a':wire['a'],'b':wire['b'],'net':wire['net']})[:32]
    if p.get('creation',{}).get('state')=='BUILT':
        from .device_bindings import synchronize
        synchronize(p,operations)
    from shapebase.operations import synchronize as synchronize_shapes
    synchronize_shapes(p)
    validate_world(p['world'])
    from shapebase.model import validate_project_shapes
    validate_project_shapes(p);p['revision']+=1
    return p
