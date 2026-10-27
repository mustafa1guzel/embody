"""Explicit family routing, never user-supplied modules or executable hooks."""
from core.simulation import ROOT


def get_family(name='rail', *, root=ROOT, evaluation=False):
    if name == 'rail': return None  # Preserve the existing implementation exactly.
    if name == 'arm':
        from core.robots.arm import ArmFamily
        return ArmFamily(root=root,evaluation=evaluation)
    raise ValueError('Unknown robot family; choose rail or arm')
