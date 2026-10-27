"""Dimensioned device interfaces, distinct from physical pins or verification."""
from jsonschema import Draft202012Validator
from world.schema import obj,ID,num
from hardware.assemblies import validate as circuit_validate
from hardware.library import pin
from world.schema import validate as world_validate

INTERFACE=obj({'id':ID,'kind':{'enum':['digital_sensor_input','analog_sample','position_command','pwm_request','motor_enable','actuator_limit','power_source','mechanical_mount']},'component':ID,'pin':{'type':'string','minLength':1,'maxLength':64},'world_object':{'anyOf':[ID,{'type':'null'}]},'unit':{'enum':['m','rad','N','N*m','V','1']},'sample_interval_s':num(.001,1),'abstraction':{'enum':['SIMULATED_DECODED_SIGNAL','STATIC_POWER_REFERENCE','MECHANICAL_REFERENCE']}})

def validate_interfaces(interfaces,world,circuit):
    if not isinstance(interfaces,list) or len(interfaces)>32:raise ValueError('Interface limit')
    world_validate(world);circuit_validate(circuit);ids=set();components={c['id']:c for c in circuit['components']};objects={o['id']:o for o in world['objects']}
    for i in interfaces:
        if not Draft202012Validator(INTERFACE).is_valid(i) or i['id'] in ids:raise ValueError('Invalid/duplicate interface')
        ids.add(i['id']);c=components.get(i['component']);p=pin(c['part'],i['pin']) if c else None
        if p is None or i['world_object'] is not None and i['world_object'] not in objects:raise ValueError('Interface target absent')
        role=c['roles'].get(i['pin'],p.role)
        spec={'digital_sensor_input':('input','m','SIMULATED_DECODED_SIGNAL'),'position_command':('input','rad','SIMULATED_DECODED_SIGNAL'),'pwm_request':('pwm','rad','SIMULATED_DECODED_SIGNAL'),'motor_enable':('output','1','SIMULATED_DECODED_SIGNAL'),'power_source':('power_out','V','STATIC_POWER_REFERENCE')}.get(i['kind'])
        if spec and (role,i['unit'],i['abstraction'])!=spec:raise ValueError('Interface role/unit/abstraction mismatch')
        if i['kind']=='analog_sample':raise ValueError('Analog sampled plant/catalog capability unavailable')
        if i['kind']=='mechanical_mount' and (i['world_object'] is None or i['unit']!='m' or i['abstraction']!='MECHANICAL_REFERENCE'):raise ValueError('Mount requires a world reference in metres')
        if i['kind']=='actuator_limit':
            target=objects.get(i['world_object']);actuator=target.get('actuator') if target else None
            if not actuator or i['unit']!=actuator['unit'] or i['abstraction']!='SIMULATED_DECODED_SIGNAL' or role not in ('input','pwm'):raise ValueError('Actuator limit requires an actual actuator, matching force/torque units and a decoded command pin')
    return interfaces
