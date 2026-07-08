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

The local archive verifier checks the checksum digest, checksum target filename, traversal-safe extraction, package contents, and `morphojet doctor` output, and rejects `--json-out` paths that would overwrite the archive or checksum file.
The local archive builder rejects version strings with path separators or spaces, keeps package/archive/checksum outputs inside `--out-dir`, and refuses to delete an existing package directory unless it contains only the expected release package files.

Before cutting a release candidate, run:

```bash
python3 benchmark/release_gate.py --require-clean-git --require-l3-provenance --run-l3 --build-release-artifact --release-version rc-preflight
```

This runs the standard code gates, requires a clean git worktree, uses the pinned local CellBinDB archive, runs the full CellProfiler oracle benchmark, runs the supported CellProfiler-style handoff trial, and writes parity, workflow-bridge, handoff-trial, impact, metrics, provenance, and release-gate reports. Release-gate reports include run timestamp, git commit, dirty-worktree status, invoked arguments, top-level `production_claim_status`, top-level `missing_or_failed_checks`, and a production-claim audit that stays `INCOMPLETE` until the required clean-git, L3 provenance, external L4 workflow, external L4 evidence package, saved external L4 reviewer reports, stable release, and saved stable-release verifier checks are all present and passing. `--require-l3-provenance` checks that the CellBinDB provenance file was written by a full non-`--skip-cellprofiler` run for the current commit, or a commit that differs only by docs/tests/release-gate/evidence-packaging/release-verification changes, and that recorded artifact hashes still match. Changes to `benchmark/run_cellbindb_oracle.py` or MorphoJet measurement code require regenerating L3 provenance. Fetch and verify the archive first when it is not already present:

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

Use `--require-clean-git --require-l3-provenance` for any report intended to support a release or production-readiness claim. A normal release-gate `status=PASS` means the executed gates passed; the top-level `production_claim_status` remains `INCOMPLETE` until external L4, saved external reviewer reports, stable GitHub release, and saved stable-release verifier validation are also included. Release-gate reports also carry top-level `claim_status`, `evidence_scope`, and `final_production_signoff`: all non-final reports are `NOT_PRODUCTION_CLAIM` / `RELEASE_GATE_PRECHECK` / `false`, and only a passing `--require-production-claim` report with a complete production audit can become `FINAL_PRODUCTION_CLAIM` / `FINAL_PRODUCTION_RELEASE_GATE` / `true`. The standard gates also run `benchmark/validate_claim_language.py` so source docs, including `README.zh-CN.md`, cannot accidentally make unsupported English or Chinese production-ready, production-grade, or CellProfiler-replacement/substitution claims. The JSON and Markdown reports also list top-level `missing_or_failed_checks` so the remaining production-claim blockers are visible without manually comparing the audit table, and JSON includes `production_claim_checklist` so the Markdown Production Claim Checklist is re-checkable by the saved report verifier. Release-gate report outputs are rejected when they would overwrite or create files inside external evidence inputs, package files/artifacts including the package copy of `readiness.json`, reviewer reports, or the GitHub release verifier report. Use `--require-production-claim` only for final production/stable-release gates; it makes the overall release-gate status fail unless the production-claim audit is complete and passing.

Saved release-gate JSON reports can be re-checked during review:

```bash
python3 benchmark/verify_release_gate_report.py benchmark/results/release-gate/report.json
python3 benchmark/verify_release_gate_report.py benchmark/results/release-gate/report.json \
  --verify-git-commit \
  --expect-missing-checks clean_git_worktree,l3_provenance_hashes,external_l4_workflow_trial,external_l4_evidence_package,external_l4_saved_reviewer_reports,stable_github_release,stable_github_release_saved_report
python3 benchmark/verify_release_gate_report.py benchmark/results/release-gate/production-claim.json --require-report-pass --require-clean-git-metadata --verify-git-commit --require-production-claim-pass
python3 benchmark/verify_release_gate_report.py benchmark/results/release-gate/production-claim.json --require-report-pass --require-clean-git-metadata --verify-git-commit --require-production-claim-pass --expect-missing-checks none
```

The saved report verifier rejects reports whose `metadata.generated_at_utc` is not UTC, whose top-level `status` conflicts with recorded gate statuses, whose recorded `metadata.require_production_claim` / `production_claim_status` combination is inconsistent, or whose top-level `claim_status`, `evidence_scope`, and `final_production_signoff` do not match the verified final-signoff state.

The verifier checks the top-level summary against `production_claim_audit`, validates report metadata and each gate entry shape, rejects duplicate gate names, requires the expected production-audit check list, can confirm `metadata.git_commit` is reachable with `--verify-git-commit`, can require `metadata.git_dirty=false` plus an empty `metadata.git_status` with `--require-clean-git-metadata`, and can pin the exact expected `missing_or_failed_checks` list with `--expect-missing-checks`. Use that expectation in reviews so production blockers cannot drift silently between reports. It rejects a saved production-claim PASS report unless the required clean-git, standard code/artifact, L3 provenance, external L4, saved external reviewer, stable GitHub release, and saved stable-release verifier gates are present in the report. A production PASS report must also carry metadata proving `--require-clean-git`, `--require-l3-provenance`, `--require-production-claim`, external L4 paths, saved reviewer/verifier report paths, and a stable release tag/kind were used.

Run real external workflow trials with the runner's strict L4 preflight so missing signoff/evidence fields fail before any handoff commands execute:

```bash
python3 benchmark/run_handoff_trial.py benchmark/handoff/external_lab_template.json \
  --var base_dir=path/to/external \
  --readiness-report path/to/external/readiness.json \
  --require-external-evidence \
  --out-json path/to/external/handoff_trial.json \
  --out-md path/to/external/handoff_trial.md
```

After a real external workflow trial has been run with `benchmark/run_handoff_trial.py --require-external-evidence --readiness-report path/to/readiness.json`, add its JSON report to the production-readiness release gate:

```bash
python3 benchmark/release_gate.py --require-clean-git --require-l3-provenance \
  --external-trial-json path/to/external/handoff_trial.json \
  --external-trial-root path/to/external \
  --external-evidence-package-dir path/to/evidence-packages/external-l4-trial
```

The external trial gate requires `status=PASS`, generator metadata from `benchmark/run_handoff_trial.py` with UTC `metadata.generated_at_utc`, canonical `metadata.argv` proving the recorded source manifest path, sorted `--var` values, `--readiness-report` bound to a READY pre-execution readiness report, `--out-json` bound to the current trial JSON path, `--out-md`, and exactly one `--require-external-evidence` flag, a clean git worktree, and a 40-character commit SHA that matches the current release gate commit or differs only by docs/tests/release-gate/evidence-packaging/release-verification changes, all trial steps passing with non-negative runtime records and string execution details, a rendered manifest snapshot that still passes the external-evidence handoff schema, a step list and step commands that exactly match the manifest-declared actions, a non-empty artifact list that exactly matches the manifest-declared outputs, files that exist and are non-empty under `--external-trial-root`, exactly one matching `artifact_provenance` SHA-256/size entry for each listed artifact with no unlisted provenance paths, filled external evidence fields, acceptance criteria, reviewer identity/role, UTC review timestamp at or after the trial generation timestamp, and signoff statement with no `REPLACE_WITH` placeholders, and `manual_csv_editing=false`. The runner's `--readiness-report` verifier runs before trial execution; `--require-external-evidence` enforces the external-evidence schema before execution. Changes to `benchmark/run_handoff_trial.py` or MorphoJet measurement code require rerunning the external trial.
The gate PASS detail includes the external trial commit and generation timestamp so release reports can be audited without opening the trial JSON first.

Reviewers can check the external trial report directly before evidence packaging:

```bash
python3 benchmark/verify_external_trial_report.py \
  path/to/external/handoff_trial.json \
  --trial-root path/to/external \
  --json-out path/to/external/handoff_trial-verification.json
```

The standalone verifier uses the same external trial validator as `benchmark/release_gate.py`; `--trial-root` must resolve every declared trial artifact, and `--json-out` writes a machine-readable PASS/FAIL report with `schema_version`, verifier identity, UTC generation timestamp, `claim_status=NOT_PRODUCTION_CLAIM`, `evidence_scope=EXTERNAL_L4_WORKFLOW_TRIAL_REVIEW`, `final_production_signoff=false`, absolute source trial/root paths, the bound readiness report summary, and canonical verifier `argv` binding the source trial JSON, trial root, and absolute saved JSON output. Saved-report review also requires the `argv` trial JSON, `--trial-root`, and `--json-out` path values themselves to be absolute, so the command line cannot be weakened to relative evidence paths while top-level metadata remains absolute. The verifier rejects `--json-out` paths that would overwrite or create files inside the source trial JSON, the bound readiness report, or any declared trial artifact, so reviewer reports should live in a separate review path. Use `--allow-fail-report` only when collecting diagnostic evidence from a known-bad trial report, because normal review should fail closed.

Saved external trial verifier reports can be re-checked during review:

```bash
python3 benchmark/verify_external_trial_report.py \
  --verify-report path/to/external/handoff_trial-verification.json \
  --verify-report-files \
  --require-report-pass
```

`--verify-report-files` recomputes the external trial validation from the report's absolute `trial_json` and `trial_root` paths, then checks the report schema/verifier/UTC timestamp, canonical verifier `argv` with absolute trial/source-root path values, the required absolute `--json-out` binding to the saved report path under review, and the recorded gate status and detail against the fresh result. Saved reports also record the source trial JSON size/SHA-256, the bound readiness report size/SHA-256, and every resolved trial artifact size/SHA-256; file recheck recomputes those summaries so a reviewer can catch stale or swapped trial inputs even when the paths still exist.

After the external trial gate passes, package the evidence for external review and release signoff:

```bash
python3 benchmark/package_external_trial.py \
  --trial-json path/to/external/handoff_trial.json \
  --trial-root path/to/external \
  --out-dir path/to/evidence-packages
```

The package step reuses the release-gate external L4 validator and refuses invalid reports. Before writing or deleting package outputs, it rejects output directories that would contain the source trial JSON or any source trial artifact, and rejects package zip/checksum paths that would overwrite source evidence files. A valid package contains the trial report, rendered manifest snapshot, external evidence JSON, artifact manifest with `claim_status=NOT_PRODUCTION_CLAIM`, `evidence_scope=EXTERNAL_L4_EVIDENCE_PACKAGE`, `final_production_signoff=false`, UTC `packaged_at_utc`, canonical packager `argv` matching the source trial JSON, trial root, output directory, and package name, absolute trial source metadata, source trial JSON size/SHA-256, review-file size/SHA-256 entries for the JSON review files plus `README.md` and `README.zh-CN.md`, release-gate input matching, unique source and package paths, the exact external trial PASS detail, copied artifacts, English and Chinese READMEs preserving the claim-status boundary, trial/signoff fields, dataset source, execution environment, reviewer identity/role, review timestamp, signoff statement, trial generation time, exact validation detail, and every acceptance criterion, a zip archive containing exactly every required package file and declared artifact with no duplicate or extra entries and bytes matching the package directory, and a zip SHA-256 file whose digest is valid and whose target filename matches the package zip. The standalone package verifier report records size/SHA-256 summaries for the source trial JSON, package review files including the copied `readiness.json` and bilingual READMEs, zip archive, checksum file, and package artifact-manifest claim-scope fields; `--verify-report-files` recomputes those summaries and claim-scope fields along with the release-gate package validation. Production-claim release gates should pass both `--external-trial-json` and `--external-evidence-package-dir` so the accepted L4 trial and review package are verified together.

Reviewers can also check a package directly without running the full release gate:

```bash
python3 benchmark/verify_external_evidence_package.py \
  path/to/evidence-packages/external-l4-trial \
  --trial-json path/to/external/handoff_trial.json \
  --json-out path/to/evidence-packages/external-l4-trial-verification.json
```

The standalone verifier uses the same package validator as `benchmark/release_gate.py`; `--trial-json` binds the package to the exact source trial report, and `--json-out` writes a machine-readable PASS/FAIL report with `schema_version`, verifier identity, UTC generation timestamp, absolute package/source-trial paths, and canonical verifier `argv` binding the package directory, optional source trial JSON, and absolute saved JSON output. Saved-report review also requires the `argv` package directory and `--trial-json` values themselves to be absolute, so the command line cannot be weakened to relative evidence paths while top-level metadata remains absolute. The verifier rejects `--json-out` paths that would overwrite or create files inside the source trial JSON, package review files including the package copy of `readiness.json` and both README files, package zip/checksum files, or package-declared artifacts, so reviewer reports should live outside the evidence package contents. Use `--allow-fail-report` only when collecting diagnostic evidence from a known-bad package, because normal review should fail closed.

Saved package verifier reports can be re-checked during review:

```bash
python3 benchmark/verify_external_evidence_package.py \
  --verify-report path/to/evidence-packages/external-l4-trial-verification.json \
  --verify-report-files \
  --require-report-pass \
  --require-trial-json
```

`--verify-report-files` recomputes package validation from the report's absolute `package_dir` and optional `trial_json` paths, then checks the report schema/verifier/UTC timestamp, canonical verifier `argv` with absolute package/source-trial path values, the required absolute `--json-out` binding to the saved report path under review, and the recorded gate status and detail against the fresh result. Use `--require-trial-json` for production signoff so the saved package reviewer report must be bound to the exact source trial JSON.

For final production/stable-release signoff, use the dedicated wrapper so every required production-claim input is bound into the same release-gate report:

```bash
python3 benchmark/run_production_gate.py \
  --external-trial-json path/to/external/handoff_trial.json \
  --external-trial-root path/to/external \
  --external-evidence-package-dir path/to/evidence-packages/external-l4-trial \
  --external-trial-verification-report path/to/external/handoff_trial-verification.json \
  --external-evidence-package-verification-report path/to/evidence-packages/external-l4-trial-verification.json \
  --github-release-verification-report path/to/github-release/verification.json \
  --github-release-tag v0.1.0
```

The wrapper rejects release-candidate tags such as `v0.1.0-rc.1`, checks that the external trial JSON, trial root, evidence package directory, and any supplied reviewer verification reports exist before an actual run, rejects final JSON/Markdown output paths that overlap each other or would overwrite external evidence inputs, trial-declared artifacts, package review files including `README.md` and `README.zh-CN.md`, package-declared artifacts, package zip/checksum files, or reviewer reports, and rejects final report paths that would create files inside protected external trial/package evidence files or the package directory, fail-closed re-checks supplied saved verifier reports with `--verify-report-files --require-report-pass`, requires `--require-trial-json` for saved package reviewer reports, requires saved trial/package reviewer reports to point to the same current `--external-trial-json`, `--external-trial-root`, and `--external-evidence-package-dir` inputs, requires `--require-stable-report` plus the final `--github-release-tag` and production repo `benngaihk/MorphoJet` for the saved GitHub release verifier report, and passes those reports into `benchmark/release_gate.py` so the final release-gate JSON/Markdown records reviewer-report gates along with `--require-clean-git`, `--require-l3-provenance`, `--require-production-claim`, the external L4 trial and package paths, `--verify-github-release`, and `--github-release-kind stable`. If the release gate succeeds, the wrapper immediately re-checks the saved final report with `benchmark/verify_release_gate_report.py --require-report-pass --require-clean-git-metadata --verify-git-commit --require-production-claim-pass --expect-missing-checks none`; dry-run prints both the assembled release-gate command and that final-report verifier command. The release gate records production evidence and reviewer-report paths as absolute metadata paths, canonicalizes path-valued `metadata.argv` entries plus live and saved GitHub verifier output paths to absolute paths, and the saved release-gate verifier rejects relative external evidence, reviewer-report, `--out-json`, or `--out-md` argv path values, binds recorded `--out-json` to the saved report path under review, requires boolean metadata flags such as clean-git, L3 provenance, L3 rerun, and release-archive build to have matching gates, requires external L4 metadata paths to have matching validation gates, requires `metadata.verify_github_release` to have a live GitHub release gate command bound to the same tag/kind/output JSON, requires every saved reviewer metadata path to have a matching gate, and requires saved reviewer gate commands to preserve file rechecks, PASS requirements, package source-trial binding, stable GitHub release checks, git commit verification, expected tag binding, and `--expect-repo benngaihk/MorphoJet`. The saved GitHub verification report is an audit artifact and does not replace the live stable-release check. Use `--dry-run` to inspect the assembled commands without checking local evidence paths or performing network/release verification side effects; dry-run still applies stable-tag and report-output path safety checks.

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

This mode reuses `release_gate.py`'s external trial and package validators, including artifact SHA-256 checks and package/trial matching, re-checks any supplied external L4 saved reviewer verifier reports, writes JSON and Markdown reports to `benchmark/results/release-gate/local-evidence-preflight.json` and `.md` by default, records `claim_status=NOT_PRODUCTION_CLAIM`, `evidence_scope=LOCAL_EXTERNAL_L4_PREFLIGHT`, `final_evidence_acceptable=false`, plus the skipped final checks and a machine-checkable `skipped_final_checklist`, records a canonical `metadata.argv` for the effective wrapper inputs with absolute evidence/report paths, and summarizes the key input file sizes/SHA-256 hashes with absolute paths for audit, including the packaged `readiness.json` copied into the evidence package and its readiness package-name summary. It intentionally skips code gates and GitHub release verification, and rejects `--github-release-verification-report` in local preflight mode so a stable-release reviewer report cannot be implied by a local evidence preflight. Override those paths with `--local-evidence-preflight-json` and `--local-evidence-preflight-md`; the wrapper rejects local preflight report paths that overlap each other, would overwrite the external trial/package/reviewer inputs or their declared artifacts, or would create files inside protected package evidence paths. It is a staging preflight, not the final production claim.

Saved local evidence preflight JSON reports can be schema-checked later without passing the original evidence paths:

```bash
python3 benchmark/run_production_gate.py \
  --verify-local-evidence-preflight-report benchmark/results/release-gate/local-evidence-preflight.json \
  --verify-local-evidence-preflight-files \
  --verify-local-evidence-preflight-gates \
  --require-local-evidence-preflight-pass
```

Workspaces prepared by `benchmark/prepare_external_l4_trial.py` include this saved local-preflight verifier immediately after `local_evidence_preflight`, so reviewers rehash the saved input files, rerun the local external L4 gates, recompute the package-readiness package-name summary, and require PASS before treating the preflight package as ready for the later stable-release gate. The same generated command set then runs live stable-release verification, re-checks the saved stable-release report with `--verify-report-files --require-report-pass --require-stable-report --verify-git-commit --expect-tag v0.1.0 --expect-repo benngaihk/MorphoJet`, runs the final production wrapper, and repeats the wrapper's saved `production-claim.json` verification with `benchmark/verify_release_gate_report.py --require-report-pass --require-clean-git-metadata --verify-git-commit --require-production-claim-pass --expect-missing-checks none` as an explicit plan step.

This verifier checks the local evidence report schema, metadata types/formats, UTC `metadata.generated_at_utc`, non-empty absolute metadata evidence paths, reachable `metadata.git_commit`, `claim_status=NOT_PRODUCTION_CLAIM`, `evidence_scope=LOCAL_EXTERNAL_L4_PREFLIGHT`, `final_evidence_acceptable=false`, validated/skipped check lists plus `skipped_final_checklist`, input artifact digest fields, unique absolute input artifact paths, metadata-to-input-artifact path bindings for the trial JSON, package trial JSON, package readiness JSON, package zip/checksum, and optional reviewer reports, absolute path-valued `metadata.argv` bindings for the preflight flag, evidence paths, reviewer reports, and stable tag, gate entry shape, top-level status consistency with recorded gate statuses, unique gate names, and the expected external L4 gate entries. Add `--verify-local-evidence-preflight-files` when the evidence files are still available to recompute recorded sizes and SHA-256 hashes. Add `--verify-local-evidence-preflight-gates` to rerun the recorded external trial, package, and saved reviewer-report gates from report metadata and reject stale gate status/detail/command data. Add `--require-local-evidence-preflight-pass` for review/signoff so structurally valid FAIL reports cannot be accepted accidentally.

For a scheduler-ready entrypoint that performs the fetch/verify step, verifies an existing CellBinDB archive with pinned MD5/size when Zenodo metadata is temporarily unavailable, pulls the pinned CellProfiler Docker image, and runs `python3 benchmark/release_gate.py --require-l3-provenance --run-l3`, use:

```bash
benchmark/run_cellbindb_l3_validation.sh
```

The release gate also validates handoff manifests. The validator rejects duplicate or path-equivalent output artifact paths and output paths that would overwrite declared input CSVs, so real external L4 trials fail before a run can clobber `Objects.csv` or expected CellProfiler CSV inputs. `benchmark/run_handoff_trial.py` applies those checks before execution and also rejects `--out-json` / `--out-md` report paths that would overwrite the manifest file, declared inputs, or declared artifacts. `benchmark/prepare_external_l4_trial.py` refuses to prepare a workspace when planned execution outputs already exist, including old trial reports, reviewer reports, preflight reports, stable-release verifier outputs, production-claim reports, or package outputs; `--overwrite` only refreshes scaffold files and does not silently replace those evidence outputs. Its `trial_plan.json` records UTC `generated_at_utc`, canonical generator `argv`, absolute template/workspace/manifest paths, template size, template SHA-256, generated command set, `claim_status=NOT_PRODUCTION_CLAIM`, `evidence_scope=EXTERNAL_L4_TRIAL_PLAN`, `final_production_signoff=false`, and `final_signoff_requirements` binding each final signoff artifact to a planned path, verification step, and final gate it is required for; `benchmark/prepare_external_l4_trial.py --verify-plan path/to/external-trial/trial_plan.json` rechecks the saved plan schema, generator command binding, UTC timestamp, absolute source paths, regenerated command set, and regenerated final signoff requirements without requiring local file access, while `--verify-plan-files` also rechecks the template file hash, manifest presence, and both English and Chinese README content. The generated command set plus bilingual READMEs list `verify_plan` first, so an external reviewer can revalidate the saved plan itself before running manifest validation, readiness checks, the external trial, saved local-preflight verification, stable-release verification, saved stable-release report verification, the final production gate, or final production report verification. `benchmark/check_external_l4_readiness.py --workspace path/to/external-trial --json-out path/to/external-trial/readiness.json` performs the same external-evidence and input-file checks before execution, checks MorphoJet Objects.csv and expected CellProfiler CSV headers/rows against the manifest-declared object set and channels, requires manifest-declared trial outputs plus planned reviewer/preflight report outputs to be absent before the run, checks the default report and package output paths, rejects readiness `--json-out` paths that would overwrite or create files inside the manifest, inputs, trial outputs, planned reviewer/preflight reports, or package outputs, records UTC `generated_at_utc` plus canonical checker `argv` with absolute workspace/manifest paths and absolute saved `--json-out`, and labels its report with `claim_status=NOT_PRODUCTION_CLAIM`, `evidence_scope=EXTERNAL_L4_READINESS_PRECHECK`, and `final_production_signoff=false`. Saved readiness reports can be rechecked with `benchmark/check_external_l4_readiness.py --verify-report path/to/readiness.json --verify-report-files --require-ready`; this validates report schema, UTC timestamp, claim-scope labels, absolute source paths, canonical `argv`, status/issues/check consistency, and reruns the current workspace readiness checks from the saved paths. Workspaces prepared with `benchmark/prepare_external_l4_trial.py --package-name ...` include that package slug in the generated readiness and readiness-verification commands so readiness checks the same package directory that packaging, package verification, local evidence preflight, stable-release verification, saved stable-release report verification, final production gate, and final production report verification use. The generated `run_trial` command passes `--readiness-report`, and the runner verifies that saved READY report before any handoff commands execute, then binds its size/SHA-256/status/claim-scope labels/timestamps into the trial report. Use the runner's `--require-external-evidence` flag for real L4 runs; keep the default runner mode only for local CellBinDB handoff preflight fixtures that intentionally have no external signoff block:

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

The GitHub release verifier downloads the release assets, checks release tag identity, URL, GitHub release ID/API identity, author, target commit-ish, UTC created/published timestamps, draft state, immutable state, and prerelease state, rejects prerelease or non-semver tags for stable gates, requires the release metadata and downloaded files to contain exactly the expected Linux and macOS archives plus `.sha256` files, records schema version, verifier identity, UTC generation timestamp, `claim_status=NOT_PRODUCTION_CLAIM`, `evidence_scope=GITHUB_STABLE_RELEASE_VERIFICATION`, `final_production_signoff=false`, canonical verifier `argv`, the full 40-character tag commit, the 12-character `doctor` commit prefix, the expected/release/downloaded asset lists, plus GitHub asset metadata records in JSON, checks each release asset metadata entry for name, GitHub asset ID, API URL, download URL, upload state, UTC created/updated timestamps, size, content type, and `sha256:` digest, compares each GitHub asset size and digest with the downloaded file bytes, checks each checksum digest and checksum target filename, validates archive package contents with traversal-safe extraction that rejects links and special files, and requires at least one archive compatible with the current machine to pass `morphojet doctor` with the expected commit prefix. Before downloading, it refuses an existing `--out-dir` that contains anything except expected release asset files for the tag, and it rejects `--json-out` paths inside the asset download directory or over an expected asset. `release_gate.py --verify-github-release` writes the verifier JSON to `benchmark/results/github-release-verification/<tag>.json`, separate from downloaded assets in `benchmark/results/github-release/<tag>/`.

Saved GitHub release verification JSON reports can be re-checked during review:

```bash
python3 benchmark/verify_github_release.py \
  --verify-report benchmark/results/github-release-verification/v0.1.0.json \
  --verify-report-files \
  --require-report-pass \
  --require-stable-report \
  --verify-git-commit \
  --expect-tag v0.1.0
```

`--verify-report-files` recomputes downloaded asset names, archive SHA-256 values, checksum file contents, and every recorded GitHub asset metadata size/digest from the report's absolute `out_dir`. `--verify-git-commit` requires `expected_commit` and `--expect-tag`, when supplied, to resolve to the same commit in the current git checkout. Saved PASS reports must keep expected, release-metadata, and downloaded asset sets identical, and their `archives` list must cover every downloaded `.tar.gz` asset. Saved reports must also preserve `claim_status=NOT_PRODUCTION_CLAIM`, `evidence_scope=GITHUB_STABLE_RELEASE_VERIFICATION`, and `final_production_signoff=false`, require a non-empty GitHub release ID, positive release database ID, GitHub API release URL bound to `repo`, release author, target commit-ish, UTC verifier/release created/published timestamps with `release_published_at >= release_created_at`, `is_draft=false`, every asset metadata entry to have `state=uploaded`, a unique non-empty GitHub asset ID, a unique GitHub API asset URL bound to `repo`, UTC created/updated timestamps with `updated_at >= created_at`, bind the release URL to `repo` plus `tag`, bind each asset metadata download URL to `repo`, `tag`, and asset name, bind each asset metadata digest to `sha256:<64 lowercase hex>`, bind canonical verifier `argv` to the saved tag, repo, absolute output directory, stable/prerelease expectation, and required absolute saved report path under review, reject saved reports whose recorded `out_dir` would contain the saved verifier report itself or other non-release assets, require archive SHA-256 summaries to match the corresponding GitHub asset digest, bind `expected_commit` to a full 40-character commit and `expected_doctor_commit` to its 12-character prefix, and any recorded compatible archive `doctor` summary must use that same prefix, have `status=PASS`, and contain no issues. Use `--require-stable-report` for production signoff so a prerelease verification JSON cannot satisfy the stable-release evidence slot.
Use `--expect-tag v0.1.0 --expect-repo benngaihk/MorphoJet` with saved GitHub release verifier reports during signoff so a report for another stable tag or repository cannot satisfy the reviewer-report slot. Saved PASS reports also reject archive summaries whose recorded `checksum_match` is not true.

## Parity Report Smoke

```bash
python3 tests/parity/compare_measurements.py \
  benchmark/results/smoke/Objects.csv \
  benchmark/results/smoke/Objects.csv \
  --fail-on-gap
```

## Measurement Convention

For grayscale 8-bit and 16-bit images, MorphoJet normalizes intensities to CellProfiler's 0-1 measurement scale during intensity accumulation. Non-grayscale inputs are converted to grayscale as a starter behavior and must be checked against CellProfiler oracle outputs before being marked parity-safe.
