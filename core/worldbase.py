"""Validated environment, initial conditions and explicit safety acceptance criteria."""
from __future__ import annotations
from dataclasses import asdict, dataclass
import math
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET
from core.context_validation import CONFIG_DIR, finite_number, frozen_context, identifier, json_values, read_json, vector, xml_numbers


@dataclass(frozen=True)
class WorldBase:
    scenario: str
    wall_reference: str
    wall_position_x_m: float
    wall_half_size_m: tuple[float, float, float]
    wall_center_yz_m: tuple[float, float]
    initial_position_x_m: float
    initial_velocity_ms: float
    minimum_clearance_m: float
    simulation_timestep_s: float
    simulation_duration_s: float
    max_final_speed_ms: float
    completion_deadline_s: float
    gravity_ms2: tuple[float, float, float]

    def __post_init__(self):
        identifier('scenario', self.scenario)
        if self.wall_reference != 'center':
            raise ValueError('wall_position_x_m refers to the wall center')
        for name in ('wall_position_x_m', 'initial_position_x_m', 'initial_velocity_ms'):
            finite_number(name, getattr(self, name))
        for name in ('minimum_clearance_m', 'simulation_duration_s'):
            finite_number(name, getattr(self, name), nonnegative=True)
        for name in ('simulation_timestep_s', 'max_final_speed_ms', 'completion_deadline_s'):
            finite_number(name, getattr(self, name), positive=True)
        for name, length, positive in (('wall_half_size_m', 3, True), ('wall_center_yz_m', 2, False), ('gravity_ms2', 3, False)):
            object.__setattr__(self, name, vector(name, getattr(self, name), length, positive=positive))
        if self.gravity_ms2[:2] != (0, 0) or self.gravity_ms2[2] > 0:
            raise ValueError('This frictionless horizontal experiment requires vertical, nonpositive gravity')
        ratio = self.simulation_duration_s / self.simulation_timestep_s
        if not math.isfinite(ratio) or not math.isclose(ratio, round(ratio), rel_tol=0, abs_tol=1e-8):
            raise ValueError('Simulation duration must be an integer multiple of the timestep')

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> WorldBase:
        try:
            return cls(**values)
        except TypeError as exc:
            raise ValueError(f'Invalid WORLDBASE schema: {exc}') from exc

    @classmethod
    def from_json(cls, path: str | Path = CONFIG_DIR / 'worldbase.json') -> WorldBase:
        return cls.from_dict(read_json(path))

    def to_dict(self):
        return json_values(asdict(self))

    @property
    def context(self):
        return frozen_context({**self.to_dict(), 'units': {'length': 'm', 'velocity': 'm/s', 'time': 's', 'gravity': 'm/s²'},
                               'safety_criteria': {'zero_wall_contact_events': True,
                                                   'minimum_clearance_m': self.minimum_clearance_m,
                                                   'final_speed_strictly_below_ms': self.max_final_speed_ms,
                                                   'completion_deadline_s': self.completion_deadline_s}})

    def apply_to_xml(self, root: ET.Element):
        obstacle = root.find(".//body[@name='obstacle']")
        obstacle.set('pos', xml_numbers([self.wall_position_x_m, *self.wall_center_yz_m]))
        obstacle.find("geom[@name='wall']").set('size', xml_numbers(self.wall_half_size_m))
        option = root.find('option')
        option.set('timestep', format(self.simulation_timestep_s, '.17g'))
        option.set('gravity', xml_numbers(self.gravity_ms2))
