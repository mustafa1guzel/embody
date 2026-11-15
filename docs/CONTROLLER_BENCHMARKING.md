# Controller descriptors and constrained benchmarking

Only `developer_velocity_brake_v1` is registered for current native rail execution.
It opposes velocity immediately with a bounded final-step force; it is developer
authored, not a GPT repair. Descriptors contain version, observations, interface,
source identity, definition, execution status and limitations. Metadata never
extends the independent native allowlist, imports a file or grants qualification.

Three candidate strategies have offline definitions and scalar tests only:
proportional velocity damping with saturation, stopping-distance-aware braking,
and a fixed-distance trigger. They are **OFFLINE_DEFINITION_NOT_REGISTERED**.
Adding one to native service requires reviewed source/model/force/contact/parity
and admission changes, resulting source identity and separate new native scope.
No candidate controller or protected execution identity changed in v0.6.

Pinned original/attempt1/attempt2 trajectories may be compared only as historical
recordings through their existing strict reader. Fair cohorts require identical
physical parameters, physics-source contract, simulation settings and acceptance
criteria. Different controller identities are allowed only within that controlled
cohort; different sources are not pooled. Native versus pinned historical readers
have distinct physics-contract identifiers. All source drift stays visible.

Metrics include minimum clearance(m), final speed(m/s), sampled settling(s),
peak force(N), trapezoidal ∫|F|dt(N s) and signed ∫Fv dt(J) where sampled force
and velocity exist. The first integral is impulse magnitude, not energy. The
second is sampled mechanical work, not battery use. No electrical model exists.

Pareto analysis maximizes minimum clearance and minimizes peak force by default.
Only verified measured PASS cases with all objective metrics qualify; mandatory
safety is a constraint. A dominates B if no objective is worse and at least one
is strictly better. Equal vectors are both nondominated. Missing, failed and
incompatible cases are excluded. Results state distinct comparable controller
count. One reference controller alone is not a demonstrated controller benchmark.
Non-dominated means only within the finite eligible set, not globally optimal.

Research displays the registry and actual compatible recorded cohorts, not a new
native multi-controller demonstration. No historical GPT source is made executable.
