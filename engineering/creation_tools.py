"""Typed review-only facade for the existing AgentOrchestrator, no commit tool."""
import copy,json
from jsonschema import Draft202012Validator
from world.schema import obj
from .agent import IDENTITY
from .requirements import PARAMETERS

REF=obj({'proposal_id':IDENTITY,'expected_sha256':IDENTITY,'expected_revision':{'type':'integer','minimum':0,'maximum':999999}})
SCHEMAS=[{'type':'function','name':name,'strict':True,'description':description,'parameters':parameters} for name,description,parameters in [
 ('inspect_creation_capabilities','Inspect two bounded families and explicit unsupported domains; no execution.',obj({})),
 ('create_device_plan','Prepare a deterministic proposal from an empty independent project; no build, application, simulation, source or spending authority.',obj({'request':{'type':'string','minLength':1,'maxLength':1000},'parameters':PARAMETERS})),
 ('inspect_creation_plan','Read a specific stored creation proposal, without mutation.',obj({'proposal_id':IDENTITY})),
 ('validate_creation','Independently replay bounded data batches against the exact empty base; compile only, no dynamics or application.',REF)]]

class CreationTools:
    def __init__(self,manager,trace):self.manager=manager;self.trace=trace
    @property
    def schemas(self):return copy.deepcopy(SCHEMAS)
    def dispatch(self,name,arguments):
        self.trace.append('tool_requested',{'name':name,'arguments':arguments})
        try:
            schema=next((s for s in SCHEMAS if s['name']==name),None)
            if schema is None or len(json.dumps(arguments,allow_nan=False).encode())>12000 or not Draft202012Validator(schema['parameters']).is_valid(arguments):raise ValueError('Exact bounded creation tool schema required')
            if name=='inspect_creation_capabilities':value=self.manager.capabilities()
            elif name=='create_device_plan':value=self.manager.start(arguments['request'],arguments['parameters'])
            elif name=='inspect_creation_plan':value=self.manager.proposals.get(arguments['proposal_id'])
            else:
                p,service,candidate=self.manager.validate_proposal(arguments['proposal_id'],arguments['expected_sha256'],arguments['expected_revision']);value={'status':'VALIDATED_NOT_BUILT','resulting_sha256':p['resulting_sha256'],'model_application_authority':False}
            output={'ok':True,'result':value}
        except (ValueError,KeyError,OSError,TypeError) as exc:output={'ok':False,'error':{'type':type(exc).__name__,'message':str(exc)[:300]}}
        self.trace.append('tool_completed',{'name':name,'output':output});return output
