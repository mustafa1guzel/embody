"""Deterministic supported request -> reviewable plan, never a generated device."""
import copy
from jsonschema import Draft202012Validator
from physics.contracts import digest
from world.schema import obj,ID
from .actions import SCHEMAS,OPERATIONS,execute_copy
from .project import identity,domain_identity

TEXT={'type':'string','minLength':1,'maxLength':1000}
TEXTS={'type':'array','items':TEXT,'maxItems':24}
PLAN_SCHEMA=obj({'schema_version':{'const':1},'id':ID,'revision':{'type':'integer','minimum':0,'maximum':999999},'base_project_sha256':{'type':'string','pattern':'^[0-9a-f]{64}$'},'base_domain_sha256':{'type':'string','pattern':'^[0-9a-f]{64}$'},'user_goal':TEXT,'family':{'enum':['sensor_barrier','gripper','smart_glasses']},'status':{'enum':['DRAFT_FOR_REVIEW','REVIEWED_PROPOSAL_ONLY']},'origin':{'const':'DETERMINISTIC_DEVELOPER_AUTHORED_PLANNING; not live AI'},'functional_requirements':{'type':'array','items':obj({'id':ID,'statement':TEXT,'verification':TEXT,'supported':{'type':'boolean'}}),'minItems':1,'maxItems':16},'nonfunctional_constraints':TEXTS,'component_candidates':{'type':'array','items':obj({'role':TEXT,'catalog_id':{'anyOf':[TEXT,{'type':'null'}]},'availability':{'enum':['CATALOG_AVAILABLE','UNAVAILABLE']},'rationale':TEXT}),'maxItems':16},'required_subsystems':TEXTS,'required_signals_interfaces':TEXTS,'mechanical_structures':TEXTS,'sensors':TEXTS,'actuators':TEXTS,'power_requirements':TEXTS,'control_software_requirements':TEXTS,'physical_assumptions':TEXTS,'environmental_conditions':TEXTS,'supported_verification_pathways':TEXTS,'unknowns':TEXTS,'missing_catalog_capabilities':TEXTS,'risks_dependencies':TEXTS,'proposed_actions':{'type':'array','items':{'anyOf':SCHEMAS},'maxItems':16},'blocked_steps':{'type':'array','items':obj({'id':ID,'status':{'const':'BLOCKED'},'reason':TEXT}),'maxItems':24},'coverage':obj({'supported_requirements':{'type':'integer','minimum':0,'maximum':16},'total_requirements':{'type':'integer','minimum':1,'maximum':16},'completion':{'const':'PLAN_ONLY; no manufactured, executed or validated device'}})})


PLAN_SCHEMA['properties']['construction_batches']={'type':'array','minItems':1,'maxItems':16,'items':OPERATIONS}

def validate_plan(p):
    if not Draft202012Validator(PLAN_SCHEMA).is_valid(p):raise ValueError('Invalid DeviceDesignPlan')
    if type(p['revision']) is not int or p['coverage']['supported_requirements']!=sum(r['supported'] for r in p['functional_requirements']) or p['coverage']['total_requirements']!=len(p['functional_requirements']):raise ValueError('Invalid plan revision/coverage')
    from hardware.library import CATALOG
    for c in p['component_candidates']:
        if (c['availability']=='CATALOG_AVAILABLE')!=(c['catalog_id'] in CATALOG):raise ValueError('Plan catalog availability mismatch')
    return copy.deepcopy(p)


def create_plan(goal,project):
    if not isinstance(goal,str) or not 1<=len(goal)<=1000:raise ValueError('Bounded goal required')
    text=goal.lower()
    family='sensor_barrier' if 'barrier' in text else 'gripper' if 'gripper' in text else 'smart_glasses' if 'glasses' in text else None
    if family is None:raise ValueError('Unsupported planning family; barrier, gripper and smart glasses only')
    reqs=[]
    def req(i,statement,verification,supported):reqs.append({'id':i,'statement':statement,'verification':verification,'supported':supported})
    p={'schema_version':1,'id':'plan_'+family,'revision':0,'base_project_sha256':identity(project),'base_domain_sha256':domain_identity(project),'user_goal':goal,'family':family,'status':'DRAFT_FOR_REVIEW','origin':'DETERMINISTIC_DEVELOPER_AUTHORED_PLANNING; not live AI','functional_requirements':reqs,'nonfunctional_constraints':['SI units, bounded models, user review before local changes.','No paid request, VM, source installation or automatic device creation.'],'component_candidates':[],'required_subsystems':[],'required_signals_interfaces':[],'mechanical_structures':[],'sensors':[],'actuators':[],'power_requirements':[],'control_software_requirements':[],'physical_assumptions':[],'environmental_conditions':[],'supported_verification_pathways':['Static graph and schema checks; restricted World Builder compilation.'],'unknowns':[],'missing_catalog_capabilities':[],'risks_dependencies':[],'proposed_actions':[],'blocked_steps':[],'coverage':{}}
    def component(role,key,why):p['component_candidates'].append({'role':role,'catalog_id':key,'availability':'CATALOG_AVAILABLE' if key else 'UNAVAILABLE','rationale':why})
    if family=='sensor_barrier':
        req('detect','Detect approaching object using distance signal.','Trusted geometric ray; real acoustics UNKNOWN.',True)
        req('open_close','Open before fixed deadline and close after clearance.','Existing reference state machine + measured MuJoCo acceptance.',True)
        req('electrical','Avoid unsupported 5 V Echo-to-3.3 V GPIO direct path.','Static sourced/assumed voltage and divider rules.',True)
        req('physical_product','Deploy a reliable physical device.','Hardware current, pulse timing and field tests unavailable.',False)
        for role,key in [('processor','esp32_devkitc_v4_wroom32'),('distance','hcsr04_sen15569'),('actuator','towerpro_sg90_digital'),('power','regulated_dual_supply'),('divider_top','resistor_2200'),('divider_bottom','resistor_3300')]:component(role,key,'Existing supported reference part; retain catalog assumptions and UNKNOWN ratings.')
        p.update(required_subsystems=['distance sensing','decoded reference control','hinged beam','divider and external servo power'],required_signals_interfaces=['Echo through supported unloaded divider -> board.IO19 -> decoded metres','board.IO18 -> TRIG digital request','board.IO23 -> servo.SIGNAL -> ideal position request in rad; no PWM waveform'],mechanical_structures=['Illustrative revolute beam and fixed base; explicit mass and actuator envelope.'],sensors=['HC-SR04 modeled as sampled geometric ray only.'],actuators=['Ideal torque-bounded servo reference, not current/thermal SG90 simulation.'],power_requirements=['External 4.8 V servo rail; common ground; 5 V board/sensor rail.'],control_software_requirements=['Existing trusted ReferenceLogic; no MCU firmware generated.'],physical_assumptions=['Beam mass .035 kg, length .24 m; torque envelope .12 N*m is a declared model envelope.'],environmental_conditions=['Bounded object approach in the existing reference scene.'],supported_verification_pathways=['CIRCUITBASE rules','World Builder native articulation','Existing independent trusted barrier rollout'],unknowns=['Worst-case current and thermal margin','Trigger/servo logic thresholds','Acoustic fidelity and pulse timing'],risks_dependencies=['World planning preview is separate from the existing reference plant; binding does not imply generic closed-loop control.'])
        p['proposed_actions']=[{'kind':'create_object','primitive':'motor','id':'planned_beam','parent':None},{'kind':'set_mass','target':'planned_beam','mass_kg':.035},{'kind':'set_geometry','target':'planned_beam','dimensions_m':[.24,.02,.016]},{'kind':'set_actuator','target':'planned_beam','actuator':{'limit':.12,'command':0.,'unit':'N*m'}}]
        p['blocked_steps']=[{'id':'deploy_hardware','status':'BLOCKED','reason':'No purchased supply rating, full electrical dynamics, MCU firmware execution or physical deployment pathway.'}]
    elif family=='gripper':
        req('grasp','Grip a bounded object with controlled force.','No supported gripper/contact plant or force controller.',False)
        req('mechanism','Plan fingers and joints.','Supported primitive preview and articulation only.',True)
        req('feedback','Sense grasp force and position.','Position sensors available in world; force hardware/catalog unavailable.',False)
        component('processor','esp32_devkitc_v4_wroom32','Candidate control interfaces only, no gripper firmware.');component('drive',None,'Need actuator, gearbox and force/current specification.');component('force_sensor',None,'No sourced force sensor in catalog.')
        p.update(required_subsystems=['jaw mechanism','drive train','force/position sensing','power','grasp controller'],required_signals_interfaces=['Position command rad or m','Force feedback N; unavailable hardware','Motor enable and current limit; unresolved'],mechanical_structures=['Two finger/link concepts; geometry/contact/grasp stability unresolved.'],sensors=['Joint position abstractly supported; tactile/force catalog absent.'],actuators=['No selected gripper drive.'],power_requirements=['Motor stall current, supply capacity and protection UNKNOWN.'],control_software_requirements=['Bounded force/position policy needed; no firmware or grasp controller implemented.'],physical_assumptions=['Rigid illustrative links only; friction/contact distribution UNKNOWN.'],environmental_conditions=['Object shape, mass and allowed contact force must be specified.'],unknowns=['Required grip force','Jaw mechanics and tolerances','Electrical/thermal margin'],missing_catalog_capabilities=['Gripper drive','Force sensor','Gripper verification plant'],risks_dependencies=['Pinch hazards and object damage require separate verified requirements.'])
        p['proposed_actions']=[{'kind':'create_object','primitive':'revolute','id':'planned_finger','parent':None}]
        p['blocked_steps']=[{'id':'grasp_validation','status':'BLOCKED','reason':'No supported gripper plant, force sensor or verified drive; world finger preview is not a functioning gripper.'}]
    else:
        for i,s in [('vision','Acquire camera frames.'),('audio_in','Acquire microphone samples.'),('audio_out','Drive speaker output.'),('assistant','Provide voice-assistant processing.'),('wearable','Meet wearable power/thermal/optical/RF constraints.')]:req(i,s,'Architecture planning only; domain/component verification unavailable.',False)
        for role in ('camera','microphone','speaker_amplifier','compute_radio','battery_bms','optics'):component(role,None,'No sourced supported catalog part or simulation domain for this subsystem.')
        p.update(required_subsystems=['camera and image pipeline','microphone and audio input','speaker and audio amplifier','compute/voice assistant','radio/data transport','battery/BMS/regulation','wearable frame and optics'],required_signals_interfaces=['Camera pixel stream: protocol/bandwidth UNKNOWN','Microphone sampled audio: codec/sample rate UNKNOWN','Speaker amplified audio: impedance/power UNKNOWN','Voice assistant request/response: privacy/latency UNKNOWN'],mechanical_structures=['Frame envelope and mounting plan; optical alignment and ergonomics unresolved.'],sensors=['Camera','Microphone'],actuators=['Speaker/audio output'],power_requirements=['Battery chemistry/capacity, regulator efficiencies, peak load and charging safety UNKNOWN.'],control_software_requirements=['Capture pipelines, voice-assistant software, privacy controls and permissions required; no firmware generated.'],physical_assumptions=['No fabricated electrical, battery, thermal, RF or optics parameters.'],environmental_conditions=['Wear conditions, ambient temperature and ingress requirements unresolved.'],unknowns=['Battery','Thermal','RF','Optics','Acoustics','Privacy, connectivity and latency'],missing_catalog_capabilities=['Camera','Microphone','Speaker amplifier','Battery/BMS','Wearable compute/radio','Optics'],risks_dependencies=['All construction, wiring and verification steps blocked pending sourced components and supported domains.'])
        p['blocked_steps']=[{'id':'glasses_'+str(i),'status':'BLOCKED','reason':s+' requires unavailable components/specifications and verification.'} for i,s in enumerate(p['required_subsystems'])]
    p['coverage']={'supported_requirements':sum(r['supported'] for r in reqs),'total_requirements':len(reqs),'completion':'PLAN_ONLY; no manufactured, executed or validated device'}
    return validate_plan(p)


def review_plan(plan):
    p=validate_plan(plan);p['status']='REVIEWED_PROPOSAL_ONLY';p['revision']+=1;return validate_plan(p)


def compile_plan(plan,project):
    p=validate_plan(plan)
    if p['status']!='REVIEWED_PROPOSAL_ONLY' or p['base_domain_sha256']!=domain_identity(project):raise ValueError('Reviewed plan and exact current project required')
    if 'construction_batches' in p:
        return {'plan_sha256':digest(p),'base_project_sha256':identity(project),'ordered_operations':[],'ordered_batches':copy.deepcopy(p['construction_batches']),'blocked_steps':copy.deepcopy(p['blocked_steps']),'status':'CREATION_REQUIRES_SEPARATE_BUILD_APPROVAL','origin':p['origin'],'automatic_application':False,'day16_execution_engine':'BOUNDED_CREATION_SERVICE'}
    if p['proposed_actions']:execute_copy(project,p['proposed_actions'])
    return {'plan_sha256':digest(p),'base_project_sha256':identity(project),'ordered_operations':copy.deepcopy(p['proposed_actions']),'blocked_steps':copy.deepcopy(p['blocked_steps']),'status':'PARTIAL_PROPOSED_NOT_APPLIED' if p['proposed_actions'] else 'BLOCKED_NO_SUPPORTED_ACTIONS','origin':p['origin'],'automatic_application':False,'day16_execution_engine':'NOT_IMPLEMENTED'}
