# Failure-boundary analysis

A boundary is an observed sampled interval, never an exact measured threshold.
The boundary view preserves lower/upper values, units, width, endpoint case IDs,
actual verdicts, fixed physical conditions and the compatibility contract.

Compatible means equal model/physics-source identity, controller, criteria and
simulation settings, with all noninvestigated parameters fixed. Execution errors,
cancellation, missing/corrupt/unverified results never become physical FAILs.
Multiple local transitions remain distinct. Different historical/current-source
records cannot establish a pooled boundary.

One-dimensional brackets require adjacent requested measurements of opposite
verdict. Two-dimensional selection shows actual sampled points and proposed
candidates, not a smooth filled safe/unsafe region. A sampled marker is not a
measured cell covering its neighbors. Incomparable physical cohorts can share plot
coordinates; exact per-case provenance must be inspected. Unknown space stays
unknown. Plot labels and accessible tables supplement color.

All measured PASS: **No measured PASS/FAIL transition has been observed.**
All measured FAIL: **No measured passing case has been observed in the sampled
domain.** Other insufficient/mixed conditions remain inconclusive. Ideal
clearance equations are analytical expectations, not native outcomes.

The earlier v0.4 native demonstration had only three PASS cases. The separate
completed v0.6.2 native study measured minimum gaps 0.003/0.028/0.053/0.103 m
from initial gaps 1.440/1.465/1.490/1.540 m. Its two FAIL/two PASS results
share the same 4 kg/1.2 m/s/2 N contract. The original 50 mm local bracket
[1.440, 1.490] m narrowed to 25 mm [1.465, 1.490] m after one actual measured
refinement. No continuous safe/unsafe region or exact boundary is inferred.
See [measurements, provenance and limits](ADAPTIVE_PHYSICAL_DEBUGGING.md).
