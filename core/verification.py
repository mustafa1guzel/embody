"""Execute the full Day 1 evidence workflow; no controller or Day 2 features."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

import mujoco
import numpy as np

from core.simulation import (DEFAULT_ARTIFACTS_DIR, DEFAULT_MODEL_PATH, ROOT,
                             run_simulation, source_hashes, write_json)


NUMERIC_FIELDS = ("time", "position", "velocity", "acceleration", "control",
                  "scalar_actuator_force", "generalized_actuator_force", "wall_clearance")


def measure_physics() -> dict[str, Any]:
    """Independent engine probes, not telemetry values copied from run_simulation."""
    model = mujoco.MjModel.from_xml_path(str(DEFAULT_MODEL_PATH))
    data = mujoco.MjData(model)
    data.qvel[0] = 1.2
    free_samples = []
    for step in range(281):
        mujoco.mj_forward(model, data)
        free_samples.append({"time": float(data.time), "position": float(data.qpos[0]),
                             "velocity": float(data.qvel[0]), "contacts": data.ncon,
                             "position_error_m": float(data.qpos[0] - 1.2 * data.time)})
        if step < 280:
            mujoco.mj_step(model, data)
    force_probes = []
    for command in (-40.0, -4.0, 0.0, 4.0, 40.0):
        probe_model = mujoco.MjModel.from_xml_path(str(DEFAULT_MODEL_PATH))
        probe = mujoco.MjData(probe_model)
        probe.ctrl[0] = command
        mujoco.mj_forward(probe_model, probe)
        measurement = {"control_input_n": command,
                       "scalar_actuator_force_n": float(probe.actuator_force[0]),
                       "generalized_actuator_force_n": float(probe.qfrc_actuator[0]),
                       "forward_acceleration_mps2": float(probe.qacc[0])}
        for _ in range(10):
            mujoco.mj_step(probe_model, probe)
        mujoco.mj_forward(probe_model, probe)
        measurement.update({"elapsed_s": float(probe.time), "final_position_m": float(probe.qpos[0]),
                            "final_velocity_mps": float(probe.qvel[0]),
                            "measured_acceleration_from_velocity_mps2": float(probe.qvel[0] / probe.time),
                            "final_contacts": probe.ncon})
        force_probes.append(measurement)
    rail = model.geom("rail_track").id
    mujoco.mj_forward(model, data)
    axis = data.geom_xmat[rail].reshape(3, 3)[:, 2]
    return {"method": "Separate MjModel/MjData probes with direct mj_forward/mj_step",
            "free_motion": {"samples": free_samples,
                            "max_position_error_m": max(abs(s["position_error_m"]) for s in free_samples),
                            "contact_count": sum(s["contacts"] for s in free_samples)},
            "actuator_probes": force_probes,
            "model": {"nq": model.nq, "nv": model.nv, "njnt": model.njnt,
                      "carriage_mass_kg": float(model.body("carriage").mass[0]),
                      "rail_radius_m": float(model.geom_size[rail, 0]),
                      "rail_half_length_m": float(model.geom_size[rail, 1]),
                      "rail_axis_world": axis.tolist(),
                      "rail_endpoints_world": [(data.geom_xpos[rail] + sign * model.geom_size[rail, 1] * axis).tolist()
                                               for sign in (-1, 1)]}}


def summarize(samples: list[dict[str, Any]]) -> dict[str, Any]:
    contacts = [s for s in samples if s["wall_collision"]]
    return {"initial_position_m": samples[0]["position"], "initial_velocity_mps": samples[0]["velocity"],
            "final_position_m": samples[-1]["position"], "final_velocity_mps": samples[-1]["velocity"],
            "final_time_s": samples[-1]["time"], "steps": len(samples) - 1, "samples": len(samples),
            "wall_contact_samples": len(contacts),
            "wall_contact_points_summed_over_samples": sum(s["contact_count"] for s in contacts),
            "first_wall_contact_time_s": contacts[0]["time"] if contacts else None,
            "minimum_clearance_m": min(s["wall_clearance"] for s in samples),
            "final_clearance_m": samples[-1]["wall_clearance"],
            "peak_wall_normal_force_n": max((sum(c["normal_force_n"] for c in s["contacts"]
                                                  if c["involves_wall"]) for s in samples), default=0),
            "unintended_contact_points": sum(1 for s in samples for c in s["contacts"]
                                              if {c["geom_1"], c["geom_2"]} != {"front_bumper", "wall"})}


def compare_runs(runs: list[dict[str, Any]], tolerance: float = 1e-12) -> dict[str, Any]:
    reference = runs[0]["telemetry"]
    if any(len(run["telemetry"]) != len(reference) for run in runs):
        return {"pass": False, "reason": "different sample counts"}
    errors = {field: max(float(np.max(np.abs(np.array([s[field] for s in run["telemetry"]])
                                                     - np.array([s[field] for s in reference]))))
                         for run in runs) for field in NUMERIC_FIELDS}
    contacts_equal = all([s["contacts"] for s in run["telemetry"]] == [s["contacts"] for s in reference]
                         for run in runs)
    return {"pass": max(errors.values()) <= tolerance and contacts_equal,
            "absolute_tolerance": tolerance, "max_abs_differences": errors,
            "contact_records_exactly_equal": contacts_equal}


def main() -> None:
    command = [sys.executable, "-m", "pytest", "-ra"]
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    pytest_output = completed.stdout + completed.stderr
    print(pytest_output, end="", flush=True)
    if completed.returncode:
        failed = ROOT / "artifacts" / "failed" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        failed.mkdir(parents=True, exist_ok=True)
        (failed / "pytest_output.txt").write_text(pytest_output)
        raise SystemExit(f"Pytest failed (exit {completed.returncode}); evidence saved at {failed}")
    # The demonstration is one original trajectory with inline native rendering.
    demo = run_simulation()
    output = DEFAULT_ARTIFACTS_DIR
    (output / "pytest_output.txt").write_text(pytest_output)
    probes = measure_physics()
    runs = [run_simulation(save_render=False, artifacts_dir=output / "reproducibility" / f"run_{i}")
            for i in range(1, 4)]
    comparison = compare_runs(runs)
    demo_comparison = compare_runs([demo, *runs])
    summary = summarize(demo["telemetry"])
    checks = {
        "one_translational_dof": (probes["model"]["nq"], probes["model"]["nv"], probes["model"]["njnt"]) == (1, 1, 1),
        "mass_2kg": probes["model"]["carriage_mass_kg"] == 2,
        "rail_dimensions": np.allclose([probes["model"]["rail_radius_m"], probes["model"]["rail_half_length_m"]], [0.03, 1.8], atol=1e-14),
        "no_unintended_contacts": summary["unintended_contact_points"] == 0,
        "real_wall_contact": summary["wall_contact_samples"] > 0,
        "free_motion": probes["free_motion"]["max_position_error_m"] < 1e-12 and probes["free_motion"]["contact_count"] == 0,
        "force_and_acceleration": all(abs(p["generalized_actuator_force_n"] - np.clip(p["control_input_n"], -4, 4)) < 1e-12
                                       and abs(p["measured_acceleration_from_velocity_mps2"] - p["generalized_actuator_force_n"] / 2) < 1e-12
                                       for p in probes["actuator_probes"]),
        "600_steps_601_samples": (summary["steps"], summary["samples"]) == (600, 601),
        "native_frames": len(demo["render_frames"]) == 4,
        "frame_time_alignment": all(f["time"] == demo["telemetry"][f["step"]]["time"]
                                    for f in demo["metadata"]["rendering"]["frames"]),
        "no_simulator_warnings": demo["metadata"]["warnings"] == {},
        "three_run_reproducibility": comparison["pass"],
        "rendered_demo_matches_repetitions": demo_comparison["pass"],
        "source_hashes_current": demo["metadata"]["source_sha256"] == source_hashes(DEFAULT_MODEL_PATH),
        "pytest_executed_successfully": completed.returncode == 0,
    }
    report = {"created_at_utc": datetime.now(timezone.utc).isoformat(),
              "source_sha256": demo["metadata"]["source_sha256"],
              "pytest": {"command": command, "exit_code": completed.returncode, "output_path": "pytest_output.txt"},
              "independent_physics": probes, "demonstration": summary,
              "reproducibility": {"runs": [{"run_id": run["metadata"]["run_id"],
                                             "telemetry_path": f"reproducibility/run_{i}/telemetry.json",
                                             **summarize(run["telemetry"])} for i, run in enumerate(runs, 1)],
                                  "comparison": comparison, "comparison_including_rendered_demo": demo_comparison},
              "checks": {name: "PASS" if value else "FAIL" for name, value in checks.items()},
              "automated_result": "PASS" if all(checks.values()) else "FAIL",
              "visual_inspection": "Direct inspection is required separately; see report.md when available."}
    write_json(output / "verification.json", report)
    print(json.dumps({"automated_result": report["automated_result"], "demonstration": summary,
                      "reproducibility": comparison, "output": str(output)}, indent=2))
    if not all(checks.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
