"""BODYBASE + WORLDBASE scenario execution and independently measured evidence."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from uuid import uuid4

import mujoco

from core.bodybase import BodyBase
from core.worldbase import WorldBase
from core.context_validation import CONFIG_DIR, json_values, read_json
from core.simulation import ROOT, DEFAULT_MODEL_PATH, compile_context_model, run_simulation, sha256, source_hashes, write_json
from core.day2 import diagnose_and_save, file_inventory
from robot.controller import faulty_braking_controller

DEFAULT_OUTPUT = ROOT / 'artifacts' / 'day3'


def load_scenarios(path: str | Path = CONFIG_DIR / 'scenarios.json'):
    body, world = BodyBase.from_json(), WorldBase.from_json()
    scenarios = {}
    for name, overrides in read_json(path).items():
        if not isinstance(overrides, dict) or set(overrides) != {'bodybase', 'worldbase'}:
            raise ValueError('Each scenario must contain bodybase and worldbase override objects')
        if not all(isinstance(v, dict) for v in overrides.values()):
            raise ValueError('Scenario overrides must be JSON objects')
        if not isinstance(name, str) or not name.isalnum():
            raise ValueError('Scenario identifiers must be alphanumeric')
        scenarios[name] = (BodyBase.from_dict({**body.to_dict(), **overrides['bodybase']}),
                           WorldBase.from_dict({**world.to_dict(), **overrides['worldbase']}))
    if not scenarios:
        raise ValueError('At least one scenario is required')
    return scenarios


def measure_force_probes(xml: str, initial_position: float):
    """Measure both saturated forces and actual velocity changes in fresh models."""
    measurements = []
    for sign in (-1, 1):
        model = mujoco.MjModel.from_xml_string(xml)
        data = mujoco.MjData(model)
        data.qpos[0] = initial_position
        limit = float(model.actuator_forcerange[0, 1])
        data.ctrl[0] = sign * limit * 10
        mujoco.mj_forward(model, data)
        row = {'requested_control_n': float(data.ctrl[0]), 'scalar_force_n': float(data.actuator_force[0]),
               'generalized_force_n': float(data.qfrc_actuator[0]), 'mass_kg': float(model.body('carriage').mass[0]),
               'forward_acceleration_ms2': float(data.qacc[0]), 'initial_contacts': data.ncon}
        mujoco.mj_step(model, data)
        row.update({'measured_acceleration_from_velocity_ms2': float(data.qvel[0] / model.opt.timestep),
                    'final_position_m': float(data.qpos[0]), 'final_velocity_ms': float(data.qvel[0]),
                    'elapsed_s': float(data.time)})
        measurements.append(row)
    return measurements


def run_scenarios(output: Path = DEFAULT_OUTPUT, pytest_output: str | None = None):
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    history = {day: file_inventory(ROOT / 'artifacts' / day) for day in ('day1', 'day2')}
    day1 = read_json(ROOT / 'artifacts/day1/telemetry.json')
    day2 = read_json(ROOT / 'artifacts/day2/baseline/telemetry.json')
    controller_hash = sha256(ROOT / 'robot/controller.py')
    records, hashes, probe_checks = {}, [], []
    with tempfile.TemporaryDirectory(prefix='.day3-', dir=output.parent) as temp:
        stage = Path(temp) / 'run'
        stage.mkdir()
        migration = output / 'migration'
        if migration.exists():
            shutil.copytree(migration, stage / 'migration')
        for name, (body, world) in load_scenarios().items():
            directory = stage / f'scenario_{name}'
            run = run_simulation(bodybase=body, worldbase=world, controller=faulty_braking_controller,
                                 artifacts_dir=directory)
            diagnostics = diagnose_and_save(run)
            probes = measure_force_probes(run['effective_model_xml'], world.initial_position_x_m)
            probe_checks.extend(abs(p['generalized_force_n']) == body.max_force_n
                                and abs(p['measured_acceleration_from_velocity_ms2'] - p['generalized_force_n'] / body.mass_kg) < 1e-12
                                and p['initial_contacts'] == 0 for p in probes)
            write_json(directory / 'force_probes.json', probes)
            context = json_values({'bodybase': body.context, 'worldbase': world.context})
            write_json(directory / 'agent_context.json', context)
            braking, contact = diagnostics['braking_initiation'], diagnostics['first_wall_contact']
            summary = {'scenario': name, 'run_id': run['metadata']['run_id'], 'physical_context': run['metadata']['context'],
                       'effective_model': run['metadata']['model'], 'effective_mjcf_sha256': run['metadata']['effective_mjcf_sha256'],
                       'controller': run['metadata']['controller'],
                       'analytical_stopping_distance_m': body.stopping_distance_m(world.initial_velocity_ms),
                       'analytical_max_deceleration_ms2': body.max_deceleration_ms2,
                       'measured_precontact_deceleration_ms2': (-(contact['velocity'] - braking['velocity']) / (contact['time'] - braking['time'])
                                                                if braking and contact else None),
                       'braking_onset': braking, 'first_wall_contact': contact,
                       'wall_contact_events': diagnostics['safety_acceptance']['wall_collision_events'],
                       'wall_contact_samples': diagnostics['wall_contact_samples'],
                       'minimum_clearance_m': diagnostics['minimum_observed_clearance_m'],
                       'final_velocity_ms': diagnostics['final_state']['velocity'],
                       'safety': diagnostics['safety_acceptance'], 'software_execution': diagnostics['software_execution'],
                       'physics_simulation': diagnostics['physics_simulation'],
                       'independent_verification': diagnostics['independent_safety_verification'],
                       'unintended_contact_points': diagnostics['unintended_contact_points'],
                       'native_frame_count': len(run['render_frames']),
                       'effective_xml_matches_saved_file': sha256(directory / 'effective_model.xml') == run['metadata']['effective_mjcf_sha256'],
                       'day2_baseline_matches': run['telemetry'] == day2['samples'] if name == 'A' else None,
                       'artifact_directory': f'scenario_{name}'}
            write_json(directory / 'scenario_report.json', summary)
            records[name] = summary
            hashes.append(run['metadata']['controller']['source_sha256'])
        # Independently exercise a changed force limit, beyond the A/B mass contrast.
        body = replace(BodyBase.from_json(), max_force_n=2.0)
        world = WorldBase.from_json()
        _, xml = compile_context_model(DEFAULT_MODEL_PATH, body, world)
        changed_force = measure_force_probes(xml, world.initial_position_x_m)
        write_json(stage / 'changed_force_probes.json', {'bodybase': body.to_dict(), 'measurements': changed_force})
        probe_checks.extend(abs(p['generalized_force_n']) == 2.0 and abs(p['measured_acceleration_from_velocity_ms2']) == 1.0 for p in changed_force)
        uncontrolled = run_simulation(save_render=False, save_telemetry=False)
        checks = {
            'required_three_scenarios_executed': set(records) == {'A', 'B', 'C'},
            'all_scenarios_executed': all(s['software_execution'] == s['physics_simulation'] == 'PASS' for s in records.values()),
            'all_independent_verifications_pass': all(s['independent_verification']['verification_execution'] == 'PASS' for s in records.values()),
            'same_unchanged_controller': all(h == controller_hash == day2['metadata']['controller']['source_sha256'] for h in hashes),
            'effective_force_and_acceleration_measured': all(probe_checks),
            'analytical_parameters_match_compiled_model': all(abs(s['analytical_stopping_distance_m'] - s['physical_context']['worldbase']['initial_velocity_ms']**2
                                                                    / (2 * s['effective_model']['scalar_forcerange_n'][1] / s['effective_model']['carriage_mass_kg'])) < 1e-12 for s in records.values()),
            'effective_models_saved': all(s['effective_xml_matches_saved_file'] for s in records.values()),
            'native_rendering_preserved': all(s['native_frame_count'] >= 4 for s in records.values()),
            'no_unintended_contacts': all(s['unintended_contact_points'] == 0 for s in records.values()),
            'day1_numeric_regression': uncontrolled['telemetry'] == day1['samples'],
            'day2_numeric_regression': records['A']['day2_baseline_matches'],
            'historical_artifacts_preserved': all(file_inventory(ROOT / 'artifacts' / day) == inventory for day, inventory in history.items()),
            'raw_model_unchanged': sha256(DEFAULT_MODEL_PATH) == day1['metadata']['source_sha256']['robot/rail_carriage.xml'],
            'prior_test_files_unchanged': all(sha256(ROOT / path) == digest for path, digest in day2['metadata']['source_sha256'].items() if path.startswith('tests/')),
        }
        summary = {'created_at_utc': datetime.now(timezone.utc).isoformat(), 'source_sha256': source_hashes(DEFAULT_MODEL_PATH),
                   'scenarios': records, 'checks': {name: 'PASS' if ok else 'FAIL' for name, ok in checks.items()},
                   'day3_automated_result': 'PASS' if all(checks.values()) else 'FAIL',
                   'historical_artifact_sha256': history,
                   'visual_inspection': 'Pending direct inspection of native scenario frames'}
        write_json(stage / 'verification.json', summary)
        if pytest_output is not None:
            (stage / 'pytest_output.txt').write_text(pytest_output)
        # Publish the entire current experiment at once; old reports cannot leak in.
        if output.exists():
            archive = output.parent / 'archive'
            archive.mkdir(exist_ok=True)
            output.rename(archive / f'day3-{uuid4()}')
        stage.rename(output)
    return summary


def main():
    command = [sys.executable, '-m', 'pytest', '-ra']
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    text = completed.stdout + completed.stderr
    print(text, end='', flush=True)
    if completed.returncode:
        failed = ROOT / 'artifacts/failed' / ('day3-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
        failed.mkdir(parents=True, exist_ok=True)
        (failed / 'pytest_output.txt').write_text(text)
        raise SystemExit(completed.returncode)
    result = run_scenarios(pytest_output=text)
    write_json(DEFAULT_OUTPUT / 'pytest_result.json', {'command': command, 'exit_code': completed.returncode})
    print(json.dumps({'day3_automated_result': result['day3_automated_result'],
                      'scenario_safety': {name: row['safety']['status'] for name, row in result['scenarios'].items()},
                      'artifacts': str(DEFAULT_OUTPUT)}, indent=2))
    if result['day3_automated_result'] != 'PASS':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
