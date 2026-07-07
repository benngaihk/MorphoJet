# MorphoJet

Language: English | [简体中文](README.zh-CN.md)

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

GitHub release verification checks release tag identity, release URL, GitHub release ID/API identity, author, target commit-ish, UTC created/published timestamps, draft/prerelease/immutable state, stable non-prerelease semver tags for stable gates, exact release/download asset sets, records schema version, verifier identity, UTC generation timestamp, canonical verifier `argv`, the full 40-character tag commit, the 12-character `doctor` commit prefix, asset lists, and GitHub asset metadata in JSON, requires GitHub assets to be `uploaded`, preserves unique GitHub asset IDs, API URLs, and UTC created/updated timestamps, applies the release identity and verifier-command checks during live verification and saved-report review, binds saved release and asset URLs to the recorded repo/tag/asset names, rejects saved reports that do not match an explicit `--expect-repo` when supplied, requires saved reports to record absolute `out_dir`, `--out-dir`, and `--json-out` paths with `--json-out` bound to the report path under review, records and re-checks GitHub asset size and `sha256:` digest metadata against downloaded files and archive summaries, verifies `.sha256` digest values, checksum target filenames, package contents, and requires a compatible archive to pass `morphojet doctor` with the expected commit prefix.

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

For a fast audit of already-generated L3 artifacts, run `python3 benchmark/release_gate.py`. Release-gate JSON and Markdown reports include the run timestamp, git commit, dirty-worktree status, invoked arguments, top-level `production_claim_status`, and top-level `missing_or_failed_checks`. The gate also scans source documentation for unsupported production-ready or CellProfiler-replacement claims and refuses report output paths that would overwrite or create files inside external evidence inputs, packaged evidence files including `readiness.json`, reviewer reports, or the GitHub release verifier report. Formal release reports should include `--require-l3-provenance`, which checks the CellBinDB provenance file written by a full non-`--skip-cellprofiler` L3 run and re-hashes the recorded artifacts. Final production or stable-release gates should add `--require-production-claim`, which fails unless the external L4 workflow trial, matching evidence package, saved external reviewer reports, live stable release, and saved stable-release verifier report checks are all present and passing.

To re-check a saved release-gate JSON report during review:

```bash
python3 benchmark/verify_release_gate_report.py benchmark/results/release-gate/report.json
python3 benchmark/verify_release_gate_report.py benchmark/results/release-gate/report.json --verify-git-commit
python3 benchmark/verify_release_gate_report.py benchmark/results/release-gate/production-claim.json --require-report-pass --require-clean-git-metadata --verify-git-commit --require-production-claim-pass
```

The saved release-gate verifier checks top-level summary fields against `production_claim_audit`, validates metadata and gate-entry schemas, requires `metadata.generated_at_utc` to be UTC, requires the expected production-audit check list, can verify the recorded git commit is reachable, can require clean-git metadata, rejects `github_release_kind=stable` metadata unless it is paired with a stable release tag, and rejects production PASS reports that omit required clean-git, L3 provenance, external L4, saved external reviewer, stable GitHub release, or saved stable-release verifier gates. Production PASS reports must also carry metadata and `metadata.argv` proving the final flags, absolute external L4 paths, saved reviewer/verifier report paths, and stable release tag/kind were used; the verifier checks this both ways so recorded metadata must appear in `argv` and key production arguments in `argv` must be reflected back into metadata. Saved release-gate reports also reject relative production evidence paths and relative path-valued `metadata.argv` entries for external L4 evidence, reviewer reports, and explicit `--out-json` / `--out-md` outputs; when `--out-json` is recorded it must match the report file under review. Boolean metadata flags such as clean-git, L3 provenance, L3 rerun, and release-archive build must have their matching gates. External L4 metadata paths must have matching validation gates. `metadata.verify_github_release` must have a matching live GitHub release gate whose command binds the same tag, stable/prerelease expectation, and verifier JSON output. Saved reviewer-report metadata must have the matching saved-reviewer gate, and those gates must preserve the fail-closed verifier commands bound to metadata paths, including file rechecks, PASS requirements, package `--require-trial-json`, stable GitHub release checks, git commit verification, expected release tag binding, and expected repo binding. `release_gate.py` canonicalizes those recorded path values to absolute paths when it writes a report.

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

The wrapper requires a stable non-RC tag, fail-fast checks that the external trial JSON, trial root, evidence package directory, and any supplied reviewer verification reports exist for actual runs, fail-closed re-checks supplied saved verifier reports with `--verify-report-files --require-report-pass`, requires saved package reviewer reports to include `trial_json`, requires saved trial/package reviewer reports to match the current external inputs, requires `--require-stable-report`, `--verify-git-commit`, the final tag, and the `benngaihk/MorphoJet` repo for a supplied saved GitHub release verifier report, and passes those reviewer reports through to `benchmark/release_gate.py` so the final JSON/Markdown includes the reviewer-report gates alongside clean-git, L3 provenance, external L4 trial, external L4 evidence package, live stable GitHub release, and `--require-production-claim` checks. If that release gate passes, the wrapper immediately re-checks the saved final report with `benchmark/verify_release_gate_report.py --require-report-pass --require-clean-git-metadata --verify-git-commit --require-production-claim-pass --expect-missing-checks none`. Direct `benchmark/release_gate.py` saved reviewer-report gates also bind saved external trial/package reports to the current external evidence inputs, re-check saved GitHub release reports with `--verify-git-commit`, require `--expect-repo benngaihk/MorphoJet`, and bind saved GitHub reports to `--verify-github-release` when a live tag is supplied. The saved GitHub release verifier report is an audit artifact and does not replace the live stable-release check. Use `--dry-run` to inspect the assembled release-gate and final-report verifier commands without requiring those external paths yet.

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

This preflight writes `benchmark/results/release-gate/local-evidence-preflight.json` and `.md` by default, records `claim_status=NOT_PRODUCTION_CLAIM`, `evidence_scope=LOCAL_EXTERNAL_L4_PREFLIGHT`, and `final_evidence_acceptable=false`, lists the final production checks it intentionally skips, records a canonical `metadata.argv` for the effective wrapper inputs with absolute evidence/report paths, and records size/SHA-256 summaries for the trial JSON, packaged trial JSON, packaged readiness JSON, package zip, zip checksum file, and any supplied external L4 saved reviewer verification reports using absolute paths. The packaged readiness JSON summary also records the canonical readiness `package_name` (or `null`) so local preflight review is bound to the package identity captured by the external L4 readiness report. It only checks the external L4 trial report, evidence package, and supplied external L4 reviewer reports before the final stable-release gate is available; `--github-release-verification-report` is rejected in local preflight mode because stable release verification is intentionally out of scope.

Re-check a saved local evidence preflight report without the original evidence paths:

```bash
python3 benchmark/run_production_gate.py \
  --verify-local-evidence-preflight-report benchmark/results/release-gate/local-evidence-preflight.json \
  --verify-local-evidence-preflight-files \
  --verify-local-evidence-preflight-gates \
  --require-local-evidence-preflight-pass
```

The verifier also confirms that the report's `metadata.generated_at_utc` is UTC, `metadata.git_commit` is a reachable commit in the current checkout, metadata evidence paths, input artifact paths, and path-valued `metadata.argv` entries are absolute, and `metadata.argv` matches the recorded preflight inputs so path, stable-tag, local-preflight flag, duplicate critical flags, and missing flag values cannot be tampered independently from metadata. It rejects packaged readiness package-name tampering when the referenced package is available. With `--verify-local-evidence-preflight-files`, it recomputes the packaged readiness JSON package-name summary in addition to file sizes and SHA-256 hashes. With `--verify-local-evidence-preflight-gates`, it reruns the recorded external L4 trial, package, and saved reviewer-report gates from the report metadata and rejects stale gate status/detail/command data.

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

Use `benchmark/handoff/external_lab_template.json` as the starting point for real lab handoff files. To create a concrete workspace with the template manifest, input directories, bilingual English/Chinese README files, and the exact plan-verification/validation/readiness/readiness-verification/run/package/preflight/preflight-verification/stable-release/saved-release-verification/final-production/final-report-verification commands, run `python3 benchmark/prepare_external_l4_trial.py --workspace path/to/external-trial`; `trial_plan.json` records UTC `generated_at_utc`, canonical generator `argv`, absolute template/workspace/manifest paths, template size, and template SHA-256; re-check it with `benchmark/prepare_external_l4_trial.py --verify-plan path/to/external-trial/trial_plan.json --verify-plan-files`. Plain `--verify-plan` regenerates the expected command set from the saved absolute manifest path, workspace, and package name so command tampering is caught even without local file access; `--verify-plan-files` also recomputes template hash data and checks manifest presence plus English and Chinese README contents. The generated READMEs list that `verify_plan` command first so reviewers can confirm the saved plan before running any external L4 step. If `--package-name` is supplied, the generated readiness, readiness-verification, package, package-verification, local-preflight, local-preflight-verification, stable-release-verification, saved-stable-release-verification, final-production-gate, and final-report-verification commands all bind to the same slug. The generated workspace is only a preparation scaffold and is not external evidence, and preparation refuses stale execution outputs such as old trial reports, reviewer reports, preflight reports, stable-release verifier outputs, production-claim reports, or package outputs even when `--overwrite` is used for scaffold files. Before executing a real trial, run `python3 benchmark/check_external_l4_readiness.py --workspace path/to/external-trial --json-out path/to/external-trial/readiness.json` to require filled external evidence, required input files, MorphoJet Objects.csv and expected CellProfiler CSV headers/rows matching the declared object set and channels, empty manifest-declared trial output paths, empty planned reviewer/preflight report paths, safe report outputs, and clear package output paths; the readiness `--json-out` path is also blocked from overwriting or creating files inside the manifest, declared inputs, trial outputs, planned reviewer/preflight reports, or package outputs, and this report records UTC `generated_at_utc`, canonical checker `argv`, absolute workspace/manifest paths, the canonical package-name slug or null, absolute saved `--json-out`, and `NOT_PRODUCTION_CLAIM`; re-check it with `benchmark/check_external_l4_readiness.py --verify-report path/to/readiness.json --verify-report-files --require-ready` before running the trial so the saved package-name field and argv binding are both validated. External workflow trials must fill the full `external_evidence` block, including non-placeholder acceptance criteria plus `reviewer_name_or_role`, UTC `reviewed_at_utc`, and `signoff_statement`, and pass validation with `--require-external-evidence`; the generated run command also passes `--readiness-report path/to/readiness.json`, so the runner verifies the READY report before execution and the trial report preserves that readiness report's path, size, SHA-256, status, claim label, workspace, manifest, package-name binding, and UTC generation time. The trial report also preserves clean-git generator metadata for the current or compatible commit, UTC `metadata.generated_at_utc`, the source manifest path, canonical `metadata.argv` matching manifest, sorted `--var` values, `--out-json` bound to the current trial JSON path, `--out-md`, exactly one `--readiness-report`, and exactly one `--require-external-evidence` flag, those fields, the rendered manifest snapshot, exact manifest-declared step command/runtime/detail and artifact coverage, and one SHA-256/size provenance entry for each listed artifact for L4 review. Reviewers can directly re-check the trial report with `benchmark/verify_external_trial_report.py path/to/handoff_trial.json --trial-root path/to/external --json-out path/to/trial-verification.json`, then re-check the saved verifier JSON with `--verify-report path/to/trial-verification.json --verify-report-files --require-report-pass`; the saved verifier report records and validates its schema version, verifier identity, UTC generation timestamp, canonical verifier `argv`, absolute source trial/root paths, source trial JSON size/SHA-256, bound readiness report size/SHA-256/package-name summary, and every resolved trial artifact size/SHA-256, requires absolute verifier `argv` trial JSON, `--trial-root`, and saved `--json-out` path values with `--json-out` bound to the saved report path under review, rejects reviewer report outputs that would overwrite or create files inside the source trial JSON, bound readiness report, or declared artifacts, and re-hashes those summaries during file recheck. After release gate accepts a real external trial, use `benchmark/package_external_trial.py` to create a reviewable evidence package with the trial report, readiness report, rendered manifest, external evidence, artifact manifest, copied artifacts, zip archive, and zip checksum. Reviewers can directly re-check that package with `benchmark/verify_external_evidence_package.py path/to/package --trial-json path/to/handoff_trial.json --json-out path/to/package-verification.json`, then re-check the saved package verifier JSON with `--verify-report path/to/package-verification.json --verify-report-files --require-report-pass --require-trial-json`; this saved verifier report has the same schema/verifier/UTC timestamp/argv audit fields, records absolute package/source-trial paths plus size/SHA-256 summaries for the source trial JSON, package review files including the copied `readiness.json` size/SHA-256/package-name summary, zip, and checksum file, requires absolute verifier `argv` package directory, `--trial-json`, and saved `--json-out` path values with `--json-out` bound to the saved report path under review, rejects reviewer report outputs that would overwrite or create files inside source/package evidence files, re-hashes those summaries during file recheck, and must be bound to the source trial JSON for production signoff. The generated local-preflight-verification command rechecks the saved local evidence preflight report with file rehashing, gate reruns, package-readiness package-name recomputation, and PASS enforcement before the stable-release gate exists. After the stable `v0.1.0` release is published, the generated stable-release-verification command writes the saved GitHub release verifier report outside the download directory, the generated saved-stable-release-verification command rechecks downloaded files, stable-report identity, git commit/tag resolution, expected tag, and expected `benngaihk/MorphoJet` repo, and the generated final-production-gate command supplies the trial report, evidence package, trial/package reviewer reports, saved GitHub release verifier report, stable tag, and final output paths to `benchmark/run_production_gate.py`; the wrapper itself then re-checks `production-claim.json` with `benchmark/verify_release_gate_report.py --require-report-pass --require-clean-git-metadata --verify-git-commit --require-production-claim-pass --expect-missing-checks none`, and the generated final-report-verification command repeats that check as a standalone saved-plan step. The production wrapper also checks that supplied saved trial/package reviewer reports point to the same `--external-trial-json`, `--external-trial-root`, and `--external-evidence-package-dir` used for the current run. Saved plan, readiness, trial-reviewer, package-reviewer, local-preflight, GitHub release, and final release-gate report verifiers reject `generated_at_utc` values whose offset is not UTC, and external L4 validators reject reviewer `reviewed_at_utc` values whose offset is not UTC. The package README must preserve the trial/signoff fields, dataset source, execution environment, reviewer identity/role, review timestamp, signoff statement, trial generation time, readiness status/time/hash/package name, exact validation detail, and every acceptance criterion; the artifact manifest must preserve UTC `packaged_at_utc`, canonical packager `argv` matching the source trial JSON, trial root, output directory, and package name, absolute source trial JSON/root metadata, source trial JSON size/SHA-256, the bound readiness report summary plus copied `readiness.json`, review-file size/SHA-256 entries, release-gate input matching, the exact external trial PASS detail, and map each source artifact to a unique package path; the package zip must contain exactly the required package files and declared artifacts with no duplicate or extra entries and with bytes matching the package directory, and its checksum file must contain a valid SHA-256 digest targeting that zip filename. Final production release gates should validate both the trial report and package with `--external-trial-json` and `--external-evidence-package-dir`.

Evidence packages now include both `README.md` and `README.zh-CN.md`. Both README files are listed in `artifact_manifest.review_files`, included in the package zip, checked by release gate for required signoff fields, and recorded by the standalone package verifier so file rechecks catch tampering in either language.

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

Production-readiness gates are tracked in [docs/PRODUCTION_READINESS.md](docs/PRODUCTION_READINESS.md). MorphoJet has a passing L3 public direct-mask benchmark, a verified `v0.1.0-rc.1` prerelease, and an L4-preflight handoff harness, but should not be described as production-ready until a real external L4 workflow trial, the matching evidence package, saved external reviewer reports, a live stable GitHub release, and a saved stable-release verifier report all pass in the same production-claim gate.
