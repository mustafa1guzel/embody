# EMBODY — Build physical intelligence.

Design, inspect controllers, replay simulations and debug physical failures in a
local engineering workspace. **v0.8 adds registered rail and rover/ramp models,
bounded robot import/export and model-specific engineering views.** The rover
implementation is awaiting separately approved native verification; no measured
rover performance is claimed. Existing advanced tools remain available.

![Product Alpha: real saved carriage geometry and numerical inspector](docs/assets/product/alpha-workspace.png)

**Create → Design → Program → Simulate → Debug → Verify → Iterate**

Open a real example, inspect its physical structure and controller, scrub saved
native motion, understand a failed requirement, and prepare a bounded change.
Measurements keep their original input/source identity. A proposed improvement
stays **verification pending**; review never silently runs physics or applies it.

## Quickstart

Verified locally on macOS Apple Silicon with Python 3.12 and the existing Node
and pinned dependencies. From a reviewed environment:

```sh
npm --prefix frontend run build
.venv/bin/python -m tools.start --check
.venv/bin/python -m tools.start
```

Open http://127.0.0.1:8765. No API key or account is needed. The launcher never
installs dependencies, calls models, launches VMs or runs physics. If setup is
incomplete, see [Quickstart](docs/QUICKSTART.md) and the declared
[Python dependencies](requirements.txt) / [frontend lockfile](frontend/package-lock.json).
Installations remain an explicit operator decision, not a startup side effect.

## Start with a supported example

| Entry | What actually works | Execution scope |
|---|---|---|
| Rail braking | Saved compiled 3D geometry, read-only controller, sample-linked playback, numerical drafts, physical debugger, comparison and adaptive guidance | New execution preparation only; separate explicit approval required |
| Rover / inclined surface | Actual typed nine-part assembly, editable bounded configuration, registered PD controller, requirements, compilation and exact simulation preparation | Native implementation present; current-source qualification NOT RUN |
| Controller debugging | Nine genuine public original/repair recordings in the existing Physics Regression Explorer | Historical source inspection and saved-data comparison only |
| Mechanical & circuit studio | Existing typed geometry, environment, SHAPEBASE, CIRCUITBASE and construction review | Independent mechanical project context; no new controller or native model admission |

**New Project** selects Rail braking or Rover / inclined surface. Rover and imported
rail/rover declarations use versioned numeric model projects with exact-head saves;
the earlier rail-plan store remains readable. These are engineering configurations,
not applied mechanical heads. Export/re-import preserves supported numbers and
registered identities without evidence, execution authority or private data.
[Toolkit guide](docs/MULTI_MODEL_TOOLKIT.md) · [configuration examples](examples/robot-projects/README.md).

## Debug from physical evidence

![Physical Debugger with a genuine measured clearance failure](docs/assets/product/alpha-debugger.png)

The debugger reads the actual measurement and its frozen requirement. It separates
**observation, interpretation, analytical hypothesis and recommended action**.
For the selected recorded case, a carriage stopped without wall contact but retained
only 3 mm instead of the required 50 mm: a 47 mm clearance deficit. Replay PASS
means the failure reproduced, not that the physical requirement passed.

Supported checks cover clearance, final speed, contact episodes, peak force and
sampled settling. Missing evidence stays unavailable. An analytical stopping
prediction is never relabelled as a simulator result. Parameter edits remain
local drafts until explicitly saved as a numerical plan; they never change the
original evidence or authoritative mechanical head.

## Genuine native adaptive demonstration · v0.6.2 preserved

| Initial clearance | Minimum measured clearance | Physical verdict |
|---:|---:|---|
| 1.440 m | 0.003 m | FAIL |
| 1.465 m | 0.028 m | FAIL |
| 1.490 m | 0.053 m | PASS |
| 1.540 m | 0.103 m | PASS |

Four distinct cases, eight native MuJoCo rollouts and 4,800 integration steps.
All fresh replays and independent saved-sample verifications passed; every case
finished at zero speed without wall contact. The deterministic engine selected
1.465 m from measured evidence, reducing the observed local interval from
**50 mm to 25 mm (50%)**. This is a sampled transition interval, not an exact
safety boundary or measured superiority over uniform sampling. **1.4775 m
remains unapproved and unexecuted.** No new simulation runs in v0.7 or this v0.8 implementation.

[Demonstration](docs/ADAPTIVE_PHYSICAL_DEBUGGING.md) ·
[Portable evidence and readback](examples/adaptive-rail-study/README.md) ·
[Verification scope](docs/VERIFICATION.md)

The new server routes change the source-bound native identity. Those measurements
remain verified saved evidence for their original source, not validation of this
modified application. Consumed approvals and old certificates grant no authority.

## Program and simulation

Program reuses Monaco to display the actual registered controller read-only. Rail
uses the unchanged velocity brake; rover uses bounded target PD with native wheel-axis
direction. Authority is configured through validated numeric inputs. This
is not arbitrary Python editing/execution, a terminal or controller installation.

Simulate links real saved sample timestamps, compiled geometry and measurement
charts. A request preview validates the existing exact native schema, unchanged
requirements and a model-specific primary/fresh replay budget (rail 600+600; rover 200+200). **The Product Alpha route cannot dispatch,
approve, retry or apply a simulation.** Actual new execution needs a separate
valid source-bound scope. No live AI research is claimed; contextual assistance
is deterministic and does not make provider calls.

## Technical depth remains available

Advanced Analysis retains [Parameter Sweep Lab](docs/PARAMETER_SWEEP_LAB.md),
[Physics Regression Explorer](docs/VERIFICATION.md#physics-regression-explorer),
[Experiment Designer](docs/AI_EXPERIMENT_DESIGNER.md),
[Research Workspace](docs/RESEARCH_WORKSPACE.md), adaptive selection, sensitivity,
controller comparison, evidence graphs, reports and reproducibility.
Returning preserves the rail project, draft and selected evidence. The legacy
workspace retains its own independent project context and pauses hidden playback.

BODYBASE/WORLDBASE supply physical inputs; SHAPEBASE derives bounded geometry and
explicit proxies; CIRCUITBASE checks supported static electrical interfaces.
[Architecture](docs/ARCHITECTURE.md) maps the reused code and trust boundaries.

## Verification and limitations

Run the supported guarded non-native checks with existing dependencies:

```sh
python -B -m tools.research_release_verify
python -B -m pytest -ra -p no:cacheprovider -p tools.non_native_guards tests/test_product_alpha.py tests/test_robot_toolkit.py
npm --prefix frontend test
```

The serial runner includes typecheck/build and excludes live integration/VM tests.
The full historical Python suite needs private archives and includes native
fixtures; it is not the no-execution Product Alpha acceptance command.

[Limitations](docs/LIMITATIONS.md): finite rigid-proxy physics is not hardware,
materials or manufacturing certification. Circuit connectivity is not SPICE or a
coupled powertrain. No arbitrary robot/XML admission, cloud collaboration, automatic
application or unrestricted AI is added. The fixed rover reference is implemented
but requires separate current-source native qualification. Public package
verification establishes integrity/arithmetic, not independently signed origin.
Private runtime folders, approvals, credentials and certificates are not published.

## Roadmap and license

[v0.8 Robotics Developer Toolkit](docs/PRODUCT_ROADMAP.md) implements bounded model/import/controller contracts; native qualification is pending. v0.9 targets separately authorized
intelligent engineering; v1.0 targets a coherent installable bounded product.
No customer-acquisition or commercialization work is part of these milestones.
The repository currently has no license grant file; licensing remains the owner's
decision. No commit, tag, push or release is created automatically.
