# Development

## Toolchain

This repository uses stable Rust. On this workstation, Cargo is available at:

```bash
$HOME/.cargo/bin/cargo
```

## Verification

```bash
$HOME/.cargo/bin/cargo fmt -- --check
$HOME/.cargo/bin/cargo test
$HOME/.cargo/bin/cargo clippy --all-targets -- -D warnings
python3 -m py_compile benchmark/*.py corpus/generate_smoke.py tests/*.py tests/parity/*.py
python3 -m unittest discover -s tests
git diff --check
```

CI runs the same core path on GitHub Actions: Rust formatting, Rust tests, Clippy, Python helper compilation, Python helper tests, smoke benchmark, and parity self-check.

## CLI Safety Rules

- `--threads` must be greater than 0.
- Image tables must contain at least one row.
- Image table headers must be unique.
- Metadata passthrough columns must not use MorphoJet output-reserved names such as `Count_Objects`, `Width`, or `Height`.
- `(ImageNumber, Channel, ObjectSet)` identities must be unique.
- Image and mask paths must resolve to readable files before measurement starts.
- `Image.csv` and `Objects.csv` are not overwritten unless `--overwrite` is passed.
- Final `Image.csv` / `Objects.csv` targets must be files when they already exist; directories or other non-file targets are rejected before publish.
- `--summary-json` writes only after successful measurement, must not resolve to `Image.csv` or `Objects.csv`, and follows the same `--overwrite` protection.
- `--summary-json` and `--error-json` targets must be files when they already exist; directories or other non-file targets are rejected before measurement.
- `--error-json` writes only on measure failure after argument parsing, must not resolve to measurement CSVs or `--summary-json`, follows the same `--overwrite` protection, and preserves the non-zero exit plus human-readable stderr.

## Diagnostics

```bash
cargo run -p morphojet -- doctor
```

The output includes the package version, git commit, OS, CPU architecture, Rayon default thread count, and current executable path.

For machine-readable batch observability, pass `--summary-json path/to/run-summary.json` to `measure`. The JSON summary records version, commit, platform, elapsed seconds, image rows, object rows, channels, object sets, output paths, compatibility mode, and effective thread count.

For machine-readable failure monitoring, pass `--error-json path/to/error.json` to `measure`. The error JSON records version, commit, command, a stable error code such as `input_not_readable` or `output_exists`, the top-level message, and the cause chain.

## Smoke Benchmark

```bash
python3 corpus/generate_smoke.py --images 16
benchmark/run.sh benchmark/data/smoke/images.csv benchmark/results/smoke
python3 benchmark/summarize.py benchmark/results/smoke
```

## Scale Benchmark

```bash
python3 benchmark/run_scale.py --cases 16,256,1024 --width 96 --height 96
```

For real oracle runs, see `docs/BENCHMARK.md`.

## Release

Push a `v*` tag to build release archives and checksums:

```bash
git tag v0.1.0
git push origin v0.1.0
```

Before tagging, build and verify a local archive with the same package shape:

```bash
python3 benchmark/build_release_archive.py --version rc-preflight --out-dir benchmark/results/release-artifacts
python3 benchmark/verify_release_archive.py \
  benchmark/results/release-artifacts/morphojet-rc-preflight-macos-arm64.tar.gz \
  --json-out benchmark/results/release-artifacts/verification.json
```

The local archive verifier checks the checksum digest, checksum target filename, traversal-safe extraction, package contents, and `morphojet doctor` output.

Before cutting a release candidate, run:

```bash
python3 benchmark/release_gate.py --require-clean-git --require-l3-provenance --run-l3 --build-release-artifact --release-version rc-preflight
```

This runs the standard code gates, requires a clean git worktree, uses the pinned local CellBinDB archive, runs the full CellProfiler oracle benchmark, runs the supported CellProfiler-style handoff trial, and writes parity, workflow-bridge, handoff-trial, impact, metrics, provenance, and release-gate reports. Release-gate reports include run timestamp, git commit, dirty-worktree status, invoked arguments, top-level `production_claim_status`, top-level `missing_or_failed_checks`, and a production-claim audit that stays `INCOMPLETE` until the required clean-git, L3 provenance, external L4 workflow, and stable release checks are all present and passing. `--require-l3-provenance` checks that the CellBinDB provenance file was written by a full non-`--skip-cellprofiler` run for the current commit, or a commit that differs only by docs/tests/release-gate/evidence-packaging/release-verification changes, and that recorded artifact hashes still match. Changes to `benchmark/run_cellbindb_oracle.py` or MorphoJet measurement code require regenerating L3 provenance. Fetch and verify the archive first when it is not already present:

```bash
python3 benchmark/fetch_zenodo_file.py \
  --record 15370205 \
  --file CellBinDB.zip \
  --out-dir benchmark/data/cellbindb \
  --metadata-out benchmark/data/cellbindb/zenodo_metadata.json \
  --skip-existing
```

For a fast local audit of already-generated L3 artifacts, run:

```bash
python3 benchmark/release_gate.py
```

Use `--require-clean-git --require-l3-provenance` for any report intended to support a release or production-readiness claim. A normal release-gate `status=PASS` means the executed gates passed; the top-level `production_claim_status` remains `INCOMPLETE` until external L4 and stable GitHub release validation are also included. The JSON and Markdown reports also list top-level `missing_or_failed_checks` so the remaining production-claim blockers are visible without manually comparing the audit table. Use `--require-production-claim` only for final production/stable-release gates; it makes the overall release-gate status fail unless the production-claim audit is complete and passing.

Saved release-gate JSON reports can be re-checked during review:

```bash
python3 benchmark/verify_release_gate_report.py benchmark/results/release-gate/report.json
python3 benchmark/verify_release_gate_report.py benchmark/results/release-gate/production-claim.json --require-report-pass --require-production-claim-pass
```

After a real external workflow trial has been run with `benchmark/run_handoff_trial.py`, add its JSON report to the production-readiness release gate:

```bash
python3 benchmark/release_gate.py --require-clean-git --require-l3-provenance \
  --external-trial-json path/to/external/handoff_trial.json \
  --external-trial-root path/to/external \
  --external-evidence-package-dir path/to/evidence-packages/external-l4-trial
```

The external trial gate requires `status=PASS`, generator metadata from `benchmark/run_handoff_trial.py` with a clean git worktree and a 40-character commit SHA that matches the current release gate commit or differs only by docs/tests/release-gate/evidence-packaging/release-verification changes, all trial steps passing with non-negative runtime records and string execution details, a rendered manifest snapshot that still passes the external-evidence handoff schema, a step list and step commands that exactly match the manifest-declared actions, a non-empty artifact list that exactly matches the manifest-declared outputs, files that exist and are non-empty under `--external-trial-root`, exactly one matching `artifact_provenance` SHA-256/size entry for each listed artifact with no unlisted provenance paths, filled external evidence fields and acceptance criteria with no `REPLACE_WITH` placeholders, and `manual_csv_editing=false`. Changes to `benchmark/run_handoff_trial.py` or MorphoJet measurement code require rerunning the external trial.
The gate PASS detail includes the external trial commit and generation timestamp so release reports can be audited without opening the trial JSON first.

Reviewers can check the external trial report directly before evidence packaging:

```bash
python3 benchmark/verify_external_trial_report.py \
  path/to/external/handoff_trial.json \
  --trial-root path/to/external \
  --json-out path/to/external/handoff_trial-verification.json
```

The standalone verifier uses the same external trial validator as `benchmark/release_gate.py`; `--trial-root` must resolve every declared trial artifact, and `--json-out` writes a machine-readable PASS/FAIL report. Use `--allow-fail-report` only when collecting diagnostic evidence from a known-bad trial report, because normal review should fail closed.

Saved external trial verifier reports can be re-checked during review:

```bash
python3 benchmark/verify_external_trial_report.py \
  --verify-report path/to/external/handoff_trial-verification.json \
  --verify-report-files \
  --require-report-pass
```

`--verify-report-files` recomputes the external trial validation from the report's `trial_json` and `trial_root` paths, then checks the recorded gate status and detail against the fresh result.

After the external trial gate passes, package the evidence for external review and release signoff:

```bash
python3 benchmark/package_external_trial.py \
  --trial-json path/to/external/handoff_trial.json \
  --trial-root path/to/external \
  --out-dir path/to/evidence-packages
```

The package step reuses the release-gate external L4 validator and refuses invalid reports. A valid package contains the trial report, rendered manifest snapshot, external evidence JSON, artifact manifest with absolute trial source metadata matching the release-gate inputs plus unique source and package paths, the exact external trial PASS detail, copied artifacts, a README preserving the trial/signoff fields, dataset source, execution environment, trial generation time, exact validation detail, and every acceptance criterion, a zip archive containing exactly every required package file and declared artifact with no duplicate or extra entries and bytes matching the package directory, and a zip SHA-256 file whose digest is valid and whose target filename matches the package zip. Production-claim release gates should pass both `--external-trial-json` and `--external-evidence-package-dir` so the accepted L4 trial and review package are verified together.

Reviewers can also check a package directly without running the full release gate:

```bash
python3 benchmark/verify_external_evidence_package.py \
  path/to/evidence-packages/external-l4-trial \
  --trial-json path/to/external/handoff_trial.json \
  --json-out path/to/evidence-packages/external-l4-trial-verification.json
```

The standalone verifier uses the same package validator as `benchmark/release_gate.py`; `--trial-json` binds the package to the exact source trial report, and `--json-out` writes a machine-readable PASS/FAIL report. Use `--allow-fail-report` only when collecting diagnostic evidence from a known-bad package, because normal review should fail closed.

Saved package verifier reports can be re-checked during review:

```bash
python3 benchmark/verify_external_evidence_package.py \
  --verify-report path/to/evidence-packages/external-l4-trial-verification.json \
  --verify-report-files \
  --require-report-pass
```

`--verify-report-files` recomputes package validation from the report's `package_dir` and optional `trial_json` paths, then checks the recorded gate status and detail against the fresh result.

For final production/stable-release signoff, use the dedicated wrapper so every required production-claim input is bound into the same release-gate report:

```bash
python3 benchmark/run_production_gate.py \
  --external-trial-json path/to/external/handoff_trial.json \
  --external-trial-root path/to/external \
  --external-evidence-package-dir path/to/evidence-packages/external-l4-trial \
  --external-trial-verification-report path/to/external/handoff_trial-verification.json \
  --external-evidence-package-verification-report path/to/evidence-packages/external-l4-trial-verification.json \
  --github-release-tag v0.1.0
```

The wrapper rejects release-candidate tags such as `v0.1.0-rc.1`, checks that the external trial JSON, trial root, evidence package directory, and any supplied reviewer verification reports exist before an actual run, fail-closed re-checks supplied saved verifier reports with `--verify-report-files --require-report-pass`, and passes those reports into `benchmark/release_gate.py` so the final release-gate JSON/Markdown records reviewer-report gates along with `--require-clean-git`, `--require-l3-provenance`, `--require-production-claim`, the external L4 trial and package paths, `--verify-github-release`, and `--github-release-kind stable`. Use `--dry-run` to print the assembled command without checking local evidence paths or performing network/release verification side effects.

When the external L4 trial and evidence package are ready but the stable GitHub release is not yet cut, run a local evidence preflight:

```bash
python3 benchmark/run_production_gate.py \
  --external-trial-json path/to/external/handoff_trial.json \
  --external-trial-root path/to/external \
  --external-evidence-package-dir path/to/evidence-packages/external-l4-trial \
  --external-trial-verification-report path/to/external/handoff_trial-verification.json \
  --external-evidence-package-verification-report path/to/evidence-packages/external-l4-trial-verification.json \
  --github-release-tag v0.1.0 \
  --local-evidence-preflight-only
```

This mode reuses `release_gate.py`'s external trial and package validators, including artifact SHA-256 checks and package/trial matching, re-checks any supplied saved reviewer verifier reports, writes JSON and Markdown reports to `benchmark/results/release-gate/local-evidence-preflight.json` and `.md` by default, records `claim_status=NOT_PRODUCTION_CLAIM`, `evidence_scope=LOCAL_EXTERNAL_L4_PREFLIGHT`, `final_evidence_acceptable=false`, plus the skipped final checks, and summarizes the key input file sizes/SHA-256 hashes for audit. It intentionally skips code gates and GitHub release verification. Override those paths with `--local-evidence-preflight-json` and `--local-evidence-preflight-md`. It is a staging preflight, not the final production claim.

Saved local evidence preflight JSON reports can be schema-checked later without passing the original evidence paths:

```bash
python3 benchmark/run_production_gate.py \
  --verify-local-evidence-preflight-report benchmark/results/release-gate/local-evidence-preflight.json \
  --verify-local-evidence-preflight-files \
  --require-local-evidence-preflight-pass
```

This verifier checks the local evidence report schema, metadata types/formats, reachable `metadata.git_commit`, `claim_status=NOT_PRODUCTION_CLAIM`, `evidence_scope=LOCAL_EXTERNAL_L4_PREFLIGHT`, `final_evidence_acceptable=false`, validated/skipped check lists, input artifact digest fields, and the expected external L4 gate entries. Add `--verify-local-evidence-preflight-files` when the evidence files are still available to recompute recorded sizes and SHA-256 hashes. Add `--require-local-evidence-preflight-pass` for review/signoff so structurally valid FAIL reports cannot be accepted accidentally.

For a scheduler-ready entrypoint that performs the fetch/verify step, verifies an existing CellBinDB archive with pinned MD5/size when Zenodo metadata is temporarily unavailable, pulls the pinned CellProfiler Docker image, and runs `python3 benchmark/release_gate.py --require-l3-provenance --run-l3`, use:

```bash
benchmark/run_cellbindb_l3_validation.sh
```

The release gate also validates handoff manifests:

```bash
python3 benchmark/validate_handoff_manifest.py benchmark/handoff/cellbindb_supported_columns.json \
  --var base_dir=benchmark/results/cellbindb/oracle-full \
  --require-downstream-check \
  --check-files

python3 benchmark/validate_handoff_manifest.py benchmark/handoff/external_lab_template.json \
  --var base_dir=benchmark/results/external-lab-template \
  --require-downstream-check \
  --require-external-evidence \
  --allow-external-evidence-placeholders
```

After a `v*` tag is published, verify the GitHub release assets:

```bash
python3 benchmark/release_gate.py --verify-github-release v0.1.0-rc.1
```

For a stable non-RC release after external workflow evidence has passed:

```bash
python3 benchmark/release_gate.py --verify-github-release v0.1.0 --github-release-kind stable
```

The GitHub release verifier downloads the release assets, checks release tag identity and URL, rejects prerelease or non-semver tags for stable gates, requires the release metadata and downloaded files to contain exactly the expected Linux and macOS archives plus `.sha256` files, records the expected/release/downloaded asset lists in JSON, checks each checksum digest and checksum target filename, validates archive package contents with traversal-safe extraction that rejects links and special files, and requires at least one archive compatible with the current machine to pass `morphojet doctor`.

## Parity Report Smoke

```bash
python3 tests/parity/compare_measurements.py \
  benchmark/results/smoke/Objects.csv \
  benchmark/results/smoke/Objects.csv \
  --fail-on-gap
```

## Measurement Convention

For grayscale 8-bit and 16-bit images, MorphoJet normalizes intensities to CellProfiler's 0-1 measurement scale during intensity accumulation. Non-grayscale inputs are converted to grayscale as a starter behavior and must be checked against CellProfiler oracle outputs before being marked parity-safe.
