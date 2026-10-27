"""Optional trusted-native contact witness adapter for EMBODY.

Requires MuJoCo in the target project's Python environment. This script does
NOT mutate the authoritative project. Create an isolated MjData with the
candidate's correct INITIAL poses/parameters before calling initial_contacts.

The exact geom names must come from EMBODY's compiled device model. Do not
infer forbidden-contact pairs from visual proximity or substring matching.
"""
from __future__ import annotations
from collections.abc import Iterable

from .phase17_repair import ContactWitness


def all_initial_contacts(model, data) -> list[tuple[str, str, float]]:
    import mujoco
    mujoco.mj_forward(model, data)
    found = []
    for i in range(int(data.ncon)):
        c = data.contact[i]
        n1 = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, int(c.geom1))
        n2 = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, int(c.geom2))
        found.append((n1 or f"geom#{c.geom1}", n2 or f"geom#{c.geom2}", float(c.dist)))
    return found


def forbidden_initial_contacts(model, data, forbidden_pairs: Iterable[tuple[str, str]], *, include_margin_contacts=False) -> list[ContactWitness]:
    import mujoco
    forbidden = {frozenset(pair) for pair in forbidden_pairs}
    if not forbidden or any(len(pair) != 2 for pair in forbidden):
        raise ValueError("Use exact, distinct pairs of geom names from the compiled model")
    for pair in forbidden:
        if any(mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, name) < 0 for name in pair):
            raise ValueError("Forbidden pair names must exist in the compiled model")
    witnesses: list[ContactWitness] = []
    for a, b, dist in all_initial_contacts(model, data):
        if frozenset((a, b)) in forbidden and (include_margin_contacts or dist <= 0):
            witnesses.append(ContactWitness(a, b, max(0.0, -dist)))
    return witnesses
