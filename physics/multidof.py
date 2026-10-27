"""Robot-independent vector contract. Robot-specific evaluators establish premises."""
from dataclasses import dataclass, asdict
import json
from .contracts import finite, sha, canonical, digest


@dataclass(frozen=True)
class JointLimit:
    name: str
    kind: str
    position_unit: str
    effort_unit: str
    position_range: tuple[float, float]
    effort_range: tuple[float, float]

    def __post_init__(self):
        if not self.name or (self.kind, self.position_unit, self.effort_unit) not in (
                ('revolute', 'rad', 'N*m'), ('prismatic', 'm', 'N')):
            raise ValueError('Invalid joint dimensions')
        for name in ('position_range', 'effort_range'):
            pair = tuple(getattr(self, name)); object.__setattr__(self, name, pair)
            if len(pair) != 2: raise ValueError('Expected a bounded interval')
            for v in pair: finite(name, v)
            if pair[0] >= pair[1]: raise ValueError('Invalid joint interval')
        if not self.effort_range[0] < 0 < self.effort_range[1]:
            raise ValueError('Effort range must straddle zero')


@dataclass(frozen=True)
class MultiDOFContract:
    family: str
    robot_id: str
    scenario_id: str
    model_sha256: str
    controller_sha256: str
    context_sha256: str
    joints: tuple[JointLimit, ...]
    q0: tuple[float, ...]
    v0: tuple[float, ...]
    target_m: tuple[float, float, float]
    end_effector_site: str
    gravity_mps2: tuple[float, float, float]
    timestep_s: float
    duration_s: float
    target_tolerance_m: float
    final_velocity_limit: float
    maximum_velocity: float
    settling_window_s: float
    joint_limit_tolerance: float
    no_contact: bool
    assumptions: tuple[str, ...]
    body_masses_kg: tuple[tuple[str, float], ...]
    joint_axes_world: tuple[tuple[float, float, float], ...]
    frame: str = 'world_X_forward_Y_left_Z_up_SI'
    schema_version: int = 1

    def __post_init__(self):
        for name in ('family', 'robot_id', 'scenario_id', 'end_effector_site'):
            if not isinstance(getattr(self, name), str) or not getattr(self, name): raise ValueError('Missing identity')
        for name in ('model_sha256', 'controller_sha256', 'context_sha256'): sha(getattr(self, name))
        object.__setattr__(self, 'joints', tuple(self.joints))
        if not self.joints or any(not isinstance(j, JointLimit) for j in self.joints): raise ValueError('Validated joints required')
        if len({j.name for j in self.joints}) != len(self.joints): raise ValueError('Duplicate joints')
        object.__setattr__(self,'joint_axes_world',tuple(tuple(v) for v in self.joint_axes_world))
        if len(self.joint_axes_world)!=len(self.joints) or self.frame!='world_X_forward_Y_left_Z_up_SI':
            raise ValueError('Invalid frame/axis dimensions')
        for axis in self.joint_axes_world:
            if len(axis)!=3:raise ValueError('Invalid movement axis')
            for value in axis:finite('axis',value)
            if abs(sum(v*v for v in axis)-1)>1e-10:raise ValueError('Axis must be normalized')
        for name in ('q0', 'v0', 'target_m', 'gravity_mps2'):
            value = tuple(getattr(self, name)); object.__setattr__(self, name, value)
            if len(value) != (len(self.joints) if name in ('q0', 'v0') else 3): raise ValueError('Vector dimension mismatch')
            for v in value: finite(name, v)
        for q, j in zip(self.q0, self.joints):
            if not j.position_range[0] <= q <= j.position_range[1]: raise ValueError('Initial configuration outside joint limits')
        for name in ('timestep_s', 'duration_s', 'target_tolerance_m', 'final_velocity_limit', 'maximum_velocity', 'settling_window_s'):
            finite(name, getattr(self, name), positive=True)
        finite('joint tolerance', self.joint_limit_tolerance, nonnegative=True)
        if self.settling_window_s > self.duration_s or self.final_velocity_limit > self.maximum_velocity:
            raise ValueError('Inconsistent task limits')
        ratio = self.duration_s/self.timestep_s
        if abs(ratio-round(ratio)) > 1e-8: raise ValueError('Horizon must contain whole timesteps')
        if type(self.no_contact) is not bool: raise ValueError('Invalid contact requirement')
        object.__setattr__(self, 'assumptions', tuple(self.assumptions))
        object.__setattr__(self, 'body_masses_kg', tuple(tuple(v) for v in self.body_masses_kg))
        if not self.assumptions or not self.body_masses_kg: raise ValueError('Missing physical premises')
        for name, mass in self.body_masses_kg: finite(name, mass, positive=True)
        if self.schema_version != 1: raise ValueError('Unknown schema')

    def to_dict(self): return json.loads(canonical(asdict(self)))

    @classmethod
    def from_dict(cls, value):
        value = dict(value); value['joints'] = tuple(JointLimit(**j) for j in value['joints'])
        return cls(**value)

    @property
    def identity(self): return digest(self.to_dict())
