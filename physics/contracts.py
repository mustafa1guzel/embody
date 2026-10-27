"""Immutable SI contracts extracted from physical configuration, never model prose."""
from __future__ import annotations
from dataclasses import asdict, dataclass
import hashlib
import json
import math

UNITS = {'mass': 'kg', 'force': 'N', 'length': 'm', 'time': 's',
         'velocity': 'm/s', 'acceleration': 'm/s^2', 'jerk': 'm/s^3',
         'work': 'J', 'power': 'W', 'angle': 'rad'}
PROBE_COLUMNS = ('position_m', 'velocity_mps', 'command', 'scalar_force_n',
                 'generalized_force_n', 'generalized_inertia_kg', 'acceleration_mps2', 'contact_count')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def finite(name, value, *, positive=False, nonnegative=False):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(name+' must be finite numeric SI data')
    if positive and value <= 0 or nonnegative and value < 0:
        raise ValueError(name+' has invalid sign')


def sha(value):
    if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
        raise ValueError('Invalid SHA-256 identity')


@dataclass(frozen=True)
class PhysicsContract:
    scenario_id: str
    robot_id: str
    model_sha256: str
    controller_sha256: str
    context_sha256: str
    source_hashes: tuple[tuple[str, str], ...]
    mass_kg: float
    generalized_inertia_kg: float
    body_masses_kg: tuple[tuple[str, float], ...]
    joint_name: str
    joint_type: str
    axis_world: tuple[float, float, float]
    actuator_name: str
    transmission: str
    gain_type: str
    bias_type: str
    dynamics_type: str
    gear: float
    control_range: tuple[float, float]
    scalar_force_range_n: tuple[float, float]
    braking_force_n: float
    frame: str
    bumper_front_offset_m: float
    bumper_half_size_m: tuple[float, float, float]
    wall_center_m: tuple[float, float, float]
    wall_half_size_m: tuple[float, float, float]
    wall_near_x_m: float
    initial_position_m: float
    initial_velocity_mps: float
    initial_clearance_m: float
    maximum_speed_mps: float
    timestep_s: float
    duration_s: float
    deadline_s: float
    minimum_clearance_m: float
    final_speed_tolerance_mps: float
    gravity_mps2: tuple[float, float, float]
    integrator: str
    checks: tuple[tuple[str, bool], ...]
    assumptions: tuple[str, ...]
    force_probe_evidence: tuple[tuple[float, ...], ...] = ()
    distance_tolerance_m: float = 1e-12
    numeric_tolerance: float = 1e-12
    uncertainties: tuple[tuple[str, float, float], ...] = ()
    provenance_kind: str = 'compiled_project'
    schema_version: int = 1

    def __post_init__(self):
        for name in ('scenario_id', 'robot_id', 'joint_name', 'joint_type', 'actuator_name',
                     'transmission', 'gain_type', 'bias_type', 'dynamics_type', 'integrator'):
            if not isinstance(getattr(self, name), str) or not getattr(self, name):
                raise ValueError('Missing '+name)
        if self.frame != 'world_X_forward_Y_left_Z_up_SI':
            raise ValueError('Unsupported coordinate frame')
        for name in ('model_sha256', 'controller_sha256', 'context_sha256'):
            sha(getattr(self, name))
        tuple_fields = ('source_hashes', 'body_masses_kg', 'checks', 'assumptions', 'uncertainties', 'force_probe_evidence')
        for name in tuple_fields:
            value = tuple(tuple(v) if isinstance(v, (tuple, list)) else v for v in getattr(self, name))
            object.__setattr__(self, name, value)
        for name in ('axis_world', 'bumper_half_size_m', 'wall_center_m', 'wall_half_size_m', 'gravity_mps2'):
            value = tuple(getattr(self, name))
            if len(value) != 3:
                raise ValueError('Invalid vector: '+name)
            for v in value:
                finite(name, v, positive=name in ('bumper_half_size_m', 'wall_half_size_m'))
            object.__setattr__(self, name, value)
        if not math.isclose(sum(v*v for v in self.axis_world), 1, abs_tol=1e-12, rel_tol=0):
            raise ValueError('Movement axis must be a unit vector')
        for name in ('mass_kg', 'generalized_inertia_kg', 'maximum_speed_mps', 'timestep_s',
                     'duration_s', 'deadline_s', 'final_speed_tolerance_mps'):
            finite(name, getattr(self, name), positive=True)
        for name in ('braking_force_n', 'minimum_clearance_m'):
            finite(name, getattr(self, name), nonnegative=True)
        ratio = self.duration_s/self.timestep_s
        if not math.isfinite(ratio) or not math.isclose(ratio, round(ratio), rel_tol=0, abs_tol=1e-8):
            raise ValueError('Duration must contain a whole number of simulation steps')
        for name in ('gear', 'bumper_front_offset_m', 'wall_near_x_m', 'initial_position_m',
                     'initial_velocity_mps', 'initial_clearance_m'):
            finite(name, getattr(self, name))
        for name in ('distance_tolerance_m', 'numeric_tolerance'):
            finite(name, getattr(self, name), positive=True)
            if getattr(self, name) > 1e-6:
                raise ValueError('Tolerance is too loose for this model')
        for name in ('control_range', 'scalar_force_range_n'):
            value = tuple(getattr(self, name))
            if len(value) != 2:
                raise ValueError('Invalid range')
            for v in value:
                finite(name, v)
            if not value[0] <= 0 <= value[1]:
                raise ValueError('Actuator range must contain zero')
            object.__setattr__(self, name, value)
        if abs(self.wall_near_x_m - (self.wall_center_m[0]-self.wall_half_size_m[0])) > 1e-10:
            raise ValueError('Inconsistent wall surface geometry')
        gap = self.wall_near_x_m-self.initial_position_m-self.bumper_front_offset_m
        if abs(self.initial_clearance_m-gap) > 1e-10:
            raise ValueError('Inconsistent initial surface clearance')
        if len(dict(self.source_hashes)) != len(self.source_hashes) or not self.source_hashes:
            raise ValueError('Invalid source identities')
        for name, value in self.source_hashes:
            if not isinstance(name, str) or not name:
                raise ValueError('Invalid source name')
            sha(value)
        if not self.body_masses_kg:
            raise ValueError('Missing body masses')
        for name, mass in self.body_masses_kg:
            finite(name, mass, positive=True)
        if not self.checks or len(dict(self.checks)) != len(self.checks):
            raise ValueError('Missing or duplicate applicability checks')
        if any(not isinstance(k, str) or type(v) is not bool for k, v in self.checks):
            raise ValueError('Invalid applicability evidence')
        if dict(self.checks).get('direct_stateless_unit_motor') and dict(self.checks).get('force_clamps'):
            expected_braking = max(0.0, -max(self.control_range[0], self.scalar_force_range_n[0]))
            if self.braking_force_n != expected_braking:
                raise ValueError('Braking authority contradicts the validated direct motor ranges')
        if not self.assumptions or any(not isinstance(v, str) or not v for v in self.assumptions):
            raise ValueError('Missing assumptions')
        if not self.force_probe_evidence:
            raise ValueError('Missing compiled force probe evidence')
        for row in self.force_probe_evidence:
            if len(row) != len(PROBE_COLUMNS):
                raise ValueError('Invalid force probe schema')
            for name, v in zip(PROBE_COLUMNS, row):
                finite(name, v)
        values = {'mass_kg': self.generalized_inertia_kg, 'force_n': self.braking_force_n,
                  'velocity_mps': self.initial_velocity_mps, 'clearance_m': self.initial_clearance_m}
        if len({u[0] for u in self.uncertainties}) != len(self.uncertainties):
            raise ValueError('Duplicate uncertainty')
        for key, low, high in self.uncertainties:
            finite('uncertainty', low); finite('uncertainty', high)
            if key not in values or not low <= values[key] <= high or key == 'mass_kg' and low <= 0 or key == 'force_n' and low < 0:
                raise ValueError('Invalid uncertainty interval')
        if self.provenance_kind not in ('compiled_project', 'analytical_fixture') or self.schema_version != 1:
            raise ValueError('Unsupported contract provenance/schema')

    def to_dict(self):
        return json.loads(canonical(asdict(self)))

    @classmethod
    def from_dict(cls, values):
        return cls(**values)

    @property
    def identity(self):
        return digest(self.to_dict())

