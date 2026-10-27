"""One MuJoCo trajectory supplies telemetry and native renders, with optional control."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
from dataclasses import replace
import hashlib
import inspect
import json
import math
from pathlib import Path
import platform
import shutil
import sys
import tempfile
from typing import Any, Callable
from uuid import uuid4
import xml.etree.ElementTree as ET

import mujoco
import numpy as np
from PIL import Image

from core.bodybase import BodyBase
from core.worldbase import WorldBase

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL_PATH = ROOT / "robot" / "rail_carriage.xml"
DEFAULT_ARTIFACTS_DIR = ROOT / "artifacts" / "day1"
CONFIG_PATH = ROOT / "configs" / "embody_config.json"
# Compatibility view for existing Day 1 callers; not a second configuration.
_default_body, _default_world = BodyBase.from_json(), WorldBase.from_json()
CONFIG = {"robot": {"mass_kg": _default_body.mass_kg, "max_actuator_force_n": _default_body.max_force_n,
                    "initial_velocity_mps": _default_world.initial_velocity_ms},
          "environment": {"initial_position_m": _default_world.initial_position_x_m,
                          "obstacle_position_m": _default_world.wall_position_x_m,
                          "minimum_clearance_m": _default_world.minimum_clearance_m,
                          "timestep_s": _default_world.simulation_timestep_s,
                          "duration_s": _default_world.simulation_duration_s,
                          "gravity_mps2": list(_default_world.gravity_ms2)}}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_hashes(model_path: Path) -> dict[str, str]:
    paths = [model_path, ROOT / "requirements.txt", ROOT / "pytest.ini"]
    paths += sorted((ROOT / "configs").glob("*.json"))
    paths += sorted((ROOT / "core").rglob("*.py"))
    paths += sorted((ROOT / "tests").glob("test_*.py"))
    paths += sorted((ROOT / "robot").glob("*.py"))
    return {str(p.relative_to(ROOT) if p.is_relative_to(ROOT) else p): sha256(p) for p in paths}


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _contact_details(model: mujoco.MjModel, data: mujoco.MjData) -> list[dict[str, Any]]:
    details = []
    for idx in range(data.ncon):
        contact = data.contact[idx]
        force = np.zeros(6)
        mujoco.mj_contactForce(model, data, idx, force)
        names = [mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, int(g))
                 for g in (contact.geom1, contact.geom2)]
        details.append({"geom_ids": [int(contact.geom1), int(contact.geom2)],
                        "geom_1": names[0], "geom_2": names[1],
                        "dist": float(contact.dist), "normal_force_n": float(force[0]),
                        "involves_wall": "wall" in names})
    return details


def collision_surfaces(model: mujoco.MjModel, data: mujoco.MjData) -> dict[str, float]:
    """Signed axial surface gap; exact for this model's aligned, overlapping boxes."""
    bumper, wall = model.geom("front_bumper").id, model.geom("wall").id
    bumper_extent = float(np.abs(data.geom_xmat[bumper].reshape(3, 3)[0]) @ model.geom_size[bumper])
    wall_extent = float(np.abs(data.geom_xmat[wall].reshape(3, 3)[0]) @ model.geom_size[wall])
    front = float(data.geom_xpos[bumper, 0]) + bumper_extent
    near = float(data.geom_xpos[wall, 0]) - wall_extent
    return {"bumper_front_x": front, "wall_near_x": near, "wall_clearance": near - front}


def compile_context_model(model_path: str | Path, bodybase: BodyBase,
                          worldbase: WorldBase) -> tuple[mujoco.MjModel, str]:
    """Apply authoritative context to a fresh MJCF tree, then compile real physics."""
    if abs(worldbase.initial_velocity_ms) > bodybase.max_velocity_ms + 1e-12:
        raise ValueError("Initial speed exceeds BODYBASE's nominal initial-speed envelope")
    root = ET.parse(model_path).getroot()
    bodybase.apply_to_xml(root)
    worldbase.apply_to_xml(root)
    xml = ET.tostring(root, encoding="unicode")
    model = mujoco.MjModel.from_xml_string(xml)
    if (model.nq, model.nv, model.njnt, model.nu) != (1, 1, 1, 1):
        raise ValueError("This foundation requires exactly one joint, DOF and actuator")
    data = mujoco.MjData(model)
    data.qpos[0] = worldbase.initial_position_x_m
    mujoco.mj_forward(model, data)
    if collision_surfaces(model, data)["wall_clearance"] <= 0 or data.ncon:
        raise ValueError("Initial geometry must have positive wall clearance and no unintended contacts")
    bumper, wall = model.geom("front_bumper").id, model.geom("wall").id
    for axis in (1, 2):
        if abs(data.geom_xpos[bumper, axis] - data.geom_xpos[wall, axis]) >= model.geom_size[bumper, axis] + model.geom_size[wall, axis]:
            raise ValueError("Wall and bumper must overlap in y/z for this one-axis clearance model")
    return model, xml


def _capture(renderer: mujoco.Renderer, model: mujoco.MjModel, data: mujoco.MjData,
             sample: dict[str, Any], stage: Path) -> dict[str, Any]:
    renderer.update_scene(data, camera="demo_camera")
    pixels = renderer.render().copy()
    if pixels.shape != (768, 1024, 3) or float(pixels.std()) < 5:
        raise RuntimeError("Native MuJoCo render is empty, uniform or has incorrect dimensions")
    # A native segmentation pass verifies that the required geoms are visible,
    # rather than treating PNG creation or pixel variation as scene verification.
    renderer.enable_segmentation_rendering()
    try:
        segmentation = renderer.render()
        counts = {}
        for name in ("carriage_box", "front_bumper", "rail_track", "wall"):
            counts[name] = int(np.count_nonzero(
                (segmentation[:, :, 0] == model.geom(name).id)
                & (segmentation[:, :, 1] == int(mujoco.mjtObj.mjOBJ_GEOM))))
        if min(counts.values()) == 0:
            raise RuntimeError(f"Required scene geometry is not visible: {counts}")
    finally:
        renderer.disable_segmentation_rendering()
    relative = Path("render_frames") / f"frame_{sample['step']:04d}.png"
    path = stage / relative
    path.parent.mkdir(exist_ok=True)
    Image.fromarray(pixels).save(path)
    return {"path": str(relative), "step": sample["step"], "time": float(data.time),
            "position": float(data.qpos[0]), "velocity": float(data.qvel[0]),
            "sha256": sha256(path), "dimensions": [1024, 768],
            "pixel_std": float(pixels.std()), "visible_geom_pixels": counts,
            "bumper_front_x": sample["bumper_front_x"],
            "control": sample["control"], "wall_collision": sample["wall_collision"],
            "wall_clearance": sample["wall_clearance"]}


def run_simulation(
    model_path: str | Path = DEFAULT_MODEL_PATH,
    duration: float | None = None,
    dt: float | None = None,
    initial_velocity: float | None = None,
    save_telemetry: bool = True,
    save_render: bool = True,
    artifacts_dir: str | Path = DEFAULT_ARTIFACTS_DIR,
    initial_position: float | None = None,
    control: float = 0.0,
    controller: Callable[[mujoco.MjModel, mujoco.MjData], None] | None = None,
    render_interval_steps: int | None = None,
    bodybase: BodyBase | None = None,
    worldbase: WorldBase | None = None,
) -> dict[str, Any]:
    explicit_context = bodybase is not None or worldbase is not None
    bodybase = bodybase if bodybase is not None else BodyBase.from_json()
    worldbase = worldbase if worldbase is not None else WorldBase.from_json()
    if not isinstance(bodybase, BodyBase) or not isinstance(worldbase, WorldBase):
        raise ValueError("Pass validated BodyBase and WorldBase instances")
    overrides = {name: value for name, value in {"simulation_duration_s": duration, "simulation_timestep_s": dt,
                                               "initial_velocity_ms": initial_velocity, "initial_position_x_m": initial_position}.items()
                 if value is not None}
    worldbase = replace(worldbase, **overrides)
    duration, dt = worldbase.simulation_duration_s, worldbase.simulation_timestep_s
    initial_velocity, initial_position = worldbase.initial_velocity_ms, worldbase.initial_position_x_m
    if controller is not None and control != 0:
        raise ValueError("Choose either a controller or a constant control command")
    if render_interval_steps is not None and (isinstance(render_interval_steps, bool)
                                              or not isinstance(render_interval_steps, int)
                                              or render_interval_steps <= 0):
        raise ValueError("render_interval_steps must be a positive integer")
    for name, value in {"duration": duration, "dt": dt, "initial_velocity": initial_velocity,
                        "initial_position": initial_position, "control": control}.items():
        if not math.isfinite(value):
            raise ValueError(f"{name} must be finite")
    if dt <= 0 or duration < 0:
        raise ValueError("dt must be positive and duration nonnegative")
    steps = round(duration / dt)
    if not math.isclose(steps * dt, duration, rel_tol=0, abs_tol=1e-10):
        raise ValueError("duration must be an integer multiple of dt")
    model_path = Path(model_path).resolve()
    model, effective_xml = compile_context_model(model_path, bodybase, worldbase)
    data = mujoco.MjData(model)
    data.qpos[model.joint("x_slide").qposadr[0]] = initial_position
    data.qvel[model.joint("x_slide").dofadr[0]] = initial_velocity
    data.ctrl[model.actuator("x_motor").id] = control
    telemetry: list[dict[str, Any]] = []
    frames: list[dict[str, Any]] = []
    output = Path(artifacts_dir).resolve()
    if (controller is not None or explicit_context) and (save_telemetry or save_render) and output == DEFAULT_ARTIFACTS_DIR.resolve():
        raise ValueError("Controller runs require a separate artifacts_dir to preserve Day 1 evidence")
    metadata = {
        "schema_version": 1, "run_id": str(uuid4()),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "python_version": sys.version, "platform": platform.platform(),
        "mujoco_version": mujoco.__version__, "numpy_version": np.__version__,
        "source_sha256": source_hashes(model_path), "model_path": str(model_path),
        "effective_mjcf_sha256": hashlib.sha256(effective_xml.encode()).hexdigest(),
        "context": {"bodybase": bodybase.to_dict(), "worldbase": worldbase.to_dict()},
        "safety_policy": "stop_before_wall" if explicit_context else "day2_compatibility",
        "configuration": {"duration_s": duration, "timestep_s": dt, "steps": steps,
                          "initial_position_m": initial_position, "initial_velocity_mps": initial_velocity,
                          "control_input_n": control, "gravity_mps2": model.opt.gravity.tolist(),
                          "desired_future_clearance_m": worldbase.minimum_clearance_m},
        "model": {"carriage_mass_kg": float(model.body("carriage").mass[0]),
                  "ctrlrange": model.actuator_ctrlrange[0].tolist(),
                  "scalar_forcerange_n": model.actuator_forcerange[0].tolist(),
                  "gear": float(model.actuator_gear[0, 0]),
                  "rail_size": model.geom("rail_track").size.tolist(),
                  "wall_center_m": model.body("obstacle").pos.tolist(),
                  "wall_half_size_m": model.geom("wall").size.tolist()},
        "geometry_convention": "wall_position_x_m is the wall center; clearance is the signed wall-near-face minus bumper-front surface gap derived from effective geometry; negative means penetration",
        "sampling": "Initial state and every completed step; mj_forward refreshes derived state before sampling and rendering",
        "rendering": {"status": "native" if save_render else "not_requested",
                      "backend": "mujoco.Renderer", "camera": "demo_camera", "frames": frames,
                      "interval_steps": render_interval_steps},
        "units": {"time": "s", "position": "m", "velocity": "m/s", "acceleration": "m/s^2",
                  "control": "N (direct motor, gear=1)", "scalar_actuator_force": "N",
                  "generalized_actuator_force": "N", "wall_clearance": "m"},
    }
    if controller is not None:
        controller_path = Path(inspect.getsourcefile(controller)).resolve()
        metadata["controller"] = {"name": f"{controller.__module__}.{controller.__qualname__}",
                                  "source_path": str(controller_path.relative_to(ROOT)
                                                     if controller_path.is_relative_to(ROOT) else controller_path),
                                  "source_sha256": sha256(controller_path),
                                  "function_sha256": hashlib.sha256(inspect.getsource(controller).encode()).hexdigest()}
        metadata["configuration"]["control_mode"] = "controller"
    with ExitStack() as stack:
        stage = None
        if save_telemetry or save_render:
            output.parent.mkdir(parents=True, exist_ok=True)
            temp = stack.enter_context(tempfile.TemporaryDirectory(prefix=".simulation-", dir=output.parent))
            stage = Path(temp) / "run"
            stage.mkdir()
        renderer = None
        if save_render:
            # Fail visibly on native renderer errors. There is no drawing fallback.
            renderer = stack.enter_context(mujoco.Renderer(model, height=768, width=1024))
        frame_steps = {0, round(steps / 3), round(2 * steps / 3), steps}
        if render_interval_steps is not None:
            frame_steps.update(range(0, steps + 1, render_interval_steps))
        braking_seen = wall_contact_seen = False
        for step in range(steps + 1):
            # mj_step integrates qpos/qvel, but derived contacts and geom transforms
            # otherwise describe the preceding state. Refresh without integrating.
            mujoco.mj_forward(model, data)
            if controller is not None:
                controller(model, data)
                if not np.isfinite(data.ctrl).all():
                    raise ValueError("Controller produced a nonfinite actuator command")
                mujoco.mj_forward(model, data)
            contacts = _contact_details(model, data)
            sample = {"step": step, "time": float(data.time), "position": float(data.qpos[0]),
                      "velocity": float(data.qvel[0]), "acceleration": float(data.qacc[0]),
                      "control": float(data.ctrl[0]),
                      "scalar_actuator_force": float(data.actuator_force[0]),
                      "generalized_actuator_force": float(data.qfrc_actuator[0]),
                      "carriage_center_x": float(data.xpos[model.body("carriage").id, 0]),
                      **collision_surfaces(model, data),
                      "wall_collision": any(c["involves_wall"] for c in contacts),
                      "contact_count": len(contacts), "contacts": contacts}
            telemetry.append(sample)
            braking_now = sample["velocity"] > 0 and sample["generalized_actuator_force"] < 0
            event_frame = controller is not None and ((braking_now and not braking_seen)
                                                      or (sample["wall_collision"] and not wall_contact_seen))
            if renderer is not None and (step in frame_steps or event_frame):
                frames.append(_capture(renderer, model, data, sample, stage))
            braking_seen |= braking_now
            wall_contact_seen |= sample["wall_collision"]
            if step < steps:
                mujoco.mj_step(model, data)
        metadata["actual_steps"] = steps
        metadata["actual_samples"] = len(telemetry)
        metadata["final_simulation_time_s"] = float(data.time)
        metadata["warnings"] = {mujoco.mjtWarning(i).name: int(w.number)
                                for i, w in enumerate(data.warning) if w.number}
        if frames:
            # Representative image is the actual t=1 s frame for the default run.
            representative = frames[min(1, len(frames) - 1)]
            shutil.copyfile(stage / representative["path"], stage / "render.png")
            metadata["rendering"]["representative_frame"] = representative["path"]
        if save_telemetry:
            write_json(stage / "telemetry.json", {"metadata": metadata, "samples": telemetry})
        if stage is not None:
            (stage / "effective_model.xml").write_text(effective_xml)
            write_json(stage / "manifest.json", metadata)
            # Publish only after the complete run succeeds. Preserve every prior
            # output (including unrelated files) in an archive rather than mixing it.
            if output.exists():
                if any(output.iterdir()):
                    archive = output.parent / "archive"
                    archive.mkdir(exist_ok=True)
                    output.rename(archive / f"{output.name}-{metadata['run_id']}")
                else:
                    output.rmdir()
            stage.rename(output)
    return {"model": model, "data": data, "telemetry": telemetry, "metadata": metadata,
            "effective_model_xml": effective_xml, "bodybase": bodybase, "worldbase": worldbase,
            "position_history": [s["position"] for s in telemetry],
            "velocity_history": [s["velocity"] for s in telemetry],
            "time_history": [s["time"] for s in telemetry],
            "contact_history": [s["contacts"] for s in telemetry],
            "render_path": output / "render.png" if frames else None,
            "render_frames": [output / f["path"] for f in frames], "artifacts_dir": output}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts-dir", type=Path, default=DEFAULT_ARTIFACTS_DIR)
    parser.add_argument("--no-render", action="store_true", help="Explicit physics-only run; no image claims")
    parser.add_argument("--control", type=float, default=0, help="Constant force command in N")
    args = parser.parse_args()
    result = run_simulation(artifacts_dir=args.artifacts_dir, save_render=not args.no_render, control=args.control)
    print(json.dumps({"artifacts_dir": str(result["artifacts_dir"]),
                      "steps": result["metadata"]["actual_steps"], "samples": len(result["telemetry"]),
                      "final_state": result["telemetry"][-1],
                      "rendering": result["metadata"]["rendering"]["status"]}, indent=2))


if __name__ == "__main__":
    main()
