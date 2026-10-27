"""Explicit two-family deterministic interpreter, not unrestricted language AI."""
import re,json,math
from jsonschema import Draft202012Validator
from world.schema import obj,num
from physics.contracts import digest

PARAMETERS=obj({'span_m':num(.1,.5),'mass_kg':num(.01,2),'torque_nm':num(.005,.17),'height_m':num(.12,.3),'frame_width_m':num(.12,.18),'temple_length_m':num(.10,.16),'frame_thickness_m':num(.005,.012)})
DEFAULTS={'span_m':.24,'mass_kg':.035,'torque_nm':.12,'height_m':.18,'frame_width_m':.14,'temple_length_m':.12,'frame_thickness_m':.005}
UNKNOWNS=['Real current/power/thermal margins','Manufacturing tolerances and mounting strength','Real firmware and hardware behavior']
def interpret(request,parameters=None):
    if not isinstance(request,str) or not 1<=len(request)<=1000:raise ValueError('Request must contain 1..1000 characters')
    text=request.lower();families=[f for f,k in [('sensor_barrier','barrier'),('smart_glasses','glasses')] if k in text]
    if len(families)!=1 or 'gripper' in text:raise ValueError('Creation supports barrier or smart glasses concept only; mixed/other families blocked')
    values=dict(DEFAULTS)
    for key,pattern in [('span_m',r'\bspan\s+(\d+(?:\.\d+)?)\s*m\b'),('mass_kg',r'\bmass\s+(\d+(?:\.\d+)?)\s*kg\b'),('torque_nm',r'\btorque\s+(\d+(?:\.\d+)?)\s*n\s*\*?\s*m\b')]:
        matches=re.findall(pattern,text)
        if len(matches)>1:raise ValueError('Conflicting numerical requirements')
        if matches:values[key]=float(matches[0])
    if parameters is not None:
        if not isinstance(parameters,dict) or set(parameters)-set(DEFAULTS):raise ValueError('Unknown numerical requirement')
        values.update(parameters)
    if any(type(v) not in (int,float) or not math.isfinite(v) for v in values.values()):raise ValueError('Finite numerical SI parameters required')
    if not Draft202012Validator(PARAMETERS).is_valid(values):raise ValueError('Numerical requirements exceed supported SI bounds')
    blocked=[]
    if families[0]=='sensor_barrier':
        for word in ('camera','solar','waterproof','wireless','certified'):
            if word in text:blocked.append('Unsupported barrier requirement: '+word)
    return {'schema_version':1,'status':'PARSED_SUPPORTED_FAMILY' if not blocked else 'BLOCKED_UNSUPPORTED_REQUIREMENTS','request':request,'request_sha256':digest(request),'family':families[0],'parameters':values,'blocked':blocked,'unknowns':UNKNOWNS+(['Optics','Battery safety','RF','Acoustics','Wearability'] if families[0]=='smart_glasses' else []),'origin':'DETERMINISTIC_FAMILY_MATCHING; only explicit span/mass/torque phrases and typed SI overrides are parsed'}
