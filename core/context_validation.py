"""Small SI validation and immutable context helpers; no runtime dependency."""
from __future__ import annotations
import json
import math
from pathlib import Path
from types import MappingProxyType
from typing import Any
from collections.abc import Mapping

CONFIG_DIR = Path(__file__).resolve().parents[1] / 'configs'


def finite_number(name: str, value: Any, *, positive=False, nonnegative=False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'{name} must be a finite SI number, not a string or boolean')
    if (positive and value <= 0) or (nonnegative and value < 0):
        raise ValueError(f'{name} must be {"positive" if positive else "nonnegative"}')
    return float(value)


def vector(name, value, length, *, positive=False) -> tuple[float, ...]:
    if not isinstance(value, (tuple, list)) or len(value) != length:
        raise ValueError(f'{name} must contain exactly {length} SI numbers')
    return tuple(finite_number(name, x, positive=positive) for x in value)


def identifier(name, value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{name} must be a nonempty string')


def read_json(path: str | Path) -> dict[str, Any]:
    result = json.loads(Path(path).read_text())
    if not isinstance(result, dict):
        raise ValueError('Configuration must be a JSON object')
    return result


def frozen_context(value):
    if isinstance(value, dict):
        return MappingProxyType({k: frozen_context(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(frozen_context(v) for v in value)
    return value


def json_values(value):
    if isinstance(value, Mapping):
        return {k: json_values(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_values(v) for v in value]
    return value


def xml_numbers(values) -> str:
    return ' '.join(format(x, '.17g') for x in values)
