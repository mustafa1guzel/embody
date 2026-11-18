# Source-bound controller engineering

Choose **New controller project** in the existing local workbench. The Controller
view exposes actual saved source, a draft editor, static validation, review diff,
explicit application, native verification, comparison and restore-as-review.

1. Inspect the source, physical configuration and original requirements.
2. Explicitly run the initial saved controller and fresh replay.
3. Inspect measured FAIL, contacts, source/artifact identities and exact checks.
4. Enter a supported task and request the offline stopping-distance proposal.
5. Review the real diff. It is unverified, unapplied and labelled
   **OFFLINE DETERMINISTIC ENGINEERING ASSISTANT**.
6. Approve the exact source and select **Apply reviewed controller source**.
7. Request a separate new native run; application never starts simulation.
8. Compare the actual source revisions and recorded outcomes; export the verified
   server report without JavaScript reserialization.
9. Reopen the project or restore an older source as a new review, never a history rewind.

Manual source edits use the same compiler and approval path. Rejected source never
changes the saved head. A rejected proposal's text can remain an unsaved draft;
Discard controller draft returns to the saved source. A statically valid source can
still fail physics. Source changes make prior results earlier-head evidence.

## Tool profile

The existing local workbench owns the following provider-independent typed profile:

| Tool | Arguments | Effect |
|---|---|---|
| `inspect_controller` | `{}` | Actual source, revision/head IDs, physical inputs, requirements and contracts |
| `validate_controller` | `source` | Bounded DSL compilation; no save/run |
| `propose_source` | `source`, `intent` | Source-bound immutable review and exact diff; no application |
| `inspect_controller_result` | exact run `nonce` | Independently audited saved source execution; earlier-head status remains explicit |

The surrounding trusted binding fixes `project_id`, numerical `project_sha256`
and `controller_head_sha256`. A model cannot select an unrelated filesystem path,
approve its own proposal, run shell commands or execute a simulator through these
tools. Exact schemas are in `ControllerEngineering.tools()` and are returned by
inspection. Unknown fields/tools and stale/foreign bindings reject.

The separate human routes require exact review/head identities and explicit source
confirmation. Source execution also requires an explicit one-case confirmation.
The existing loopback Host/Origin/CSRF and global expensive-job lock remain in use.
No provider, credential or financial authority is added by a source tool.

## Persistence and provenance

Numerical projects retain their existing format and immutable snapshots. Optional
versioned controller snapshots live in a separate project-scoped store. Each source
revision includes the raw source, compiler output, both hashes and implementation
binding. Reviews retain before/proposed hashes, intent, origin and base identities;
decision receipts retain the approved source hash. New explicit reviews have distinct
identities even when their source contents match earlier rejected proposals.

Immutable run requests bind numerical and source snapshots, parameters, requirements,
controller artifact, implementation and unique execution ID. Results retain actual
model XML/hash, primary/fresh replay samples/hashes, measurements, contacts, strict
checks and verdict. The native reader regenerates only the registered model, never
executes a supplied XML/controller path. Local hashes are not remote signatures or
protection against an adversarial same-UID process rewriting the entire store.

Source jobs have a 60-second cooperative execution deadline, no automatic retries,
and at most 16 retained jobs per local workbench. An interrupted/failed admission
keeps its identity consumed. A deliberate new run needs a new explicit action.
Compiler/native source drift blocks execution or current read-back; old evidence
is preserved, not silently requalified. Cross-version source migration is not
implemented; use a separately reviewed new project rather than altering old proofs.

## Genuine AI status

The current offline algorithm is a fixed supported stopping-distance proposal,
not general language understanding or a successful GPT run. Actual model-authored
source may be submitted only through the same strict source tool contract under a
future explicit qualification. Existing provider adapters/accounting are preserved.
No provider client, credential, paid reservation or consent is accessed here.
A valid proposal, human-approved source and a physically passing execution are
three different claims and must be qualified separately.
