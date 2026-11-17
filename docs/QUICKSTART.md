# Robotics toolkit quickstart

For the rover: choose **New Project → Rover / inclined surface**, enter a name,
then inspect Design, Program, Simulate, Debug and Verify. Enter bounded numbers,
**Preview configuration**, then explicitly **Save robot configuration**. Preview
compiles the typed model but never integrates it. Debug/Verify remain unmeasured
until a separately approved run produces compatible evidence. **Prepare model
simulation** opens an exact 200+200-step review; cancel before execution.

**Export saved robot project** downloads a bounded JSON declaration. Return Home
and **Import robot project → Load local JSON → Validate & import robot**. This
creates a new numeric project and preserves model/controller/configuration, never
an applied World head or a physical PASS. Try the [reviewed starters](../examples/robot-projects/README.md).
Optional XML inspection is topology-only and cannot register/execute models.
See the [toolkit guide](MULTI_MODEL_TOOLKIT.md) before any qualification.

The steps below retain the genuine historical rail workflow.

Use the existing reviewed Python 3.12/macOS Apple Silicon environment. Dependency
sources are requirements.txt, optional requirements files and the frontend lockfile.
Nothing is installed automatically. Existing frontend dependencies and built
assets are required. Native setup readiness does not authorize a native run.

```sh
npm --prefix frontend run build
.venv/bin/python -m tools.start --check
.venv/bin/python -m tools.start
```

Open http://127.0.0.1:8765. Stop the owned server with Ctrl+C. Read setup errors
rather than installing or weakening checks automatically. Engine & setup status
on Home reports the existing import/build check, not a simulation or credential
inspection. Optional live AI is unavailable here and does not block saved review.
Only this local platform was exercised; no cross-platform claim is made.

1. **Explore Examples → Rail braking.** This opens actual public saved evidence,
   not a new robot build, simulation or passing current project.
2. **Design.** Select carriage or wall in the explorer/3D view. Orbit, pan, zoom,
   fit scene/selection and change projection using existing viewport controls.
   The scene is compiled from the selected saved XML, not inferred from a draft.
3. **Program.** Inspect the actual trusted brake excerpt in read-only Monaco.
   Its displayed excerpt hash differs in purpose from the native execution digest.
4. **Simulate.** Play/pause/restart or scrub genuine samples. Open Recorded
   measurement charts; its cursor and the 3D timeline refer to the same sample.
   Position, velocity and clearance charts use saved data; the live strip also
   shows measured actuator force. No interpolated sample is invented.
5. **Debug.** Inspect measured/required clearance and deficit. Observation,
   interpretation, hypothesis and action are labelled separately. No live model
   is used. Physical FAIL is distinct from replay PASS or unavailable evidence.
6. **Prepare supported improvement.** Change a bounded numerical field in the
   inspector. Inspect the ideal prediction. The selected saved evidence stays
   tied to its old input; a favorable prediction does not verify the draft.
7. **Prepare simulation.** Review the exact numerical case and unchanged
   requirements. Execution is disabled pending separate explicit authorization.
   Cancel before execution. No job, rollout or approval is created by preparation.
8. **Verify.** Compare compatible recorded inputs. This compares physical
   parameter changes, not a controller-code repair. Read exact evidence hashes
   and the preserved adaptive 50-to-25 mm result.
9. **New Project.** Name a rail numerical plan. Explicitly save validated draft
   parameters, then reopen the actual recent record. This persists existing typed
   Research project/campaign snapshots in a separate local namespace; it does not
   apply robot geometry or inherit a physical PASS.
10. **Advanced Analysis.** Use the existing mechanical/circuit studio, regressions,
    sweeps and Research. Its project context is independent and explicitly labelled.
    Return preserves the rail project/draft; hidden playback is paused.

Home also offers **Controller debugging**, opening the nine portable historical
original/repair recordings. These sources are never made executable by viewing.
Advanced saved rover/ramp/arm studies remain conditional on their original archives;
no substitute recordings are fabricated if private evidence is absent.

Shortcuts: Cmd/Ctrl+K opens searchable actual commands; Enter runs the first
available match, Escape dismisses dialogs. Cmd/Ctrl+S saves an eligible named
rail plan explicitly. Explorer/inspector buttons collapse panels; inspector width
is adjustable and remembered locally. The guide is local, repeatable and dismissible.
Five-minute onboarding is a design goal, not a measured comprehension claim.

Numerical drafts/selections persist across engineering views and an Advanced
round trip within the same browser session. Named plan snapshots persist across
reloads. Not every unsaved UI selection/draft is restored after a full reload.
See [scope](PRODUCT_ALPHA.md), [verification](VERIFICATION.md) and
[architecture](ARCHITECTURE.md).

## Inspect saved native results (v0.8.2)

From Home, choose **Open native rail results**, then select an exact saved run in
Simulation history. Design/Simulate renders its actual saved model and samples;
Debug explains the measured requirement failure; Verify shows every saved check,
replay/readback and source provenance. Use the minimum-clearance sample button
or scrub recorded time. Historical public examples remain under **Rail braking**.

An authored rail plan lists only results matching its saved numerical inputs,
controller, requirements and compatible native source. The read-only native study
is a separate evidence library, not proof that an unrelated project executed.
Select a compatible comparison explicitly; physical conditions may differ.

Open either retained rover review project to load its exact nominal or incline
result. Rover pose playback remains model-specific. Passing the target-error
**tolerance** does not mean the exact target was reached. No sample is generated
when you play, select, compare or inspect saved evidence.

Edit a supported numeric value to prepare an improvement. **Modified configuration
— verification required** keeps the old result scoped to its recorded inputs.
Preview/prepare validates bounds and shows an exact new request, but does not run
it. A separate explicit source-bound execution approval is always required.

## Contextual engineering tools

Use `python -m tools.start` for the assistant-enabled product server. The existing
`ide_api.server` module remains the legacy handler. In the current rail or rover
inspector, open **Engineering assistant**, select a local engineering command,
and inspect actual saved evidence. Numerical proposals require explicit review;
verification preparation grants no execution. The live bridge is disabled without fresh exact operator-recorded approval; no genuine provider qualification is claimed.
See the [engineering assistant guide](ENGINEERING_AGENT.md).

## Prepare a model turn without spending

Use `python -m tools.start`, select real saved evidence, and open the same assistant.
The **Live AI reasoning** section discloses local bridge availability. Free
preparation freezes the actual context, tools, model, limits and canonical digest.
The Run control stays disabled without separately recorded exact approval. No
API key is required for ordinary deterministic commands or saved playback.

A clean public checkout lacks private accounting history. The trusted operator
can run `python -m tools.engineering_agent_live admit-history --history-root
<reviewed-original-workspace>` using the existing genuine accounting anchor.
This is read-only recovery, not spending consent or an empty ledger baseline.
Never copy keys, receipts or private runtime data into Git. See the
[provider and approval guide](ENGINEERING_AGENT.md#live-provider-bridge--v091).
