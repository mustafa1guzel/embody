# Developing and verifying EMBODY

## Environment

Use a reviewed Python 3.12 environment and the repository's declared dependencies.
`requirements.txt` covers the local engine; optional API/workspace requirements are
separate. Frontend versions are in `frontend/package-lock.json`. Do not assume a
clean checkout contains a virtual environment or installed Node modules. Review
installation separately; startup and verification never install automatically.

```sh
npm --prefix frontend run build
python -m tools.start --check
python -m tools.start --port 8765
```

The server binds loopback. Stop the owned process with Ctrl+C. Use a different
explicit port if yours is occupied; the launcher does not terminate other apps.

## Layout

| Path | Role |
|---|---|
| `frontend/src/LocalWorkbench.tsx` | Default local workflow, source review, actual result/playback and assistant |
| `ide_api/workbench.py` | Composition over existing typed stores/tools/native services |
| `ide_api/workbench_http.py` | Existing server extension and exact bounded local routes |
| `ide_api/toolkit.py`, `engineering/store.py` | Numerical projects and content-addressed persistence |
| `ide_api/rail_sweeps.py`, `ide_api/native_results.py` | Trusted native jobs, replay and independent saved-state checks |
| `core/`, `world/`, `shapebase/`, `hardware/` | Existing physics, geometry and electrical contracts |
| `tests/`, `frontend/src/*.test.*` | Backend, contract, integration, native and UI tests |

## Supported local regression

Use a **new** output directory on every run:

```sh
python -m tools.verify_local_release --output .runtime/local-release-check-001
npm --prefix frontend test
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

The fixed public Python selection extends the pre-existing research release policy
with product, multi-model, agent, security, circuit, shape and local-workbench tests.
It includes real trusted native fixtures in disposable projects, so it is not an
engine-free test suite. The guard denies real credential paths, outbound network,
VM launches and writes to protected/original workspaces. Synthetic protocol fixtures
remain labelled; they do not prove model reasoning or native outcomes.

The unrestricted `python -m pytest -ra -m "not live_vm"` additionally collects retained
archival-development tests. Some require deliberately undistributed Day/Phase private
recordings. They can fail in a public checkout; never copy secrets into the repo,
change historical hashes, fabricate fixtures or claim those tests passed. Live VM
qualification is also separate and not part of the public local command. See current
results in `docs/VERIFICATION.md`.

## Local workflow reproduction

1. New rail project → inspect fixed parameters/controller/requirements.
2. Explicit one-case native run → inspect physical FAIL versus replay PASS.
3. Inspect recorded evidence → actual tool output and canonical references.
4. Propose bounded authority change → inspect diff and optional compiled preview.
5. Check review confirmation → save numerical configuration only.
6. Explicitly run again → inspect measurements, strict outcomes and saved playback.
7. Download report → reopen project and compare both run revisions.

Manual JSON edits use the same review/save boundary. A stale head, source mismatch,
invalid numeric value, changed requirements or corrupt association rejects. Save
and run are independent actions. Interrupted native jobs/decisions are retained and
never resumed automatically. A deliberate new run needs its own new UI action.

## Contribution and security

Use a feature branch and focused commits. Keep private `.runtime/`, credentials,
consents, certificates, raw provider records and machine paths out of commits.
Never use prior approval for a changed source revision. Provider tests need fresh
explicit source/model/context/tool/token/cost/time scope and separate permission.

Controller Python in this workflow is read-only. To support arbitrary edited
controllers requires a separately designed/audited execution boundary, not removal
of existing checks. Keep physical predicates strict and record unavailable results
as unavailable. Native replay PASS and physical PASS must remain distinct.

## Troubleshooting

- **Missing build/dependency:** read the startup error; review the environment rather
  than allowing automatic installation or fallback.
- **Stale project/review:** reopen the saved head or create a new reviewed project;
  never silently migrate source-bound evidence.
- **Interrupted job:** inspect retained state. Do not reset its nonce or overwrite it.
- **No analytical candidate:** no bounded authority-only prediction met the limits;
  this is not a verified repair and does not authorize relaxing requirements.
- **Missing historical arm/experimental media:** not every private development
  recording is shipped. Current local rail verification does not depend on it.
