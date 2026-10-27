"""Pinned recorded evidence -> independently reproducible analytical/measured report."""
from __future__ import annotations
from dataclasses import replace
import hashlib
from pathlib import Path
from core.simulation import ROOT
from workspace.data import EvidenceError, default_recording
from .contracts import canonical, digest, UNITS, PROBE_COLUMNS
from .extraction import extract_contract
from .guard import assess_task, assess_program_source
from .profiler import profile

VARIANTS = ('original', 'attempt_1', 'attempt_2')


def implementation_hashes():
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path(__file__).parent.glob('*.py'))}


def recorded_report(scenario, variant, *, recording=None):
    if scenario not in ('A', 'B', 'C') or variant not in VARIANTS:
        raise EvidenceError('Unknown analysis selection')
    r = recording or default_recording()
    source = r.original() if variant == 'original' else r.proposal(variant)
    text = source['content'] if variant == 'original' else source['source']
    controller_hash = hashlib.sha256(text.encode()).hexdigest()
    trajectory = r.trajectory(scenario, variant)
    c = extract_contract(scenario, controller_hash)
    meta, samples, summary = trajectory['metadata'], trajectory['samples'], trajectory['summary']
    if (meta['controller']['source_sha256'] != c.controller_sha256
            or meta['effective_mjcf_sha256'] != c.model_sha256
            or hashlib.sha256(trajectory['xml'].encode()).hexdigest() != c.model_sha256
            or digest(meta['context']) != c.context_sha256
            or summary['controller_sha256'] != c.controller_sha256):
        raise EvidenceError('Analysis model/source/context identity mismatch')
    if any(meta['source_sha256'].get(name) != value for name, value in c.source_hashes):
        raise EvidenceError('Recorded physical source implementation differs from contract')
    if len(samples) != round(c.duration_s/c.timestep_s)+1:
        raise EvidenceError('Analysis requires the complete recorded horizon')
    if (abs(samples[0]['time']) > c.numeric_tolerance
            or abs(samples[0]['position']-c.initial_position_m) > c.numeric_tolerance
            or abs(samples[0]['velocity']-c.initial_velocity_mps) > c.numeric_tolerance):
        raise EvidenceError('Recorded initial state differs from contract')
    independent = trajectory['independent']
    if (independent.get('effective_context_matches') is not True
            or independent.get('verification_execution') != summary['independent_verification']
            or independent['safety_acceptance']['status'] != summary['physical_safety_status']):
        raise EvidenceError('Independent verification identity/outcome mismatch')
    independent_model = (independent.get('effective_mjcf_sha256') if variant == 'original'
                         else independent['fresh_worker_handshake']['xml_sha256'])
    if independent_model != c.model_sha256:
        raise EvidenceError('Independent verification model mismatch')
    for s in samples:
        expected = c.wall_near_x_m-s['position']-c.bumper_front_offset_m
        if abs(s['wall_clearance']-expected) > c.distance_tolerance_m:
            raise EvidenceError('Recorded surface geometry differs from contract')
    profiler = profile(samples, c)
    if profiler['status'] != 'AVAILABLE':
        raise EvidenceError('Recorded telemetry unavailable')
    measured = observed_assessment(samples, c)
    if measured['safety_status'] != summary['physical_safety_status']:
        raise EvidenceError('Independent measured assessment disagrees with recorded acceptance')
    onset_index = next((i for i, s in enumerate(samples) if s['velocity'] > 0 and s['generalized_actuator_force'] < 0), None)
    onset = None
    if onset_index is not None:
        s = samples[onset_index]
        onset = {'sample_index': onset_index, 'time_s': s['time'], 'velocity_mps': s['velocity'],
                 'clearance_m': s['wall_clearance'], 'applied_force_n': s['generalized_actuator_force'],
                 'analysis': assess_task(c, velocity_mps=s['velocity'], clearance_m=s['wall_clearance'],
                                        remaining_time_s=c.deadline_s-s['time'], contact_present=s['wall_collision'])}
    outside = assess_task(c, velocity_mps=c.maximum_speed_mps+1)
    report = {'schema_version': 1, 'scenario_id': scenario, 'variant': variant,
              'evidence_kind': 'recorded genuine MuJoCo trajectory; new deterministic analysis, no new rollout',
              'contract_sha256': c.identity, 'physics_contract': c.to_dict(), 'units': UNITS,
              'force_probe_columns': list(PROBE_COLUMNS),
              'analytical_feasibility': assess_task(c), 'controller_static_assessment': assess_program_source(text, c),
              'observed_physics': measured, 'braking_onset': onset, 'profiler': profiler,
              'outside_envelope': outside,
              'recorded_independent_verification': summary['independent_verification'],
              'uncertainty': ['No nonzero parameter uncertainty certified.', 'No global source-program safety proof.',
                              'Predictive model excludes soft contact and reverse recovery.',
                              'Recorded A/B/C success is not a guarantee for untested parameters or real hardware.'],
              'provenance': {'recording_inventory_sha256': r.inventory_sha256,
                             'telemetry_reference': trajectory['telemetry_reference'],
                             'telemetry_sha256': hashlib.sha256(r.read(trajectory['telemetry_reference'])).hexdigest(),
                             'diagnostics_reference': (r.reference(summary['artifact_references']['diagnostics.json'])
                                                       if 'diagnostics.json' in summary['artifact_references'] else None),
                             'independent_trace_reference': r.reference(summary['artifact_references']['independent_safety_trace.json']),
                             'model_sha256': c.model_sha256, 'controller_sha256': c.controller_sha256,
                             'implementation_sha256': implementation_hashes(),
                             'mujoco_version_recorded': meta['mujoco_version']},
              'authorization': {'vm_execution_approved': False, 'permanent_apply_approved': False}}
    report['report_sha256'] = digest(report)
    return report


def observed_assessment(samples, c):
    if not samples:
        return {'safety_status': 'NOT_AVAILABLE', 'guard_status': 'UNKNOWN', 'violations': ['Missing trajectory']}
    values = profile(samples, c)['metrics']
    gap = values['minimum_clearance']['value']; final = abs(samples[-1]['velocity'])
    forces = [s['generalized_actuator_force'] for s in samples]
    force_low = max(c.control_range[0], c.scalar_force_range_n[0])
    force_high = min(c.control_range[1], c.scalar_force_range_n[1])
    checks = {'no_wall_contact': values['contact_episodes']['value'] == 0,
              'minimum_clearance': gap >= c.minimum_clearance_m-c.distance_tolerance_m,
              'final_speed': final < c.final_speed_tolerance_mps,
              'completion': len(samples) == round(c.duration_s/c.timestep_s)+1
                  and abs(samples[-1]['time']-c.duration_s) <= c.numeric_tolerance
                  and samples[-1]['time'] <= c.deadline_s+c.numeric_tolerance,
              'actuator_force_limits': all(force_low-c.numeric_tolerance <= f <= force_high+c.numeric_tolerance for f in forces)}
    violations = [k for k, value in checks.items() if not value]
    return {'safety_status': 'FAIL' if violations else 'PASS',
            'guard_status': 'PROVEN_VIOLATION' if violations else 'UNKNOWN',
            'claim_scope': 'finite recorded samples only; not a predictive controller certificate',
            'checks': checks, 'violations': violations, 'minimum_clearance_m': gap,
            'clearance_margin_m': gap-c.minimum_clearance_m, 'final_absolute_velocity_mps': final,
            'final_time_s': samples[-1]['time'], 'contact_episodes': values['contact_episodes']['value'],
            'force_range_n': [min(forces), max(forces)]}


def impossible_fixture(contract):
    """Separate labelled mathematical fixture; never changes scenario configuration."""
    gap = contract.minimum_clearance_m+0.01
    c = replace(contract, scenario_id='analytical_impossible', provenance_kind='analytical_fixture',
                initial_clearance_m=gap,
                initial_position_m=contract.wall_near_x_m-contract.bumper_front_offset_m-gap,
                context_sha256=digest({'base_context_sha256': contract.context_sha256,
                                       'analytical_override_initial_clearance_m': gap}))
    result = {'evidence_kind': 'analytical fixture, not a simulation or historical scenario',
            'physics_contract': c.to_dict(), 'contract_sha256': c.identity,
            'analytical_feasibility': assess_task(c), 'observed_physics': None,
            'profiler': profile([], c), 'uncertainty': ['No trajectory was run for this mathematical fixture.'],
            'provenance': {'base_context_sha256': contract.context_sha256,
                           'implementation_sha256': implementation_hashes()},
            'authorization': {'vm_execution_approved': False, 'permanent_apply_approved': False}}
    result['report_sha256'] = digest(result)
    return result


def markdown(report):
    c = report['physics_contract']; a = report['analytical_feasibility']
    lines = [f"# Physics analysis — {report.get('scenario_id', c['scenario_id'])} / {report.get('variant', 'analytical fixture')}",
             '', report['evidence_kind'], '', f"Contract SHA-256: `{report['contract_sha256']}`",
             f"Model: `{c['model_sha256']}`", f"Controller source: `{c['controller_sha256']}`", '',
             '## Physics contract', '', f"Mass/inertia: {c['mass_kg']} / {c['generalized_inertia_kg']} kg; braking authority: {c['braking_force_n']} N.",
             f"Initial speed {c['initial_velocity_mps']} m/s; surface gap {c['initial_clearance_m']} m; wall center {c['wall_center_m'][0]} m, near face {c['wall_near_x_m']} m.",
             f"Requirement: no wall contact, gap >= {c['minimum_clearance_m']} m, final |v| < {c['final_speed_tolerance_mps']} m/s, deadline {c['deadline_s']} s.",
             '', '## Analytical feasibility', '', f"**{a['status']}** — {a['explanation']}", '',
             *[f'- `{equation}`' for equation in a['equations'].values()], '', '```json', canonical(a['bounds']), '```', '',
             '## Assumptions and uncertainty', '', *['- '+s for s in c['assumptions']],
             *['- '+s for s in report.get('uncertainty', [])], '',
             'This analysis grants no VM, verification or installation approval.']
    if report.get('observed_physics') is not None:
        o = report['observed_physics']
        lines += ['', '## Observed physics and violations', '',
                  f"Recorded safety **{o['safety_status']}**; independent recorded verification **{report['recorded_independent_verification']}**.",
                  f"Minimum gap {o['minimum_clearance_m']:.12g} m; margin {o['clearance_margin_m']:.12g} m; final |v| {o['final_absolute_velocity_mps']:.12g} m/s; contacts {o['contact_episodes']}.",
                  'Violations: '+(', '.join(o['violations']) or 'none in these recorded samples'), '',
                  '## Measured braking onset', '', '```json', canonical(report['braking_onset']), '```', '',
                  '## Profiler', '', '| Metric | Value | Unit | Method |', '| --- | --- | --- | --- |']
        lines += [f"| {name} | {v['value'] if v['status']=='AVAILABLE' else 'NOT_AVAILABLE'} | {v['unit']} | {v['method']} |" for name, v in report['profiler']['metrics'].items()]
        lines += ['', '## Reproducibility', '', 'Full measured series, source/model/data/implementation identities and methods are in the adjacent JSON.',
                  '```json', canonical(report['provenance']), '```', '', f"Report payload SHA-256: `{report['report_sha256']}`"]
    else:
        lines += ['', '## Observed physics / profiler', '',
                  'NOT_AVAILABLE — this fixture was not simulated. Its infeasibility claim is analytical only.',
                  '', '## Reproducibility', '', '```json', canonical(report['provenance']), '```',
                  f"Report payload SHA-256: `{report['report_sha256']}`"]
    return '\n'.join(lines)+'\n'


def write_reports(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    reports = []
    for scenario in ('A', 'B', 'C'):
        for variant in VARIANTS:
            report = recorded_report(scenario, variant); reports.append(report)
            base = output/f'{scenario}_{variant}'
            base.with_suffix('.json').write_text(canonical(report)+'\n')
            base.with_suffix('.md').write_text(markdown(report))
    impossible = impossible_fixture(extract_contract('A'))
    (output/'impossible.json').write_text(canonical(impossible)+'\n')
    (output/'impossible.md').write_text(markdown(impossible))
    table = ['# Analytical versus recorded physical evidence', '',
             'All rows assume the checked pre-contact direct motor/Euler rail model. Nonzero uncertainty and global program safety remain UNKNOWN.', '',
             '| Scenario / controller | Initial task | Ideal stopping (m) | F (N) | Onset model | Min gap (m) | Measured behavior | Measured safety | Independent recorded verification | Uncertainty |',
             '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    for r in reports:
        o = r['observed_physics']
        behavior = ('wall contact' if o['contact_episodes'] else f"no contact; final absolute speed={o['final_absolute_velocity_mps']:.5g} m/s")
        table.append(f"| {r['scenario_id']} / {r['variant']} | {r['analytical_feasibility']['status']} | {r['analytical_feasibility']['bounds']['continuous_zero_stop_m']:.6g} | {r['physics_contract']['braking_force_n']} | {r['braking_onset']['analysis']['status']} | {o['minimum_clearance_m']:.12g} | {behavior} | {o['safety_status']} | {r['recorded_independent_verification']} | pre-contact theorem only; global source/uncertainty UNKNOWN |")
    table += ['', 'A feasible task can have an unsafe controller. Recorded success does not certify arbitrary source or untested parameters.',
              'The baseline soft-contact/rebound phase is outside the stopping theorem. The weaker necessary bound respects the strict final-speed requirement; the discrete constructive bound explains why safe onset margins differ from continuous estimates.']
    (output/'comparison.md').write_text('\n'.join(table)+'\n')
    inventory = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.iterdir())}
    (output/'inventory.json').write_text(canonical(inventory)+'\n')
    return reports


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Analyze pinned recorded physics without executing any controller.')
    parser.add_argument('--output', type=Path, required=True)
    write_reports(parser.parse_args().output)
