# Generalized physical engineering core v1

The local v1.1 contract supports two independently verified rigid-proxy families:
a single-axis braking carriage and a differential-drive rover. One controller
compiler, tool protocol, revision lifecycle, native loop, replay and requirement
verifier serve both. Bounded transfer does not qualify genuine GPT reasoning or
establish universal robotics support.

## Versioned project and source

PHYSICAL_ENGINEERING_PROJECT_V1 contains exact title, family, parameters,
environment, task and requirements. Unknown fields/families, nonfinite/bool
numbers, invalid units and unsupported dimensions reject. Tasks declare bounded
named SI constants. Requirements have canonical IDs, typed quantity expressions,
min/max/final/settling aggregation, operator, threshold, units and settling band.

PHYSICAL_CONTROL_CONTRACT_V1 names observations, measurements, actuators,
horizon and 5 ms timestep. Controller observations are pre-action. Actuator peak
is a post-action measurement, excluded from controller input. Thresholds and
measurements remain separate; descriptions never replace canonical IDs.
Mandatory family floors retain quantity, aggregation, operator and unit.
Projects may tighten them or add supported quantities.

A bounded data controller has this form:

~~~text
physical_controller 1
force_n = -force_limit_n if speed_mps > 0.03 else 0
~~~

This illustrates syntax, not a verified controller. No Python, imports, files,
loops, user functions, external calls or source installation are supported.
The only named math operation is abs; arithmetic, comparisons, Boolean combinations
and conditionals have size/depth/node limits and dimensional checks. Actions
saturate to actual compiled envelopes; requested/actual values remain separate.

Source, compiled artifact, contract, model XML, implementation, project head and
trajectory have different mapped hashes. A revision advances only through a
separately confirmed reviewed change. Restore creates a new proposal; rejection
preserves the head. Old evidence cannot verify a later source or definition.

## Tools and authority

The same four tools are inspect_system, validate_source, propose_change and
inspect_result. They expose actual identities, units, requirements and schemas.
They cannot apply, execute physics, invoke a provider, access arbitrary files or
install code. The offline workflow calls inspect → validate → propose using an
explicit caller-supplied source plan. It neither interprets language autonomously
nor looks up a hidden correction. Examples remain labelled developer data.

Native execution separately requires confirmation, exclusive job, nonce and
exact-head binding. Deadlines, cancellation and interrupted states persist.
Each job runs one primary and fresh rollout with no retry. Admission bounds
requests to 64 KiB and checks storage before dispatch; artifacts are bounded.
No new VM or arbitrary source executor is used.

## Models and independent checks

| Family | Real registered native model | Actuation | Steps |
|---|---|---|---|
| Rail | Existing physical-context carriage/wall compiler | One bounded force, N | 600 + 600 |
| Differential rover | Typed nine-part World/SHAPEBASE rover, free chassis, wheel joints, surface contact | Two bounded rear torques, N·m | 200 + 200 |

The common verifier checks initial state, exact model/artifact, complete finite
time/state/force vectors, normalized quaternions, contacts, independent source
evaluation, observations, every requirement and fresh replay. Saved-state forward
audit adds no trajectory integration. Shared MuJoCo/compiler is not a second
physics engine or formal proof.

Rover observations include native wheel-axis projections, signed progress,
velocity, lateral drift, yaw, upright state, contacts and gravity along the
surface. Its example feedback controller uses these quantities without a separate
agent. Default contact acceptance requires all four wheels in contact in at least
one sample, not uninterrupted contact throughout the run.

## Frozen evaluation and limits

The native closure, example bytes and corrected source identities were frozen
before held-out definitions were generated. No core, adapter, example or control
program changed after held-out measurements. Later frontend navigation fixes
did not change that frozen implementation.

| Case | Initial | Same example correction | Actual final observation |
|---|---|---|---|
| Reference rail | FAIL, contact | PASS | 0.099 m minimum clearance, zero contact |
| Reference rover | FAIL, backward | PASS | +0.0157648 m progress |
| New rail mass/force/gap/speed/wall width and tighter clearance | FAIL | FAIL retained | 0.0999491 m clearance; 5.099518 N exceeds retained 4 N requirement |
| New rover mass, geometry, slope, friction, initial state and goal | FAIL | PASS | +0.0169790 m progress; 0.0211380 m final target error |
| New asymmetric rear-wheel actuation failure | FAIL | PASS | +0.0209825 m progress; same corrected source |
| Same held-out rover with 0.00001 m accuracy requirement | FAIL retained | No retuning | 0.0211380 m measured error |

Actuator capability and a tighter task force constraint differ. Braking behavior
transfers, but that source does not discover/enforce the stricter force bound.
A compile-valid controller also cannot be assumed to meet arbitrary accuracy.

Unknown families/source/requirements reject. No generalized arm adapter,
arbitrary CAD/import, steering/autonomy, hardware validation, materials proof,
coupled electrical drivetrain or unrestricted code execution is added. Legacy
arm functionality remains separate. Genuine AI and VM qualification stay
unqualified; historical FAIL evidence and unresolved accounting are unchanged.
