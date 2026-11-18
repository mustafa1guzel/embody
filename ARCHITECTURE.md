# EMBODY architecture

The v1 local workbench composes existing engineering services; it does not introduce
a second simulation engine, arbitrary source executor or provider ledger.

```text
LocalWorkbench (React + existing Three.js viewport/playback)
  → same-origin WorkbenchHandler / existing loopback server + global job lock
  → Workbench composition
      → Toolkit + Store: typed numerical projects and immutable snapshots
      → EngineeringAgent: inspect_result / propose_parameters
      → RailSweeps: fixed registered controller, bounded native job + fresh replay
      → NativeResults: source/model/trajectory/force/contact/requirement readback
  → actual samples, exact requirements, review diff, explicit numeric save, report
```

`tools.start` runs the existing dependency/build preflight and the extended local
server. Existing routes and advanced workspaces retain their own services and
project identities. New routes live under `/api/workbench/`; every mutating request
retains the existing Host, Origin and CSRF checks and strict field/size limits.
There is no workbench provider, credential, arbitrary-code or mechanical-apply route.

## Physical context and evidence

BODYBASE and WORLDBASE own the rail physical/scenario inputs. The registered
numeric declaration selects only supported model/controller identities and SI
parameters. SHAPEBASE and CIRCUITBASE remain existing advanced tools; this local
rail workflow does not infer their coupling or missing material properties.

The unchanged rail engine owns real dynamics, clipped actuator commands and fresh
replay. The existing native reader recompiles registered numeric geometry and checks
saved state, contact, force and acceptance values. The UI uses that actual saved
trajectory; it does not invent an animation or a physical verdict.

Local run associations bind an immutable project snapshot/revision to the admitted
native request. The record remains accessible after a later save, clearly labelled
as earlier-head evidence. Corrupt or inconsistent references reject.

## Reviews and persistence

`robot.json` is configuration source. JSON schema, bounds, duplicate/nonfinite
rejection, registered identity and unchanged requirements are validated before
review. The existing compiler checks proposed geometry without native integration.
A content-addressed review binds the base head, revision and relevant source hashes.

Only an explicit human save advances the numerical head through Toolkit. Intent and
completion receipts preserve interrupted decisions; retries do not silently apply
again. Restore creates a new review, never rewinds history. Workspace mutations use
an owner-only no-follow lock in this new workspace; it is not the old live-admission
lock or a certificate. This is a loopback single-operator application, not an
adversarial same-UID filesystem sandbox or remote approval/signature service.

## Agent and execution boundaries

The default assistant is deterministic. It calls the actual existing inspection
and numerical proposal tools. The force proposal searches the existing discrete
analytical prediction; only new native execution can verify it. Machine references
use actual check keys; strict numerical/outcome validation and complete unique
selected-check coverage remain separate from readable explanation text.

The genuine provider bridge, budget accounting and source-bound human approval
mechanism remain separate. No v1 UI action grants paid execution or consumes an old
approval. Historical qualification, reservations and raw model output are unchanged.
Untrusted source execution still requires its existing adequate isolation boundary;
the local workbench never provides it with a new executor.

## Source-bound controller extension

`ControllerWorkbench` is mounted inside the current workbench, not a separate app.
`ControllerEngineering` adds typed inspection/validation/proposal tools and explicit
human source decisions over existing numerical projects, Store and Workbench locks.
It does not add a model adapter or financial ledger. `controller_language` translates
bounded source to data; `controller_native` interprets it inside the existing
registered MuJoCo loop, runs fresh replay and independently audits saved controls,
contacts, forces, geometry and original acceptance checks. The numerical reference
path refuses execution for a selected DSL project, preventing silent substitution.

[Language and safety contract](docs/CONTROLLER_LANGUAGE.md) ·
[Source lifecycle and tools](docs/CONTROLLER_ENGINEERING.md)
