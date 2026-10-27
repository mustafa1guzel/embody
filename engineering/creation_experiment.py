"""Review-only Phase 17 protocol over the Day 16 engine, never an apply tool."""
import copy,json
from pathlib import Path
from jsonschema import Draft202012Validator
from world.schema import obj,num
from physics.contracts import digest
from robustness.contracts import write_once
from .device_bindings import PARTS
from .project import identity,validate
from .actions import execute_copy

GOAL='Build a sensor-controlled robotic barrier that detects an approaching object and opens automatically.'
FUNCTIONS=['detect_approach','open_on_detection','bounded_hinge_motion','native_rigid_body_verification']
LIMITS=['NO_REAL_MCU_OR_PWM','IDEAL_RAY_SENSOR_ONLY','ELECTRICAL_CURRENT_AND_THERMAL_UNKNOWN','VISUAL_MOUNTS_EXCLUDE_ELECTRONIC_MASS','NO_REAL_HARDWARE_SAFETY_PROOF']
MECHANICAL=obj({'span_m':num(.1,.5),'mass_kg':num(.01,2),'torque_nm':num(.005,.17),'height_m':num(.12,.3)})
def text(lo,hi):return {'type':'string','minLength':lo,'maxLength':hi}
def choices(values):return {'type':'string','enum':values}
def many(values,lo,hi):return {'type':'array','minItems':lo,'maxItems':hi,'items':choices(values)}
PROPOSAL=obj({
 'goal_interpretation':text(20,500),
 'template':choices(['day16_hinged_barrier_v1']),
 'functional_requirements':many(FUNCTIONS,4,4),
 'mechanical':MECHANICAL,
 'circuit_roles':obj({r:choices(list(PARTS.values())) for r in PARTS}),
 'interfaces':obj({'trigger_gpio':choices(['IO18','IO19','IO23']),'echo_gpio':choices(['IO18','IO19','IO23']),'servo_gpio':choices(['IO18','IO19','IO23']),'echo_conditioning':choices(['SUPPORTED_RESISTOR_DIVIDER','DIRECT_CONNECTION']),'actuator_supply':choices(['EXTERNAL_REGULATED_4V8','BOARD_GPIO'])}),
 'controller_family':choices(['TRUSTED_BARRIER_V1','NONE_GEOMETRY_ONLY']),
 'selection_rationale':text(40,1000),
 'unsupported_domains':many(LIMITS,5,5)})
SCHEMAS=[
 {'type':'function','name':'propose_barrier_from_template','strict':True,
  'description':'Select and parameterize the supported hinged-barrier construction tool. Supply your own engineering interpretation, catalog roles, interfaces, controller and limitations. The deterministic engine expands the chosen template into typed actions and compiles a review copy. No project build, activation, application, simulation, source execution or spending authority.',
  'parameters':PROPOSAL},
 {'type':'function','name':'report_unsupported_creation','strict':True,
  'description':'Report that the requested goal cannot be responsibly proposed using the declared capabilities. This records a limitation and creates no project.',
  'parameters':obj({'reason':text(20,1000)})}]
INTERFACES={'trigger_gpio':'IO18','echo_gpio':'IO19','servo_gpio':'IO23','echo_conditioning':'SUPPORTED_RESISTOR_DIVIDER','actuator_supply':'EXTERNAL_REGULATED_4V8'}

class CreationExperimentTools:
    def __init__(self,manager,trace):
        self.manager,self.trace=manager,trace;self.attempted=False;self.result=None
    @property
    def schemas(self):return copy.deepcopy(SCHEMAS)
    def dispatch(self,name,arguments):
        try:
            if self.attempted:raise ValueError('One tool dispatch only; no local repair/retry')
            self.attempted=True
            encoded=json.dumps(arguments,allow_nan=False)
            self.trace.append('tool_requested',{'name':name,'arguments':arguments})
            schema=next((s for s in SCHEMAS if s['name']==name),None)
            if schema is None or len(encoded.encode())>12000 or not Draft202012Validator(schema['parameters']).is_valid(arguments):raise ValueError('Exact bounded schema required; no operation translation')
            if name=='report_unsupported_creation':
                value={'status':'MODEL_REPORTED_UNSUPPORTED','reason':arguments['reason'],'proposal_applied':False}
            else:
                if set(arguments['functional_requirements'])!=set(FUNCTIONS) or set(arguments['unsupported_domains'])!=set(LIMITS):raise ValueError('Missing/duplicate supported requirement or explicit limitation')
                if arguments['circuit_roles']!=PARTS or arguments['interfaces']!=INTERFACES or arguments['controller_family']!='TRUSTED_BARRIER_V1':raise ValueError('Unsupported catalog/controller/interface selection; no silent correction')
                proposal=self.manager.start(GOAL,arguments['mechanical'])
                self.manager.validate_proposal(proposal['proposal_id'],proposal['base_sha256'],0)
                if self.manager.active() is not None or self.manager.project(proposal['project_id']).current()!=proposal['initial_project']:raise ValueError('Unexpected project application')
                from .barrier_repair import preflight_project
                value={'status':'VALIDATED_REVIEW_ONLY','model_design_intent':copy.deepcopy(arguments),'model_design_intent_sha256':digest(arguments),'construction_proposal':proposal,'physics_preflight':preflight_project(proposal['proposed_project']),'proposal_applied':False,'plan_authorship':'Model supplies design intent and template parameters; Day16 deterministic engine supplies exact DeviceDesignPlan and typed construction batches. Neither is misattributed to the other.'}
            output={'ok':True,'result':value};self.result=output
        except (ValueError,KeyError,TypeError,OSError) as exc:
            output={'ok':False,'error':{'type':type(exc).__name__,'message':str(exc)[:300]}};self.result=output
        self.trace.append('tool_completed',{'name':name,'output':output});return output

def preview_measurements(selection,manager,output,*,render_image=True):
    """At most three trusted preview scenarios, never committed to the empty head."""
    from .created_simulation import run
    from .diagnosis import diagnose
    if selection['status']!='VALIDATED_REVIEW_ONLY':raise ValueError('Validated construction proposal required')
    proposal=selection['construction_proposal'];service=manager.project(proposal['project_id'])
    manager.validate_proposal(proposal['proposal_id'],proposal['base_sha256'],0)
    original=service.current()
    if original!=proposal['initial_project'] or manager.active() is not None:raise ValueError('Preview must preserve actual empty head and inactive selection')
    out=Path(output);out.mkdir(exist_ok=False,parents=True)
    from .barrier_repair import preflight_project
    p=proposal['proposed_project'];pf=preflight_project(p);write_once(out/'physics_preflight.json',pf)
    if pf['status']!='READY_FOR_NATIVE_PREVIEW':
        summary={'primary_status':'BLOCKED_PHYSICS_PREFLIGHT','physics_preflight':pf,'simulation_scenarios':0,'proposal_applied':False,'empty_head_unchanged':service.current()==original,'vm_launches':0,'new_secondary_model_requests':0}
        write_once(out/'summary.json',summary);return summary
    baseline=run(p,out/'primary',render_image)
    summary={'primary_status':baseline['status'],'primary_independent_verification':baseline['independent_verification'],'primary_project_sha256':identity(p),'simulation_scenarios':1,'native_renders':{'primary':baseline.get('native_render',{'status':'NOT_REQUESTED'})},'model_origin':'Genuine only if linked to actual provider response; offline fixtures must be labeled separately.'}
    old_mass=p['device_spec']['mechanical']['mass_kg'];heavy_mass=min(2.,max(.5,10*old_mass))
    if heavy_mass>old_mass:
        heavy_op={'kind':'set_device_mass','mass_kg':heavy_mass};heavy=validate(execute_copy(p,[heavy_op]));failure=run(heavy,out/'heavy',render_image);diagnosis=diagnose(heavy,failure)
        write_once(out/'heavy_diagnosis.json',diagnosis)
        correction_op={'kind':'set_device_mass','mass_kg':old_mass};repair=validate(execute_copy(heavy,[correction_op]));corrected=run(repair,out/'correction_preview',render_image)
        write_once(out/'correction_proposal.json',{'origin':'DETERMINISTIC_RESTORE_ORIGINAL_SELECTED_MASS; no secondary paid model call','base_project_sha256':identity(heavy),'operations':[correction_op],'resulting_project_sha256':identity(repair),'proposed_project':repair,'approval_status':'PROPOSED_NOT_APPLIED','proposal_applied':False,'meaning':'Counterfactual measured preview only; not a committed project or proof of global optimum.'})
        summary.update(simulation_scenarios=3,heavy_mass_kg=heavy_mass,heavy_status=failure['status'],heavy_acceptance=failure['acceptance'],diagnostic_categories=sorted({x['category'] for x in diagnosis['findings']}),correction_status=corrected['status'],correction_independent_verification=corrected['independent_verification'])
        summary['native_renders'].update(heavy=failure.get('native_render',{'status':'NOT_REQUESTED'}),correction_preview=corrected.get('native_render',{'status':'NOT_REQUESTED'}))
    else:summary['secondary_status']='NOT_RUN: selected mass already at supported upper bound'
    assert service.current()==original and manager.active() is None
    summary.update(empty_head_unchanged=True,proposal_applied=False,vm_launches=0,new_secondary_model_requests=0)
    write_once(out/'summary.json',summary);return summary
