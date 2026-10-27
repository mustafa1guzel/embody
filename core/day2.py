"""Reproduce the intentionally unsafe braking baseline without changing Day 1."""
from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

from core.diagnostics import failure_diagnostics, independently_verify_safety, physical_parameters
from core.simulation import DEFAULT_MODEL_PATH, ROOT, run_simulation, sha256, source_hashes, write_json
from core.verification import compare_runs
from robot.controller import faulty_braking_controller

DEFAULT_OUTPUT = ROOT / "artifacts" / "day2" / "baseline"


def file_inventory(directory: Path) -> dict[str, str]:
    return {str(p.relative_to(directory)): sha256(p) for p in sorted(directory.rglob("*")) if p.is_file()}


def diagnose_and_save(run: dict[str, Any]) -> dict[str, Any]:
    independent = independently_verify_safety(run)
    diagnostics = failure_diagnostics(run, independent)
    write_json(run["artifacts_dir"] / "independent_safety_trace.json", independent)
    write_json(run["artifacts_dir"] / "diagnostics.json", diagnostics)
    return diagnostics


def write_replay(run: dict[str, Any], diagnostics: dict[str, Any]) -> dict[str, Any]:
    """A timed viewer of original native PNGs; no synthetic frames or physics replay."""
    frames = run["metadata"]["rendering"]["frames"]
    if not frames:
        raise ValueError("A replay requires native rendered frames")
    events = {"approach": 0, "braking": diagnostics["braking_initiation"]["step"],
              "contact": diagnostics["first_wall_contact"]["step"]}
    indices = {name: next(i for i, frame in enumerate(frames) if frame["step"] == step)
               for name, step in events.items()}
    encoder = {"ffmpeg": shutil.which("ffmpeg"),
               "imageio_ffmpeg": importlib.util.find_spec("imageio_ffmpeg") is not None,
               "pyav": importlib.util.find_spec("av") is not None}
    replay = {"kind": "Native MuJoCo PNG sequence with original simulation timestamps",
              "duration_s": run["metadata"]["final_simulation_time_s"],
              "events": events, "event_frame_indices": indices, "frames": frames,
              "mp4": {"status": "NOT_GENERATED", "available_encoders": encoder,
                      "reason": "No MP4 encoder is installed in the verified environment; native frames and a timed HTML replay are provided without downloads."}}
    output = run["artifacts_dir"]
    write_json(output / "replay_timeline.json", replay)
    # Inline timeline makes file:// playback work without fetching local JSON.
    timeline = json.dumps(replay).replace("</", "<\\/")
    html = '''<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>EMBODY Day 2 — physical braking failure</title>
<style>body{margin:24px auto;max-width:1060px;padding:0 16px;font:16px system-ui;background:#171b23;color:#f1f3f5}img{width:100%;height:auto}button{padding:8px 14px;margin:6px 8px 6px 0}input{width:100%}output{display:block;font-variant-numeric:tabular-nums;margin:10px 0}p{line-height:1.5}</style>
<h1>EMBODY Day 2: braking starts too late</h1>
<p>Original native MuJoCo frames. Software and simulation complete; the safety task fails because the carriage contacts the wall.</p>
<img id="scene" alt="Native MuJoCo carriage, rail and wall">
<output id="state"></output>
<button id="play">Play</button><button id="restart">Restart</button>
<button data-event="approach">Approach</button><button data-event="braking">Brake onset</button><button data-event="contact">First contact</button>
<input id="scrub" aria-label="Simulation time" type="range" min="0" step="0.005">
<p>Frames retain their simulator timestamps, including the first contact state. Playback uses the latest captured state at each time. MP4 was not generated because no encoder was installed.</p>
<script>
const replay = TIMELINE;
const frames=replay.frames, scene=document.getElementById('scene'), state=document.getElementById('state'), scrub=document.getElementById('scrub'), play=document.getElementById('play');
let playing=false, simulationTime=0, start=0, loadedIndex=-1;
scrub.max=replay.duration_s;
const images=frames.map(f=>{const image=new Image(); image.src=f.path; return image});
function show(time){simulationTime=Math.max(0,Math.min(time,replay.duration_s));let i=0;while(i+1<frames.length && frames[i+1].time<=simulationTime+1e-12)i++;const f=frames[i];if(i!==loadedIndex){scene.src=f.path;scene.dataset.step=f.step;loadedIndex=i;}scrub.value=simulationTime;state.textContent=`t=${f.time.toFixed(3)} s | x=${f.position.toFixed(4)} m | v=${f.velocity.toFixed(3)} m/s | clearance=${f.wall_clearance.toFixed(4)} m | command=${f.control.toFixed(1)} N | wall contact: ${f.wall_collision?'YES':'no'}`;}
function pause(){playing=false;play.textContent='Play';}
function tick(now){if(!playing)return;show((now-start)/1000);if(simulationTime>=replay.duration_s){pause();return;}requestAnimationFrame(tick);}
play.onclick=()=>{if(playing){pause();return;}if(simulationTime>=replay.duration_s)show(0);playing=true;play.textContent='Pause';start=performance.now()-simulationTime*1000;requestAnimationFrame(tick);};
document.getElementById('restart').onclick=()=>{pause();show(0);};
scrub.oninput=()=>{pause();show(Number(scrub.value));};
document.querySelectorAll('[data-event]').forEach(button=>button.onclick=()=>{pause();show(frames[replay.event_frame_indices[button.dataset.event]].time);});
show(0);
</script></html>'''.replace("TIMELINE", timeline)
    (output / "replay.html").write_text(html)
    return replay


def run_experiment(output: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    """Three primary runs plus independent verification executions for each run."""
    output = Path(output)
    day1_dir = ROOT / "artifacts" / "day1"
    preserved = file_inventory(day1_dir)
    historic = json.loads((day1_dir / "telemetry.json").read_text())
    baseline = run_simulation(controller=faulty_braking_controller, artifacts_dir=output, render_interval_steps=5)
    runs = [baseline]
    diagnostics = [diagnose_and_save(baseline)]
    for number in (2, 3):
        run = run_simulation(controller=faulty_braking_controller, save_render=False,
                             artifacts_dir=output / "reproducibility" / f"run_{number}")
        runs.append(run)
        diagnostics.append(diagnose_and_save(run))
    comparison = compare_runs(runs)
    uncontrolled = run_simulation(save_render=False, save_telemetry=False)
    replay = write_replay(baseline, diagnostics[0])
    checks = {
        "three_runs_numerically_reproducible": comparison["pass"],
        "full_telemetry_exactly_equal": all(r["telemetry"] == baseline["telemetry"] for r in runs),
        "identical_configuration": all(r["metadata"]["configuration"] == baseline["metadata"]["configuration"] for r in runs),
        "identical_controller_source": all(r["metadata"]["controller"] == baseline["metadata"]["controller"] for r in runs),
        "identical_physical_parameters": all(physical_parameters(r["model"]) == physical_parameters(baseline["model"]) for r in runs),
        "same_braking_onset": all(d["braking_initiation"] == diagnostics[0]["braking_initiation"] for d in diagnostics),
        "same_first_contact": all(d["first_wall_contact"] == diagnostics[0]["first_wall_contact"] for d in diagnostics),
        "expected_failure_reproduced_in_all_runs": all(d["expected_contact_failure_reproduced"] for d in diagnostics),
        "independent_verifications_complete": all(d["independent_safety_verification"]["verification_execution"] == "PASS" for d in diagnostics),
        "no_unintended_contacts": all(d["unintended_contact_points"] == 0 for d in diagnostics),
        "day1_artifacts_unchanged": file_inventory(day1_dir) == preserved,
        "day1_zero_force_trajectory_unchanged": uncontrolled["telemetry"] == historic["samples"],
        "model_unchanged_from_day1": sha256(DEFAULT_MODEL_PATH) == historic["metadata"]["source_sha256"]["robot/rail_carriage.xml"],
        "day1_test_file_unchanged": sha256(ROOT / "tests" / "test_physics_foundation.py") == historic["metadata"]["source_sha256"]["tests/test_physics_foundation.py"],
        "sources_current": baseline["metadata"]["source_sha256"] == source_hashes(DEFAULT_MODEL_PATH),
        "native_event_frames_captured": all(step in [f["step"] for f in replay["frames"]] for step in replay["events"].values()),
    }
    evidence = {"created_at_utc": datetime.now(timezone.utc).isoformat(),
                "checks": {name: "PASS" if ok else "FAIL" for name, ok in checks.items()},
                "comparison": comparison, "primary_run_count": len(runs),
                "independent_verification_execution_count": len(diagnostics),
                "runs": [{"run_id": r["metadata"]["run_id"], "controller": r["metadata"]["controller"],
                          "braking_initiation": d["braking_initiation"], "first_wall_contact": d["first_wall_contact"],
                          "minimum_clearance_m": d["minimum_observed_clearance_m"],
                          "final_velocity_mps": d["final_state"]["velocity"],
                          "unintended_contact_points": d["unintended_contact_points"]} for r, d in zip(runs, diagnostics)],
                "day1_preserved_artifact_sha256": preserved,
                "automated_experiment_result": "PASS" if all(checks.values()) else "FAIL",
                "physical_safety_task": diagnostics[0]["physical_safety_task"],
                "visual_review": "Pending direct inspection of native event frames and replay"}
    write_json(output / "reproducibility.json", evidence)
    return {"baseline": baseline, "diagnostics": diagnostics[0], "evidence": evidence, "replay": replay}


def main() -> None:
    command = [sys.executable, "-m", "pytest", "-ra"]
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    output = completed.stdout + completed.stderr
    print(output, end="", flush=True)
    if completed.returncode:
        failed = ROOT / "artifacts" / "failed" / ("day2-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
        failed.mkdir(parents=True, exist_ok=True)
        (failed / "pytest_output.txt").write_text(output)
        raise SystemExit(completed.returncode)
    result = run_experiment()
    (DEFAULT_OUTPUT / "pytest_output.txt").write_text(output)
    write_json(DEFAULT_OUTPUT / "pytest_result.json", {"command": command, "exit_code": completed.returncode})
    print(json.dumps({"day2_automated_experiment": result["evidence"]["automated_experiment_result"],
                      "software_execution": result["diagnostics"]["software_execution"],
                      "physics_simulation": result["diagnostics"]["physics_simulation"],
                      "physical_safety_task": result["diagnostics"]["physical_safety_task"],
                      "braking_time_s": result["diagnostics"]["braking_initiation"]["time"],
                      "contact_time_s": result["diagnostics"]["first_wall_contact"]["time"],
                      "artifacts": str(DEFAULT_OUTPUT)}, indent=2))
    if result["evidence"]["automated_experiment_result"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
