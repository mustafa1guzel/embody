# EMBODY v0.6.2 — Verified adaptive physical debugging

Draft GitHub release description. Prepared for owner review; not published.

EMBODY now demonstrates a complete bounded physical-debugging loop: measure
failure conditions, preserve independently checkable evidence, and select an
informative follow-up test.

Four genuine rail-braking cases used **eight native MuJoCo rollouts and 4,800
integration steps**. All fresh replays and independent saved-sample verifications
passed. At fixed 4 kg, 1.2 m/s and 2 N braking authority:

| Initial clearance | Minimum measured clearance | Physical verdict |
|---:|---:|---|
| 1.440 m | 0.003 m | FAIL |
| 1.465 m | 0.028 m | FAIL |
| 1.490 m | 0.053 m | PASS |
| 1.540 m | 0.103 m | PASS |

Every case stopped without wall contact. Two still missed the unchanged 50 mm
clearance requirement. From the initial measured evidence, the deterministic
engine selected 1.465 m; its separately approved result narrowed the observed
local PASS/FAIL interval **from 50 mm to 25 mm — a 50% reduction**.

Included: concise [demonstration](ADAPTIVE_PHYSICAL_DEBUGGING.md), four genuine
application screenshots, exact measured tables/source identities and two compact
[portable evidence exports](../examples/adaptive-rail-study/README.md). Public
verification rechecks saved data without running physics. Private approvals,
certificates, credentials, logs and runtime directories remain excluded.

Release preparation checks: 21 targeted evidence/security tests passed, both
export packages passed strict saved-data verification, and recorded adaptive
selection/interval results were independently recomputed. All 46 source identities
match. No new native integration or paid requests occurred. Existing source-bound
218-backend/149-frontend/typecheck/build results are retained, not claimed as new runs.

This is a sampled local interval, not an exact/global safety boundary. The
controller is developer-authored; no live AI research, hardware safety or measured
sampling superiority is claimed. Replay shares MuJoCo. The 5 mm target is unmet;
**1.4775 m remains unapproved and unexecuted**. Consumed authority is not renewed.
Known preview/report labels remain documented; frozen native source is unchanged.

The adaptive research milestone is closed. Next: **v0.7 Product Alpha**, without
starting that work in this release.

Suggested commit (not executed):

```text
docs(release): prepare v0.6.2 verified adaptive physical debugging
```
