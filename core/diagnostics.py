"""Measured Day 2 diagnostics and a separate direct-MuJoCo safety execution."""
from __future__ import annotations

import math
import hashlib
from pathlib import Path
from typing import Any

import mujoco

from core.simulation import sha256
from robot.controller import BRAKING_THRESHOLD_M, faulty_braking_controller
from core.bodybase import BodyBase
from core.worldbase import WorldBase


def stopping_prediction(mass_kg: float, braking_force_n: float, velocity_mps: float,
                        available_distance_m: float) -> dict[str, Any]:
    values = (mass_kg, braking_force_n, velocity_mps, available_distance_m)
    if not all(math.isfinite(v) for v in values) or mass_kg <= 0 or braking_force_n <= 0:
        raise ValueError("Prediction requires finite values and positive mass/force")
    acceleration = braking_force_n / mass_kg
    distance = velocity_mps**2 / (2 * acceleration)
    return {"kind": "analytical_prediction_not_simulator_measurement",
            "assumptions": "Constant maximum braking, no contact or opposing force, continuous time",
            "max_deceleration_mps2": acceleration, "stopping_distance_m": distance,
            "available_distance_m": available_distance_m, "distance_shortfall_m": distance - available_distance_m,
            "stop_before_wall_predicted": distance < available_distance_m,
            "predicted_wall_surface_speed_mps": math.sqrt(max(0, velocity_mps**2 - 2 * acceleration * max(0, available_distance_m)))}


def physical_parameters(model: mujoco.MjModel) -> dict[str, Any]:
    motor = model.actuator("x_motor").id
    if model.actuator_gear[motor, 0] != 1:
        raise ValueError("This experiment requires the established direct motor with gear=1")
    minimum_command = max(float(model.actuator_ctrlrange[motor, 0]),
                          float(model.actuator_forcerange[motor, 0]))
    return {"mass_kg": float(model.body("carriage").mass[0]),
            "max_braking_force_n": -minimum_command, "gear": float(model.actuator_gear[motor, 0]),
            "ctrlrange": model.actuator_ctrlrange[motor].tolist(),
            "scalar_forcerange_n": model.actuator_forcerange[motor].tolist(),
            "gravity_mps2": model.opt.gravity.tolist(),
            "contact_solref": model.geom("wall").solref.tolist()}


def evaluate_safety(samples: list[dict[str, Any]], world: WorldBase,
                    wall_geom_id: int, tolerance: float = 1e-12) -> dict[str, Any]:
    """Strict Day 3 acceptance from measured states and actual contact identities."""
    if not samples:
        raise ValueError("Safety evaluation requires measured samples")
    contact_states = [any(wall_geom_id in c["geom_ids"] for c in s["contacts"]) for s in samples]
    events = sum(contact and (i == 0 or not contact_states[i - 1]) for i, contact in enumerate(contact_states))
    minimum = min(s["wall_clearance"] for s in samples)
    speed, end = abs(samples[-1]["velocity"]), samples[-1]["time"]
    finite = all(math.isfinite(s[f]) for s in samples for f in ("time", "velocity", "wall_clearance"))
    completed = (len(samples) == round(world.simulation_duration_s / world.simulation_timestep_s) + 1
                 and math.isclose(end, world.simulation_duration_s, rel_tol=0, abs_tol=tolerance))
    checks = {"zero_wall_collision_events": events == 0,
              "minimum_clearance": minimum >= world.minimum_clearance_m - tolerance,
              "final_speed": speed < world.max_final_speed_ms,
              "completion_within_deadline": completed and end <= world.completion_deadline_s + tolerance,
              "finite_measurements": finite}
    explanations = {
        "zero_wall_collision_events": f"Observed {events} wall contact episode(s) in {sum(contact_states)} sampled states",
        "minimum_clearance": f"Minimum clearance {minimum:.12g} m is below required {world.minimum_clearance_m:.12g} m",
        "final_speed": f"Final speed {speed:.12g} m/s is not below {world.max_final_speed_ms:.12g} m/s",
        "completion_within_deadline": f"Completed horizon={completed}, actual end={end:.12g} s, deadline={world.completion_deadline_s:.12g} s",
        "finite_measurements": "Nonfinite state measurements prevent acceptance"}
    return {"status": "PASS" if all(checks.values()) else "FAIL",
            "criteria": {"wall_collision_events": 0, "minimum_clearance_m": world.minimum_clearance_m,
                         "max_final_speed_ms_exclusive": world.max_final_speed_ms,
                         "completion_deadline_s": world.completion_deadline_s},
            "checks": {name: "PASS" if passed else "FAIL" for name, passed in checks.items()},
            "wall_collision_events": events, "wall_contact_samples": sum(contact_states),
            "minimum_measured_clearance_m": minimum, "final_speed_ms": speed, "final_time_s": end,
            "failure_reasons": [explanations[name] for name, passed in checks.items() if not passed]}


def independently_verify_safety(run: dict[str, Any], tolerance: float = 1e-12) -> dict[str, Any]:
    """Fresh direct stepping, geometry-distance query and contact IDs; no simulator helper.

    Reuses the actual controller under test, never its inferred behavior. Safety
    classification and observations are independent of the main telemetry flags.
    """
    metadata = run["metadata"]
    if metadata["controller"]["name"] != "robot.controller.faulty_braking_controller":
        raise ValueError("Independent Day 2 verifier requires the actual faulty controller")
    effective_xml = run["effective_model_xml"]
    digest = hashlib.sha256(effective_xml.encode()).hexdigest()
    if digest != metadata["effective_mjcf_sha256"]:
        raise ValueError("Effective MuJoCo model snapshot hash mismatch")
    model = mujoco.MjModel.from_xml_string(effective_xml)
    body = BodyBase.from_dict(metadata["context"]["bodybase"])
    world = WorldBase.from_dict(metadata["context"]["worldbase"])
    cfg = metadata["configuration"]
    model.opt.timestep = cfg["timestep_s"]
    data = mujoco.MjData(model)
    data.joint("x_slide").qpos[0] = cfg["initial_position_m"]
    data.joint("x_slide").qvel[0] = cfg["initial_velocity_mps"]
    wall, bumper = model.geom("wall").id, model.geom("front_bumper").id
    trace = []
    for step in range(cfg["steps"] + 1):
        mujoco.mj_forward(model, data)
        faulty_braking_controller(model, data)
        mujoco.mj_forward(model, data)
        contacts = [{"geom_ids": [int(c.geom1), int(c.geom2)],
                     "geom_names": [model.geom(int(c.geom1)).name, model.geom(int(c.geom2)).name],
                     "distance_m": float(c.dist)} for c in data.contact[:data.ncon]]
        wall_contacts = [c for c in contacts if wall in c["geom_ids"]]
        trace.append({"step": step, "time": float(data.time), "position": float(data.qpos[0]),
                      "velocity": float(data.qvel[0]), "control": float(data.ctrl[0]),
                      "generalized_actuator_force": float(data.qfrc_actuator[0]),
                      "wall_clearance": float(mujoco.mj_geomDistance(
                          model, data, bumper, wall,
                          math.dist(data.geom_xpos[bumper], data.geom_xpos[wall])
                          + sum(model.geom_size[bumper]) + sum(model.geom_size[wall]) + 1, None)),
                      "wall_contacts": wall_contacts, "contacts": contacts})
        if step < cfg["steps"]:
            mujoco.mj_step(model, data)
    measured = run["telemetry"]
    same_length = len(trace) == len(measured)
    fields = ("time", "position", "velocity", "control", "generalized_actuator_force", "wall_clearance")
    differences = {field: max(abs(a[field] - b[field]) for a, b in zip(trace, measured)) for field in fields}
    consistent = same_length and max(differences.values()) <= tolerance
    # Match actual IDs, rather than trusting the main run's wall_collision boolean.
    contact_ids_match = same_length and all([c["geom_ids"] for c in a["contacts"]]
                                           == [c["geom_ids"] for c in b["contacts"]]
                                           for a, b in zip(trace, measured))
    events = [s for s in trace if s["wall_contacts"]]
    minimum = min(s["wall_clearance"] for s in trace)
    desired = cfg["desired_future_clearance_m"]
    no_contact = not events
    clearance_ok = minimum >= desired
    finite = all(math.isfinite(s[f]) for s in trace for f in fields)
    acceptance = evaluate_safety(trace, world, wall)
    params = physical_parameters(model)
    context_matches = (params["mass_kg"] == body.mass_kg and params["max_braking_force_n"] == body.max_force_n
                       and model.body("obstacle").pos[0] == world.wall_position_x_m
                       and model.opt.timestep == world.simulation_timestep_s
                       and cfg["initial_velocity_mps"] == world.initial_velocity_ms
                       and cfg["initial_position_m"] == world.initial_position_x_m)
    legacy_task = "PASS" if no_contact and clearance_ok and finite else "FAIL"
    task = acceptance["status"] if metadata["safety_policy"] == "stop_before_wall" else legacy_task
    return {"method": "Fresh MjModel/MjData; direct mj_step; wall geom IDs and mj_geomDistance",
            "model_sha256": sha256(Path(metadata["model_path"])),
            "effective_mjcf_sha256": digest, "effective_context_matches": context_matches,
            "trace": trace, "samples": len(trace), "absolute_tolerance": tolerance,
            "max_abs_telemetry_differences": differences,
            "telemetry_matches": consistent and contact_ids_match,
            "contact_ids_match": contact_ids_match, "finite_state": finite,
            "wall_contact_samples": len(events), "first_wall_contact": events[0] if events else None,
            "minimum_clearance_m": minimum, "desired_clearance_m": desired,
            "collision_free": no_contact, "desired_clearance_satisfied": clearance_ok,
            "task": metadata["safety_policy"], "safety_acceptance": acceptance,
            "physical_safety_task": task,
            "verification_execution": "PASS" if consistent and contact_ids_match and finite and context_matches else "FAIL"}


def failure_diagnostics(run: dict[str, Any], independent: dict[str, Any]) -> dict[str, Any]:
    samples, metadata = run["telemetry"], run["metadata"]
    model = run["model"]
    params = physical_parameters(model)
    wall_id = model.geom("wall").id
    braking = next((s for s in samples if s["velocity"] > 0 and s["generalized_actuator_force"] < 0), None)
    contacts = [s for s in samples if any(wall_id in c["geom_ids"] for c in s["contacts"])]
    first = contacts[0] if contacts else None
    prediction = stopping_prediction(params["mass_kg"], params["max_braking_force_n"],
                                     samples[0]["velocity"], BRAKING_THRESHOLD_M)
    at_braking = (stopping_prediction(params["mass_kg"], params["max_braking_force_n"],
                                     braking["velocity"], braking["wall_clearance"]) if braking else None)
    cfg = metadata["configuration"]
    finite = all(math.isfinite(s[f]) for s in samples for f in ("position", "velocity", "time"))
    execution_ok = len(samples) == cfg["steps"] + 1 and math.isclose(samples[-1]["time"], cfg["duration_s"], abs_tol=1e-12)
    simulation_ok = execution_ok and finite and not metadata["warnings"]
    unexpected = [c for s in samples for c in s["contacts"]
                  if set(c["geom_ids"]) != {model.geom("front_bumper").id, wall_id}]
    minimum = min(s["wall_clearance"] for s in samples)
    task_pass = not contacts and minimum >= cfg["desired_future_clearance_m"]
    world = WorldBase.from_dict(metadata["context"]["worldbase"])
    acceptance = evaluate_safety(samples, world, wall_id)
    if metadata["safety_policy"] == "stop_before_wall":
        task_pass = acceptance["status"] == "PASS"
    verified = independent["verification_execution"] == "PASS" and independent["telemetry_matches"]
    reproduced = (simulation_ok and verified and braking is not None and first is not None
                  and first["velocity"] > 0 and not task_pass and not unexpected
                  and not at_braking["stop_before_wall_predicted"])
    if braking is None:
        explanation = "No braking onset was observed in the executed trajectory."
    elif first is None:
        explanation = (f"Braking began with {braking['wall_clearance']:.6g} m clearance at "
                       f"{braking['velocity']:.6g} m/s; no wall contact was observed.")
    else:
        explanation = (f"The fixed {BRAKING_THRESHOLD_M:g} m rule began braking at {braking['time']:.6g} s, "
                       f"with {braking['wall_clearance']:.6g} m clearance and {braking['velocity']:.6g} m/s velocity. "
                       f"At the model's {params['max_braking_force_n']:g} N braking limit and {params['mass_kg']:g} kg mass, "
                       f"continuous-time stopping needs {at_braking['stopping_distance_m']:.6g} m. "
                       f"MuJoCo detected wall contact at {first['time']:.6g} s while velocity was {first['velocity']:.6g} m/s. "
                       "The code executed, but the fixed threshold ignored the required stopping distance.")
    return {"schema_version": 1, "run_id": metadata["run_id"],
            "simulation_configuration": cfg, "source_sha256": metadata["source_sha256"],
            "physical_context": metadata["context"], "effective_mjcf_sha256": metadata["effective_mjcf_sha256"],
            "controller": metadata["controller"], "controller_fixed_threshold_m": BRAKING_THRESHOLD_M,
            "robot_physical_parameters": params, "analytical_prediction": prediction,
            "prediction_at_measured_braking_onset": at_braking,
            "actual_available_braking_distance_m": braking["wall_clearance"] if braking else None,
            "braking_initiation": braking, "first_wall_contact": first,
            "wall_contact_samples": len(contacts),
            "wall_contact_points_summed_over_samples": sum(s["contact_count"] for s in contacts),
            "unintended_contact_points": len(unexpected), "minimum_observed_clearance_m": minimum,
            "final_state": samples[-1], "physical_failure_explanation": explanation,
            "software_execution": "PASS" if execution_ok else "FAIL",
            "physics_simulation": "PASS" if simulation_ok else "FAIL",
            "physical_safety_task": "PASS" if task_pass else "FAIL",
            "safety_policy": metadata["safety_policy"], "safety_acceptance": acceptance,
            "expected_contact_failure_reproduced": reproduced,
            "independent_safety_verification": {k: v for k, v in independent.items() if k != "trace"},
            "contact_timing_note": "First contact is a discrete sampled state before its subsequent contact impulse; it is not a continuous-time impact root.",
            "contact_model_note": "Soft-contact overlap and rebound are measured; positive final clearance does not undo an earlier collision."}
