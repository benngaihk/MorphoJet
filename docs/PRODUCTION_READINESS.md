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
| CLI safety | Validate required paths, reject empty image tables, reject invalid thread counts, protect existing outputs unless explicitly overwritten | In progress |
| Output safety | Avoid partial final `Image.csv` / `Objects.csv` files on failure | Not complete |
| Correctness | CellProfiler oracle parity report for public data | Not complete |
| Testing | Unit, integration, CLI failure-mode, and benchmark smoke tests in CI | In progress |
| Performance | Synthetic regression benchmark plus real CellProfiler benchmark | Synthetic only |
| Observability | Clear stderr summary and actionable error context | In progress |
| Release | GitHub release workflow and checksums | Not complete |
| Documentation | Supported inputs, unsupported scope, parity gaps, and production caveats documented | In progress |

## Production Hardening Backlog

Priority order:

1. Add CLI `--overwrite` and fail when output files already exist.
2. Validate image table before measurement: non-empty, unique `ImageNumber`, readable image and mask paths.
3. Write outputs through temporary files and rename into place only after success.
4. Add CLI integration tests for success, overwrite protection, invalid paths, empty table, duplicate image numbers, and dimension mismatch.
5. Add `cargo clippy` to CI.
6. Add release packaging workflow for macOS/Linux binaries and checksums.
7. Add a pinned public CellProfiler oracle benchmark.
8. Add structured benchmark metadata and RSS capture.

## Claim Policy

Until every required gate is complete, documentation should say "prototype", "validation harness", or "M0 candidate", not "production-ready".
