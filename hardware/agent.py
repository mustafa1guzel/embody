"""Additive traced hardware tools; live transport requires separate approval.

The six existing tool names/schemas and candidate verifier remain unchanged.
These two additional bounded hardware tools only inspect and propose data.
"""
import copy
from .assemblies import validate, identity
from .library import catalog
from .validation import inspect
from .proposals import propose
from .tool_contract import PROPOSAL_PARAMETERS,validate_proposal_arguments


class HardwareTools:
    def __init__(self,base,assembly,device_spec):
        self.base=base;self.assembly=validate(assembly);self.device_spec=copy.deepcopy(device_spec)
    def __getattr__(self,name):
        return getattr(self.base,name)
    def inspection_context(self):
        return {'catalog':catalog(),'circuitbase':self.assembly,'assembly_sha256':identity(self.assembly),
            'electrical':inspect(self.assembly),'device_spec':self.device_spec,'origin':'AUTHORITATIVE_LOCAL_DATA; no model result'}
    @property
    def schemas(self):
        return (*self.base.schemas,
          {'type':'function','name':'inspect_hardware','description':'Read selected CIRCUITBASE, catalog, electrical diagnostics and explicit mechanical/control mappings. No execution.',
           'strict':True,'parameters':{'type':'object','properties':{},'required':[],'additionalProperties':False}},
          {'type':'function','name':'propose_hardware_change','description':'Propose 1–16 typed connect/disconnect wiring operations for the inspected assembly and revision. Review only; cannot apply, execute or install.',
           'strict':True,'parameters':copy.deepcopy(PROPOSAL_PARAMETERS)})
    def dispatch(self,name,arguments):
        if name not in ('inspect_hardware','propose_hardware_change'):return self.base.dispatch(name,arguments)
        self.base.trace.append('tool_requested',{'name':name,'arguments':arguments})
        try:
            if name=='inspect_hardware':
                if arguments!={}:raise ValueError('No inspection arguments supported')
                value=self.inspection_context()
            else:
                validate_proposal_arguments(arguments)
                if arguments['expected_revision']!=self.assembly['revision']:raise ValueError('Stale assembly revision')
                value=propose(self.assembly,arguments['expected_sha256'],arguments['operations'],arguments['explanation'],origin='model_tool_proposal_untrusted_data')
            result={'ok':True,'result':value}
        except (ValueError,TypeError,KeyError) as exc:result={'ok':False,'error':{'type':type(exc).__name__,'message':str(exc)}}
        self.base.trace.append('tool_completed',{'name':name,'output':result});return result
