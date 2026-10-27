"""One versioned project binds authoritative domain documents and evidence IDs."""
import copy,json,hashlib,re
from pathlib import Path
from world.schema import validate as world_validate,identity as world_identity
from world.objects import empty_world
from hardware.assemblies import validate as circuit_validate,identity as circuit_identity
from hardware.template import barrier
from devices.contracts import DeviceSpec
from physics.contracts import digest
from .interfaces import validate_interfaces

ROOT=Path(__file__).resolve().parents[1]


def controller_identity():return hashlib.sha256((ROOT/'devices/controller.py').read_bytes()).hexdigest()

def device_contract(p):
    if p.get('creation',{}).get('family')=='sensor_barrier':
        from .generated_contract import GeneratedSpec
        return GeneratedSpec.from_dict(p['device_spec'])
    return DeviceSpec.from_dict(p['device_spec'])

def new_project():
    return {'schema_version':1,'id':'engineering_project','revision':0,'world':empty_world(),'circuit':barrier(),'device_spec':json.loads(json.dumps(DeviceSpec().to_dict())),'controller_sha256':controller_identity(),'interfaces':[{'id':'distance_input','kind':'digital_sensor_input','component':'board','pin':'IO19','world_object':None,'unit':'m','sample_interval_s':.07,'abstraction':'SIMULATED_DECODED_SIGNAL'},{'id':'servo_request','kind':'pwm_request','component':'board','pin':'IO23','world_object':None,'unit':'rad','sample_interval_s':.02,'abstraction':'SIMULATED_DECODED_SIGNAL'},{'id':'servo_power','kind':'power_source','component':'supply','pin':'4V8','world_object':None,'unit':'V','sample_interval_s':1.,'abstraction':'STATIC_POWER_REFERENCE'}],'evidence_refs':[],'design_plans':[]}


def validate(p):
    expected={'schema_version','id','revision','world','circuit','device_spec','controller_sha256','interfaces','evidence_refs','design_plans'}
    if isinstance(p,dict) and 'creation' in p:expected.add('creation')
    if isinstance(p,dict) and 'shape_specs' in p:expected.add('shape_specs')
    if not isinstance(p,dict) or set(p)!=expected or type(p['schema_version']) is not int or p['schema_version']!=1 or not (p['id']=='engineering_project' and 'creation' not in p or isinstance(p['id'],str) and re.fullmatch(r'p_[0-9a-f]{32}',p['id']) and 'creation' in p) or type(p['revision']) is not int or not 0<=p['revision']<=999999:raise ValueError('Invalid project schema/revision')
    if len(json.dumps(p,allow_nan=False).encode())>140000:raise ValueError('Project size limit')
    world_validate(p['world']);circuit_validate(p['circuit']);device_contract(p)
    if p['controller_sha256']!=controller_identity():raise ValueError('Trusted reference controller identity changed; new evidence/review required')
    validate_interfaces(p['interfaces'],p['world'],p['circuit'])
    if 'shape_specs' in p:
        from shapebase.model import validate_project_shapes
        if 'creation' in p:raise ValueError('SHAPEBASE requires an independent non-generated project')
        validate_project_shapes(p)
    if 'creation' in p:
        from .creation_contract import validate_creation
        validate_creation(p)
    if not isinstance(p['evidence_refs'],list) or len(p['evidence_refs'])>32:raise ValueError('Evidence reference limit')
    for e in p['evidence_refs']:
        if not isinstance(e,dict) or set(e)!={'id','kind','sha256','base_project_sha256'}:raise ValueError('Invalid evidence reference')
        if e['kind'] not in ('world','device') or not isinstance(e['id'],str) or len(e['id'])>64 or any(x not in 'abcdefghijklmnopqrstuvwxyz0123456789_' for x in e['id']):raise ValueError('Invalid evidence identifier')
        for key in ('sha256','base_project_sha256'):
            if not isinstance(e[key],str) or len(e[key])!=64 or any(x not in '0123456789abcdef' for x in e[key]):raise ValueError('Invalid evidence identity')
    if not isinstance(p['design_plans'],list) or len(p['design_plans'])>16:raise ValueError('Plan reference limit')
    for r in p['design_plans']:
        if not isinstance(r,dict) or set(r)!={'id','revision','sha256'} or type(r['revision']) is not int or not 0<=r['revision']<=999999 or not isinstance(r['id'],str) or not 1<=len(r['id'])<=64 or not isinstance(r['sha256'],str) or len(r['sha256'])!=64 or any(x not in '0123456789abcdef' for x in r['sha256']):raise ValueError('Invalid plan reference')
    return copy.deepcopy(p)


def identity(p):return digest(validate(p))

def identities(p):
    return {'project':identity(p),'revision':p['revision'],'world':world_identity(p['world']),'circuit':circuit_identity(p['circuit']),'device_contract':device_contract(p).identity,'controller':p['controller_sha256'],'interfaces':digest(p['interfaces'])}


def domain_identity(p):
    p=validate(p);return digest({k:p[k] for k in ('id','world','circuit','device_spec','controller_sha256','interfaces',*(['creation'] if 'creation' in p else []),*(['shape_specs'] if 'shape_specs' in p else []))})
