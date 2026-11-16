# Reproducible offline research release verification

With already reviewed local dependencies available, run from the repository root:

```sh
python -B -m tools.research_release_verify
```

The command serially runs the complete targeted Research/Designer/Sweep/Regression
frontend suites, focused non-native Python tests, typecheck, production build,
relative documentation links, whitespace, changed-source privacy and committed
protected-source/historical-fixture comparisons. No package installer is called.
An optional paired `--original-root` and `--original-inventory` compares only an
existing historical inventory; it does not create or overwrite a baseline.

Python loads an opt-in guard plugin that instruments actual MuJoCo integration,
provider-client creation, VM command creation and engineering application entry
points. Any attempt is counted and refused. This instrumentation is a release
check, not a security sandbox or qualification certificate. Tests use saved data,
strictly labelled mathematical fixtures and the existing local HTTP guards.

Completed commands receive `EMBODY_VERIFICATION_RECEIPT_V1`: exact command,
UTC interval, actual exit code/counts, source/base identity, installed versions,
log SHA-256, finite resource limits, stage status and guard counters. Failure and
timeout receipts remain failures. Stages run once; the runner stops on failure.
Logs are bounded to 2 MiB and each stage to 900 seconds. A new invocation gets a
new run identity; it never rewrites old logs or combines isolated passes into a
successful aggregate. Logs/receipts remain private because exact commands can
contain operator paths. Store limits require deliberate maintenance, not pruning.

Durable logs: `.runtime/release_verification/<run-id>/`.
Immutable receipt copies: `.runtime/evidence_store/receipts/`.
Browser QA remains a separate real installed-browser interaction and must have
its own observed results, screenshots and counter evidence. A unit-test pass is
not browser QA or native physical validation.

Current-source adaptive native demonstration is a separate unexecuted scope:
three cases, three fresh replays, at most 3,600 steps, only the registered trusted
rail controller and unchanged acceptance predicates. A source-bound exact consent
must be explicitly approved before native execution. Later measured-bracket
midpoints require new approval; an eight-case campaign ceiling is planning only.
The old unapproved consent cannot authorize changed source.

## Preparing the separate native request

```sh
python -B -m tools.research_native_preflight prepare
python -B -m tools.research_native_preflight check --manifest <returned-relative-path>
```

Preparation writes a new ignored immutable consent with exact numeric cases,
46 relevant source/dependency identities, current catalog/engine versions and a
48-hour expiry. Check validates it without reserving a job or granting authority.
There is deliberately no execute action in this command. A separate explicit
user approval of the exact definition and trusted operator admission through
the existing service are still required. Any source drift, expiry, consumed nonce
or full retained-job capacity blocks the old scope. Keep original manifest bytes
and the preparation receipt's byte digest for the subsequent approval audit.
