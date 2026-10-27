"""Explicitly scoped analytical claims, separate from measured acceptance."""
import math
from fractions import Fraction
from .analytical import EQUATIONS, stopping_bounds
from .contracts import UNITS, finite
from .extraction import CHECK_NAMES

STATUSES = ('PROVEN_VIOLATION', 'PROVEN_INFEASIBLE', 'CONDITIONALLY_FEASIBLE', 'UNKNOWN')


def assess_task(contract, *, velocity_mps=None, clearance_m=None, remaining_time_s=None,
                reaction_delay_s=0.0, contact_present=False):
    c = contract
    v = c.initial_velocity_mps if velocity_mps is None else velocity_mps
    gap = c.initial_clearance_m if clearance_m is None else clearance_m
    horizon = min(c.duration_s, c.deadline_s) if remaining_time_s is None else remaining_time_s
    result = {'status': 'UNKNOWN', 'claim_scope': 'task existence in the supported discrete analytical model; not controller safety',
              'contract_sha256': c.identity, 'model_sha256': c.model_sha256, 'controller_sha256': c.controller_sha256,
              'equations': EQUATIONS, 'units': UNITS, 'assumptions': list(c.assumptions),
              'inputs': {'mass_kg': c.generalized_inertia_kg, 'braking_force_n': c.braking_force_n,
                         'velocity_mps': v, 'clearance_m': gap, 'remaining_time_s': horizon,
                         'reaction_delay_s': reaction_delay_s, 'timestep_s': c.timestep_s,
                         'minimum_clearance_m': c.minimum_clearance_m,
                         'final_speed_tolerance_mps': c.final_speed_tolerance_mps},
              'bounds': {}, 'unsupported': [], 'explanation': '',
              'limitations': ['No arbitrary-program proof.', 'No statement outside the extracted envelope.',
                              'No execution, verification approval or installation authorization.']}
    try:
        finite('velocity', v); finite('clearance', gap); finite('horizon', horizon, nonnegative=True)
        finite('delay', reaction_delay_s, nonnegative=True)
        if type(contact_present) is not bool:
            raise ValueError('Contact state must be explicit boolean')
    except ValueError as exc:
        result['unsupported'] = [str(exc)]; result['explanation'] = 'Invalid analysis input.'
        # Invalid inputs must still be safely serializable.
        result['inputs'] = None
        return result
    checks = dict(c.checks)
    unsupported = [name for name in CHECK_NAMES if checks.get(name) is not True]
    if c.joint_type != 'prismatic' or c.axis_world != (1, 0, 0) or c.integrator != 'Euler':
        unsupported.append('unsupported joint, movement axis or integrator semantics')
    if v < 0:
        unsupported.append('reverse motion / recovery')
    if abs(v) > c.maximum_speed_mps+c.numeric_tolerance:
        unsupported.append('speed outside BODYBASE envelope')
    if c.uncertainties:
        unsupported.append('uncertainty intervals are recorded but not certified by this model')
    if contact_present:
        unsupported.append('contact dynamics')
    if unsupported:
        result.update(unsupported=unsupported, explanation='Predictive theorem does not apply to this state/model.')
        return result
    if gap < c.minimum_clearance_m-c.distance_tolerance_m:
        result.update(status='PROVEN_VIOLATION', explanation='Surface clearance already violates the requirement.')
        return result
    if remaining_time_s is None and c.duration_s > c.deadline_s+c.numeric_tolerance:
        result.update(status='PROVEN_INFEASIBLE', explanation='The fixed required simulation horizon exceeds its acceptance deadline, independent of controller behavior.')
        return result
    if c.braking_force_n == 0:
        if v >= c.final_speed_tolerance_mps:
            result.update(status='PROVEN_INFEASIBLE', explanation='No braking authority; terminal speed cannot be reached.')
        elif gap-v*horizon >= c.minimum_clearance_m+c.distance_tolerance_m:
            result.update(status='CONDITIONALLY_FEASIBLE', explanation='Zero-force coasting satisfies this finite-horizon task.')
        else:
            result['explanation'] = 'Zero authority and insufficient established coasting margin.'
        return result
    try:
        bounds = stopping_bounds(c.generalized_inertia_kg, c.braking_force_n, v, c.timestep_s,
                                 c.final_speed_tolerance_mps, reaction_delay_s=reaction_delay_s)
    except ValueError as exc:
        result.update(unsupported=[str(exc)], explanation='Numerical envelope exceeded.')
        return result
    bounds['necessary_clearance_m'] = math.nextafter(c.minimum_clearance_m+bounds['necessary_motion_lower_bound_m'], -math.inf)
    bounds['constructive_clearance_m'] = math.nextafter(c.minimum_clearance_m+bounds['constructive_motion_upper_bound_m'], math.inf)
    bounds['necessary_margin_m'] = gap-bounds['necessary_clearance_m']
    bounds['constructive_margin_m'] = gap-bounds['constructive_clearance_m']
    intervals = max(0, math.floor(Fraction(horizon+c.numeric_tolerance)/Fraction(c.timestep_s))-bounds['delay_steps'])
    best_speed = max(Fraction(0), Fraction(v)-Fraction(c.braking_force_n)/Fraction(c.generalized_inertia_kg)*intervals*Fraction(c.timestep_s))
    bounds['best_terminal_speed_lower_bound_mps'] = max(0.0, math.nextafter(float(best_speed), -math.inf))
    result['bounds'] = bounds
    if (bounds['necessary_margin_m'] < -c.distance_tolerance_m
            or bounds['best_terminal_speed_lower_bound_mps'] > c.final_speed_tolerance_mps+c.numeric_tolerance):
        result.update(status='PROVEN_INFEASIBLE', explanation='Even maximally admissible braking violates a necessary distance or deadline bound.')
    elif (bounds['constructive_margin_m'] > c.distance_tolerance_m
          and bounds['constructive_time_upper_bound_s'] <= horizon-c.numeric_tolerance):
        result.update(status='CONDITIONALLY_FEASIBLE', explanation='A bounded non-reversing discrete stop exists; this is not a certificate for the controller source.')
    else:
        result['explanation'] = 'Necessary and constructive bounds do not decide this boundary case.'
    return result


def assess_program_source(source, contract):
    """Never parse/import/evaluate the supplied source; a hash is identity, not proof."""
    return {'status': 'UNKNOWN', 'contract_sha256': contract.identity,
            'explanation': 'Arbitrary Python behavior is outside this analytical model. Explicitly approved qualified VM verification is required.'}
