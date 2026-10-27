"""Explicit deterministic planner for the one supported device goal, not an LLM."""
import re
from dataclasses import replace
from hardware.template import barrier
from hardware.assemblies import identity
from hardware.validation import inspect
from .contracts import DeviceSpec


def plan(request):
    if not isinstance(request,str) or not 1<=len(request)<=2000:raise ValueError('Bounded device goal required')
    text=request.lower()
    if not all(re.search(pattern,text) for pattern in (r'\bbarrier\b',r'\bopen\w*\b',r'\bclos\w*\b',r'\b(sensor|object)\b')):
        raise ValueError('Unsupported goal: this deterministic planner supports only an object/sensor-controlled opening and closing barrier')
    spec=DeviceSpec();threshold=re.search(r'within\s+([0-9]+(?:\.[0-9]+)?)\s*(cm|m)\b',text)
    if threshold:
        distance=float(threshold[1])*(.01 if threshold[2]=='cm' else 1.)
        spec=replace(spec,logic=replace(spec.logic,threshold_m=distance,clear_threshold_m=distance+.15))
    assembly=barrier()
    return {'origin':'DETERMINISTIC_SUPPORTED_GOAL_PARSER + HUMAN_DEFINED_TEMPLATE','request':request,'status':'PLAN_FOR_REVIEW',
        'assembly':assembly,'assembly_sha256':identity(assembly),'spec':spec.to_dict(),'diagnostics':inspect(assembly),
        'steps':['Inspect catalog identities and unknown ratings.','Review explicit divider, external servo power and common ground.',
                 'Inspect reference state machine and documented sampled interfaces.','Run trusted MuJoCo only after electrical preconditions pass.',
                 'Inspect measured acceptance and review corrections separately.'],
        'model_requests':0,'installation_effect':'NONE','limitations':['One supported device grammar; no general device synthesis or autonomous AI build.']}
