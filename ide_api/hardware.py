"""Same-origin Hardware Studio operations over the one authoritative graph."""
from pathlib import Path
from uuid import uuid4
import copy
from hardware.library import catalog, catalog_hash
from hardware.assemblies import validate, identity, instance, connect, remove_wire, fields
from hardware.serialization import Store, export, load
from hardware.validation import inspect
from hardware.template import barrier
from hardware.proposals import propose, apply
from devices.contracts import DeviceSpec
from devices.simulation import run
from core.simulation import ROOT
from robustness.contracts import write_once


class HardwareService:
    def __init__(self,root=None):self.root=Path(root) if root else ROOT/'artifacts/day11_12/workspaces'
    def bootstrap(self):
        source=(ROOT/'devices/controller.py').read_text()
        import hashlib
        return {'catalog':catalog(),'catalog_sha256':catalog_hash(),'template':barrier(),'device_spec':DeviceSpec().to_dict(),
          'controller_source':{'path':'devices/controller.py','content':source,'sha256':hashlib.sha256(source.encode()).hexdigest(),'historical':True},
          'planner_origin':'HUMAN_DEFINED_TEMPLATE; deterministic instantiation, no live AI build',
          'live_agent_status':'UNTESTED; no API spending authorized'}
    def plan(self,request):
        from devices.planner import plan
        return plan(request)
    def inspect(self,a):return inspect(a)
    def edit(self,a,op):
        a=validate(a);result=copy.deepcopy(a)
        kind=op.get('kind')
        if kind=='connect':fields(op,['kind','a','b']);return connect(a,op['a'],op['b'])
        if kind=='disconnect':fields(op,['kind','wire_id']);return remove_wire(a,op['wire_id'])
        if kind=='add':
            fields(op,['kind','part']);result['components'].append(instance(a,op['part']))
        elif kind in ('transform','rename','delete','roles'):
            expected={'transform':['position_m','rotation_rad'],'rename':['name'],'roles':['roles'],'delete':[]}[kind]
            fields(op,['kind','component',*expected]);c=next((c for c in result['components'] if c['id']==op['component']),None)
            if c is None:raise ValueError('Unknown component')
            if kind=='delete':
                for w in list(result['wires']):
                    if c['id'] in (w['a']['component'],w['b']['component']):result=remove_wire(result,w['id'])
                result['components']=[x for x in result['components'] if x['id']!=c['id']]
            else:
                for key in expected:c[key]=copy.deepcopy(op[key])
        else:raise ValueError('Unsupported assembly edit')
        result['revision']+=1;return validate(result)
    def save(self,a):return Store(self.root/'assemblies').save(a)
    def load(self,key):return Store(self.root/'assemblies').get(key)
    def import_data(self,envelope):
        from physics.contracts import canonical
        return load(canonical(envelope).encode())
    def run(self,a,spec):
        spec=DeviceSpec.from_dict(spec);a=validate(a)
        output=self.root/'runs'/('run_'+uuid4().hex)
        result=run(a,spec,output)
        return {**result,'evidence_path':str(output.relative_to(ROOT)) if ROOT in output.parents else str(output)}
    def propose(self,a,operations,explanation):
        value=propose(a,identity(a),operations,explanation)
        write_once(self.root/'proposals'/('proposal_'+uuid4().hex+'.json'),value)
        return value
    def apply(self,a,proposal,confirmation):
        result=apply(a,proposal,confirmation)
        write_once(self.root/'proposal_actions'/('apply_'+uuid4().hex+'.json'),{'action':'APPLY_WIRING_CHANGE','base_sha256':identity(a),'result':export(result),'installation_effect':'NONE'})
        return result
