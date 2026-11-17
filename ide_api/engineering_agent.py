"""Context-bound engineering tools. No provider, native stepping, save or apply.

Model arguments are data. Existing readers/compiler/validators own physical facts.
Local review records are not authorizations, executions, or authoritative heads.
"""
import copy,hashlib,json,re,threading
from itertools import islice
from pathlib import Path
from jsonschema import Draft202012Validator
from core.simulation import ROOT
from engineering.store import Store
from ide_api import native_models as models,rail_sweeps as rail,robot_import
from ide_api.product_alpha import diagnosis
from ide_api.model_evidence import diagnose
from ide_api.native_results import compare_records
from ide_api.research.physical_math import predictions
from workspace.data import bounded_read,decode_json

PROVIDER={'status':'UNAVAILABLE_GENERAL_ENGINEERING_SCOPE','mode':'DETERMINISTIC_ENGINEERING_TOOLS_NOT_LIVE_AI','paid_calls':0,'reason':'No exact approved general investigation scope is active for these local tools. The separate source-bound live bridge requires operator-recorded approval; an API key is not consent.','required':'Use the existing accounted live bridge with reconciled history, a frozen context/tool/source/token/cost scope and fresh explicit approval. Local deterministic tools remain available without credentials.'}

def obj(properties):return {'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}
def string(limit=160):return {'type':'string','minLength':1,'maxLength':limit}
NUMBER={'type':'number'}
CHANGES={'type':'object','minProperties':1,'maxProperties':8,'propertyNames':{'enum':sorted(set(rail.BOUNDS)|{'chassis_mass_kg','length_m','width_m','wheel_radius_m','angle_deg','friction','torque_nm','target_m'})},'additionalProperties':NUMBER}
CONTEXT=obj({'kind':{'enum':['rail_plan','numeric','native_study','public_example']},'project_id':{'type':['string','null'],'maxLength':64},'project_sha256':{'type':['string','null'],'pattern':'^[a-f0-9]{64}$'},'model_id':{'enum':[models.RAIL,models.ROVER]},'parameters':{'type':'object','maxProperties':8,'additionalProperties':NUMBER},'requirements':{'type':'object','maxProperties':8,'additionalProperties':NUMBER},'result_id':{'type':['string','null'],'maxLength':110},'selection':{'type':['string','null'],'maxLength':120}})
INPUTS={'inspect_context':obj({}),'inspect_result':obj({}),'inspect_component':obj({}),'compare_results':obj({'baseline_id':string(110)}),'calculate_physics':obj({}),'propose_parameters':obj({'changes':CHANGES,'rationale':string(1000)}),'review_proposal':obj({'proposal_id':string(64),'decision':{'enum':['RETAINED','REJECTED']}}),'prepare_verification':obj({'proposal_id':string(64)}),'provider_status':obj({})}
AUTHORITIES={n:('PROPOSE' if n=='propose_parameters' else 'HUMAN_REVIEW' if n=='review_proposal' else 'PREPARE_ONLY' if n=='prepare_verification' else 'ANALYZE' if n in ('calculate_physics','compare_results') else 'INSPECT') for n in INPUTS}
DESCRIPTIONS={'inspect_context':'Inspect exact project/head, draft, registered capabilities, requirements, selection and source compatibility. No source files.','inspect_result':'Inspect the selected verified result and its actual failed requirements; observation, requirement and hypotheses are separate. No invented measurements.','inspect_component':'Inspect the actual selected compiled body/joint/shape identity. Missing selections reject.','compare_results':'Compare a distinct compatible saved result with selected evidence; baseline_id is an exact result ID, never a path. Different physical conditions are explicit.','calculate_physics':'Rail-only ideal braking calculation for current validated numbers. Prediction only; unsupported for rover.','propose_parameters':'Create a review-only numeric proposal. changes contains only exact supported SI parameter names/values. No controller edits, requirement relaxation, source, files or execution.','review_proposal':'Human UI review only. Retain or permanently reject the exact context-bound proposal. This is not apply or spending approval. Not exposed as a model tool.','prepare_verification':'Prepare a retained human-reviewed numerical scope using existing Toolkit.prepare; no job, consent reservation or execution.','provider_status':'Explain actual provider unavailability. Never creates a provider client.'}
# Outputs deliberately carry bounded model-specific data rather than fake shared metrics.
OUTPUT=obj({'ok':{'const':True},'name':{'enum':list(INPUTS)},'context_sha256':string(64),'authority':{'enum':sorted(set(AUTHORITIES.values()))},'origin':{'const':'DETERMINISTIC_ENGINEERING_TOOL_NOT_LIVE_AI'},'data':{'type':'object'},'execution_authorized':{'const':False},'applied':{'const':False}})

DATA_SCHEMAS={
 'inspect_context':{'type':'object','required':['context_sha256','project','model_id','controller_id','parameters','requirements','result','source','provider','tools']},
 'inspect_result':obj({'evidence':{'type':'object','required':['id','parameters','criteria','metrics','verdict','source_sha256']},'analysis':{'type':'object','required':['status','issues']},'scope':string(240)}),
 'inspect_component':obj({'component':{'type':'object','required':['id']},'model_id':string(),'representation':string()}),
 'compare_results':{'type':'object','required':['status','verdicts']},
 'calculate_physics':obj({'prediction':{'type':'object','required':['continuous','discrete']},'authorship':{'const':'ANALYTICAL_NOT_MEASURED_NOT_AI'},'formula':string()}),
 'propose_parameters':obj({'proposal_id':string(64),'proposal':{'type':'object','required':['format','context_sha256','project','model_id','controller_id','native_source','before','proposed','changes','rationale','supporting_evidence','requirements','validation','fresh_verification_required','applied','authorship','declaration']},'review_state':{'enum':['PROPOSED_NOT_APPLIED','RETAINED','REJECTED']},'compiled':string()}),
 'review_proposal':obj({'proposal_id':string(64),'review_state':{'enum':['RETAINED','REJECTED']},'applied':{'const':False}}),
 'prepare_verification':obj({'proposal_id':string(64),'review_state':{'const':'RETAINED'},'preparation':{'type':'object','required':['request','execution_authorized','native_steps']},'applied':{'const':False}}),
 'provider_status':obj({k:({'const':v} if not isinstance(v,str) else string(1000)) for k,v in PROVIDER.items()})}

def output_schema(name):
 value=copy.deepcopy(OUTPUT);value['properties']['name']={'const':name};value['properties']['data']=copy.deepcopy(DATA_SCHEMAS[name]);return value

def validate(schema,value):
 Draft202012Validator(schema).validate(value)
 if len(rail.canonical(value))>24_000:raise ValueError('Bounded engineering input exceeded')
 return value

def schemas(model=False):
 return [{'type':'function','name':n,'description':DESCRIPTIONS[n],'parameters':copy.deepcopy(s),'output_schema':output_schema(n),'authority':AUTHORITIES[n],'limits':{'input_bytes':24000,'output_bytes':64000,'native_steps':0,'paid_requests':0}} for n,s in INPUTS.items() if not model or n not in ('review_proposal','prepare_verification')]

class EngineeringAgent:
 def __init__(self,product,toolkit,root=None):
  self.product,self.toolkit=product,toolkit;self.root=Path(root) if root else ROOT/'.runtime/engineering_agent';self.lock=threading.RLock()
  if any(p.is_symlink() for p in (self.root,*self.root.parents)):raise ValueError('Symlink assistant storage refused')
 def _selected(self,c):
  if not c['result_id']:return None
  if c['model_id']==models.RAIL:return self.product.case(c['result_id'])['record']
  record,_=self.toolkit.native.load(c['result_id'])
  return record
 def context(self,value):
  c=copy.deepcopy(validate(CONTEXT,value));model=models.for_model(c['model_id']);descriptor=models.descriptor(c['model_id']);saved=None
  if c['kind']=='numeric':
   p=self.toolkit.read(c['project_id'])
   if p['sha256']!=c['project_sha256'] or p['stale'] or p['declaration']['model_id']!=c['model_id']:raise ValueError('Stale or mismatched numeric project/head/source')
   saved=p['declaration']['parameters'];requirements=p['declaration']['requirements']
  elif c['kind']=='rail_plan':
   p=self.product.project(c['project_id'])
   if c['model_id']!=models.RAIL or p['sha256']!=c['project_sha256'] or p.get('stale'):raise ValueError('Stale rail plan/head/source')
   saved=p['configuration'];requirements=rail.DEFAULT_CRITERIA
  else:
   if c['model_id']!=models.RAIL or c['project_id'] is not None or c['project_sha256'] is not None:raise ValueError('Read-only studies require no mutable project identity and the registered rail model')
   requirements=rail.DEFAULT_CRITERIA
  parameters=model.parameters(c['parameters']);criteria=model.criteria(c['requirements'])
  if criteria!=requirements:raise ValueError('Assistant context must retain exact saved project requirements')
  record=self._selected(c)
  if record:
   if record['controller_id']!=model.CONTROLLER or record.get('model_id',models.RAIL)!=c['model_id'] or not record.get('verified'):raise ValueError('Selected evidence model/controller/verification mismatch')
   if saved is not None and (record['parameters']!=saved or record['criteria']!=requirements):raise ValueError('Selected evidence does not belong to saved project configuration')
   if c['kind']=='public_example' and record.get('origin')!='PINNED_PUBLIC_HISTORICAL':raise ValueError('Public example cannot substitute private native evidence')
   if c['kind']=='native_study' and record.get('origin')!='LOCAL_SAVED_REGISTERED_JOB':raise ValueError('Native study requires an actual native result')
  selection=c['selection']
  if selection is not None and not re.fullmatch('[a-zA-Z0-9_:. -]{1,120}',selection):raise ValueError('Unsupported selection identity')
  from tools.model_qualification import sources
  from ide_api.research.bundles import repo_base
  binding={'input':c,'native_source':model.source_identity(),'app_sources_sha256':rail.digest(sources()),'git_base':repo_base(),'result_sha256':None if record is None else record.get('result_sha256',rail.digest(record))}
  result={'context_sha256':rail.digest(binding),'project':{'kind':c['kind'],'id':c['project_id'],'sha256':c['project_sha256']},'model_id':c['model_id'],'controller_id':model.CONTROLLER,'environment':descriptor['environment'],'selection':selection,'parameters':parameters,'requirements':criteria,'fields':descriptor['fields'],'result':None if record is None else self._summary(record),'source':binding,'provider':PROVIDER,'tools':schemas(),'authority':'INSPECT_ANALYZE_PROPOSE_REVIEW_PREPARE_ONLY','native_execution':'SEPARATE_EXACT_APPROVAL_REQUIRED','applied':False}
  if len(rail.canonical(result))>24000:raise ValueError('Context output exceeded bound')
  return result
 def _summary(self,r):
  return {k:copy.deepcopy(r[k]) for k in ('id','model_id','controller_id','parameters','criteria','metrics','checks','verdict','source_sha256','source_current','replay_status','independent_verification','provenance','evidence_package_identity','origin') if k in r}
 def _proposal(self,key,ctx):
  if not isinstance(key,str) or not re.fullmatch('[a-f0-9]{64}',key):raise ValueError('Exact proposal hash required')
  p=Store(self.root/'proposals').get(key)
  if p['context_sha256']!=ctx['context_sha256']:raise ValueError('Stale proposal context, head, selection, source or evidence; inspect again')
  return p
 def _review(self,key):
  root=self.root/'reviews';path=root/(key+'.json')
  if any(p.is_symlink() for p in (path,root,*root.parents)):raise ValueError('Symlink review refused')
  if not path.exists():return 'PROPOSED_NOT_APPLIED'
  value=decode_json(bounded_read(root,key+'.json'))
  rail.exact(value,['proposal_id','decision','context_sha256','applied'])
  if value['proposal_id']!=key or value['decision'] not in ('RETAINED','REJECTED') or value['applied'] is not False:raise ValueError('Invalid review record')
  return value['decision']
 def dispatch(self,context,expected,name,arguments,*,human=False,provenance=None):
  if name not in INPUTS:raise ValueError('Unsupported engineering tool; no source, terminal, apply, provider or execute tool')
  validate(INPUTS[name],arguments)
  if provenance is not None:
   rail.exact(provenance,['origin','request_id','response_id','call_id'])
   if provenance['origin'] not in ('GENUINE_PROVIDER_RESPONSE','OFFLINE_TRANSPORT_FIXTURE_NOT_AI'):raise ValueError('Unsupported trusted call provenance')
  with self.lock:
   ctx=self.context(context)
   if ctx['context_sha256']!=expected:raise ValueError('Stale engineering context; refresh exact project/head/source/evidence')
   record=self._selected(context)
   if name=='inspect_context':data=ctx
   elif name=='provider_status':data=copy.deepcopy(PROVIDER)
   elif name=='inspect_result':
    if record is None:raise ValueError('No verified saved result selected; missing evidence is not physical FAIL')
    if ctx['model_id']==models.RAIL:diagnostic=diagnosis(record)
    else:
     _,raw=self.toolkit.native.load(context['result_id']);diagnostic=diagnose(raw)
    data={'evidence':self._summary(record),'analysis':diagnostic,'scope':'Original recorded input only; draft and hypothesis are not new verification.'}
   elif name=='inspect_component':
    if not context['selection']:raise ValueError('Select an actual component first')
    d=self._declaration(ctx);design=self.toolkit.design(d);items=design['world']['objects'] if 'world' in design else sum([design['scene'][k] for k in ('bodies','geoms','joints','actuators')],[])
    component=next((x for x in items if x['id']==context['selection']),None)
    if component is None:raise ValueError('Selection is not a registered compiled component in this context')
    data={'component':component,'model_id':ctx['model_id'],'representation':'COMPILED_PROXY_NOT_MEASURED_MATERIAL_SAFETY'}
   elif name=='compare_results':
    if record is None:raise ValueError('Select measured evidence before comparison')
    other=self.product.case(arguments['baseline_id'])['record'] if ctx['model_id']==models.RAIL else self.toolkit.native.load(arguments['baseline_id'])[0]
    if record.get('compatibility') and other.get('compatibility'):data=compare_records(other,record)
    elif ctx['model_id']==models.RAIL:data=self.product.compare(other['id'],record['id'])
    else:raise ValueError('Unsupported evidence cohort')
   elif name=='calculate_physics':
    if ctx['model_id']!=models.RAIL:raise ValueError('Ideal braking calculation is rail-only; no rover performance equation is supplied')
    data={'prediction':predictions(ctx['parameters'],ctx['requirements']),'authorship':'ANALYTICAL_NOT_MEASURED_NOT_AI','formula':'d_stop = mass_kg * speed_mps² / (2 * force_n)'}
   elif name=='propose_parameters':
    if set(arguments['changes'])-set(ctx['fields']):raise ValueError('Unknown model-specific parameters')
    target={**ctx['parameters'],**arguments['changes']};d=self._declaration(ctx,target);d=robot_import.validate(d)
    compiled=self.toolkit.design(d) # real deterministic typed compilation; zero integration
    p={'format':'EMBODY_NUMERIC_ENGINEERING_PROPOSAL_V1','context_sha256':expected,'project':ctx['project'],'model_id':ctx['model_id'],'controller_id':ctx['controller_id'],'native_source':ctx['source']['native_source'],'before':ctx['parameters'],'proposed':d['parameters'],'changes':{k:{'before':ctx['parameters'][k],'after':d['parameters'][k],'unit':ctx['fields'][k]['unit'],'bounds':ctx['fields'][k]['bounds']} for k in arguments['changes']},'rationale':arguments['rationale'],'supporting_evidence':None if record is None else self._summary(record),'requirements':ctx['requirements'],'validation':'TYPED_AND_NATIVE_COMPILED_NOT_PHYSICALLY_VERIFIED','fresh_verification_required':True,'applied':False,'authorship':provenance['origin'] if provenance else 'USER_SUPPLIED_TOOL_ARGUMENTS_NOT_LIVE_AI','provider_provenance':copy.deepcopy(provenance),'declaration':d}
    folder=self.root/'proposals'
    if folder.exists() and len(list(islice(folder.iterdir(),64)))>=64:raise ValueError('Proposal retention limit; no automatic deletion')
    key=Store(folder).put(p);data={'proposal_id':key,'proposal':p,'review_state':self._review(key),'compiled':compiled['verification']}
   else:
    key=arguments['proposal_id'];p=self._proposal(key,ctx);state=self._review(key)
    if name=='review_proposal':
     if not human:raise PermissionError('Separate explicit human review required; models cannot review their own proposals')
     if state!='PROPOSED_NOT_APPLIED' and state!=arguments['decision']:raise ValueError('Review decision already recorded; rejected proposals cannot reopen')
     if state=='PROPOSED_NOT_APPLIED':rail.write_once(Store(self.root/'reviews').root/(key+'.json'),{'proposal_id':key,'decision':arguments['decision'],'context_sha256':expected,'applied':False},4096)
     data={'proposal_id':key,'review_state':arguments['decision'],'applied':False}
    else:
     if state!='RETAINED':raise ValueError('Human retention required before verification preparation')
     data={'proposal_id':key,'review_state':state,'preparation':self.toolkit.prepare(p['declaration']),'applied':False}
   out={'ok':True,'name':name,'context_sha256':expected,'authority':AUTHORITIES[name],'origin':'DETERMINISTIC_ENGINEERING_TOOL_NOT_LIVE_AI','data':data,'execution_authorized':False,'applied':False}
   Draft202012Validator(output_schema(name)).validate(out)
   if len(rail.canonical(out))>64000:raise ValueError('Bounded engineering output exceeded')
   return out
 def _declaration(self,ctx,parameters=None):
  return {'format':robot_import.FORMAT,'title':'Review-only engineering configuration','model_id':ctx['model_id'],'controller_id':ctx['controller_id'],'parameters':parameters if parameters is not None else ctx['parameters'],'requirements':ctx['requirements']}
