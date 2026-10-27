"""Capability-limited facade for the existing AgentOrchestrator, no live calls."""
import copy,json
from world.schema import obj
from .actions import OPERATIONS

IDENTITY={'type':'string','minLength':64,'maxLength':64,'pattern':'^[0-9a-f]{64}$'}
PARAMETERS=obj({'expected_sha256':IDENTITY,'expected_revision':{'type':'integer','minimum':0,'maximum':999999},'operations':OPERATIONS,'explanation':{'type':'string','minLength':1,'maxLength':2000}})
SCHEMAS=({'type':'function','name':'inspect_engineering','strict':True,'description':'Inspect bounded authoritative identities, mechanical/electrical context and measured diagnosis. No execution.','parameters':obj({})},{'type':'function','name':'propose_engineering_change','strict':True,'description':'Validate one typed ordered changeset against exact project hash/revision. Review only. Cannot execute, install, apply or call a model.','parameters':PARAMETERS})
RESULT_SCHEMA={'oneOf':[obj({'ok':{'const':True},'result':{'type':'object'}}),obj({'ok':{'const':False},'error':obj({'type':{'type':'string'},'message':{'type':'string'}})})]}

class EngineeringTools:
    def __init__(self,service,trace):self.service=service;self.trace=trace
    @property
    def schemas(self):return copy.deepcopy(SCHEMAS)
    def dispatch(self,name,arguments):
        from jsonschema import Draft202012Validator
        self.trace.append('tool_requested',{'name':name,'arguments':arguments})
        try:
            schema=next((s for s in SCHEMAS if s['name']==name),None)
            if schema is None or len(json.dumps(arguments,allow_nan=False).encode())>20000 or not Draft202012Validator(schema['parameters']).is_valid(arguments):raise ValueError('Unsupported tool or exact structured parameters')
            if name=='inspect_engineering':value=self.service.inspect_context()
            else:
                if type(arguments['expected_revision']) is not int:raise ValueError('Exact integer revision required')
                value=self.service.propose(arguments['expected_sha256'],arguments['expected_revision'],arguments['operations'],arguments['explanation'])
            result={'ok':True,'result':value}
        except (ValueError,KeyError,TypeError,OSError,StopIteration) as exc:result={'ok':False,'error':{'type':type(exc).__name__,'message':str(exc)[:300]}}
        self.trace.append('tool_completed',{'name':name,'output':result});return result
