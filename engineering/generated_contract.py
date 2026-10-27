"""Explicit generated-world protocol. Historical DeviceSpec acceptance is untouched."""
import copy
from dataclasses import asdict,replace
from types import SimpleNamespace
from devices.contracts import DeviceSpec
from physics.contracts import digest

class GeneratedSpec(SimpleNamespace):
    @classmethod
    def from_dict(cls,data):
        d=copy.deepcopy(data)
        try:
            m,e=d['mechanical'],d['environment']
            if m['timestep_s']!=.005 or e['duration_s']!=5. or e['approach_end_s']!=1.5 or e['departure_end_s']!=3. or not .01<=e['object_half_extent_m']<=.1:raise ValueError('Generated protocol bounds changed')
            half=e['object_half_extent_m'];m['timestep_s']=.002;e.update(duration_s=8.,departure_end_s=4.2,object_half_extent_m=.04)
        except (KeyError,TypeError):raise ValueError('Invalid generated contract fields') from None
        old=DeviceSpec.from_dict(d)
        return cls(schema_version=old.schema_version,device_id=old.device_id,mechanical=replace(old.mechanical,timestep_s=.005),sensor=old.sensor,logic=old.logic,environment=replace(old.environment,duration_s=5.,departure_end_s=3.,object_half_extent_m=half),requirements=old.requirements)
    def to_dict(self):
        return {k:asdict(v) if hasattr(v,'__dataclass_fields__') else v for k,v in vars(self).items()}
    @property
    def identity(self):return digest(self.to_dict())

def default_generated_spec():
    d=DeviceSpec().to_dict();d['mechanical']['timestep_s']=.005;d['environment'].update(duration_s=5.,approach_end_s=1.5,departure_end_s=3.)
    return GeneratedSpec.from_dict(d)
