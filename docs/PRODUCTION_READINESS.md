# Production Readiness

MorphoJet is not production-grade until this checklist is satisfied by current code, current tests, and current release artifacts.

## Release Contract

Production-grade means:

- A tagged release can be built from CI.
- macOS and Linux binaries are published with checksums.
- The CLI exits non-zero on invalid inputs and never silently overwrites existing measurement outputs.
- Output CSV files are complete for the successful run or absent for a failed run.
- Every public compatibility claim is tied to a parity report.
- Every performance claim is tied to a benchmark report.

## Required Gates

| Area | Gate | Current Status |
|---|---|---|
| CLI safety | Validate required paths, reject empty image tables, reject invalid thread counts, protect existing outputs unless explicitly overwritten | Implemented for current CLI |
| Output safety | Avoid partial final `Image.csv` / `Objects.csv` files on failure | Implemented through staging writes for current CLI |
| Correctness | CellProfiler oracle parity report for public data | L2 ExampleHuman PASS and L3 CellBinDB direct-mask PASS for the current measurement subset |
| Testing | Unit, integration, CLI failure-mode, Clippy, and benchmark smoke tests in CI | Implemented for current CLI |
| Performance | Synthetic regression benchmark plus real CellProfiler benchmark | L3 CellBinDB benchmark PASS: 597.54x speedup, 12.15% RSS ratio |
| Workflow fit | CellProfiler-style object CSV handoff can run without manual CSV editing | CellBinDB L4-preflight handoff PASS with 35 contract columns; manifest schema gate and external lab template implemented |
| Observability | Clear stderr summary, actionable error context, and runtime diagnostics | Runtime `doctor` implemented; richer structured logs pending |
| Release | GitHub release workflow and checksums | `v0.1.0-rc.1` prerelease PASS: GitHub Actions built Linux/macOS archives, checksums verified, macOS packaged `doctor` commit verified |
| Documentation | Supported inputs, unsupported scope, parity gaps, and production caveats documented | L3 evidence and release gate documented; L4 workflow caveats remain |

## Production Hardening Backlog

Priority order:

1. Promote the release-candidate validation path from `v0.1.0-rc.1` to a stable `v0.1.0` tag after external workflow evidence.
2. Copy `benchmark/handoff/external_lab_template.json` and run an external lab workflow trial against real batch handoff files.
3. Broaden the supported measurement subset beyond the current intensity and size/shape columns.

## Claim Policy

Until every required gate is complete, documentation may claim the narrow L3 benchmark result and the supported-column handoff preflight, but must not say "production-ready" or "replaces CellProfiler workflows" without an external workflow trial.
