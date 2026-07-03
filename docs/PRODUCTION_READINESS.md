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
| CLI safety | Validate required paths and image-table schema, reject empty image tables, reject invalid thread counts, protect existing outputs unless explicitly overwritten | Implemented for current CLI |
| Output safety | Avoid partial final `Image.csv` / `Objects.csv` files on failure and prevent diagnostic reports from masquerading as measurement CSVs | Implemented through staging writes plus final-target and report-target preflight checks for current CLI |
| Correctness | CellProfiler oracle parity report for public data | L2 ExampleHuman PASS and L3 CellBinDB direct-mask PASS for the current measurement subset |
| Testing | Unit, integration, CLI failure-mode, Clippy, Python helper tests, benchmark smoke tests, and scheduler-ready L3 validation | Implemented for current CLI; CellBinDB L3 validation script and L3 provenance/hash gate added |
| Performance | Synthetic regression benchmark plus real CellProfiler benchmark | L3 CellBinDB benchmark PASS: 609.82x speedup, 13.98% RSS ratio |
| Workflow fit | CellProfiler-style object CSV handoff can run without manual CSV editing | CellBinDB L4-preflight handoff PASS with 35 contract columns; external trial template and release-gate external trial report plus clean-git current-or-compatible commit metadata, manifest-declared step command/runtime/detail/artifact coverage, and one-to-one artifact hash validation implemented |
| Observability | Clear stderr summary, actionable error context, runtime diagnostics, and machine-readable success/failure metadata | Runtime `doctor`, optional `measure --summary-json`, and optional `measure --error-json` with basic error codes implemented |
| Release | GitHub release workflow and checksums | `v0.1.0-rc.1` prerelease PASS: GitHub Actions built Linux/macOS archives, checksums verified, macOS packaged `doctor` commit verified; release gate reports now record git commit, dirty-worktree status, arguments, optional L3 provenance/hash validation, and a production-claim audit |
| Documentation | Supported inputs, unsupported scope, parity gaps, and production caveats documented | L3 evidence and release gate documented; L4 workflow caveats remain |

## Production Hardening Backlog

Priority order:

1. Copy `benchmark/handoff/external_lab_template.json`, fill the required external evidence block, run an external lab workflow trial against real batch handoff files, validate the resulting report with release gate, and package it with `benchmark/package_external_trial.py` for review/signoff.
2. Promote the release-candidate validation path from `v0.1.0-rc.1` to a stable `v0.1.0` tag after external workflow evidence is accepted by `benchmark/release_gate.py --external-trial-json`, then verify it with `benchmark/release_gate.py --verify-github-release v0.1.0 --github-release-kind stable`.
3. Broaden the supported measurement subset beyond the current intensity and size/shape columns.

After items 1 and 2 are complete, run the final production wrapper:

```bash
python3 benchmark/run_production_gate.py \
  --external-trial-json path/to/external/handoff_trial.json \
  --external-trial-root path/to/external \
  --external-evidence-package-dir path/to/evidence-packages/external-l4-trial \
  --github-release-tag v0.1.0
```

This is the single command intended to produce the final production-claim report. It requires a stable non-RC tag, checks that the external evidence paths exist before an actual run, and delegates to `benchmark/release_gate.py --require-production-claim`, so production remains incomplete until that command passes with real external evidence and a stable release.

If the external L4 evidence is ready before the stable release, run the same wrapper with `--local-evidence-preflight-only` to validate only the external trial report and evidence package and write a local evidence-preflight JSON/Markdown report. That report is machine-labeled `NOT_PRODUCTION_CLAIM`, `evidence_scope=LOCAL_EXTERNAL_L4_PREFLIGHT`, and `final_evidence_acceptable=false`, lists the skipped final checks, and binds the key evidence files by size and SHA-256. Passing that preflight reduces L4 packaging risk, but it does not satisfy the stable-release or final production-claim gates.

Use `benchmark/run_production_gate.py --verify-local-evidence-preflight-report path/to/local-evidence-preflight.json` to re-check the saved local evidence-preflight report's schema, claim-scope labels, and final-evidence rejection flag during review. Add `--verify-local-evidence-preflight-files` when the referenced evidence files are available so the recorded input file sizes and SHA-256 hashes are recomputed. Add `--require-local-evidence-preflight-pass` for review/signoff.

## Claim Policy

Until every required gate is complete, documentation may claim the narrow L3 benchmark result and the supported-column handoff preflight, but must not say "production-ready" or "replaces CellProfiler workflows" without an external workflow trial report and evidence package accepted by release gate.

The release-gate report's `production_claim_status` is the machine-readable summary for this policy. It is expected to remain `INCOMPLETE` until clean-git, L3 provenance, external L4 workflow, external L4 evidence package, and stable GitHub release checks are all present and passing in the same report. Reports also include `missing_or_failed_checks`, which names the exact production-claim checks still blocking a production-ready or CellProfiler-replacement claim. Final production/stable-release validation should run release gate with `--require-production-claim`; that mode fails the overall report unless the production-claim audit is `PASS`.
