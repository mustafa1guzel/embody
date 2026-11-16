# Durable research evidence

Open **Research Workspace → Evidence Completeness** after selecting a campaign.
Link the existing pinned rail study (nine genuine historical runs), choose exact
cases and capture a bundle. Capture calls existing verified readers; it never
runs native dynamics. Raw telemetry, effective model and original independent
trace remain separate from derived summaries, research manifests and reports.

`EMBODY_RESEARCH_EVIDENCE_BUNDLE_V1` uses semantic manifest identity and SHA-256
of actual object bytes. Historical trajectory and result digest algorithms are
unchanged. Every artifact has explicit provenance. Local reader captures receive
an installation-local attestation; this is not a remote signature or physics proof.

The ignored `.runtime/evidence_store/` contains objects, bundles, local attestations,
external imports, completed-command receipts, offline benchmarks and finite upload
staging. Final names are write-once with atomic promotion. Safe relative references,
no-follow file reads, size/retention quotas and finite strict JSON bound the store.
Limits: 16 bundles, 48 artifacts each, 2 MiB per artifact, 12 MiB per bundle,
18 MiB per package, 128 MiB store, 64 receipts and 8 upload sessions. Quotas refuse
new writes; no automatic pruning. Explicit operator maintenance/export is needed.
Ignored persistent storage is **not a backup** against deletion or disk failure.

Availability is checked on every load: VERIFIED_AVAILABLE, VERIFIED_HISTORICAL,
PARTIALLY_AVAILABLE, MISSING, INTEGRITY_FAILED or EXTERNAL_UNVERIFIED. Source
compatibility is separate from availability; historical native data are not
silently upgraded to current source. Unavailable support removes a finding's
verified badge while preserving the finding. Unknown missing case counts remain
unknown. Completeness counts come from the actual selected campaign.

The old private three-case v0.4 raw directory remains unavailable at its known
reference. No disk-wide recovery, screenshot-based reconstruction or replacement
receipt is claimed. Existing v0.6 screenshots document what was observed then,
not currently portable original raw evidence.

## Portable packages

Export only a complete locally reader-verified bundle. Credentials, personal paths,
raw operator logs, qualification material, unrelated archives and installed/build
content are excluded or cause refusal; original bytes are never silently redacted.
Upload a package through the existing finite same-origin API in 48 KiB chunks.
Verification checks exact version/schema, references, identities, duplicates,
byte bounds, base64, required original data and recomputed saved measurements.

A valid package returns **INTEGRITY_VALID_EXTERNAL_UNVERIFIED**. Anyone can author
self-consistent JSON: hashes and arithmetic do not establish genuine MuJoCo origin.
Import stores external data without a local attestation, review status, execution
approval or application authority. It cannot be linked as locally verified physics.
No arbitrary file path or executable source is accepted.

Independent readback recomputes minimum gap, peak/final speed, contact samples and
episodes, peak force, sample count/grid, sustained final low-speed suffix, travel,
trapezoidal impulse magnitude (N s) and signed mechanical work (J). First threshold
entry, sampled suffix and continuous ideal stopping time are distinct. Missing
replay/model/source/measurement definitions reject. No native integration occurs.

See [workflow](RESEARCH_WORKSPACE.md) and [verification runner](RESEARCH_RELEASE.md).

## Public v0.6.2 demonstration exports

The [adaptive rail study](../examples/adaptive-rail-study/README.md) exports two
complete existing verified-reader captures: three initial cases and one refinement.
The existing exporter and strict package checker accept both without redacting
or altering original manifests, XML, samples, checks, verdicts or replay bytes.
Four case readbacks pass. Decoded artifacts and metadata were privacy-reviewed;
no consent/approval documents, local attestations, certificates, operator logs,
credentials or personal host paths are included. These are selected public
scientific exports, not a published private runtime directory.

`original_request.json` is the consumed numerical service request, retained by
the export format for reproducibility. Its nonce/confirmation marker is not user
approval or an execution token. Public result/source summaries are explicitly
derived projections, never replacements for sealed original evidence. External
verification remains INTEGRITY_VALID_EXTERNAL_UNVERIFIED; import cannot promote
origin, local trust, reviewed state or execution/application authority.
