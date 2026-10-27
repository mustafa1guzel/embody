"""Numerical metrics of supplied measured samples; no rollout or fabricated signal."""
from .contracts import finite


def profile(samples, contract):
    c = contract
    def metric(value, unit, method, reason=None):
        return {'status': 'NOT_AVAILABLE' if value is None else 'AVAILABLE', 'value': value,
                'unit': unit, 'method': method, **({'reason': reason} if reason else {})}
    def signal(name):
        if not samples or any(name not in row for row in samples):
            return None
        values = [row[name] for row in samples]
        for v in values:
            finite(name, v)
        return values
    time = signal('time')
    position, velocity, command = signal('position'), signal('velocity'), signal('control')
    force, scalar, gap = signal('generalized_actuator_force'), signal('scalar_actuator_force'), signal('wall_clearance')
    if time is not None and any(abs(b-a-c.timestep_s) > c.numeric_tolerance for a, b in zip(time, time[1:])):
        raise ValueError('Profiler requires uniform increasing contract timestep')
    dt = [b-a for a, b in zip(time, time[1:])] if time else []
    interval_times = [(a+b)/2 for a, b in zip(time, time[1:])] if time else []
    acceleration = [(b-a)/h for a, b, h in zip(velocity, velocity[1:], dt)] if velocity is not None and dt else None
    jerk = [(b-a)/(tb-ta) for a, b, ta, tb in zip(acceleration, acceleration[1:], interval_times, interval_times[1:])] if acceleration and len(acceleration) > 1 else None
    works = [f*(b-a) for f, a, b in zip(force, position, position[1:])] if force is not None and position is not None and dt else None
    last_braking = (max((i for i, f in enumerate(force[:-1]) if f < -c.numeric_tolerance), default=None)
                    if force is not None else None)
    tail_start = last_braking+1 if last_braking is not None else None
    tail_travel = (position[-1]-position[tail_start] if position is not None and tail_start is not None else None)
    def saturation(values, low, high):
        if values is None or not dt or low == high:
            return None
        return sum(h for value, h in zip(values, dt) if value <= low+c.numeric_tolerance or value >= high-c.numeric_tolerance)
    lower = max(c.control_range[0], c.scalar_force_range_n[0])
    upper = min(c.control_range[1], c.scalar_force_range_n[1])
    force_duration = saturation(force, lower, upper) if all(v for _, v in c.checks) else None
    command_duration = saturation(command, *c.control_range)
    duration = sum(dt)
    contacts = None
    if samples and all(type(s.get('wall_collision')) is bool for s in samples):
        contacts = [{'sample_index': i, 'time_s': s.get('time')} for i, s in enumerate(samples)
                    if s['wall_collision'] and (i == 0 or not samples[i-1]['wall_collision'])]
    interval_method = 'Forward velocity difference on [t[k],t[k+1]], placed at interval midpoint; no endpoint padding.'
    work_method = 'Sum generalized_force[k]*(position[k+1]-position[k]); left-held force, final unadvanced command excluded.'
    minimum = min(gap) if gap is not None else None
    metrics = {
        'minimum_clearance': metric(minimum, 'm', 'Minimum sampled geometric surface gap.'),
        'clearance_safety_margin': metric(minimum-c.minimum_clearance_m if minimum is not None else None, 'm', 'Minimum sampled gap minus required gap.'),
        'final_velocity': metric(velocity[-1] if velocity is not None else None, 'm/s', 'Last measured signed velocity.'),
        'peak_deceleration': metric(max([0]+[-a for a in acceleration]) if acceleration is not None else None, 'm/s^2', 'Maximum negative longitudinal forward-difference acceleration; may include contact forces.'),
        'peak_absolute_jerk': metric(max(map(abs, jerk)) if jerk is not None else None, 'm/s^3', 'Difference of adjacent interval accelerations over midpoint separation; no endpoint padding, no damage inference.'),
        'force_saturation_duration': metric(force_duration, 's', 'Time at effective generalized-force clamps in supported direct motor; excludes final sample.'),
        'force_saturation_fraction': metric(force_duration/duration if force_duration is not None and duration else None, '1', 'Saturation duration divided by measured interval duration.'),
        'command_saturation_duration': metric(command_duration, 's', 'Time requested input is at or beyond a compiled control clamp; distinct from applied force.'),
        'signed_mechanical_work': metric(sum(works) if works is not None else None, 'J', work_method),
        'positive_mechanical_work': metric(sum(max(0, w) for w in works) if works is not None else None, 'J', work_method+' Positive interval contributions.'),
        'braking_work_magnitude': metric(-sum(min(0, w) for w in works) if works is not None else None, 'J', work_method+' Magnitude of negative interval contributions.'),
        'contact_episodes': metric(len(contacts) if contacts is not None else None, '1', 'Rising edges of actual wall-collision signal.'),
        'electrical_energy': metric(None, 'J', 'Requires an electrical/efficiency model.', 'No electrical signals or motor efficiency model.'),
        'travel_after_last_braking': metric(tail_travel, 'm', 'Signed measured position change after the last negative-force integration interval; exposes residual coasting, not a safety proof.'),
        'time_after_last_braking': metric(time[-1]-time[tail_start] if time is not None and tail_start is not None else None, 's', 'Measured remaining horizon after last negative-force interval.'),
    }
    series = {
        'time': metric(time, 's', 'Exact measured sample timestamps.'),
        'position': metric(position, 'm', 'Exact measured qpos.'),
        'velocity': metric(velocity, 'm/s', 'Exact measured qvel.'),
        'command': metric(command, 'N (validated direct motor only)', 'Input ctrl, not assumed force for unsupported transmission.'),
        'scalar_actuator_force': metric(scalar, 'N', 'Measured scalar actuator output before transmission.'),
        'generalized_actuator_force': metric(force, 'N', 'Measured generalized force along x slide.'),
        'acceleration_interval_midpoints': metric(interval_times if acceleration is not None else None, 's', interval_method),
        'acceleration': metric(acceleration, 'm/s^2', interval_method),
        'jerk': metric(jerk, 'm/s^3', 'Difference of midpoint accelerations; located between adjacent acceleration midpoints.'),
        'jerk_times': metric([(a+b)/2 for a, b in zip(interval_times, interval_times[1:])] if jerk is not None else None, 's', 'Midpoint of adjacent acceleration midpoints.'),
        'mechanical_power': metric([f*v for f, v in zip(force, velocity)] if force is not None and velocity is not None else None, 'W', 'Sampled generalized force times velocity; distinct from work quadrature.'),
        'wall_clearance': metric(gap, 'm', 'Exact measured signed surface gap.'),
    }
    return {'status': 'AVAILABLE' if time and len(time) > 1 else 'NOT_AVAILABLE',
            'contract_sha256': c.identity, 'metrics': metrics, 'series': series, 'contact_events': contacts,
            'limitations': ['Missing signals are NOT_AVAILABLE, not zero.',
                            'Actuator work excludes contact/passive work; discrete quadrature is not electrical energy.',
                            'Derivative spikes can reflect sampling/contact; they do not establish mechanical damage.']}
