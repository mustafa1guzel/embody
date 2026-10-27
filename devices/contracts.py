"""Typed SI cross-domain contract. These are reference-model assumptions."""
from dataclasses import dataclass, asdict, field, fields
import math
from physics.contracts import digest


@dataclass(frozen=True)
class Mechanical:
    length_m: float = .24
    mass_kg: float = .035
    torque_limit_nm: float = .12
    damping_nm_s_rad: float = .015
    timestep_s: float = .002
    joint_range_rad: tuple = (0.,1.65)


@dataclass(frozen=True)
class Sensor:
    origin_m: tuple = (0.,-.12,.08)
    direction: tuple = (1.,0.,0.)
    minimum_m: float = .02
    maximum_m: float = 4.
    interval_s: float = .07
    latency_s: float = .02
    quantization_m: float = .001


@dataclass(frozen=True)
class Logic:
    threshold_m: float = .45
    clear_threshold_m: float = .60
    debounce_samples: int = 2
    update_s: float = .02
    open_target_rad: float = 1.4
    hold_s: float = .4
    timeout_s: float = 2.
    stale_s: float = .25
    close_while_near: bool = False


@dataclass(frozen=True)
class Environment:
    initial_object_x_m: float = .8
    near_object_x_m: float = .25
    approach_end_s: float = 2.
    departure_end_s: float = 4.2
    object_half_extent_m: float = .04
    duration_s: float = 8.


@dataclass(frozen=True)
class Requirements:
    open_angle_rad: float = 1.25
    opening_deadline_s: float = 2.
    closed_tolerance_rad: float = .04
    max_speed_rad_s: float = 6.
    joint_tolerance_rad: float = .01


@dataclass(frozen=True)
class DeviceSpec:
    schema_version: int = 1
    device_id: str = 'sensor_controlled_barrier'
    mechanical: Mechanical = field(default_factory=Mechanical)
    sensor: Sensor = field(default_factory=Sensor)
    logic: Logic = field(default_factory=Logic)
    environment: Environment = field(default_factory=Environment)
    requirements: Requirements = field(default_factory=Requirements)

    def __post_init__(self):
        if type(self.schema_version) is not int or self.schema_version!=1 or self.device_id!='sensor_controlled_barrier':raise ValueError('Unsupported device')
        def finite(x):
            if type(x) not in (float,int) or not math.isfinite(x):raise ValueError('Nonfinite device value')
        for group in (self.mechanical,self.sensor,self.logic,self.environment,self.requirements):
            for key,value in asdict(group).items():
                if isinstance(value,(tuple,list)):
                    for v in value:finite(v)
                elif group is self.logic and key=='close_while_near':
                    if type(value) is not bool:raise ValueError('Boolean close behavior required')
                else:finite(value)
        m,s,l,e,r=self.mechanical,self.sensor,self.logic,self.environment,self.requirements
        if not (.1<=m.length_m<=.5 and .01<=m.mass_kg<=2 and .005<=m.torque_limit_nm<=.17 and .001<=m.damping_nm_s_rad<=.1 and m.timestep_s==.002 and tuple(m.joint_range_rad)==(0.,1.65)):
            raise ValueError('Unsupported mechanical envelope')
        if not (len(s.origin_m)==3 and len(s.direction)==3 and abs(sum(x*x for x in s.direction)-1)<1e-12 and all(abs(x)<=2 for x in s.origin_m)
                and s.minimum_m==.02 and s.maximum_m==4. and .06<=s.interval_s<=.2 and 0<=s.latency_s<=.1 and .0001<=s.quantization_m<=.01):raise ValueError('Unsupported sensor envelope')
        if not (0.1<=l.threshold_m<l.clear_threshold_m<=1. and type(l.debounce_samples) is int and 1<=l.debounce_samples<=5 and l.update_s==.02
                and 1.3<=l.open_target_rad<=1.5 and .1<=l.hold_s<=1 and .5<=l.timeout_s<=3 and .2<=l.stale_s<=.5 and type(l.close_while_near) is bool):raise ValueError('Unsupported control envelope')
        if not (.7<=e.initial_object_x_m<=1 and .2<=e.near_object_x_m<=.3 and 1<=e.approach_end_s<=2.5 and 4<=e.departure_end_s<=5
                and e.object_half_extent_m==.04 and e.duration_s==8.):raise ValueError('Unsupported environment envelope')
        if r!=Requirements():raise ValueError('Acceptance criteria are fixed for this reference device')

    def to_dict(self):return asdict(self)
    @property
    def identity(self):return digest(self.to_dict())

    @classmethod
    def from_dict(cls,data):
        if not isinstance(data,dict) or set(data)!={f.name for f in fields(cls)}:raise ValueError('Invalid device fields')
        result={k:data[k] for k in ('schema_version','device_id')}
        for key,kind in [('mechanical',Mechanical),('sensor',Sensor),('logic',Logic),('environment',Environment),('requirements',Requirements)]:
            if not isinstance(data[key],dict) or set(data[key])!={f.name for f in fields(kind)}:raise ValueError('Invalid '+key+' fields')
            result[key]=kind(**data[key])
        return cls(**result)
