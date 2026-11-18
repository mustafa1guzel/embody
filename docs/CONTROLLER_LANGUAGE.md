# Rail controller language v1

EMBODY executes a **bounded controller DSL**, not arbitrary Python. Its four-line
source is compiled into a finite data tree. The trusted native adapter interprets
that tree at every control update; editing a condition changes actual applied
motor commands. Static validation does not establish physical PASS.

```text
rail_controller 1
when clearance_m <= 0.25
then brake
else coast
```

This initial developer-authored example brakes too late in the provided source
project. It is intentionally unsafe and has no verified verdict until actually run.

## Inputs and actions

| Name | Meaning / SI units |
|---|---|
| `clearance_m` | Current native bumper-to-wall surface distance, m |
| `stopping_distance_m` | Analytical `mass × velocity² / (2 × force_limit)`, m; not measured future motion |
| `speed_mps` | Absolute current native joint velocity, m/s |
| `time_s` | Current native simulation time, s |
| `mass_kg` | Validated entered and independently compiled carriage mass, kg |
| `force_limit_n` | Validated entered and compiled actuator authority, N |

`when` must be a comparison, optionally joined with `and` / `or`. Supported
comparisons are `<`, `<=`, `>` and `>=`. Arithmetic supports `+`, `-` and scalar
multiplication. A numeric literal takes the units of the surrounding quantity;
conflicting dimensions reject. Numeric literal magnitude is at most 100. There
are at most 64 parsed nodes and eight levels of nesting; source is at most 4 KiB.
Arithmetic outside the finite runtime envelope stops execution with no PASS.

Actions are only `brake` and `coast`. Brake requests velocity-opposing force,
clipped to the actual authority and to the force needed to stop in one 5 ms step.
Coast commands zero actuator force. Contacts, gravity and all dynamics still belong
to MuJoCo. Neither action directly sets position, velocity, contact or a verdict.
The update frequency is 200 Hz. Each explicitly requested three-second case has
600 primary integration steps and 600 fresh replay steps, with 601 samples each.

## Security and identity

Python AST parsing is a syntax-to-data translator only. No user AST is compiled
or evaluated by Python. There are no user imports, calls, attributes, indexing,
strings, reflection, loops, comprehensions, file/network access or unsafe builtins.
The trusted interpreter has only fixed opcodes and finite native numeric inputs.
This is not an OS sandbox and does not authorize unrestricted Python execution.
Existing isolation requirements for arbitrary controllers remain unchanged.

The exact UTF-8 **source SHA-256**, canonical generated **artifact SHA-256**, and
trusted compiler/interpreter **implementation SHA-256** identify different layers.
Whitespace can change the source hash while leaving the compiled artifact identical.
The application records the mapping; it never claims these hashes are interchangeable.

The native runner uses the approved snapshot's artifact. A fresh model/data replay
uses that same artifact. Independent read-back recompiles the source, checks the
mapping, uses a separate data-tree evaluator to check each control command, and
reconstructs native force, contact and geometry. It re-evaluates the original fixed
physical requirements. Shared MuJoCo and acceptance predicates are not a second
physics engine or formal source-correctness proof.

## Scope and limitations

Only the registered rigid rail model is supported. Source projects use existing
numerical project snapshots for physical configuration; their JSON controller ID
retains its numerical reference identity. The selected effective controller is
explicitly `EMBODY_RAIL_DSL_V1`, and numerical-reference execution is refused for
these projects. Existing numerical-only projects retain their original behavior.

The source starter uses 4 kg, 1.2 m/s, 4 N and 1.44 m clearance. The measured
source-only demonstration retained those parameters and the original requirements:
late braking hit the wall; the offline stopping-distance source achieved about
0.099 m minimum clearance with zero wall contacts. This is finite simulation
coverage, not hardware safety, universal correctness or a global repair optimum.
