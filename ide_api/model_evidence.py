"""Strict versioned rover saved evidence. Historical rail reader is unchanged.

Export verification checks bytes, compiled identity, saved force/contact states,
PD commands, metrics and saved fresh replay. It grants no local attestation or
execution authority and performs zero integration.
"""
import copy,hashlib
from ide_api import rail_sweeps as rail,rover_reference as rover
from ide_api.research.artifacts import finite_json
from world.compiler import compile_world
FORMAT='EMBODY_REGISTERED_MODEL_EVIDENCE_V2'
MAX_BYTES=9_000_000

def verify_result(result):
    if not isinstance(result,dict) or result.get('model_id')!=rover.MODEL or result.get('measurement_definition')!='ROVER_TARGET_SAMPLED_V1':raise ValueError('Unsupported model evidence version')
    rail.exact(result,['execution_status','verdict','metrics','checks','failure_reasons','comparison','samples','trajectory_sha256','model_xml','effective_model_sha256','world','roles','compiled_contract','construction_proof','independent_readback','replay','controller_contract','engine_version','units','limitations','model_id','measurement_definition','case_id','experiment_id','controller_id','source_sha256','parameters','criteria','simulation_configuration'])
    if result['controller_contract']!={'id':rover.CONTROLLER,'runtime_controls':'Registered target PD feedback; compiler constant command is only the initial authoring/probe value','kp_n_per_m':3.,'kd_ns_per_m':.8} or result['engine_version']!=__import__('mujoco').__version__ or result['units']!=rover.UNITS or result['limitations']!=rover.LIMITATIONS:raise ValueError('Controller/engine/units contract mismatch')
    if result.get('experiment_id')!=rover.EXPERIMENT or result.get('controller_id')!=rover.CONTROLLER or result.get('source_sha256')!=rover.source_identity():raise ValueError('Incompatible rover/controller/current source; historical bytes must not be migrated')
    p=rover.parameters(result['parameters']);c=rover.criteria(result['criteria'])
    expected_id=rail.digest({'source':result['source_sha256'],'experiment':rover.EXPERIMENT,'controller':rover.CONTROLLER,'parameters':p,'criteria':c})
    if result.get('case_id')!=expected_id or result.get('simulation_configuration')!={'duration_s':1.,'timestep_s':.005,'initial_position_m':0.}:raise ValueError('Case/simulation identity mismatch')
    project,roles,proof,model,xml,compiled=rover.compiled(p)
    if result['world']!=project['world'] or result['roles']!=roles or xml!=result['model_xml'] or result['effective_model_sha256']!=hashlib.sha256(xml.encode()).hexdigest() or result['compiled_contract']!=compiled or result['construction_proof']!=proof:raise ValueError('Compiled model/construction identity mismatch')
    if rail.digest(result['samples'])!=result['trajectory_sha256']:raise ValueError('Primary trajectory identity mismatch')
    replay=result['replay']
    rail.exact(replay,['status','primary_steps','fresh_steps','samples','trajectory_sha256'])
    if replay['status']!='PASS' or type(replay['primary_steps']) is not int or type(replay['fresh_steps']) is not int or replay['primary_steps']!=200 or replay['fresh_steps']!=200 or rail.digest(replay['samples'])!=replay['trajectory_sha256'] or result['samples']!=replay['samples']:raise ValueError('Missing/corrupt saved fresh replay')
    m,checks=rover.measure(result['samples'],p,c,model,roles)
    audit=rover.forward_audit(result['samples'],p,roles,model,project['world']);checks['fresh_replay']=True
    if result['metrics']!=m or result['checks']!=checks or result['independent_readback']!=audit or result['execution_status']!='MEASURED' or result['verdict']!=('PASS' if all(checks.values()) else 'FAIL') or result['failure_reasons']!=[k for k,v in checks.items() if not v]:raise ValueError('Saved measurements/verdict mismatch')
    return {'status':'INTEGRITY_VALID_EXTERNAL_UNVERIFIED','saved_readback':'PASS','saved_replay':'PASS','new_native_steps':0,'record':copy.deepcopy(result),'origin':'Declared developer-native origin; external hash/readback is not a local execution attestation'}

def package(result):
    verify_result(result);value={'format':FORMAT,'sha256':rail.digest(result),'result':result}
    if len(rail.canonical(value))>MAX_BYTES:raise ValueError('Evidence package limit')
    return value

def verify_package(raw):
    value=finite_json(raw,MAX_BYTES) if isinstance(raw,bytes) else finite_json(rail.canonical(raw),MAX_BYTES)
    rail.exact(value,['format','sha256','result'])
    if value['format']!=FORMAT or value['sha256']!=rail.digest(value['result']):raise ValueError('Evidence package identity/version differs')
    return verify_result(value['result'])

def diagnose(result):
    if result is None:return {'status':'UNVERIFIED_NO_MEASUREMENTS','issues':[],'reason':'No authorized rover rollout exists; compile and analytical metadata are not measured verification.'}
    result=verify_result(result)['record'];m=result['metrics'];c=result['criteria']
    pairs=[('progress',m['signed_progress_m'],c['minimumProgress'],'m','>='),('target_error',m['target_error_m'],c['maximumTargetError'],'m','<='),('speed',m['final_speed_mps'],c['maximumFinalSpeed'],'m/s','<'),('orientation',m['minimum_up_dot'],c['minimumUpDot'],'dot','>=')]
    issues=[]
    for name,value,required,unit,relation in pairs:
        failed=value<required if relation=='>=' else value>=required if relation=='<' else value>required
        issues.append({'id':name,'measured':value,'required':required,'unit':unit,'relation':relation,'status':'FAIL' if failed else 'PASS',
                       'observation':'Independently re-read saved pose/velocity samples.','interpretation':'The stated requirement failed.' if failed else 'This sampled requirement passed.',
                       'hypothesis':'Inspect mass, authority, target and slope; no traction-loss/slip/insufficient-torque cause is proven.',
                       'action':'Prepare a bounded configuration and separately authorize new verification.'})
    for key in ['all_wheels_surface_contact','no_prohibited_contacts','bounded_actuator_forces','joint_ranges']:
        issues.append({'id':key,'status':'PASS' if result['checks'][key] else 'FAIL','measured':m,'observation':'Saved contact, native force and wheel-angle readback, not a causal diagnosis.'})
    return {'status':'REQUIREMENTS_PASS' if result['verdict']=='PASS' else 'MEASURED_REQUIREMENT_FAILURE','issues':issues,'authorship':'DETERMINISTIC_NOT_AI'}

def compare(left,right):
    a=verify_result(left)['record'];b=verify_result(right)['record']
    keys=['model_id','controller_id','source_sha256','measurement_definition','simulation_configuration','criteria']
    if a['case_id']==b['case_id'] or any(a[k]!=b[k] for k in keys):raise ValueError('Distinct exact model/controller/source/criteria/measurement cohorts required')
    return {'status':'COMPATIBLE_PARAMETER_COMPARISON','changed_parameters':{k:{'before':a['parameters'][k],'after':b['parameters'][k]} for k in rover.BOUNDS if a['parameters'][k]!=b['parameters'][k]},'verdicts':[a['verdict'],b['verdict']]}
