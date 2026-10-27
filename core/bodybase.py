"""Validated robot embodiment, applied before MuJoCo compiles the model."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
import math
import xml.etree.ElementTree as ET
from core.context_validation import CONFIG_DIR, finite_number, frozen_context, identifier, json_values, read_json, vector, xml_numbers


@dataclass(frozen=True)
class CarriageGeometry:
    carriage_half_size_m: tuple[float, float, float]
    bumper_half_size_m: tuple[float, float, float]
    bumper_center_x_m: float

    def __post_init__(self):
        for name in ('carriage_half_size_m', 'bumper_half_size_m'):
            object.__setattr__(self, name, vector(name, getattr(self, name), 3, positive=True))
        finite_number('bumper_center_x_m', self.bumper_center_x_m, positive=True)
        if self.bumper_center_x_m + self.bumper_half_size_m[0] <= self.carriage_half_size_m[0]:
            raise ValueError('The bumper front must extend beyond the chassis front')
        if self.bumper_center_x_m - self.bumper_half_size_m[0] > self.carriage_half_size_m[0] + 1e-12:
            raise ValueError('The bumper must meet or overlap the chassis')


@dataclass(frozen=True)
class BodyBase:
    robot_id: str
    mass_kg: float
    max_force_n: float
    max_velocity_ms: float
    joint_type: str
    axis: str
    collision_geometry: CarriageGeometry

    def __post_init__(self):
        identifier('robot_id', self.robot_id)
        for name in ('mass_kg', 'max_force_n', 'max_velocity_ms'):
            finite_number(name, getattr(self, name), positive=True)
        if not math.isfinite(self.max_force_n / self.mass_kg) or self.max_force_n / self.mass_kg <= 0:
            raise ValueError('The configured force/mass ratio must be finite and positive')
        if self.joint_type != 'prismatic' or self.axis != 'x':
            raise ValueError('This foundation supports one x-axis prismatic joint')
        if not isinstance(self.collision_geometry, CarriageGeometry):
            raise ValueError('collision_geometry must be validated CarriageGeometry')

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> BodyBase:
        values = dict(values)
        try:
            values['collision_geometry'] = CarriageGeometry(**values['collision_geometry'])
            return cls(**values)
        except (KeyError, TypeError) as exc:
            raise ValueError(f'Invalid BODYBASE schema: {exc}') from exc

    @classmethod
    def from_json(cls, path: str | Path = CONFIG_DIR / 'bodybase.json') -> BodyBase:
        return cls.from_dict(read_json(path))

    def to_dict(self):
        return json_values(asdict(self))

    @property
    def context(self):
        return frozen_context({**self.to_dict(), 'units': {'mass': 'kg', 'force': 'N', 'velocity': 'm/s', 'length': 'm'},
                               'max_deceleration_ms2': self.max_deceleration_ms2})

    @property
    def max_deceleration_ms2(self):
        return self.max_force_n / self.mass_kg

    def stopping_distance_m(self, velocity_ms):
        finite_number('velocity_ms', velocity_ms)
        return velocity_ms**2 / (2 * self.max_deceleration_ms2)

    def apply_to_xml(self, root: ET.Element):
        body = root.find(".//body[@name='carriage']")
        inertial = body.find('inertial')
        # Uniform mass scaling retains the template assembly's inertia/mass ratios.
        ratio = self.mass_kg / float(inertial.get('mass'))
        inertial.set('mass', format(self.mass_kg, '.17g'))
        inertial.set('diaginertia', xml_numbers([float(x) * ratio for x in inertial.get('diaginertia').split()]))
        body.find("geom[@name='carriage_box']").set('size', xml_numbers(self.collision_geometry.carriage_half_size_m))
        bumper = body.find("geom[@name='front_bumper']")
        bumper.set('size', xml_numbers(self.collision_geometry.bumper_half_size_m))
        bumper.set('pos', xml_numbers([self.collision_geometry.bumper_center_x_m, 0, 0]))
        motor = root.find("./actuator/motor[@name='x_motor']")
        if float(motor.get('gear')) != 1:
            raise ValueError('BODYBASE expects the established direct motor with gear=1')
        for attr in ('ctrlrange', 'forcerange'):
            motor.set(attr, xml_numbers([-self.max_force_n, self.max_force_n]))
