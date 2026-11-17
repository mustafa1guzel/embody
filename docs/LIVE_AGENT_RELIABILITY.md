# Live agent reliability — v0.9.2.1

The tool-to-answer pipeline now preserves usable physical evidence during failures,
shares one finite execution deadline, and records safe request lifecycle timings.
**Offline verification passes; a complete genuine model explanation remains
unqualified.** No new paid request or native rollout was made for this update.

## What the genuine qualification established

GPT-5.4 genuinely selected `inspect_result({})` and received the approved historical
rail measurement: approximately 0.003 m minimum clearance against 0.050 m required,
zero contacts and zero final speed. This remains a physical FAIL. Its continuation
was dispatched but timed out locally; no final explanation or second response ID
was received. Credential acceptance is established for the first request only.

The completed request reported 1,250 input and 25 output tokens, including nine
reasoning tokens within that output. Calculated usage cost was $0.003500. The
second request retains $0.184320 unknown exposure; session accounting is $0.187820,
not an invoice. Neither timeout nor local worker termination proves remote
cancellation, absence of storage, or absence of billing. The consumed consent
cannot be reused. No provider reconciliation network request was made.

The retained run measured 10,857 saved-state `mj_forward` calls across three cold
processes, with zero integration. Count/source readback supports 10,818 per-sample
checks (six rail cases × 601 samples × three processes), 18 native model initial
checks and 21 scene initial checks. Native sample/contact/replay checks are
substantive; the complete count is not labelled waste. Public agent inspection
now bypasses unrelated catalog discovery and scene construction while retaining
complete pinned package, artifact, sample and replay verification. Existing native
reader validation and byte/source-bound in-process reuse remain unchanged.

Parent monotonic elapsed was 86.440016 s; the separately bounded worker/parent
wall timestamps span 419.228399 s. These do not measure identical endpoints.
The monotonic implementation is `mach_absolute_time()`. Sleep, time adjustment and
logging behavior remain hypotheses; the cause is unresolved. No old 180-second
wall-window PASS or FAIL is inferred from these inconsistent records.

## Changes and limits

- Parent and worker share the same monotonic start/window. Absolute consent expiry
  also applies; drift above one second stops further dispatch. HTTP timeout is
  clamped to remaining authority, with no retries or reset of the window.
- The existing trace records admission, dispatch, response, reported-usage settlement,
  tool timing, continuation readiness and terminal status. A fresh non-authority
  UUID supplies `X-Client-Request-Id`; exception text and credentials are excluded.
  This follows the [official request-correlation guidance](https://developers.openai.com/api/reference/overview#debugging-requests).
- Inspect requires one genuine tool inspection; the continuation requests only a
  final answer. It retains server-side response continuity and `store:true`.
- Bounded saved tool receipts are schema/context/evidence checked after a worker
  interruption. A supervisor stop cannot become a successful execution result.
- The existing assistant shows incomplete reasoning, unresolved accounting and
  actual deterministic tool evidence with links even without a model explanation.
  Offline transport behavior is prominently labelled; no fallback prose poses as AI.
- Rail Inspect fits two 32,768-input / 4,096-output reservations: $0.28672 maximum
  under a $0.30 cap. Its full continuation envelope is checked before preparation.
  Rover keeps its larger existing envelope. See [all profiles](ENGINEERING_AGENT.md).

Protected provider/credential/budget implementations, both native source identities,
physical predicates, historical recordings and existing project heads are unchanged.
Broader application binding changes; no old qualification is inherited by this code.
The local operator remains trusted; this is not remote signed financial authority.
A tool's cooperative timeout is backed by the supervised worker, not a sandbox.
Free interpretation prose is not a semantic truth proof or physical certification.

## Verification

| Check | Pass | Fail | Skip | Deselected |
|---|---:|---:|---:|---:|
| Supported non-native Python policy | 466 | 0 | 0 | 0 |
| Focused deadline/reliability/live-bridge tests, overlapping | 55 | 0 | 0 | 0 |
| Frontend, 49 files | 335 | 0 | 0 | 0 |
| Typecheck / production build | PASS | 0 | — | — |
| Actual installed-Chrome main journey + partial-evidence capture | PASS | 0 final | — | — |

Native integration/VM suites are outside the explicit supported file policy and
are not counted as passes or deselections. The build retains its large-chunk warning.
A separately approved bounded saved-state QA scope allowed retained rail/rover
checks and existing disposable fixtures, not new integration. Guarded provider,
integration, VM and application entry points recorded zero attempts. The initial
focused compilation path lacked the additional forward counter; a conservative
1,000-entry allowance and earlier window start cover it, separately from observed
calls. The exact counter and permission receipt remain private, without claiming
that allowance is a measured count.

Chrome used genuine saved samples and Python-only explicitly labelled transport
doubles. It verified continuation timeout with retained evidence, no fabricated
answer/retry, unknown accounting, cancellation, context switching, actual saved
rail/rover playback, diagnostics, unapplied numerical proposals and separate
native authorization. Final UI captures show the actual failure/evidence card.
Earlier private harness diagnostics are retained: malformed pytest arguments,
an unsupported screenshot slider value and a reused private command number. No
engineering validator was weakened to address them. No real provider call was used.

## Next genuine qualification — prepare only after a reviewed commit

1. Review the feature diff and verification; commit only through the user's own
   decision. Record the full resulting HEAD and require a clean working tree.
2. Preserve all old leaf ledgers, including the unknown second-request reservation.
   Independently review current exposure. Provider-dashboard/support reconciliation
   is a separate read-only action; aggregate usage cannot establish an individual
   request's cost. Do not edit or release the old ledger entry.
3. Using the existing trusted prepare command, select the exact public historical
   rail case and freeze the actual question, compact context, one strict tool,
   structured final schema, installed versions, current source map and committed
   base. No fixture answer, source files, secrets or private history enter context.
4. Freeze at most two GPT-5.4 low Responses requests, the verified rail Inspect
   token profile/cap, one shared 180-second deadline, 30-second HTTP cap clamped
   to remaining time, one-second drift stop, no retry/fallback, and zero native,
   VM, controller or application effects. Explicitly disclose `store:true`,
   server-side continuation and random public request-correlation IDs.
5. Recheck current official pricing, actual envelope, historical exposure, expiry,
   unused nonce, canonical digest and exact bytes. Present that new concrete
   manifest for fresh explicit approval before any client creation or dispatch.

No new financial consent is frozen against the current dirty pre-commit tree.
There is no authority to run another qualification today. Preparation is ready for
feature review; a full live answer, old billing outcome and timing cause remain
unresolved. Suggested commit:
`fix: harden engineering agent continuation and verification latency`.
