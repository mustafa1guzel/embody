# Native adaptive rail-braking study · v0.6.2

Four genuine measured cases; two clearance failures and two passes. The native
runs were completed under separate finite approvals. This public collection
exports selected scientific evidence through the existing bounded exporter;
it contains no private runtime directory, consent, certificate or local attestation.

| Initial surface gap | Minimum measured gap | Physical verdict |
|---:|---:|---|
| 1.440 m | 0.003 m | FAIL |
| 1.465 m | 0.028 m | FAIL |
| 1.490 m | 0.053 m | PASS |
| 1.540 m | 0.103 m | PASS |

Mass 4 kg, initial velocity 1.2 m/s, braking authority 2 N. Mandatory clearance
is 0.05 m. All cases finish at zero speed and have zero wall contact samples and
episodes. Each contains 600 primary steps and a fresh 600-step replay: **four
cases, eight rollouts, 4,800 integration steps**. All replays and independent
saved-sample verifications passed; a reproducible failure remains a physical FAIL.

The initial three measured cases support [1.440, 1.490] m. The deterministic
engine selected 1.465 m from that evidence. Its separately approved measurement
narrows the local interval to [1.465, 1.490] m, **50 mm → 25 mm (50%)**.
Next proposed 1.4775 m is **unapproved and unexecuted**. No exact/global boundary,
hardware safety, live AI reasoning or measured sampling-strategy superiority
is established. The 5 mm target has not been reached.

## Contents and provenance

| File | Contents |
|---|---|
| [initial-evidence.json](initial-evidence.json) | Unchanged complete existing three-case reader-capture export |
| [refinement-evidence.json](refinement-evidence.json) | Unchanged complete existing one-case reader-capture export |
| [measurements.csv](measurements.csv) | Exact derived measurements, case/model/trajectory/result identities |
| [results.json](results.json) | Public derived summary with criteria, counts and explicit limitations |
| [adaptive-selection.json](adaptive-selection.json) | Actual recorded engine outputs, campaign config and measured interval update |
| [source-identities.json](source-identities.json) | All 46 verified execution source identities, bases and installed versions |
| [provenance.json](provenance.json) | Export hashes, bundle identities, sizes, exclusions and trust meaning |

The two packages total approximately **1.57 MiB**. Primary and fresh replay
samples, model XML, measured force/contact state, acceptance dictionaries and
original result/trajectory identities remain unchanged. They are two separate
native jobs; the collection does not pretend they were one four-case dispatch.
`original_request.json` is an inert consumed numeric service request required by
the existing format, not a consent document or new execution permission.

The initial execution base was `68b4c14efd523d1fad267d1d01d458bfb04a3b82`;
the refinement base was `2fca35e8e56b3b63271e6bcbf033ff59fad3b916`.
All 46 execution source identities remained equal across those bases. The
native source identity is
`b3070a8ccadc0897b5981cca6ea9aab54f56c12f53ebebeea8ff7c3500c0ed29`.
The documentation release does not rewrite execution identities or renew approval.
The source manifest lets a reader check the exact public files used; it is not
an installation certificate or a universal dependency reproducibility claim.

Package verification returns **INTEGRITY_VALID_EXTERNAL_UNVERIFIED**, with
saved-arithmetic matches. This is intentional: self-consistent bytes and hashes
cannot independently prove MuJoCo origin. Publisher-reported native execution
is supported by retained private execution audits; their logs, approvals and
local attestations are excluded. Import never promotes local trust or grants
review, simulation, financial or application authority.

## Verify saved data without executing physics

From the repository root, with the existing reviewed dependencies available:

```sh
python -B - <<'CHECK'
import hashlib, json
from pathlib import Path
from tools.non_native_guards import install, COUNTERS
install()
from ide_api.research.artifacts import ArtifactStore
from ide_api.research.sampling import adaptive
from ide_api.research.analysis import boundaries
root = Path('examples/adaptive-rail-study')
read = lambda name: json.loads((root / name).read_text())
records, steps = [], 0
for name in ('initial-evidence.json', 'refinement-evidence.json'):
    checked = ArtifactStore.verify_package(read(name))
    assert checked['status'] == 'INTEGRITY_VALID_EXTERNAL_UNVERIFIED'
    summary = json.loads(checked['decoded']['summary.json'])
    records.extend(summary['records'])
    for key, raw in checked['decoded'].items():
        if key.endswith('/native.json'):
            case = json.loads(raw)
            steps += len(case['samples']) + len(case['replay']['samples']) - 2
selection = read('adaptive-selection.json')
config = selection['campaign_config']
initial = [r for r in records if r['parameters']['gap_m'] != 1.465]
assert adaptive(config, initial, [r['parameters'] for r in initial], 5) == selection['after_initial']
assert adaptive(config, records, [r['parameters'] for r in records], 4) == selection['after_refinement']
assert boundaries(records, ['gap_m'])['intervals'] == [selection['interval_update']['current']]
for name, digest in read('source-identities.json')['source_manifest'].items():
    assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest
assert len(records) == 4 and steps == 4800 and not any(COUNTERS.values())
print('PASS: 4 cases; 4800 recorded steps; replay/readback and adaptive selection match; 0 new native steps')
CHECK
```

The checker recomputes saved arithmetic and compares saved fresh native samples;
it does **not** run a new physics replay or attest external origin. Existing
negative package tests cover tampering, missing replay/support, duplicate
artifacts, unsafe paths and finite JSON. No full private archive is required
for these public package checks. Private advanced studies remain separate.

Read the [public demonstration](../../docs/ADAPTIVE_PHYSICAL_DEBUGGING.md),
[verification scope](../../docs/VERIFICATION.md#v062-verified-native-adaptive-refinement)
and [export rules](../../docs/RESEARCH_EVIDENCE.md).
