"""Independent checks against compiled MJCF and real MuJoCo execution."""
from __future__ import annotations

import json
from pathlib import Path

import mujoco
import numpy as np
from PIL import Image
import pytest

from core.simulation import CONFIG, DEFAULT_MODEL_PATH, collision_surfaces, run_simulation, sha256


@pytest.fixture
def model():
    return mujoco.MjModel.from_xml_path(str(DEFAULT_MODEL_PATH))


@pytest.fixture(scope="module")
def physics_run(tmp_path_factory):
    return run_simulation(save_render=False, artifacts_dir=tmp_path_factory.mktemp("physics"))


@pytest.fixture(scope="module")
def rendered_run(tmp_path_factory):
    return run_simulation(artifacts_dir=tmp_path_factory.mktemp("native-render"))


def test_model_has_exactly_one_unlimited_x_slide(model):
    assert (model.nq, model.nv, model.njnt, model.nu) == (1, 1, 1, 1)
    assert model.joint("x_slide").type[0] == mujoco.mjtJoint.mjJNT_SLIDE
    np.testing.assert_allclose(model.joint("x_slide").axis, [1, 0, 0], atol=1e-15)
    assert not model.jnt_limited[0]
    np.testing.assert_array_equal(model.dof_damping, 0)
    np.testing.assert_array_equal(model.dof_frictionloss, 0)
    np.testing.assert_array_equal(model.dof_armature, 0)


def test_compiled_mass_and_actuator_configuration(model):
    assert model.body("carriage").mass[0] == pytest.approx(2.0)
    assert sum(model.body_mass) == pytest.approx(2.0)
    assert model.actuator_gear[0, 0] == 1
    np.testing.assert_array_equal(model.actuator_ctrlrange[0], [-4, 4])
    np.testing.assert_array_equal(model.actuator_forcerange[0], [-4, 4])
    assert model.actuator_ctrllimited[0] and model.actuator_forcelimited[0]
    assert model.opt.timestep == pytest.approx(0.005)
    np.testing.assert_array_equal(model.opt.gravity, [0, 0, -9.81])
    assert model.body("carriage").mass[0] == CONFIG["robot"]["mass_kg"]
    assert model.actuator_forcerange[0, 1] == CONFIG["robot"]["max_actuator_force_n"]
    assert model.body("obstacle").pos[0] == CONFIG["environment"]["obstacle_position_m"]
    assert model.opt.timestep == CONFIG["environment"]["timestep_s"]
    np.testing.assert_array_equal(model.opt.gravity, CONFIG["environment"]["gravity_mps2"])


@pytest.mark.parametrize("command, expected_force", [(-40, -4), (-4, -4), (0, 0), (4, 4), (40, 4)])
def test_measured_scalar_joint_force_acceleration_and_velocity(model, command, expected_force):
    data = mujoco.MjData(model)
    data.ctrl[0] = command
    mujoco.mj_forward(model, data)
    assert data.ncon == 0
    assert data.actuator_force[0] == pytest.approx(expected_force)
    assert data.qfrc_actuator[0] == pytest.approx(expected_force)
    assert data.qacc[0] == pytest.approx(expected_force / 2)
    before = float(data.qvel[0])
    mujoco.mj_step(model, data)
    assert (data.qvel[0] - before) / model.opt.timestep == pytest.approx(expected_force / 2, abs=1e-12)
    assert data.qpos[0] == pytest.approx(expected_force / 2 * model.opt.timestep**2)


@pytest.mark.parametrize("limit", ["control", "force"])
@pytest.mark.parametrize("sign", [-1, 1])
def test_each_clipping_mechanism_independently(model, limit, sign):
    # Remove one clamp in this isolated model to prove the other actually works.
    if limit == "control":
        model.actuator_forcelimited[0] = False
    else:
        model.actuator_ctrllimited[0] = False
    data = mujoco.MjData(model)
    data.ctrl[0] = sign * 40
    mujoco.mj_forward(model, data)
    assert data.qfrc_actuator[0] == pytest.approx(sign * 4)
    mujoco.mj_step(model, data)
    assert data.qvel[0] / model.opt.timestep == pytest.approx(sign * 2)


def test_rail_radius_half_length_orientation_and_endpoints(model):
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    rail = model.geom("rail_track").id
    assert model.geom_type[rail] == mujoco.mjtGeom.mjGEOM_CAPSULE
    np.testing.assert_allclose(model.geom_size[rail, :2], [0.03, 1.8], atol=1e-14)
    axis = data.geom_xmat[rail].reshape(3, 3)[:, 2]
    np.testing.assert_allclose(np.abs(axis), [1, 0, 0], atol=1e-14)
    ends = [data.geom_xpos[rail] + s * model.geom_size[rail, 1] * axis for s in [-1, 1]]
    np.testing.assert_allclose(sorted(p[0] for p in ends), [-0.8, 2.8], atol=1e-14)
    for p in ends:
        np.testing.assert_allclose(p[1:], [0, 0.14], atol=1e-14)
    for name in ("rail_track", "rail_base"):
        assert model.geom(name).contype[0] == model.geom(name).conaffinity[0] == 0
    for name in ("carriage_box", "front_bumper", "wall", "floor"):
        assert model.geom(name).contype[0] != 0 and model.geom(name).conaffinity[0] != 0


def test_analytic_free_motion_before_contact(physics_run):
    free = [s for s in physics_run["telemetry"] if s["time"] <= 1.4]
    assert len(free) > 200
    for sample in free:
        assert sample["contact_count"] == 0
        assert sample["position"] == pytest.approx(1.2 * sample["time"], abs=1e-12)
        assert sample["velocity"] == pytest.approx(1.2, abs=1e-12)
        assert sample["generalized_actuator_force"] == 0


def test_initial_state_steps_times_and_nondefault_timestep(physics_run, tmp_path):
    samples = physics_run["telemetry"]
    assert len(samples) == 601
    assert samples[0]["position"] == 0 and samples[0]["velocity"] == 1.2
    assert samples[-1]["time"] == pytest.approx(3, abs=1e-12)
    assert physics_run["data"].time == samples[-1]["time"]
    np.testing.assert_allclose(np.diff([s["time"] for s in samples]), 0.005, atol=1e-15)
    changed = run_simulation(duration=0.1, dt=0.01, initial_position=0.1, initial_velocity=0,
                             control=4, save_render=False, artifacts_dir=tmp_path)
    assert changed["model"].opt.timestep == 0.01
    assert len(changed["telemetry"]) == 11
    assert changed["data"].time == pytest.approx(0.1)
    assert changed["data"].qvel[0] == pytest.approx(0.2)
    assert changed["data"].qpos[0] > 0.1


def test_all_samples_match_independent_runtime_states(model, physics_run):
    data = mujoco.MjData(model)
    data.qvel[0] = 1.2
    for i, s in enumerate(physics_run["telemetry"]):
        mujoco.mj_forward(model, data)
        assert s["time"] == data.time
        assert s["position"] == data.qpos[0]
        assert s["velocity"] == data.qvel[0]
        assert s["generalized_actuator_force"] == data.qfrc_actuator[0]
        assert s["contact_count"] == data.ncon
        assert s["carriage_center_x"] == data.xpos[model.body("carriage").id, 0]
        if i < 600:
            mujoco.mj_step(model, data)
    assert physics_run["metadata"]["warnings"] == {}


def test_clearance_uses_surfaces_not_centers(model, physics_run):
    data = mujoco.MjData(model)
    for x in (0, 1, 1.77, 1.771):
        data.qpos[0] = x
        mujoco.mj_forward(model, data)
        surfaces = collision_surfaces(model, data)
        assert surfaces["bumper_front_x"] == pytest.approx(x + 0.18)
        assert surfaces["wall_near_x"] == pytest.approx(1.95)
        assert surfaces["wall_clearance"] == pytest.approx(1.77 - x, abs=1e-14)
        # MuJoCo's independent geometric distance query agrees with the surface gap.
        distance = mujoco.mj_geomDistance(model, data, model.geom("front_bumper").id,
                                         model.geom("wall").id, 10, None)
        assert distance == pytest.approx(surfaces["wall_clearance"], abs=1e-12)
    for s in physics_run["telemetry"]:
        assert s["wall_clearance"] == pytest.approx(1.77 - s["position"], abs=1e-14)


def test_real_wall_contacts_and_no_rail_contacts(physics_run):
    contact_samples = [s for s in physics_run["telemetry"] if s["wall_collision"]]
    assert contact_samples
    assert contact_samples[0]["time"] == pytest.approx(1.475, abs=1e-12)
    assert min(s["wall_clearance"] for s in contact_samples) <= 1e-12
    for s in physics_run["telemetry"]:
        for c in s["contacts"]:
            assert {c["geom_1"], c["geom_2"]} == {"front_bumper", "wall"}
            assert c["involves_wall"]
            assert c["dist"] == pytest.approx(s["wall_clearance"], abs=1e-12)
        assert s["wall_collision"] == bool(s["contacts"])
    assert max(c["normal_force_n"] for s in contact_samples for c in s["contacts"]) > 0
    # Soft contact is not a rigid nonpenetration guarantee; bound observed overlap.
    assert min(s["wall_clearance"] for s in physics_run["telemetry"]) > -0.01
    assert physics_run["telemetry"][-1]["velocity"] < 0


def test_saved_telemetry_metadata_and_hashes(physics_run):
    payload = json.loads((physics_run["artifacts_dir"] / "telemetry.json").read_text())
    assert payload["samples"] == physics_run["telemetry"]
    assert payload["metadata"] == physics_run["metadata"]
    assert payload["metadata"]["actual_steps"] == 600
    assert payload["metadata"]["actual_samples"] == 601
    for path, digest in payload["metadata"]["source_sha256"].items():
        assert sha256(Path(__file__).resolve().parents[1] / path) == digest


@pytest.mark.rendering
def test_native_frame_content_timestamps_and_trajectory(rendered_run, physics_run):
    assert rendered_run["telemetry"] == physics_run["telemetry"]
    assert rendered_run["data"].time == pytest.approx(3, abs=1e-12)
    frames = rendered_run["metadata"]["rendering"]["frames"]
    assert [f["step"] for f in frames] == [0, 200, 400, 600]
    for frame, expected_time, path in zip(frames, [0, 1, 2, 3], rendered_run["render_frames"]):
        sample = rendered_run["telemetry"][frame["step"]]
        assert frame["time"] == sample["time"] == pytest.approx(expected_time, abs=1e-12)
        assert frame["position"] == sample["position"]
        assert frame["velocity"] == sample["velocity"]
        assert sha256(path) == frame["sha256"]
        with Image.open(path) as image:
            assert image.format == "PNG"
            pixels = np.asarray(image)
            assert pixels.shape == (768, 1024, 3)
            assert pixels.std() > 5
        assert min(frame["visible_geom_pixels"].values()) > 20
    assert sha256(rendered_run["render_path"]) == frames[1]["sha256"]
    assert frames[0]["sha256"] != frames[1]["sha256"]


@pytest.mark.rendering
def test_saved_frames_equal_independent_native_render_at_recorded_state(model, rendered_run):
    data = mujoco.MjData(model)
    with mujoco.Renderer(model, height=768, width=1024) as renderer:
        for frame, path in zip(rendered_run["metadata"]["rendering"]["frames"], rendered_run["render_frames"]):
            sample = rendered_run["telemetry"][frame["step"]]
            data.time = sample["time"]
            data.qpos[0] = sample["position"]
            data.qvel[0] = sample["velocity"]
            mujoco.mj_forward(model, data)
            renderer.update_scene(data, camera="demo_camera")
            with Image.open(path) as image:
                np.testing.assert_array_equal(np.asarray(image), renderer.render())


def test_three_fresh_runs_are_numerically_identical(tmp_path):
    runs = [run_simulation(save_render=False, artifacts_dir=tmp_path / str(i)) for i in range(3)]
    assert len({r["metadata"]["run_id"] for r in runs}) == 3
    for run in runs[1:]:
        assert run["model"] is not runs[0]["model"] and run["data"] is not runs[0]["data"]
        assert run["telemetry"] == runs[0]["telemetry"]


def test_independent_verification_probes_and_comparison_detect_changed_physics(tmp_path):
    from core.verification import compare_runs, measure_physics

    probes = measure_physics()
    assert probes["free_motion"]["max_position_error_m"] < 1e-12
    assert probes["free_motion"]["contact_count"] == 0
    assert [p["generalized_actuator_force_n"] for p in probes["actuator_probes"]] == [-4, -4, 0, 4, 4]
    for probe in probes["actuator_probes"]:
        assert probe["measured_acceleration_from_velocity_mps2"] == pytest.approx(probe["generalized_actuator_force_n"] / 2)
    baseline = run_simulation(duration=0.1, save_render=False, artifacts_dir=tmp_path / "baseline")
    changed = run_simulation(duration=0.1, control=0.1, save_render=False, artifacts_dir=tmp_path / "changed")
    assert compare_runs([baseline, baseline])["pass"]
    assert not compare_runs([baseline, changed])["pass"]


def test_replacing_output_preserves_previous_files_without_stale_frames(tmp_path):
    output = tmp_path / "run"
    output.mkdir()
    (output / "unrelated.txt").write_text("preserve me")
    (output / "render.png").write_bytes(b"old output")
    result = run_simulation(duration=0, save_render=False, artifacts_dir=output)
    assert not (output / "render.png").exists()
    archives = list((tmp_path / "archive").iterdir())
    assert len(archives) == 1
    assert (archives[0] / "unrelated.txt").read_text() == "preserve me"
    assert (archives[0] / "render.png").read_bytes() == b"old output"
    assert len(result["telemetry"]) == 1
    assert result["metadata"]["rendering"]["status"] == "not_requested"


@pytest.mark.parametrize("kwargs", [{"dt": 0}, {"dt": -1}, {"duration": -1},
                                   {"duration": 0.012}, {"control": float("nan")},
                                   {"initial_velocity": float("inf")}])
def test_invalid_experiments_are_rejected(kwargs, tmp_path):
    with pytest.raises(ValueError):
        run_simulation(save_render=False, artifacts_dir=tmp_path, **kwargs)
