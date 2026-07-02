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
| Performance | Synthetic regression benchmark plus real CellProfiler benchmark | L3 CellBinDB benchmark PASS: 673.38x speedup, 14.92% RSS ratio |
| Observability | Clear stderr summary, actionable error context, and runtime diagnostics | Runtime `doctor` implemented; richer structured logs pending |
| Release | GitHub release workflow and checksums | Implemented for tagged macOS/Linux builds |
| Documentation | Supported inputs, unsupported scope, parity gaps, and production caveats documented | L3 evidence documented; L4 workflow caveats remain |

## Production Hardening Backlog

Priority order:

1. Run `python3 benchmark/run_cellbindb_oracle.py --threads 8` before release candidates.
2. Run an external lab workflow trial against real batch handoff files.
3. Broaden the supported measurement subset beyond the current intensity and size/shape columns.

## Claim Policy

Until every required gate is complete, documentation may claim the narrow L3 benchmark result, but must not say "production-ready" or "replaces CellProfiler workflows" without an external workflow trial.
