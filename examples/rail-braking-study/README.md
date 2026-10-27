# Recorded rail-braking study

This self-contained **derived publication package** contains an authentic saved
carriage study: three physical scenarios, the original controller and two genuine
model-authored proposals. The original and first proposal fail the recorded
requirements; the second proposal passes in all three scenarios.

No model request, simulation, controller execution or render was performed to
package these files. Nine trajectories, independent traces, controller source,
compiled XML and 51 native PNGs come from existing measured evidence.

The included task policy is the original consumed session's record, not current
execution permission. Private development accounting and the raw internal report
stay outside this package; the UI identifies their absence explicitly.

## Identities and provenance

`source-manifest.json` is the byte-identical original inventory. Its actual hash
is recorded in `derivation.json`. Original private records remain untouched.
The public inventory has its **own** hash. JSON path metadata was projected only
in declared artifact-reference, API-reference and model-provenance fields.
Numerical measurements, timestamps, verdicts and controller arguments were not
changed. XML, controller sources, independent traces and PNGs retain their
original byte identities.

The native index is explicitly a derived packaging index: its recording binding
refers to the public inventory, and it retains the original index hash. This is
not a newly rendered replay. Raw API payloads and worker exchanges are not
included; their informational references cannot be opened through the inventory.

The original manifest anchors source identities. Reproducing the metadata
derivation independently requires access to the private originals; the public
package alone does not prove the contents of omitted original records. Saved
physics and fresh-replay results are historical finite measurements, not new
verification, a second physics engine or real-world safety certification.

## Read and check

The existing bounded, hash-pinned reader is unchanged. It accepts indexed relative
paths and rejects unindexed files, symlinks, traversal, altered bytes and foreign
absolute roots. The default local configuration selects this package explicitly.

```sh
.venv/bin/python -m pytest -ra tests/test_public_recording.py
```

With reviewed dependencies, the existing API and legacy recorded-study workspace
can read scenarios A/B/C and the saved native frames. Opening evidence performs
no dynamics and does not apply a proposal. Advanced historical rover, arm and
robustness archives are separate; this package does not silently replace them.

`tools/public_study.py` provides a write-once exporter for an operator who has the
original inventory, its pinned hash, the original native index and its pinned
hash. Unknown host-bearing fields stop export; existing output is never replaced.
It does not change application configuration or grant execution authority.
