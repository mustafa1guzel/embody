"""Parametric recipes -> existing bounded typed batches, starting with no objects."""
import copy,json
from uuid import uuid4
from hardware.assemblies import empty
from world.objects import empty_world
from world.compiler import compile_world
from hardware.advanced import advanced_inspect
from devices.contracts import DeviceSpec
from .generated_contract import default_generated_spec
from .project import controller_identity,identity,validate
from .actions import execute_copy,check_operations
from .plans import create_plan,validate_plan
from .device_bindings import PARTS,synchronize,check_binding

def empty_project(family,request_sha256,project_id=None):
    identifier=project_id or 'p_'+uuid4().hex
    w=empty_world();w.update(id='w_'+identifier[2:],objects=[]);w['environment']['duration_s']=5.
    a=empty();a['id']='a_'+identifier[2:]
    meta={'family':family,'state':'EMPTY','plan_id':'plan_'+uuid4().hex,'request_sha256':request_sha256,'template_version':'day16_v1','origin':'DETERMINISTIC_OFFLINE; not live AI synthesis','world_roles':{},'component_roles':{},'controller_family':'NONE','mounts':[],'concept_envelopes':[],'dependencies':[],'capabilities':['Bounded geometric concept'] if family=='smart_glasses' else ['Native generated hinged-barrier control'],'unsupported':['No real hardware or MCU execution','Electrical current, acoustic, thermal and manufacturing behavior UNKNOWN'],'empty_project_sha256':None}
    return validate(json.loads(json.dumps({'schema_version':1,'id':identifier,'revision':0,'world':w,'circuit':a,'device_spec':default_generated_spec().to_dict() if family=='sensor_barrier' else DeviceSpec().to_dict(),'controller_sha256':controller_identity(),'interfaces':[],'evidence_refs':[],'design_plans':[],'creation':meta})))

def recipe(requirements,project):
    if requirements['blocked']:raise ValueError('Unresolved requirements block construction')
    if project['creation']['state']!='EMPTY' or project['world']['objects'] or project['circuit']['components']:raise ValueError('Creation starts only from an actually empty project')
    p=requirements['parameters'];prefix=project['id'];batches=[];world_roles={};component_roles={};meta=copy.deepcopy(project['creation'])
    def object(role,name,kind,position,dimensions,mass=0,parent=None,joint='default',actuator='default'):
        identifier=prefix+'_'+role;world_roles[role]=identifier
        ops=[{'kind':'create_object','primitive':kind,'id':identifier,'parent':parent},{'kind':'rename_object','target':identifier,'name':name},{'kind':'move_object','target':identifier,'position_m':position},{'kind':'set_geometry','target':identifier,'dimensions_m':dimensions},{'kind':'set_mass','target':identifier,'mass_kg':mass}]
        if joint!='default':ops.append({'kind':'create_joint','target':identifier,'joint':joint})
        if actuator!='default':ops.append({'kind':'set_actuator','target':identifier,'actuator':actuator})
        batches.append(ops);return identifier
    if requirements['family']=='sensor_barrier':
        object('floor','Ground','floor',[0,0,0],[4,4,.1])
        support=object('support','Stationary barrier support','anchor',[0,0,.08],[.05,.05,.16])
        pivot=object('pivot','Driven barrier hinge','motor',[0,0,p['height_m']-.08],[.005,.005,.005],.001,support,{'kind':'revolute','axis':[0,-1,0],'range':[0,1.65],'initial_position':0,'initial_velocity':0,'damping':.015},{'limit':p['torque_nm'],'command':0,'unit':'N*m'})
        object('beam','Barrier beam','rigid_link',[p['span_m']/2,0,0],[p['span_m'],.02,.016],p['mass_kg'],pivot,None,None)
        object('sensor','Sensor ray mounting reference','anchor',[0,-.12,.08],[.024,.05,.024])
        object('board_mount','Board location reference — mass excluded','anchor',[-.07,0,.015],[.055,.028,.012])
        object('target','Approaching kinematic target','obstacle',[.8,-.12,.08],[.08,.09,.12])
        placements={'board':[-.07,0,.015],'sensor':[0,-.12,.08],'servo':[0,0,p['height_m']],'supply':[-.08,-.08,.015],'upper':[-.04,-.08,.015],'lower':[-.04,-.11,.015]}
        ops=[]
        for role,part in PARTS.items():
            identifier=prefix+'_'+role;component_roles[role]=identifier
            ops.extend([{'kind':'add_component','part':part,'id':identifier},{'kind':'move_component','target':identifier,'position_m':placements[role],'rotation_rad':[0,0,0]}])
        ops.extend({'kind':'set_pin_role','target':component_roles['board'],'pin':pin,'role':role} for pin,role in [('IO18','output'),('IO19','input'),('IO23','pwm')]);batches.append(ops)
        edges=[('supply','5V','board','5V'),('supply','5V','sensor','VCC'),('supply','4V8','servo','VCC'),('supply','GND','board','GND'),('supply','GND','sensor','GND'),('supply','GND','servo','GND'),('board','IO18','sensor','TRIG'),('sensor','ECHO','upper','A'),('upper','B','board','IO19'),('upper','B','lower','A'),('lower','B','supply','GND'),('board','IO23','servo','SIGNAL')]
        batches.append([{'kind':'connect_pins','a':{'component':component_roles[a],'pin':pa},'b':{'component':component_roles[b],'pin':pb}} for a,pa,b,pb in edges])
        interfaces=[]
        for name,kind,role,pin,world,unit,abstraction in [('distance','digital_sensor_input','board','IO19','sensor','m','SIMULATED_DECODED_SIGNAL'),('request','pwm_request','board','IO23','pivot','rad','SIMULATED_DECODED_SIGNAL'),('authority','actuator_limit','servo','SIGNAL','pivot','N*m','SIMULATED_DECODED_SIGNAL'),('mount','mechanical_mount','sensor','GND','sensor','m','MECHANICAL_REFERENCE'),('power','power_source','supply','4V8',None,'V','STATIC_POWER_REFERENCE')]:
            interfaces.append({'kind':'bind_interface','interface':{'id':prefix+'_'+name,'kind':kind,'component':component_roles[role],'pin':pin,'world_object':world_roles[world] if world else None,'unit':unit,'sample_interval_s':.07 if name=='distance' else .02,'abstraction':abstraction}})
        batches.append(interfaces)
        meta.update(controller_family='TRUSTED_BARRIER_V1',mounts=[{'component':component_roles[role],'world_object':world_roles[world],'kind':kind,'electronic_mass_included':False} for role,world,kind in [('sensor','sensor','GEOMETRIC_SENSOR'),('board','board_mount','VISUAL_ONLY'),('servo','pivot','VISUAL_ONLY')]])
    else:
        width=p['frame_width_m'];temple=p['temple_length_m'];thickness=p['frame_thickness_m'];z=.18
        frame=object('frame','Concept front frame — assumed dimensions','anchor',[0,0,z],[width,thickness,thickness])
        meta['concept_envelopes'].append({'world_object':frame,'subsystem':'frame','assumed_mass_kg':.006,'capability':'GEOMETRY_ONLY','verified_functionality':False})
        entries=[('bridge','Bridge region',[0,0,-.012],[.018,thickness,thickness],.001),('lens_l','Left lens region — optics UNKNOWN',[-width*.24,0,-.02],[width*.40,.005,.035],.003),('lens_r','Right lens region — optics UNKNOWN',[width*.24,0,-.02],[width*.40,.005,.035],.003),('temple_l','Left temple — concept',[-width/2,temple/2,0],[thickness,temple,thickness],.004),('temple_r','Right temple — concept',[width/2,temple/2,0],[thickness,temple,thickness],.004),('camera','CAMERA envelope — unavailable',[-width*.36,0,.008],[.012,.012,.008],.002),('mic','MICROPHONE envelope — unavailable',[width*.36,.015,0],[.006,.006,.005],.001),('speaker_l','LEFT SPEAKER envelope — unavailable',[-width/2,temple*.72,0],[.01,.018,.006],.002),('speaker_r','RIGHT SPEAKER envelope — unavailable',[width/2,temple*.72,0],[.01,.018,.006],.002),('processor','PROCESSOR / RF envelope — unavailable',[-width/2,temple*.36,0],[.016,.026,.006],.004),('battery','BATTERY envelope — safety UNKNOWN',[width/2,temple*.38,0],[.012,.035,.008],.008),('regulator','POWER / BMS envelope — unavailable',[width/2,temple*.62,0],[.01,.016,.005],.002),('compartment','Electronics compartment — concept',[-width/2,temple*.35,0],[.018,.045,.012],.003)]
        for role,name,pos,dims,mass in entries:
            identifier=object(role,name,'box',pos,dims,parent=frame)
            meta['concept_envelopes'].append({'world_object':identifier,'subsystem':role,'assumed_mass_kg':mass,'capability':'GEOMETRY_ONLY','verified_functionality':False})
            meta['dependencies'].append({'source':identifier,'target':frame,'kind':'PLANNING_ONLY'})
        meta['unsupported']+=['No active camera/audio/processor/battery/RF catalog selected','Optics, acoustics, thermal, battery safety, wearability and manufacturing UNKNOWN','Provisional mass budget is an assumption, excluded from native static layout mass']
    meta.update(state='BUILT',world_roles=world_roles,component_roles=component_roles,empty_project_sha256=identity(project))
    if len(batches)>16:raise ValueError('Creation stage limit')
    for batch in batches:check_operations(batch)
    return batches,meta

def build_copy(project,batches,metadata):
    if len(batches)>16 or not batches:raise ValueError('Creation requires 1..16 bounded stages')
    candidate=copy.deepcopy(project);phases=[]
    for i,batch in enumerate(batches):
        candidate=execute_copy(candidate,batch);phases.append({'stage':i,'operations':len(batch),'uncommitted_sha256':__import__('physics.contracts',fromlist=['digest']).digest(candidate)})
    candidate['creation']=copy.deepcopy(metadata);candidate['revision']=project['revision']+1
    synchronize(candidate);candidate=validate(candidate);_,_,compiled=compile_world(candidate['world']);electrical=advanced_inspect(candidate['circuit'])
    if metadata['family']=='sensor_barrier':check_binding(candidate)
    if electrical['errors']:raise ValueError('Construction electrical errors')
    return candidate,{'world':'VALID_COMPILED','world_contract_sha256':compiled['contract_sha256'],'electrical':electrical,'uncommitted_phases':phases,'simulation':'NOT_RUN','concept_mass_assumptions_kg':sum(e['assumed_mass_kg'] for e in metadata['concept_envelopes'])}

def design_plan(requirements,project,batches):
    plan=create_plan(requirements['request'],project);plan['id']=project['creation']['plan_id'];plan['proposed_actions']=[];plan['construction_batches']=copy.deepcopy(batches)
    plan['physical_assumptions']=['Numerical geometry/mass values are explicit reviewable assumptions, not sourced manufactured dimensions.','Complete supported construction is recorded in ordered bounded construction_batches.']
    if requirements['family']=='smart_glasses':
        plan['functional_requirements'].append({'id':'concept_layout','statement':'Create an editable primitive-based physical concept.','verification':'Bounded world schema and native compilation, not active electronics.','supported':True});plan['coverage']['supported_requirements']+=1;plan['coverage']['total_requirements']+=1
    return validate_plan(plan)
