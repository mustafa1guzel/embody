"""Source-bound physical-feedback facade over existing typed construction.

The author supplies every changed actuator argument. This module never reverses
a command or executes physics, source, API requests or an application decision.
"""
import copy
from jsonschema import Draft202012Validator
from physics.contracts import digest
from world.schema import obj,ID
from .actions import SCHEMAS
from .assembly_direction import physical_feedback,kinematics,contract
from .assembly_plan import validate_plan,PlanError
from .project import identity
from .assembly_live import wire_schema

def amended_plan(baseline,operations,step_id,explanation):
    """Transparent appended typed batch, not mutation of the original plan."""
    plan=copy.deepcopy(baseline)
    if step_id in {s['id'] for s in plan['steps']}:raise PlanError('Repair batch ID already exists')
    plan['steps'].append({'id':step_id,'depends_on':[s['id'] for s in plan['steps']],
        'purpose':explanation,'operations':copy.deepcopy(operations)})
    validate_plan(plan)
    return plan

class PhysicalRepairTools:
    def __init__(self,composer,baseline,native,trace):
        self.composer=composer;self.baseline=copy.deepcopy(baseline);self.native=copy.deepcopy(native)
        self.trace=trace;self.stage=0;self.result=None
        composer.reconstruct(self.baseline)
        if self.native['result']['independent_verification']['status']!='PASS':raise ValueError('Fresh successful native replay required before physical repair')
        self.feedback=physical_feedback(self.baseline,self.native)
        if self.feedback['status']!='PHYSICAL_FAILURE':raise ValueError('A measured native failure is required, not a successful or unexecuted construction')
        self.before=copy.deepcopy(composer.service.current())
        roles=baseline['assembly_plan']['roles']
        self.targets=[r['joint_body_id'] for place,r in roles['wheels'].items() if place.startswith('rear_')]
        self.objects={o['id']:o for o in baseline['proposed_project']['world']['objects']}
    def inspection(self):
        p=self.baseline['proposed_project'];roles=self.baseline['assembly_plan']['roles']
        # Avoid source bytes and a prewritten repaired action list. This is an
        # existing measured design, not an open synthesis task with an answer key.
        feedback=copy.deepcopy(self.feedback);feedback.pop('source_sha256')
        return {'authoritative_head':{'sha256':identity(self.before),'revision':self.before['revision'],'shape_specs':len(self.before.get('shape_specs',[]))},
            'baseline':{'proposal_id':self.baseline['proposal_id'],'proposed_project_sha256':self.baseline['resulting_project_sha256'],
                'revision':p['revision'],'status':'PROPOSED_NOT_APPLIED','origin':self.baseline['origin'],
                'parts':[{'part_id':s['id'],'body_id':s['body_id'],'parent_body_id':s['parent_body_id'],'family':s['family'],'parameters':s['parameters']} for s in p['shape_specs']]},
            'physical_failure':feedback,'direction_semantics':kinematics(p,roles),
            'allowed_changes':{'operations':'Existing set_actuator only; one or two unique REAR role joint body targets',
                'targets':self.targets,'authority_and_unit':'Keep each inspected existing limit and N*m unit unchanged',
                'command_abs_bounds_nm':[.0005,.02],'both_positive_and_negative_commands_supported':True,
                'preserve':'All original geometry, masses, frame relationships, construction operations and acceptance predicates',
                'construction_path':'Append exactly the author-supplied typed operations as a named dependent batch to a copied baseline plan; validate/compile through existing AssemblyComposer against actual EMPTY r0. Never apply.'},
            'permissions':{'apply':False,'execute_source':False,'model_simulation_tool':False,'max_proposals':1}}
    @property
    def schemas(self):
        if self.stage>=2:return []
        if self.stage==0:
            return [{'type':'function','name':'inspect_assembly_physical_failure','strict':True,
                'description':'Inspect the actual source-bound proposed assembly and measured native failure, actual axes, commands, contacts and strict repair permissions. No simulation or application.',
                'parameters':obj({})}]
        operations=[]
        for target in self.targets:
            old=self.objects[target]['actuator'];maximum=min(.02,old['limit'])
            operation=copy.deepcopy(next(s for s in SCHEMAS if s['properties']['kind']['enum']==['set_actuator']))
            operation['properties']['target']={'type':'string','enum':[target],
                'description':'World joint body ID of this existing rear actuator; not a ShapeSpec part ID.'}
            operation['properties']['actuator']=obj({'limit':{'type':'number','enum':[old['limit']]},
                'unit':{'type':'string','enum':[old['unit']]},'command':{'anyOf':[
                    {'type':'number','minimum':.0005,'maximum':maximum},
                    {'type':'number','minimum':-maximum,'maximum':-.0005}]}})
            operations.append(operation)
        params=obj({'expected_sha256':{'type':'string','pattern':'^[0-9a-f]{64}$'},
            'expected_revision':{'type':'integer','enum':[0]},
            'baseline_proposal_id':{'type':'string','enum':[self.baseline['proposal_id']]},
            'physical_feedback_sha256':{'type':'string','enum':[self.feedback['feedback_sha256']]},
            'step_id':ID,'operations':{'type':'array','minItems':1,'maxItems':2,'items':{'anyOf':operations}},
            'explanation':{'type':'string','minLength':1,'maxLength':500}})
        return [{'type':'function','name':'propose_assembly_physical_repair','strict':True,
            'description':'Author one exact review-only actuator change batch. Select your own valid commands; both signs are supported. Keep inspected authority/unit, geometry and original operations. No automatic reversal, application, simulation, source or retry. Compilation is distinct from measured success.',
            'parameters':wire_schema(params)}]
    def dispatch(self,name,args):
        try:
            schema=next((s for s in self.schemas if s['name']==name),None)
            if schema is None:raise ValueError('One inspection and one author-supplied physical repair only')
            Draft202012Validator(schema['parameters']).validate(args)
            if self.composer.service.current()!=self.before:raise ValueError('Authoritative head changed')
            self.composer.reconstruct(self.baseline)
            if physical_feedback(self.baseline,self.native)!=self.feedback:raise ValueError('Physical failure evidence changed')
            if self.stage==0:out={'ok':True,'result':self.inspection()};self.stage=1
            else:
                if args['expected_sha256']!=identity(self.before) or args['expected_revision']!=self.before['revision']:raise ValueError('Stale authoritative head revision/hash')
                seen=set()
                for op in args['operations']:
                    target=op['target'];a=op['actuator'];old=self.objects[target]['actuator']
                    if target in seen:raise ValueError('Duplicate actuator target')
                    seen.add(target)
                    if not a or a['limit']!=old['limit'] or a['unit']!=old['unit'] or not .0005<=abs(a['command'])<=.02 or abs(a['command'])>a['limit']:
                        raise ValueError('Repair command/authority/unit outside unchanged contract')
                plan=amended_plan(self.baseline['assembly_plan'],args['operations'],args['step_id'],args['explanation'])
                q=self.composer.propose(args['expected_sha256'],args['expected_revision'],plan,origin='AUTHOR_SUPPLIED_PHYSICAL_REPAIR_REVIEW')
                # Keep explicit lineage beside the actual ordinary assembly
                # proposal; never alter its content-addressed source record.
                out={'ok':True,'result':q,'repair':{'baseline_proposal_id':self.baseline['proposal_id'],
                    'physical_feedback_sha256':self.feedback['feedback_sha256'],'operations':copy.deepcopy(args['operations']),
                    'explanation':args['explanation'],'authorship':'Supplied by caller; provider receipts required before calling this an AI repair.',
                    'status':'COMPILED_REVIEW_ONLY; native outcome NOT_EXECUTED'}}
                self.stage=2;self.result=out
        except Exception as exc:
            self.stage=2;out={'ok':False,'error':{'type':type(exc).__name__,'message':str(exc)[:500]}}
            self.result=out
        self.trace.append('assembly_physical_repair_tool_completed',{'name':name,'output':out,'model_requests_by_tool':0})
        return out
