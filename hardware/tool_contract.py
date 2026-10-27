"""One strict schema shared by model generation and local hardware-tool validation."""
import copy
import json
from jsonschema import Draft202012Validator


def object_schema(properties):
    return {'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}


COMPONENT_ID={'type':'string','minLength':1,'maxLength':64,'pattern':'^[a-zA-Z][a-zA-Z0-9_-]{0,63}$'}
PIN_ID={'type':'string','minLength':1,'maxLength':64,'pattern':'^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$'}
ENDPOINT=object_schema({'component':COMPONENT_ID,'pin':PIN_ID})
DISCONNECT=object_schema({'kind':{'type':'string','enum':['disconnect']},'wire_id':{
    **COMPONENT_ID,'description':'Exact existing wire id returned by inspect_hardware.'}})
CONNECT=object_schema({'kind':{'type':'string','enum':['connect']},'a':copy.deepcopy(ENDPOINT),'b':copy.deepcopy(ENDPOINT)})
PROPOSAL_PARAMETERS=object_schema({
    'expected_sha256':{'type':'string','pattern':'^[0-9a-f]{64}$','minLength':64,'maxLength':64,
                       'description':'Exact current assembly_sha256 from inspection; includes graph revision.'},
    'expected_revision':{'type':'integer','minimum':0,'maximum':999999,
                         'description':'Exact current circuitbase.revision from inspection.'},
    'operations':{'type':'array','minItems':1,'maxItems':16,'items':{'anyOf':[DISCONNECT,CONNECT]},
                  'description':'Ordered wiring-only operations using existing IDs. No JSON strings, op/remove_wire dialect, paths, code or application.'},
    'explanation':{'type':'string','minLength':1,'maxLength':4000,
                   'description':'Concise review explanation; retain UNKNOWN electrical properties. Validation is authoritative.'},
})


def validate_proposal_arguments(arguments):
    # Reject non-JSON / oversized values before recursive schema validation.
    raw=json.dumps(arguments,allow_nan=False,ensure_ascii=False).encode()
    if len(raw)>20_000:raise ValueError('Hardware tool arguments exceed 20000 bytes')
    if not Draft202012Validator(PROPOSAL_PARAMETERS).is_valid(arguments):
        raise ValueError('Hardware tool arguments violate the declared structured schema')
    if type(arguments['expected_revision']) is not int:
        raise ValueError('Assembly revision must be an integer')
    return arguments
