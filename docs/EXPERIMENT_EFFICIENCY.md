# Offline experiment efficiency benchmarks

Open **Research Workspace → Efficiency Benchmarks** with a campaign selected.
Choose an environment, maximum 3–25 oracle queries per strategy, seed and observed
interval target. Run the bounded comparison; inspect exact query histories,
point plot, bracket-width curves, evaluation-cost counts and export JSON.

These results are **ANALYTICAL_ORACLE_NOT_MUJOCO** or
**SYNTHETIC_ALGORITHM_FIXTURE**, never measured physical outcomes. All three
strategies share the domain, query ceiling and observed-interval stopping rule.
Every endpoint/corner counts; there are zero free observations. Actual counts
may differ when a target is reached. Seeds, configuration, algorithm version,
implementation digest, query order and termination are saved write-once.

- Uniform: 1D evenly spaced inclusive sequence. 2D bounded regular lattice with
  outcome-blind maximin ordering to retain edge coverage for a partial grid.
- Seeded stratified: independently shuffled jittered strata for each axis.
- Adaptive: only domain and past queried outcomes enter the selector. Counted
  endpoints/corners come first. 1D refines the widest observed opposite-outcome
  interval, otherwise the widest coverage gap. 2D ranks the 9×9 pool using four
  nearest outcomes and normalized nearest distance. No environment/threshold,
  oracle function, answer key or unsampled truth enters the selector.

Environments: ideal continuous rail clearance at mass 4 kg, speed 1.2 m/s,
force 2 N and required gap .05 m; one transition; two transitions; narrow failure
region; all PASS; all FAIL; and a two-dimensional diagonal transition.
The analytical rail oracle omits contacts, timing and discretization. Synthetic
classifications use ORACLE_PASS/FAIL rather than native MEASURED labels.

Report evaluated points, observed brackets/widths, queries to target or unavailable,
duplicates, candidate-score count, termination and 2D lattice fill-distance/local
opposite-outcome metrics. Known-transition coverage/misses are evaluated **after**
selection for these known fixtures. Real unsampled transitions remain unknown.
A narrow failure can be missed entirely, and observed interval resolution does
not prove every transition was found. No universal adaptive advantage is claimed.

Pinned historical measurements lack a common sampled oracle for fair retrospective
strategy comparison. Their case cohorts are reported; no interpolation or zero-cost
hidden outcomes are substituted. There is no measured efficiency advantage claim.

See [adaptive selection](ADAPTIVE_EXPERIMENT_DESIGN.md),
[sensitivity](PARAMETER_SENSITIVITY.md), [evidence](RESEARCH_EVIDENCE.md).
