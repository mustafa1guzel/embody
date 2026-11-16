# Parameter sensitivity

For ideal immediate constant braking, d=m v²/(2F):

| Variable | Local derivative | Unit | Elasticity for nonzero d |
|---|---|---|---|
| mass m | v²/(2F) | m/kg | +1 |
| speed v | m v/F | s | +2 |
| authority F | −m v²/(2F²) | m/N | −1 |
| initial gap | 0 for stopping distance | m/m | 0 |

At zero speed/distance all relative sensitivities are undefined, not0. Bounded
1% perturbations report actual parameter change and predicted distance change;
a catalog-clipped perturbation can have zero change. These analytical values
are not measured controller sensitivities or actuator energy efficiencies.

Measured finite differences use exact verified case IDs and actual spacing,
with model/source/controller/criteria/settings and all other parameters fixed.
At a reference point with left/right neighbors, the derivative of the quadratic
interpolant is used for irregular spacing h,j:

`−j*y_left/[h(h+j)] + (j−h)*y_center/(hj) + h*y_right/[j(h+j)]`.

With only one direction, a labelled one-sided secant is reported. Missing metrics
or neighbors yield INSUFFICIENT_COMPARABLE_NEIGHBORS. No analytical substitute
is inserted. Every estimate lists its cases, spacing, method and metric/parameter
unit. It is finite sampled evidence, not a continuous derivative or global ranking.

The actual saved v0.4 pair at equal4kg,1.2m/s,2N and gaps1.49/2.2m supports a
one-sided clearance-versus-gap estimate. Its actual result values come from the
verified reader. Historical/current source status remains visible. Select the
reference case in the dashboard; use a separately reviewed sensitivity campaign
to obtain missing neighbors. Zero new native rollouts were run for this analysis.

## Residuals and discrete idealization

Each verified saved case exposes measured minimum gap minus continuous ideal
remaining gap, signed/absolute residual and signed relative residual normalized by
absolute predicted gap. Zero predicted gap makes relative residual undefined.
A 600-update clipped-velocity Euler arithmetic prediction is explicitly analytical,
not MuJoCo, and excludes contact/delay/damping. Historical trigger controllers
need not satisfy those assumptions. Residuals alone establish no causal timing,
discretization or contact explanation. Braking ratio is d_stop / initial gap.
