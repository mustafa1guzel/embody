# Release notes

## v0.2.1 — Unreleased

### Physics Regression Explorer

- Compare scenarios A/B/C across the three genuine recorded rail-controller revisions in the existing workbench.
- Keep historical verdicts immutable while exploring hypothetical clearance, final-speed, sampled-settling and contact-episode requirements. Explain failure criteria and rank remaining margins within one physical unit.
- Overlay actual saved trajectories, inspect exact timestamps and read checksum-matched controller sources/diffs. Report unavailable data explicitly.
- Summarize observed controller improvements and remaining failures using deterministic analysis, without a model call, new simulation or proposal application.

Open **Simulate → Open Physics Regression Explorer**, or **Advanced workspaces → Physics Explorer**. See [verification and usage](docs/VERIFICATION.md#physics-regression-explorer). This finite recorded study is not proof of real-world safety or universal robustness. No new charting dependency, backend endpoint, protected execution change or historical-data modification is included.

Validation: 63 targeted frontend tests passed (30 new explorer tests and 33 nearby regressions), TypeScript typecheck and production build passed. Actual installed-Chrome QA verified navigation, thresholds, immutable verdicts, controller checksums, overlays/timestamps, keyboard interaction and desktop/narrow layouts. No new physics simulation or VM qualification was run.
