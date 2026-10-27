"""Bounded, review-only repair search for EMBODY Phase 17 barrier failures.

This file is not a replacement for EMBODY's authoritative project, its
MuJoCo-based controller, or its engineering acceptance verifier.

The caller MUST provide the project's trusted native preview function.
A proposed repair is accepted only after that function reports every frozen
requirement as satisfied and independent native verification completed.

No API requests, file modifications or untrusted code execution occur here.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from itertools import product
import json
import math
from typing import Any, Callable, Mapping, Sequence

GRAVITY = 9.81


@dataclass(frozen=True, slots=True)
class BarrierParameters:
    span_m: float
    mass_kg: float
    torque_nm: float
    pivot_height_m: float
    beam_thickness_m: float = 0.016
    support_top_m: float = 0.16
    initial_angle_rad: float = 0.0
    gravity_m_s2: float = GRAVITY

    def validate(self) -> None:
        numbers = asdict(self)
        for name, value in numbers.items():
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError(f"{name} must be a finite number")
        for name in ("span_m", "mass_kg", "torque_nm", "beam_thickness_m", "gravity_m_s2"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        if not 0 < self.span_m <= 5 or not .001 <= self.mass_kg <= 100:
            raise ValueError("Dimensions/mass outside bounded global envelope")
        if not .001 <= self.torque_nm <= 100 or not -10 <= self.pivot_height_m <= 10:
            raise ValueError("Torque/pivot outside bounded global envelope")
        if not 0 < self.beam_thickness_m <= 5:
            raise ValueError("Beam thickness outside bounded global envelope")


@dataclass(frozen=True, slots=True)
class ContactWitness:
    geom_a: str
    geom_b: str
    penetration_m: float

    def __post_init__(self) -> None:
        if self.penetration_m < 0 or not math.isfinite(self.penetration_m):
            raise ValueError("Penetration must be finite and nonnegative")


@dataclass(frozen=True, slots=True)
class PreflightFinding:
    code: str
    status: str   # ERROR, WARNING, UNKNOWN, PASS
    detail: str
    metrics: Mapping[str, float] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PreflightResult:
    design: BarrierParameters
    findings: tuple[PreflightFinding, ...]

    @property
    def has_error(self) -> bool:
        return any(f.status == "ERROR" for f in self.findings)

    @property
    def has_unknown(self) -> bool:
        return any(f.status == "UNKNOWN" for f in self.findings)


# Returns actual forbidden contact witnesses from the trusted native model.
# Return None when no authoritative collision check has been performed.
ContactProbe = Callable[[BarrierParameters], Sequence[ContactWitness] | None]


def static_gravity_torque(design: BarrierParameters) -> float:
    """Uniform horizontal hinged beam approximation, not a dynamics proof.

    The reported Phase 17 reference uses a uniform beam and a horizontal
    initial pose. An alternative COM/inertia model requires a different guard.
    """
    design.validate()
    return (design.mass_kg * design.gravity_m_s2 * design.span_m / 2
            * abs(math.cos(design.initial_angle_rad)))


def preflight(
    design: BarrierParameters,
    *,
    contact_probe: ContactProbe | None = None,
    static_torque_safety_factor: float = 1.20,
    visual_support_clearance_m: float = 0.004,
) -> PreflightResult:
    """Detect unsupported load and contact failures BEFORE a simulation preview.

    The support envelope condition is ONLY a warning. Actual contact decisions
    require the trusted native static-contact probe, because the envelope
    check doesn't include the support's horizontal dimensions or pivots.
    """
    design.validate()
    if not 1.0 <= static_torque_safety_factor <= 3.0:
        raise ValueError("Invalid torque safety factor")
    if not 0 <= visual_support_clearance_m <= 0.05:
        raise ValueError("Invalid clearance")

    findings: list[PreflightFinding] = []
    grav = static_gravity_torque(design)
    target = grav * static_torque_safety_factor
    ratio = grav / design.torque_nm
    metrics = {"static_gravity_nm": grav, "available_nm": design.torque_nm,
               "gravity_over_authority": ratio, "target_with_margin_nm": target}
    if design.torque_nm < target:
        findings.append(PreflightFinding(
            "INSUFFICIENT_STATIC_TORQUE", "ERROR",
            f"Gravity bias ~{grav:.6f} N.m, authority {design.torque_nm:.6f} N.m; "
            f"require >= {target:.6f} N.m with stated margin.", metrics))
    else:
        findings.append(PreflightFinding(
            "STATIC_TORQUE_SCREEN", "PASS",
            "Static gravity bound passed; transient acceleration, contact and "
            "closed-loop completion still require native verification.", metrics))

    underside = design.pivot_height_m - design.beam_thickness_m / 2
    envelope_clearance = underside - design.support_top_m
    if envelope_clearance < visual_support_clearance_m:
        findings.append(PreflightFinding(
            "SUPPORT_ENVELOPE_PROXIMITY", "WARNING",
            "Beam underside is close to/below the support top; this is a "
            "conservative envelope alert, NOT a measured collision.",
            {"vertical_envelope_gap_m": envelope_clearance,
             "desired_visual_gap_m": visual_support_clearance_m}))

    if contact_probe is None:
        findings.append(PreflightFinding(
            "NATIVE_INITIAL_CONTACTS", "UNKNOWN",
            "Native MuJoCo collision check not supplied."))
    else:
        contacts = contact_probe(design)
        if contacts is None:
            findings.append(PreflightFinding(
                "NATIVE_INITIAL_CONTACTS", "UNKNOWN",
                "Native MuJoCo collision check did not return evidence."))
        elif contacts:
            for c in contacts:
                findings.append(PreflightFinding(
                    "FORBIDDEN_CONTACT", "ERROR",
                    f"{c.geom_a} / {c.geom_b}: {c.penetration_m:.6f} m penetration.",
                    {"penetration_m": c.penetration_m}))
        else:
            findings.append(PreflightFinding(
                "NATIVE_INITIAL_CONTACTS", "PASS",
                "No forbidden initial contacts found in the checked native model."))
    return PreflightResult(design=design, findings=tuple(findings))


@dataclass(frozen=True, slots=True)
class NativeOutcome:
    """Must be populated from EMBODY's actual trusted MuJoCo verifier."""
    checks: Mapping[str, bool]
    independent_native_verification: bool
    engine: str = "mujoco"
    evidence_path: str = ""
    measured: Mapping[str, float] = field(default_factory=dict)


# The trusted host callback MUST construct/compile and simulate the candidate
# through existing Day 16 engine, without applying it to the live project.
NativePreview = Callable[[BarrierParameters], NativeOutcome]


@dataclass(frozen=True, slots=True)
class RepairAttempt:
    design: BarrierParameters
    preflight: PreflightResult
    native_outcome: NativeOutcome | None
    accepted: bool
    reason: str


@dataclass(frozen=True, slots=True)
class RepairSearchResult:
    original: BarrierParameters
    attempts: tuple[RepairAttempt, ...]
    accepted_candidate: BarrierParameters | None
    native_previews: int
    state: str


def candidate_designs(original: BarrierParameters, *, max_candidates: int = 100) -> tuple[BarrierParameters, ...]:
    """Bounded prioritized search, not a global optimum or universal repair.

    First two candidates explicitly target BOTH measured Phase 17 defects.
    Beam mass 0.035 and pivot 0.18 are *hypotheses* until MuJoCo passes.
    The actual DeviceSpec may reject these; native integration must respect it.
    """
    original.validate()
    if type(max_candidates) is not int or not 1 <= max_candidates <= 100:
        raise ValueError("max_candidates must be an integer 1..100")
    prioritized = [
        (.035, .12, .18),
        (.035, original.torque_nm, .18),
        (.035, .25, .18),
        (.045, .25, .19),
        (.06, .35, .19),
        (.035, .35, .20),
    ]
    masses = (.025, .035, .045, .06, .08, .10, original.mass_kg)
    torques = (original.torque_nm, .12, .20, .25, .35, .50)
    pivots = (.175, .18, .19, .20, .22, original.pivot_height_m)
    combos = prioritized + list(product(masses, torques, pivots))
    seen = set()
    result: list[BarrierParameters] = []
    for mass, torque, pivot in combos:
        candidate = replace(original, mass_kg=mass, torque_nm=torque,
                            pivot_height_m=pivot)
        key = (round(mass, 8), round(torque, 8), round(pivot, 8))
        if key in seen or candidate == original:
            continue
        seen.add(key)
        try:
            candidate.validate()
        except ValueError:
            continue
        result.append(candidate)
        if len(result) >= max_candidates:
            break
    return tuple(result)


def find_verified_repair(
    original: BarrierParameters,
    *,
    trusted_native_preview: NativePreview,
    frozen_check_names: Sequence[str],
    contact_probe: ContactProbe | None = None,
    max_native_previews: int = 8,
    max_candidates: int = 100,
    candidate_validator: Callable[[BarrierParameters], None] | None = None,
) -> RepairSearchResult:
    """Review-only, bounded search. Never alters project or approves changes.

    The caller must supply all existing frozen acceptance checks. A result counts
    as accepted only if *every* expected check exists and is true AND native
    independent verification was performed. Absent contact_probe is allowed
    because the native preview itself must include the no-contact criterion.
    """
    if type(max_native_previews) is not int or not 0 <= max_native_previews <= 20:
        raise ValueError("max_native_previews must be 0..20")
    expected = tuple(frozen_check_names)
    if not expected or len(set(expected)) != len(expected):
        raise ValueError("Provide distinct frozen acceptance check names")
    if not any("contact" in check.lower() for check in expected):
        raise ValueError("Frozen checks must include the original contact requirement")
    attempts: list[RepairAttempt] = []
    native_runs = 0
    for cand in candidate_designs(original, max_candidates=max_candidates):
        if max_native_previews == 0:
            break
        try:
            if candidate_validator is not None:
                candidate_validator(cand)
        except ValueError as exc:
            pf = PreflightResult(cand, (PreflightFinding("PROJECT_ENVELOPE", "ERROR", str(exc)),))
            attempts.append(RepairAttempt(cand, pf, None, False, "PROJECT_VALIDATION_ERROR"))
            continue
        pf = preflight(cand, contact_probe=contact_probe)
        if pf.has_error:
            attempts.append(RepairAttempt(cand, pf, None, False, "PREFLIGHT_ERROR"))
            continue
        if native_runs >= max_native_previews:
            break
        native_runs += 1
        try:
            outcome = trusted_native_preview(cand)
            missing = set(expected) - set(outcome.checks)
            extra = set(outcome.checks) - set(expected)
            ok = (not missing and not extra
                  and all(outcome.checks[name] is True for name in expected)
                  and outcome.independent_native_verification is True
                  and outcome.engine == "mujoco"
                  and bool(outcome.evidence_path))
            reason = "NATIVE_ALL_FROZEN_CHECKS_PASS" if ok else (
                "INCOMPLETE_OR_FAILED_NATIVE_VERIFICATION")
            attempts.append(RepairAttempt(cand, pf, outcome, ok, reason))
            if ok:
                return RepairSearchResult(original, tuple(attempts), cand,
                                          native_runs, "VERIFIED_PROPOSAL_NOT_APPLIED")
        except Exception as exc:
            # Fail closed and preserve error evidence; no silent candidate success.
            attempts.append(RepairAttempt(
                cand, pf, None, False, f"TRUSTED_PREVIEW_ERROR:{type(exc).__name__}:{exc}"))
    state = "NOT_RUN" if max_native_previews == 0 else "NO_VERIFIED_FIX_WITHIN_BUDGET"
    return RepairSearchResult(original, tuple(attempts), None, native_runs, state)


def report_to_json(result: RepairSearchResult) -> str:
    """Build a serializable review artifact, not an approval or an application."""
    return json.dumps(asdict(result), indent=2, sort_keys=True, allow_nan=False)


PHASE17_REPORTED_DESIGN = BarrierParameters(
    span_m=.28, mass_kg=.18, torque_nm=.11,
    pivot_height_m=.16, beam_thickness_m=.016, support_top_m=.16,
)

if __name__ == "__main__":
    # Read-only analytical illustration only. Never call a fabricated simulator.
    case = PHASE17_REPORTED_DESIGN
    original = preflight(case)
    first = candidate_designs(case)[0]
    candidate = preflight(first)
    print(json.dumps({
        "source": "Phase 17 report; no native simulation run in this script",
        "original": {"parameters": asdict(case),
                     "findings": [asdict(x) for x in original.findings]},
        "first_hypothesis": {"parameters": asdict(first),
                             "findings": [asdict(x) for x in candidate.findings]},
        "warning": "This is an unverified candidate. Pass it through the REAL Day16 MuJoCo verifier before acceptance or application."
    }, indent=2))
