# EMBODY — Cursor for the Physical World

A local engineering workspace for inspecting robot context, reviewing configuration
changes, running supported MuJoCo verification, and understanding measured failures.

**v1.0.0-rc1 is a bounded local release-candidate workstream. Live GPT qualification
remains pending.** The default workbench uses deterministic engineering tools;
it does not present them as model reasoning. No API key is needed for the local loop.

## The local debugging loop

1. Create an independent **rail project**. The starter is developer-authored.
2. Inspect mass, speed, actuator authority, initial wall clearance, fixed requirements,
   and the actual registered controller.
3. Edit `robot.json` if needed. This is validated configuration source, not executable
   Python. Review its diff and compiled proposed geometry before explicitly saving.
4. Check the one-case execution box and choose **Run native verification**.
   The existing trusted engine runs 600 steps and a fresh 600-step replay.
5. Inspect the actual physical FAIL or PASS, numerical measurements, original
   requirement checks, source identity, and saved playback.
6. Ask **Inspect recorded evidence**. The deterministic assistant invokes the real
   engineering inspection tool and returns exact canonical references.
7. **Propose bounded authority change** searches the existing analytical braking
   prediction. Its output is a typed, compiled, **unapplied and unverified** proposal.
8. Explicitly review/save the numerical configuration, then run verification again.
   The earlier result stays tied to its original revision.
9. Reopen the project or download its verified JSON report.

A fresh replay PASS means an outcome reproduced; the physical requirements may
still FAIL. Compilation, prediction, recorded evidence and hardware safety are
separate concepts. A saved result never verifies a different configuration.

## Quick start

Use an existing reviewed **Python 3.12** environment and the declared dependencies
in [requirements.txt](requirements.txt), plus the existing Node/frontend lockfile.
Nothing installs automatically. Installation/setup changes are operator decisions.

```sh
# From the repository, using your activated reviewed Python environment:
npm --prefix frontend run build
python -m tools.start --check
python -m tools.start
```

Open **http://127.0.0.1:8765**. Startup imports installed dependencies and serves the
local production build; it does not run a trajectory, read a provider credential,
start a VM, or make a model request. Local simulation requires its explicit UI action.

Locally exercised platform: macOS Apple Silicon, Python 3.12, installed MuJoCo 3.16.0,
jsonschema 4.26.0, and the repository's reviewed frontend dependencies. Other
platforms have not received this release's browser/native acceptance checks.
See [developer setup and testing](DEVELOPER.md).

## What this candidate supports

| Capability | Scope |
|---|---|
| Local projects | Existing immutable Toolkit snapshots, exact-head numerical saves, reopen, source review/discard, restore as a new review |
| Source | Editable bounded `robot.json`; registered Python controller inspection is read-only |
| Physical context | BODYBASE/WORLDBASE-derived rail geometry, entered SI parameters, fixed original requirements |
| Native verification | One trusted rail case per explicit action, fresh replay and existing independent native saved-state validation |
| Engineering assistant | Actual inspect/propose tools, deterministic factual explanation and analytical force proposal; **not GPT** |
| Evidence | Actual saved samples, separate physical/replay outcomes, revision/source association, downloadable JSON report |
| Existing workspaces | Saved experiments, numerical rover toolkit, mechanical/SHAPEBASE/CIRCUITBASE and advanced analysis remain separately accessible |

The local workbench writes only its dedicated `.runtime/local_workbench/` project,
review and native-evidence stores. It does not update historical mechanical heads,
install controller code or reuse any historical approval/accounting record.

## Important limits

- This is a supported rigid rail reference, not universal robotics or real hardware validation.
- JSON edits change numeric settings, including actuator authority. They do not edit
  or execute arbitrary Python controller logic, firmware or model-authored source.
- The new workflow does not integrate circuit powertrain behavior with the rail simulation.
- General live AI remains unqualified after the canonical-ID repair. Historical FAIL,
  blocked launches and unresolved reservations remain unchanged. New source requires
  its own fresh, exact provider approval; no such execution is included here.
- Some retained archival tests require private development artifacts absent from a
  clean public checkout. They are not replaced or represented as passing. The
  documented public regression selection and the unrestricted archival tree have
  different coverage; see [verification](docs/VERIFICATION.md).
- Saved/native evidence is finite simulation evidence, not material, manufacturing,
  hardware or universal safety certification. Local hashes are not remote signatures.

## Existing measured studies

The [adaptive rail study](docs/ADAPTIVE_PHYSICAL_DEBUGGING.md) retains four physical
cases, eight rollouts and 4,800 integration steps, with a sampled PASS/FAIL interval
reduced from 50 mm to 25 mm. The next historical point remains unexecuted.
These are preserved historical results, not a new live v1.0 AI success.

[Portable rail evidence](examples/adaptive-rail-study/README.md) ·
[Controller failure/repair recordings](examples/rail-braking-study/README.md) ·
[Multi-model toolkit](docs/MULTI_MODEL_TOOLKIT.md) ·
[Engineering tools](docs/ENGINEERING_AGENT.md)

## Engineering and contribution

- [Architecture and trust boundaries](ARCHITECTURE.md)
- [Development, tests and troubleshooting](DEVELOPER.md)
- [Release notes and limitations](RELEASE_NOTES.md)
- [Feature matrix](docs/V100_FEATURE_MATRIX.md)
- [Verification history and current scope](docs/VERIFICATION.md)

AI proposes. Tools execute. Physics provides evidence. Deterministic verifiers decide.
