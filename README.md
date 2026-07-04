# MorphoJet

CellProfiler-compatible fast batch measurements for microscopy images.

MorphoJet is not a CellProfiler replacement. CellProfiler remains the oracle for pipeline authoring and full feature behavior; MorphoJet focuses on running stable measurement-only batches faster and with lower deployment friction.

## Current Scope

M0 supports an intentionally small path:

- 2D intensity images readable by the Rust `image` crate, including common TIFF files.
- Existing label masks where `0` is background and positive integer labels are objects.
- Image table CSV with `ImageNumber`, `ImagePath`, `MaskPath`, and optional `Channel` plus metadata columns.
- `Image.csv` and `Objects.csv` outputs.
- Existing outputs are protected unless `--overwrite` is passed.
- Duplicate image table headers and metadata columns that collide with MorphoJet output columns such as `Count_Objects`, `Width`, or `Height` are rejected.

Not supported yet:

- GUI.
- Full `.cppipe` parsing.
- Segmentation, thresholding, illumination correction, tracking, 3D, WSI, or OME-Zarr.
- Full CellProfiler feature parity.

## Quick Start

```bash
cargo run -p morphojet -- measure \
  --images images.csv \
  --out measurements \
  --threads 16 \
  --cellprofiler-compatible \
  --summary-json measurements/run-summary.json \
  --overwrite
```

## Release Builds

Tagged releases (`v*`) build macOS and Linux CLI archives with SHA-256 checksums through GitHub Actions.

To validate the local release archive shape before tagging:

```bash
python3 benchmark/release_gate.py --build-release-artifact --release-version local
```

Local archive verification checks the archive checksum digest and checksum target filename before extracting the package.

To verify a published GitHub release candidate:

```bash
python3 benchmark/release_gate.py --verify-github-release v0.1.0-rc.1
```

After external workflow evidence has passed, verify a stable non-RC release with:

```bash
python3 benchmark/release_gate.py --verify-github-release v0.1.0 --github-release-kind stable
```

GitHub release verification checks release tag identity, release URL, stable non-prerelease semver tags for stable gates, exact release/download asset sets, records schema version, verifier identity, generation timestamp, asset lists, and GitHub asset metadata in JSON, verifies `.sha256` digest values, checksum target filenames, package contents, and requires a compatible archive to pass `morphojet doctor` with the expected commit.

## Diagnostics

```bash
morphojet doctor
```

The `doctor` command prints version, commit, platform, thread, and executable-path context for reproducible bug reports.

For batch monitoring, `measure --summary-json path/to/run-summary.json` writes a machine-readable run summary after successful measurement. The summary includes version, commit, platform, elapsed seconds, image row count, object row count, observed channels/object sets, output paths, compatibility mode, and effective thread count. Existing summary files are protected by the same `--overwrite` rule as measurement CSVs.

For failure monitoring, `measure --error-json path/to/error.json` writes a machine-readable failure report when measurement exits non-zero after argument parsing. The report includes version, commit, command, stable error code, top-level message, and cause chain while preserving stderr output for humans. Error reports are protected by `--overwrite`, must not resolve to `Image.csv` or `Objects.csv`, and must resolve to a different path from `--summary-json`.

`images.csv`:

```csv
ImageNumber,ImagePath,MaskPath,Channel,Plate,Well,Site
1,images/A01_s1_DAPI.tif,masks/A01_s1_cells.tif,DAPI,P001,A01,1
2,images/A01_s1_CD3.tif,masks/A01_s1_cells.tif,CD3,P001,A01,1
```

## Smoke Benchmark

```bash
python3 corpus/generate_smoke.py --images 16
benchmark/run.sh benchmark/data/smoke/images.csv benchmark/results/smoke
python3 benchmark/summarize.py benchmark/results/smoke
```

Real CellProfiler oracle benchmark setup is documented in [docs/BENCHMARK.md](docs/BENCHMARK.md).

Before a release candidate, run:

```bash
python3 benchmark/release_gate.py --require-clean-git --require-l3-provenance --run-l3 --build-release-artifact --release-version rc-preflight
```

For a fast audit of already-generated L3 artifacts, run `python3 benchmark/release_gate.py`. Release-gate JSON and Markdown reports include the run timestamp, git commit, dirty-worktree status, invoked arguments, top-level `production_claim_status`, and top-level `missing_or_failed_checks`. The gate also scans source documentation for unsupported production-ready or CellProfiler-replacement claims. Formal release reports should include `--require-l3-provenance`, which checks the CellBinDB provenance file written by a full non-`--skip-cellprofiler` L3 run and re-hashes the recorded artifacts. Final production or stable-release gates should add `--require-production-claim`, which fails unless the external L4 workflow trial, matching evidence package, and stable release checks are also present and passing.

To re-check a saved release-gate JSON report during review:

```bash
python3 benchmark/verify_release_gate_report.py benchmark/results/release-gate/report.json
python3 benchmark/verify_release_gate_report.py benchmark/results/release-gate/report.json --verify-git-commit
python3 benchmark/verify_release_gate_report.py benchmark/results/release-gate/production-claim.json --require-report-pass --require-clean-git-metadata --verify-git-commit --require-production-claim-pass
```

The saved release-gate verifier checks top-level summary fields against `production_claim_audit`, validates metadata and gate-entry schemas, requires the expected production-audit check list, can verify the recorded git commit is reachable, can require clean-git metadata, and rejects production PASS reports that omit required clean-git, L3 provenance, external L4, or stable GitHub release gates. Production PASS reports must also carry metadata proving the final flags, external L4 paths, and stable release tag/kind were used.

For the final production claim, use the wrapper that assembles the required checks into one command:

```bash
python3 benchmark/run_production_gate.py \
  --external-trial-json path/to/external/handoff_trial.json \
  --external-trial-root path/to/external \
  --external-evidence-package-dir path/to/evidence-packages/external-l4-trial \
  --external-trial-verification-report path/to/external/trial-verification.json \
  --external-evidence-package-verification-report path/to/evidence-packages/package-verification.json \
  --github-release-verification-report path/to/github-release/verification.json \
  --github-release-tag v0.1.0
```

The wrapper requires a stable non-RC tag, fail-fast checks that the external trial JSON, trial root, evidence package directory, and any supplied reviewer verification reports exist for actual runs, fail-closed re-checks supplied saved verifier reports with `--verify-report-files --require-report-pass`, requires saved package reviewer reports to include `trial_json`, requires `--require-stable-report` plus the final tag for a supplied saved GitHub release verifier report, and passes those reviewer reports through to `benchmark/release_gate.py` so the final JSON/Markdown includes the reviewer-report gates alongside clean-git, L3 provenance, external L4 trial, external L4 evidence package, live stable GitHub release, and `--require-production-claim` checks. The saved GitHub release verifier report is an audit artifact and does not replace the live stable-release check. Use `--dry-run` to inspect the assembled command without requiring those external paths yet.

Before the stable release exists, validate a completed external L4 trial and evidence package locally with the same release-gate validators:

```bash
python3 benchmark/run_production_gate.py \
  --external-trial-json path/to/external/handoff_trial.json \
  --external-trial-root path/to/external \
  --external-evidence-package-dir path/to/evidence-packages/external-l4-trial \
  --external-trial-verification-report path/to/external/trial-verification.json \
  --external-evidence-package-verification-report path/to/evidence-packages/package-verification.json \
  --github-release-tag v0.1.0 \
  --local-evidence-preflight-only
```

This preflight writes `benchmark/results/release-gate/local-evidence-preflight.json` and `.md` by default, records `claim_status=NOT_PRODUCTION_CLAIM`, `evidence_scope=LOCAL_EXTERNAL_L4_PREFLIGHT`, and `final_evidence_acceptable=false`, lists the final production checks it intentionally skips, and records size/SHA-256 summaries for the trial JSON, packaged trial JSON, package zip, zip checksum file, and any supplied external L4 saved reviewer verification reports. It only checks the external L4 trial report, evidence package, and supplied external L4 reviewer reports before the final stable-release gate is available.

Re-check a saved local evidence preflight report without the original evidence paths:

```bash
python3 benchmark/run_production_gate.py \
  --verify-local-evidence-preflight-report benchmark/results/release-gate/local-evidence-preflight.json \
  --verify-local-evidence-preflight-files \
  --verify-local-evidence-preflight-gates \
  --require-local-evidence-preflight-pass
```

The verifier also confirms that the report's `metadata.git_commit` is a reachable commit in the current checkout. With `--verify-local-evidence-preflight-gates`, it reruns the recorded external L4 trial, package, and saved reviewer-report gates from the report metadata and rejects stale gate status/detail/command data.

## CellProfiler-Style Wide Export

MorphoJet's native `Objects.csv` is a long table keyed by `ImageNumber`, `ObjectSet`, `ObjectNumber`, and `Channel`. For downstream tools that expect a CellProfiler object CSV such as `Cells.csv`, materialize the supported measurement subset into a wide table:

```bash
python3 benchmark/materialize_morphojet_cellprofiler_wide.py \
  --objects measurements/Objects.csv \
  --object-set Cells \
  --channels DNA,PH3 \
  --out measurements/Cells.wide.csv
```

Validate the supported wide columns against a CellProfiler object CSV with:

```bash
python3 benchmark/compare_cellprofiler_wide_subset.py CellProfiler/Cells.csv measurements/Cells.wide.csv --fail-on-gap
```

For a no-manual-CSV-edit handoff preflight, run a manifest-driven trial:

```bash
python3 benchmark/validate_handoff_manifest.py benchmark/handoff/cellbindb_supported_columns.json \
  --var base_dir=benchmark/results/cellbindb/oracle-full \
  --require-downstream-check \
  --check-files

python3 benchmark/run_handoff_trial.py benchmark/handoff/cellbindb_supported_columns.json \
  --var base_dir=benchmark/results/cellbindb/oracle-full \
  --out-json benchmark/results/cellbindb/oracle-full/handoff_trial.json \
  --out-md benchmark/results/cellbindb/oracle-full/handoff_trial.md
```

Use `benchmark/handoff/external_lab_template.json` as the starting point for real lab handoff files. External workflow trials must fill the full `external_evidence` block, including non-placeholder acceptance criteria plus `reviewer_name_or_role`, timezone-qualified `reviewed_at_utc`, and `signoff_statement`, and pass validation with `--require-external-evidence`; the trial report preserves clean-git generator metadata for the current or compatible commit, those fields, the rendered manifest snapshot, exact manifest-declared step command/runtime/detail and artifact coverage, and one SHA-256/size provenance entry for each listed artifact for L4 review. Reviewers can directly re-check the trial report with `benchmark/verify_external_trial_report.py path/to/handoff_trial.json --trial-root path/to/external --json-out path/to/trial-verification.json`, then re-check the saved verifier JSON with `--verify-report path/to/trial-verification.json --verify-report-files --require-report-pass`; the saved verifier report records and validates its schema version, verifier identity, and generation timestamp. After release gate accepts a real external trial, use `benchmark/package_external_trial.py` to create a reviewable evidence package with the trial report, rendered manifest, external evidence, artifact manifest, copied artifacts, zip archive, and zip checksum. Reviewers can directly re-check that package with `benchmark/verify_external_evidence_package.py path/to/package --trial-json path/to/handoff_trial.json --json-out path/to/package-verification.json`, then re-check the saved package verifier JSON with `--verify-report path/to/package-verification.json --verify-report-files --require-report-pass --require-trial-json`; this saved verifier report has the same schema/verifier/timestamp audit fields and must be bound to the source trial JSON for production signoff. The package README must preserve the trial/signoff fields, dataset source, execution environment, reviewer identity/role, review timestamp, signoff statement, trial generation time, exact validation detail, and every acceptance criterion; the artifact manifest must preserve absolute source trial JSON/root metadata, source trial JSON size/SHA-256, review-file size/SHA-256 entries, release-gate input matching, the exact external trial PASS detail, and map each source artifact to a unique package path; the package zip must contain exactly the required package files and declared artifacts with no duplicate or extra entries and with bytes matching the package directory, and its checksum file must contain a valid SHA-256 digest targeting that zip filename. Final production release gates should validate both the trial report and package with `--external-trial-json` and `--external-evidence-package-dir`.

## Parity Report

```bash
python3 tests/parity/normalize_measurements.py CellProfiler_Objects.csv normalized/cp_objects.csv
python3 tests/parity/normalize_measurements.py benchmark/results/smoke/Objects.csv normalized/morphojet_objects.csv
python3 tests/parity/compare_measurements.py normalized/cp_objects.csv normalized/morphojet_objects.csv --fail-on-gap
```

## M0 Gate

| Area | Target |
|---|---:|
| Object count parity | 100% |
| Core measurement parity | >=99% within documented tolerance |
| Wall-clock speedup | >=10x vs CellProfiler headless |
| Peak RSS | <=50% of CellProfiler |

See [docs/PARITY.md](docs/PARITY.md) for the current compatibility ledger.

Current milestone status is tracked in [docs/M0_STATUS.md](docs/M0_STATUS.md).

Industry-impact claims are gated by [docs/INDUSTRY_VALIDATION.md](docs/INDUSTRY_VALIDATION.md); synthetic benchmarks alone are not enough to claim CellProfiler replacement value.

Current validation results are summarized in [docs/VALIDATION_RESULTS.md](docs/VALIDATION_RESULTS.md).

The CellProfiler oracle validation checklist is in [docs/ORACLE_VALIDATION.md](docs/ORACLE_VALIDATION.md).

Production-readiness gates are tracked in [docs/PRODUCTION_READINESS.md](docs/PRODUCTION_READINESS.md). MorphoJet has a passing L3 public direct-mask benchmark, a verified `v0.1.0-rc.1` prerelease, and an L4-preflight handoff harness, but should not be described as production-ready until a real external L4 workflow trial, the matching evidence package, and a live stable GitHub release all pass in the same production-claim gate.
