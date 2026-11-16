# Deterministic adaptive experiment selection

All algorithms return numeric proposals only. Viewing recommendations performs
no model/native request. Every batch needs review and the existing native
confirmation. No Bayesian or calibrated uncertainty claim is made.

Initial v1 strategies:

- Uniform: inclusive equally spaced endpoints, six-decimal rounding. One axis
  uses at most the requested count; two axes use floor(sqrt(count)) per axis.
- Endpoints: all2 or4corners, requiring that many available points.
- Space filling: evenly spaced columns independently permuted with a stored
  Python Random seed. This bounded Latin-hypercube-style stratification is
  reproducible in the supported implementation; no statistical confidence claim.
- Near threshold: one-axis samples centered on the ideal clearance equation
  gap−m v²/(2F)=selected clearance, within ±quarter domain width. No valid in-domain
  solution rejects; it never fabricates a measured boundary.

Every candidate is schema/domain/precision checked; duplicated points reject or
are explicitly deduplicated by the deterministic sampler before a proposal. The
actual generated case count is shown, never inferred from the requested maximum.
Minimum spacing is Euclidean distance after scaling each axis by its domain span.
Axes use physical units in configuration; spacing and heuristic scores are
explicitly dimensionless. Round to six decimals before final admission.

## One-dimensional refinement

Only independently verified measured cases with equal physical-source contract,
controller, criteria, simulation settings and other fixed parameters compare.
Adjacent opposite verdicts form local intervals. An intermediate requested but
unexecuted/error point prevents falsely calling nonadjacent measured points an
adjacent bracket. Midpoints are rounded/checked and ranked by normalized interval
width. Multiple transitions remain separate; no global monotonicity assumption.
Existing/planned points are excluded except explicit reproducibility requests.

Stop for exhausted proposal capacity, insufficient comparable evidence, mixed
identities, normalized interval width≤2×spacing, repeated/out-of-domain midpoint
or no valid new point. Without a bracket, deterministic coverage midpoints may
be suggested, explicitly labelled **no measured transition exists**.

## Two-dimensional selection

Candidate pool:9×9inclusive domain lattice, filtered by spacing, bounds and
previous points. Nearest≤4verified compatible neighbors supply a transparent score:

`4 × local outcome disagreement + 2/(1 + normalized clearance margin)`
`+ min(1, normalized prediction discrepancy) + nearest normalized distance`.

Clearance margin is absolute distance from the selected clearance requirement,
divided by max(1mm, selected clearance). Prediction discrepancy is normalized by
the gap-axis span when varied, otherwise1m. Neighbor distances use each domain
span. Scores sort descending with canonical point digest as deterministic tie
breaker; greedy spacing prevents near-duplicate selected candidates. Each point
retains neighbors, components, method and rationale. This is an explainable local
heuristic, not a surrogate posterior or proof of information optimality.

User selection can reject individual suggestions. The remaining selected batch
is revalidated and remains AWAITING_REVIEW. Campaigns cap100unique proposed points
and25perbatch; proposal capacity grants zero native authority.

Synthetic tests cover known brackets, multiple transitions, mixed identities,
missing/error cases, spacing/precision, budgets and2Ddeterminism. These are
algorithm fixtures, not MuJoCo measurements. Genuine saved v0.4 evidence has
three PASS cases; its gap-compatible pair supports coverage guidance, not an
observed PASS/FAIL boundary in that earlier demonstration. The later v0.6.2
campaign measured both outcomes and executed one separately approved midpoint:

The initial [1.440, 1.490] m bracket selected 1.465 m from verified records.
Its measured clearance FAIL narrowed the interval to [1.465, 1.490] m, width
25 mm versus 50 mm. All four cases and fresh replays are preserved in the
[public demonstration](ADAPTIVE_PHYSICAL_DEBUGGING.md). The next midpoint
1.4775 m is unapproved/unexecuted; the 5 mm target is not achieved. This
establishes one real measured refinement, not a sampling-efficiency advantage.

## Current hardening

Comparability also requires explicit experiment, model and measurement-definition
identities. Conflicting repeated outcomes stop refinement. Out-of-domain or
different fixed-condition rows cannot contribute brackets. Each midpoint retains
its parent interval, supporting cases, expected half-width if a valid comparable
measurement is obtained and requested SI resolution. Optional `resolution_target`
applies only to one axis; no default is inserted into historical documents.
Stop when all observed brackets meet the target, while unobserved regions remain
unknown. Available matching results are displayed by reviewed batch, not invented
execution timestamps. Old private three-PASS raw data remain unavailable; the
paragraph above records the former observation, not current independent access.
See [fair offline comparisons](EXPERIMENT_EFFICIENCY.md).
