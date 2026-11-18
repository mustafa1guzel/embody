# v1.0 feature scope and acceptance matrix

The release scope is the local registered rail debugging workflow. Evidence is
reported separately for contracts, native runs, browser interactions and external AI.

| Priority / capability | Implementation and user value | Acceptance / verification |
|---|---|---|
| P0 Project workspace | Toolkit numerical snapshots in a new dedicated namespace | Create/open/reopen, exact-head save, no historical head mutation |
| P0 Physical context | Original BODYBASE/WORLDBASE, registered rail geometry and SI settings | Actual compilation; invalid/missing/nonfinite fields rejected |
| P0 Supported source | Editable robot.json, bounded Rail DSL and readonly registered Python | Typed source diff/review/discard, explicit application, restore as a new reviewed revision |
| P0 Requirements | Original fixed rail predicates and canonical saved check IDs | No threshold relaxation; incorrect/missing/duplicate/cross-result references reject |
| P0 Tools | Existing EngineeringAgent inspect/propose methods | Deterministic origin explicit; actual saved measurements and exact references |
| P0 Native verification | Existing RailSweeps + fresh replay + NativeResults | One explicit bounded case, physical failure retained, independent force/contact/geometry audit |
| P0 Evidence / reports | Actual samples, revision/source association, JSON export | Same-head and earlier-head evidence distinguished; corrupt links rejected |
| P0 User decisions | Separate source review/save/run actions | No automatic numerical save, controller installation or model execution |
| P0 Reliability | Fixed public regression policy and new contract/API/native/UI tests | Exact outcomes/logs; archival failures never represented as passes |
| P1 Usability | Existing 3D renderer/playback, source view, actual measurement thresholds | Real Chrome checks, bounded viewport, usable controls and resizing |
| P1 Persistence | Existing immutable Store plus decision/run receipts | Reload/reopen, interrupted admission and repeated/stale operations fail safely |
| P1 Security | Same-origin token/Host, no-follow paths, exact schema and fixed controller | Wrong IDs/paths/symlinks/permissions/unknown routes rejected; no secret/provider/VM access |
| P2 Advanced mechanical/circuit | Existing SHAPEBASE/CIRCUITBASE studio, unchanged | Public geometry/circuit regressions; not claimed electrically coupled to rail |
| P2 Rover and research | Existing separate multi-model/research workspaces | Existing public regression scope; no new v1 rover performance claim |
| External genuine AI | Existing accounted provider bridge; canonical-ID repair retained | **NOT QUALIFIED** for v1; future exact explicit approval required |
| Out of scope | Arbitrary Python/controller/firmware execution, hardware, general CAD/robot support | Existing isolation/authorization boundaries preserved; no new executor |

The source-editing gate includes actual Rail DSL compilation/execution as well as
numeric configuration. Arbitrary Python and genuine AI qualification remain
unproven; deterministic source verification must not be described as either.
