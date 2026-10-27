"""Bounds for pre-contact, bounded-force, semi-implicit one-axis motion only."""
import math
from fractions import Fraction
from .contracts import finite

EQUATIONS = {
    'continuous': 'a=F/m; D_cont=v^2/(2*a); D_required=v*tau+D_cont+d_safe',
    'discrete': 'v[i]>=v-i*a*h; x[k]-x[0]>=h*(k*v-a*h*k*(k+1)/2)',
    'necessary': 'n_req=max(0,ceil((v-v_tol)/(a*h))-1); L=h*sum(v-i*a*h,i=1..n_req)',
    'constructive': 'n=max(0,ceil(v/(a*h))-1); D0=h*sum(v-i*a*h,i=1..n); fractional last brake reaches zero',
    'delay': 'r=ceil(tau/h); delay_distance=v*r*h; no second implicit reaction interval',
}


def stopping_bounds(mass_kg, force_n, velocity_mps, timestep_s, final_speed_tolerance_mps,
                    *, reaction_delay_s=0.0):
    for name, value in [('mass', mass_kg), ('force', force_n), ('timestep', timestep_s),
                        ('final tolerance', final_speed_tolerance_mps)]:
        finite(name, value, positive=True)
    finite('velocity', velocity_mps, nonnegative=True)
    finite('reaction delay', reaction_delay_s, nonnegative=True)
    # Exact rational arithmetic on represented SI inputs avoids cancellation and
    # integer-step rounding errors. Directed float bounds are used by the guard.
    m, f, v, h, tol, tau = map(Fraction, (mass_kg, force_n, velocity_mps, timestep_s,
                                         final_speed_tolerance_mps, reaction_delay_s))
    a = f/m
    ah = a*h
    try:
        representable = all(math.isfinite(float(x)) and float(x) > 0 for x in (a, ah))
    except OverflowError:
        representable = False
    if not representable:
        raise ValueError('Unrepresentable dynamics')
    # Deliberately bounded arithmetic domain; never allocate one entry per step.
    ratios = (v/ah, tau/h)
    if any(x > 1e9 for x in ratios):
        raise ValueError('Analytical numerical envelope exceeded')
    steps = math.ceil(v/ah)
    n = max(0, steps-1)
    nr = max(0, math.ceil((v-tol)/ah)-1)
    delay_steps = math.ceil(tau/h)
    def travel(k):
        return max(Fraction(0), h*(k*v-ah*k*(k+1)/2))
    continuous = v*v/(2*a)
    result = {'deceleration_mps2': a, 'continuous_zero_stop_m': continuous,
              'necessary_travel_m': travel(nr), 'discrete_zero_stop_m': travel(n),
              'zero_stop_time_s': steps*h, 'delay_steps': delay_steps,
              'quantized_delay_s': delay_steps*h, 'delay_distance_m': v*delay_steps*h,
              'continuous_required_motion_m': v*tau+continuous,
              'conservative_discrete_motion_m': v*delay_steps*h+continuous,
              'constructive_required_motion_m': v*delay_steps*h+travel(n),
              'necessary_required_motion_m': v*delay_steps*h+travel(nr)}
    try:
        result = {k: (int(value) if k == 'delay_steps' else float(value)) for k, value in result.items()}
    except OverflowError as exc:
        raise ValueError('Unrepresentable analytical result') from exc
    result['necessary_motion_lower_bound_m'] = max(0.0, math.nextafter(result['necessary_required_motion_m'], -math.inf))
    result['constructive_motion_upper_bound_m'] = math.nextafter(result['constructive_required_motion_m'], math.inf)
    result['constructive_time_upper_bound_s'] = math.nextafter(float((steps+delay_steps)*h), math.inf)
    if any(not math.isfinite(x) for x in result.values()):
        raise ValueError('Unrepresentable analytical result')
    return result
