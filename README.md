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

GitHub release verification checks release tag identity, release URL, GitHub release ID/API identity, author, target commit-ish, UTC created/published timestamps, draft/prerelease/immutable state, stable non-prerelease semver tags for stable gates, exact release/download asset sets, records schema version, verifier identity, UTC generation timestamp, canonical verifier `argv`, the full 40-character tag commit, the 12-character `doctor` commit prefix, asset lists, and GitHub asset metadata in JSON, requires saved release API URLs to match the recorded release database ID, requires GitHub assets to be `uploaded`, preserves unique GitHub asset IDs, API URLs, and UTC created/updated timestamps, applies the release identity and verifier-command checks during live verification and saved-report review, binds live release-gate verification to the production repo `benngaihk/MorphoJet`, binds saved release and asset URLs to the recorded repo/tag/asset names, rejects saved reports that do not match an explicit `--expect-repo` when supplied, requires saved reports to record absolute `out_dir`, `--out-dir`, and `--json-out` paths with `--json-out` bound to the report path under review, records and re-checks GitHub asset size and `sha256:` digest metadata against downloaded files and archive summaries, verifies `.sha256` digest values, checksum target filenames, package contents, and requires a compatible archive to pass `morphojet doctor` with the expected commit prefix.

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

`Image.csv` always carries non-empty image-table metadata columns such as `Plate`, `Well`, and `Site`. `Objects.csv` keeps its stable measurement schema by default; pass `--include-object-metadata` when each object row should repeat those image-table metadata values for downstream grouping or handoff systems:

```bash
cargo run -p morphojet -- measure \
  --images images.csv \
  --out measurements \
  --cellprofiler-compatible \
  --include-object-metadata \
  --overwrite
```

When object metadata export is enabled, metadata columns that collide with object measurement columns such as `AreaShape_Area` are rejected instead of producing duplicate CSV headers.

## Smoke Benchmark

```bash
python3 corpus/generate_smoke.py --images 16
benchmark/run.sh benchmark/data/smoke/images.csv benchmark/results/smoke
python3 benchmark/summarize.py benchmark/results/smoke
```

Real CellProfiler oracle benchmark setup is documented in [docs/BENCHMARK.md](docs/BENCHMARK.md).
Before promoting a public source into the oracle path, generate a non-final candidate triage report:

```bash
python3 benchmark/triage_oracle_candidates.py \
  --json-out benchmark/results/cellprofiler/oracle-candidate-triage.json \
  --md-out benchmark/results/cellprofiler/oracle-candidate-triage.md
```

The report records `claim_status=NOT_PRODUCTION_CLAIM`, `evidence_scope=ORACLE_CANDIDATE_TRIAGE`, and `final_production_signoff=false`. It separates official CellProfiler examples that still need exported label masks from public direct-mask candidates such as CellBinDB that still require file/layout/license inspection before they can become manifest-driven oracle evidence.

For CellBinDB, turn that inspection step into a saved direct-mask contract report:

```bash
python3 benchmark/inspect_cellbindb_direct_masks.py \
  --full \
  --verify-md5 \
  --require-pass \
  --json-out benchmark/results/cellbindb/direct-mask-inspection.json \
  --md-out benchmark/results/cellbindb/direct-mask-inspection.md
```

This report is also non-final evidence with `claim_status=NOT_PRODUCTION_CLAIM`, `evidence_scope=CELLBINDB_DIRECT_MASK_INSPECTION`, and `final_production_signoff=false`. It verifies the archive size/checksum metadata, image and instance-mask pair count, matching dimensions, background label `0`, positive integer labels, and recorded source/license metadata before CellBinDB is used as direct-mask oracle input. `benchmark/release_gate.py` also runs the same full MD5-backed direct-mask inspection as a standard gate, so L3 release prechecks fail if the input mask contract drifts.

Before a release candidate, run:

```bash
python3 benchmark/release_gate.py --require-clean-git --require-l3-provenance --run-l3 --build-release-artifact --release-version rc-preflight
```

The same full CellBinDB L3 gate is wired into `.github/workflows/cellbindb-l3.yml` for weekly and manual GitHub Actions runs. That workflow executes `benchmark/run_cellbindb_l3_validation.sh`, refreshes the pinned CellBinDB oracle evidence, writes `benchmark/results/release-gate/l3-cellbindb.json` / `.md`, and uploads the L3 parity, impact, provenance, workflow-bridge, and handoff-trial reports as a 30-day artifact. Scheduled L3 evidence is a regression signal for the public oracle path; it still does not satisfy the external L4 workflow trial or stable-release production-claim gates.

For a fast audit of already-generated L3 artifacts, run `python3 benchmark/release_gate.py`. Release-gate JSON and Markdown reports include the run timestamp, git commit, dirty-worktree status, invoked arguments, top-level `claim_status`, `evidence_scope`, `final_production_signoff`, `production_claim_status`, and top-level `missing_or_failed_checks`; JSON also includes `production_claim_checklist`, and the Markdown report renders that checklist to map each audit check to the required evidence and next reviewer action. Non-final reports are labeled `claim_status=NOT_PRODUCTION_CLAIM`, `evidence_scope=RELEASE_GATE_PRECHECK`, and `final_production_signoff=false`; only a passing report generated with `--require-production-claim` and a complete production audit is labeled `claim_status=FINAL_PRODUCTION_CLAIM`, `evidence_scope=FINAL_PRODUCTION_RELEASE_GATE`, and `final_production_signoff=true`. The standard gate set includes the full CellBinDB direct-mask inspection, existing L3 artifacts, workflow bridge artifacts, and handoff trial artifacts. The saved report verifier rejects missing or tampered checklist rows and claim-scope labels. External L4 trial-plan, readiness, trial, package, reviewer-report, stable-release verifier, and local-preflight labels reuse the same release-gate-owned non-final claim-scope contracts, so intermediate evidence cannot drift into final production wording. Production audit check statuses (`PASS`, `FAIL`, `MISSING`) and top-level production-claim statuses (`PASS`, `INCOMPLETE`) also come from the same release-gate contract used by saved report review. The planned stable tag (`v0.1.0`), stable release URL, and stable semver matcher also come from the release-gate contract used by the external L4 plan generator, final wrapper, GitHub verifier, and saved report verifier. The gate also scans top-level Markdown files plus recursive `docs/` and `corpus/` documentation, including `README.zh-CN.md` and `MORPHOJET-FEASIBILITY.md`, for unsupported English or Chinese production-ready, production-grade, CellProfiler-replacement, or CellProfiler-substitution claims and refuses report output paths that would overwrite or create files inside external evidence inputs, packaged evidence files including `readiness.json`, reviewer reports, or the GitHub release verifier report. Formal release reports should include `--require-l3-provenance`, which checks the CellBinDB provenance file written by a full non-`--skip-cellprofiler` L3 run and re-hashes the recorded artifacts. Final production or stable-release gates should add `--require-production-claim`, which now fails at the CLI contract layer unless `--require-clean-git` and `--require-l3-provenance` are also present, and still fails unless the external L4 workflow trial, matching evidence package, saved external reviewer reports, live stable release, and saved stable-release verifier report checks are all present and passing.

Direct final-claim release-gate use must also keep the live GitHub release check stable: `benchmark/release_gate.py --require-production-claim --verify-github-release <tag>` rejects prerelease/RC gates unless `--github-release-kind stable` is supplied.

The same source-doc guard treats the root bilingual README contract as release evidence: it requires the English README to link to `README.zh-CN.md` and requires the Chinese README to keep the external L4 workflow, local preflight, final production wrapper, current blocker list, package README evidence path, and the [README 中文版维护承诺](README.zh-CN.md#readme-中文版维护承诺) visible for Chinese-community review. Chinese reviewers can start from the [中文社区验证入口](README.zh-CN.md#中文社区验证入口), which points to the same non-final evidence chain and final blockers instead of a weaker parallel path.

To re-check a saved release-gate JSON report during review:

```bash
python3 benchmark/verify_release_gate_report.py benchmark/results/release-gate/report.json
python3 benchmark/verify_release_gate_report.py benchmark/results/release-gate/report.json --verify-git-commit
python3 benchmark/verify_release_gate_report.py benchmark/results/release-gate/production-claim.json --require-report-pass --require-clean-git-metadata --verify-git-commit --require-production-claim-pass --expect-missing-checks none
```

The saved release-gate verifier checks top-level summary fields and claim-scope labels against `production_claim_audit`, validates metadata and gate-entry schemas, requires `metadata.generated_at_utc` to be UTC, requires the expected production-audit check list, can verify the recorded git commit is reachable, can require clean-git metadata, rejects `github_release_kind=stable` metadata unless it is paired with a stable release tag, and rejects production PASS reports that omit required clean-git, L3 provenance, external L4, saved external reviewer, stable GitHub release, or saved stable-release verifier gates. Production PASS reports must also carry metadata and `metadata.argv` proving the final flags, absolute external L4 paths, saved reviewer/verifier report paths, and stable release tag/kind were used; the verifier checks this both ways so recorded metadata must appear in `argv` and key production arguments in `argv` must be reflected back into metadata. Saved release-gate reports also reject relative production evidence paths and relative path-valued `metadata.argv` entries for external L4 evidence, reviewer reports, and explicit `--out-json` / `--out-md` outputs; when `--out-json` is recorded it must match the report file under review. The production evidence metadata keys and path-valued `metadata.argv` flags are release-gate-owned contracts shared by the writer and saved report verifier. Boolean metadata flags such as clean-git, L3 provenance, L3 rerun, and release-archive build must have their matching gates. External L4 metadata paths must have matching validation gates. `metadata.verify_github_release` must have a matching live GitHub release gate whose command binds the same tag, stable/prerelease expectation, and verifier JSON output. Saved reviewer-report metadata must have the matching saved-reviewer gate, and those gates must preserve the fail-closed verifier commands bound to metadata paths, including file rechecks, PASS requirements, package `--require-trial-json`, stable GitHub release checks, git commit verification, expected release tag binding, and expected repo binding. `release_gate.py` canonicalizes those recorded path values to absolute paths when it writes a report.
Final saved-report signoff treats `--require-production-claim-pass` as fail-closed: it now requires `--require-report-pass`, `--require-clean-git-metadata`, `--verify-git-commit`, and `--expect-missing-checks none`, so a production-claim PASS cannot be reviewed without also proving the saved report passed, came from a clean committed tree, points at a reachable commit, and has no remaining production blockers.

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

The wrapper requires a stable non-RC tag and, for actual final runs, fail-fast requires all three saved verifier reports: `--external-trial-verification-report`, `--external-evidence-package-verification-report`, and `--github-release-verification-report`. It checks that the external trial JSON, trial root, evidence package directory, and saved verifier reports exist before invoking the final gate, fail-closed re-checks those saved verifier reports with `--verify-report-files --require-report-pass`, rejects final output paths that would overwrite package review files such as `README.md` or `README.zh-CN.md`, requires saved package reviewer reports to include `trial_json`, requires saved trial/package reviewer reports to match the current external inputs, requires `--require-report-pass`, `--require-stable-report`, `--verify-report-files`, `--verify-git-commit`, the final tag, and the `benngaihk/MorphoJet` repo for the saved GitHub release verifier report, and passes those reviewer reports through to `benchmark/release_gate.py` so the final JSON/Markdown includes the reviewer-report gates alongside clean-git, L3 provenance, external L4 trial, external L4 evidence package, live stable GitHub release, and `--require-production-claim` checks. If that release gate passes, the wrapper immediately re-checks the saved final report with `benchmark/verify_release_gate_report.py --require-report-pass --require-clean-git-metadata --verify-git-commit --require-production-claim-pass --expect-missing-checks none`. Direct `benchmark/release_gate.py` saved reviewer-report gates also bind saved external trial/package reports to the current external evidence inputs, re-check saved GitHub release reports with `--verify-git-commit`, require `--expect-tag <final-tag>` and `--expect-repo benngaihk/MorphoJet`, and bind saved GitHub reports to `--verify-github-release` when a live tag is supplied. The saved GitHub release verifier report is labeled `claim_status=NOT_PRODUCTION_CLAIM`, `evidence_scope=GITHUB_STABLE_RELEASE_VERIFICATION`, and `final_production_signoff=false`; it is an audit artifact and does not replace the live stable-release check or final production gate. The saved GitHub verifier treats `--require-stable-report` as signoff mode and rejects it unless PASS enforcement, file rechecks, git commit/tag verification, expected tag, and expected repo are all present. Use `--dry-run` to inspect the assembled release-gate and final-report verifier commands without requiring those external paths yet; use `--local-evidence-preflight-only` for the earlier non-final path where external saved reviewer reports may still be absent.

Direct `benchmark/release_gate.py` final-claim runs that include live `--verify-github-release` enforce `--github-release-kind stable` at argument validation, matching the final wrapper's stable non-RC release requirement.

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

This preflight writes `benchmark/results/release-gate/local-evidence-preflight.json` and `.md` by default, records `claim_status=NOT_PRODUCTION_CLAIM`, `evidence_scope=LOCAL_EXTERNAL_L4_PREFLIGHT`, and `final_evidence_acceptable=false`, lists the final production checks it intentionally skips, writes a machine-checkable `skipped_final_checklist` with required evidence and next actions for those skipped final checks, records a canonical `metadata.argv` for the effective wrapper inputs with absolute evidence/report paths, and records size/SHA-256 summaries for the trial JSON, packaged trial JSON, packaged artifact manifest, packaged readiness JSON, package `README.md`, package `README.zh-CN.md`, package zip, zip checksum file, and any supplied external L4 saved reviewer verification reports using absolute paths. It also copies claim-scope summaries into the local preflight inputs: source and packaged trial JSON entries must carry `claim_status=NOT_PRODUCTION_CLAIM`, `evidence_scope=EXTERNAL_L4_WORKFLOW_TRIAL`, and `final_production_signoff=false`; the packaged `artifact_manifest.json` entry must carry both its package scope and the source trial scope (`trial_claim_status`, `trial_evidence_scope`, and `trial_final_production_signoff`). The packaged readiness JSON summary also records READY status, `claim_status=NOT_PRODUCTION_CLAIM`, `evidence_scope=EXTERNAL_L4_READINESS_PRECHECK`, `final_production_signoff=false`, UTC generation time, the canonical readiness `package_name` (or `null`), workspace, and manifest; the package README summaries record the package claim scope, the README-rendered readiness scope, and the README-rendered handoff contract in both English and Chinese. The Markdown report renders those readiness fields, each package README `review_entrypoint_present` value, and a dedicated package README handoff-contract table, so local preflight review is bound to the readiness context, Chinese-community entrypoint, and downstream CSV contract captured by the external L4 evidence package without requiring reviewers to open the JSON first. It only checks the external L4 trial report, evidence package, and supplied external L4 reviewer reports before the final stable-release gate is available; only when both saved external reviewer reports are supplied and both saved reviewer verifier gates pass does `external_l4_saved_reviewer_reports` move into `validated_checks`, otherwise it remains in `skipped_final_checklist`. `stable_github_release` and `stable_github_release_saved_report` always remain skipped in local preflight, and `--github-release-verification-report` is rejected in local preflight mode because stable release verification is intentionally out of scope.

Re-check a saved local evidence preflight report without the original evidence paths:

```bash
python3 benchmark/run_production_gate.py \
  --verify-local-evidence-preflight-report benchmark/results/release-gate/local-evidence-preflight.json \
  --verify-local-evidence-preflight-files \
  --verify-local-evidence-preflight-gates \
  --require-local-evidence-preflight-pass
```

The verifier also confirms that the report's `metadata.generated_at_utc` is UTC, `metadata.git_commit` is a reachable commit in the current checkout, `metadata.github_release_tag` is a stable non-RC release tag, metadata evidence paths, input artifact paths, and path-valued `metadata.argv` entries are absolute, `skipped_final_checklist` matches the preflight contract, saved reviewer metadata paths have matching saved reviewer gate entries and existing input-artifact hash summaries, and `metadata.argv` matches the recorded preflight inputs so path, stable-tag, local-preflight flag, duplicate critical flags, missing flag values, and local preflight claim-scope summaries cannot be tampered independently from metadata. Required trial/package input artifacts must remain `exists=true` with size/SHA-256 summaries. It rejects packaged readiness `package_name`, workspace, or manifest tampering when the referenced package is available, and binds the saved package README handoff-contract summaries and `review_entrypoint_present` values back to the current package `README.md`, package `README.zh-CN.md`, and `rendered_manifest.json`. With `--verify-local-evidence-preflight-files`, it recomputes the source trial, packaged trial, and package artifact-manifest claim-scope summaries, the packaged readiness JSON `package_name`, workspace, and manifest summary, and the package README scope, handoff-contract summaries, and reviewer-entrypoint status in addition to file sizes and SHA-256 hashes. With `--verify-local-evidence-preflight-gates`, it reruns the recorded external L4 trial, package, and saved reviewer-report gates from the report metadata and rejects stale gate status/detail/command data. `--require-local-evidence-preflight-pass` is a signoff-mode flag and now requires `metadata.git_dirty=false`, empty `metadata.git_status`, `--verify-local-evidence-preflight-files`, and `--verify-local-evidence-preflight-gates`, so a dirty, structurally valid, or un-rehashed saved preflight JSON cannot be accepted as reviewer-ready evidence.

## CellProfiler-Style Wide Export

MorphoJet's native `Objects.csv` is a long table keyed by `ImageNumber`, `ObjectSet`, `ObjectNumber`, and `Channel`. For downstream tools that expect a CellProfiler object CSV such as `Cells.csv`, materialize the supported measurement subset into a wide table:

```bash
python3 benchmark/materialize_morphojet_cellprofiler_wide.py \
  --objects measurements/Objects.csv \
  --object-set Cells \
  --channels DNA,PH3 \
  --metadata-columns Plate,Well,Site \
  --out measurements/Cells.wide.csv
```

Validate the supported wide columns against a CellProfiler object CSV with:

```bash
python3 benchmark/compare_cellprofiler_wide_subset.py CellProfiler/Cells.csv measurements/Cells.wide.csv \
  --allow-extra-columns Plate,Well,Site \
  --fail-on-gap
```

When `--metadata-columns` is used, the materializer carries those columns through from `Objects.csv` to the wide CSV and fails if a metadata value differs across channel rows for the same object. The subset comparer can allow those declared metadata columns as MorphoJet-only pass-through fields while still failing on unexpected extra columns.

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

Use `benchmark/handoff/external_lab_template.json` as the starting point for real lab handoff files. To create a concrete workspace with the template manifest, input directories, bilingual English/Chinese README files, and the exact plan-verification/validation/readiness/readiness-verification/run/trial-review/trial-review-recheck/package/package-review/package-review-recheck/preflight/preflight-verification/stable-release/saved-release-verification/final-production/final-report-verification commands, run `python3 benchmark/prepare_external_l4_trial.py --workspace path/to/external-trial`; `trial_plan.json` records UTC `generated_at_utc`, canonical generator `argv`, absolute template/workspace/manifest paths, template size, template SHA-256, `claim_status=NOT_PRODUCTION_CLAIM`, `evidence_scope=EXTERNAL_L4_TRIAL_PLAN`, `final_production_signoff=false`, `external_evidence_requirements` for required reviewer/signoff fields, UTC review timestamp, `manual_csv_editing=false`, at least 3 acceptance criteria, `pre_signoff_requirements` for readiness, saved reviewer-report rechecks, and local-preflight prerequisites, `final_signoff_requirements` that bind every final signoff artifact to its planned path, verification step, and exact final wrapper argument it satisfies, and `production_claim_blockers` that mirror the release-gate production audit blockers (`clean_git_worktree`, `l3_provenance_hashes`, external L4 trial/package/reviewer reports, stable release, and saved stable-release report) with required evidence, next action, planned paths, and final-gate binding; re-check it with `benchmark/prepare_external_l4_trial.py --verify-plan path/to/external-trial/trial_plan.json --verify-plan-files --require-plan-files`. Plain `--verify-plan` regenerates the expected command set plus external evidence, pre-signoff, final signoff, and production-blocker requirements from the saved absolute manifest path, workspace, and package name so command, signoff-requirement, external-evidence-contract, or production-blocker tampering is caught even without local file access; it also checks that the readiness planned path matches `check_readiness --json-out`, `verify_readiness --verify-report`, and `run_trial --readiness-report`, that trial/package saved reviewer-report pre-signoff rows point to `verify_trial_report`/`verify_package_report`, are required before `local_evidence_preflight`, and match the local-preflight reviewer-report inputs, that the local-preflight planned path matches `local_evidence_preflight --local-evidence-preflight-json` and `verify_local_evidence_preflight --verify-local-evidence-preflight-report`, that trial JSON, package directory, reviewer-report JSON, GitHub release verifier JSON, and final production-claim JSON paths stay consistent across the generated run/verify/package/preflight/stable-release/final-wrapper commands, that saved trial/package reviewer-report recheck commands point to the planned reviewer JSONs with file rechecks, PASS enforcement, and source-trial binding for package review, that stable-release verification commands bind to `v0.1.0`, `benngaihk/MorphoJet`, stable-report enforcement, git-commit verification, and the same final-wrapper tag, and that every final-signoff `required_for` wrapper flag exists exactly once in the generated `final_production_gate` command with each planned artifact path matching that flag's command value. `--verify-plan-files` also recomputes template hash data and checks manifest presence plus English and Chinese README contents; `--require-plan-files` rejects saved-plan signoff unless that file-level recheck is present. The generated READMEs list that `verify_plan` command first, render the external evidence requirements and production claim blockers for reviewers, state that saved trial-plan signoff must pair `--require-plan-files` with `--verify-plan-files`, and state that saved readiness signoff must pair `--require-ready` with `--verify-report-files`, that saved package verifier reports are `claim_status=NOT_PRODUCTION_CLAIM`, `evidence_scope=EXTERNAL_L4_EVIDENCE_PACKAGE_REVIEW`, and `final_production_signoff=false`, that saved trial/package reviewer reports must be rechecked with `verify_trial_report` and `verify_package_report` before local preflight or final signoff treats them as reviewer evidence, and that those saved-report signoff commands must pair `--require-report-pass` with `--verify-report-files`; they also preserve that saved local preflight reports are `claim_status=NOT_PRODUCTION_CLAIM`, `evidence_scope=LOCAL_EXTERNAL_L4_PREFLIGHT`, and `final_evidence_acceptable=false`, so reviewers can confirm the saved plan, non-final package-review scope, local-preflight scope, production blockers, and reviewer/signoff contract before running any external L4 step. If `--package-name` is supplied, the generated readiness, readiness-verification, package, package-verification, package-report-recheck, local-preflight, local-preflight-verification, stable-release-verification, saved-stable-release-verification, final-production-gate, and final-report-verification commands all bind to the same slug. The generated workspace is only a preparation scaffold and is not external evidence, and preparation refuses stale execution outputs such as old trial reports, reviewer reports, preflight reports, stable-release verifier outputs, production-claim reports, or package outputs even when `--overwrite` is used for scaffold files. Before executing a real trial, run `python3 benchmark/check_external_l4_readiness.py --workspace path/to/external-trial --json-out path/to/external-trial/readiness.json` to require the saved `trial_plan.json`, template hash, manifest presence, English and Chinese README contents, filled external evidence, required input files, MorphoJet Objects.csv and expected CellProfiler CSV headers/rows matching the declared object set and channels, empty manifest-declared trial output paths, empty planned reviewer/preflight report paths, safe report outputs, and clear package output paths; the readiness `--json-out` path is also blocked from overwriting or creating files inside the manifest, declared inputs, trial outputs, planned reviewer/preflight reports, or package outputs, and this report records UTC `generated_at_utc`, canonical checker `argv`, absolute workspace/manifest paths, the canonical package-name slug or null, absolute saved `--json-out`, `claim_status=NOT_PRODUCTION_CLAIM`, `evidence_scope=EXTERNAL_L4_READINESS_PRECHECK`, and `final_production_signoff=false`; re-check it with `benchmark/check_external_l4_readiness.py --verify-report path/to/readiness.json --verify-report-files --require-ready` before running the trial so the saved package-name field, argv binding, saved plan, and bilingual README contents are all validated. External workflow trials must fill the full `external_evidence` block, including non-placeholder acceptance criteria plus `reviewer_name_or_role`, UTC `reviewed_at_utc`, and `signoff_statement`, and pass validation with `--require-external-evidence`; the generated run command also passes `--readiness-report path/to/readiness.json`, so the runner verifies the READY report before execution, refuses to run if that report's manifest or workspace differs from the current trial manifest and `base_dir`, and the trial report records `claim_status=NOT_PRODUCTION_CLAIM`, `evidence_scope=EXTERNAL_L4_WORKFLOW_TRIAL`, and `final_production_signoff=false` while preserving that readiness report's path, size, SHA-256, status, claim-scope labels, workspace, manifest, package-name binding, and UTC generation time. The trial report also preserves clean-git generator metadata for the current or compatible commit, UTC `metadata.generated_at_utc`, the source manifest path, canonical `metadata.argv` matching manifest, sorted `--var` values, `--out-json` bound to the current trial JSON path, `--out-md`, exactly one `--readiness-report`, and exactly one `--require-external-evidence` flag, those fields, the rendered manifest snapshot, exact manifest-declared step command/runtime/detail and artifact coverage, and one SHA-256/size provenance entry for each listed artifact for L4 review. Reviewers can directly re-check the trial report with `benchmark/verify_external_trial_report.py path/to/handoff_trial.json --trial-root path/to/external --json-out path/to/trial-verification.json`, then re-check the saved verifier JSON with `--verify-report path/to/trial-verification.json --verify-report-files --require-report-pass`; the saved verifier report records and validates its schema version, verifier identity, UTC generation timestamp, canonical verifier `argv`, absolute source trial/root paths, source trial JSON size/SHA-256 plus source trial claim-scope labels, bound readiness report size/SHA-256, READY status, non-final claim-scope labels, UTC generation time, workspace, manifest, package-name summary, and every resolved trial artifact size/SHA-256, requires absolute verifier `argv` trial JSON, `--trial-root`, and saved `--json-out` path values with `--json-out` bound to the saved report path under review, rejects reviewer report outputs that would overwrite or create files inside the source trial JSON, bound readiness report, or declared artifacts, and re-hashes those summaries during file recheck. After release gate accepts a real external trial, use `benchmark/package_external_trial.py` to create a reviewable evidence package with the trial report, readiness report, rendered manifest, external evidence, artifact manifest, copied artifacts, zip archive, and zip checksum. The package README files must preserve the readiness package name, workspace, and manifest so human reviewers see the same readiness context as the saved verifier JSON. Reviewers can directly re-check that package with `benchmark/verify_external_evidence_package.py path/to/package --trial-json path/to/handoff_trial.json --json-out path/to/package-verification.json`, then re-check the saved package verifier JSON with `--verify-report path/to/package-verification.json --verify-report-files --require-report-pass --require-trial-json`; this saved verifier report has the same schema/verifier/UTC timestamp/argv audit fields, records absolute package/source-trial paths plus size/SHA-256 summaries for the source trial JSON, package review files including the copied `readiness.json` size/SHA-256 plus READY status, non-final claim-scope labels, UTC generation time, package-name, workspace, and manifest summary, zip, and checksum file, requires absolute verifier `argv` package directory, `--trial-json`, and saved `--json-out` path values with `--json-out` bound to the saved report path under review, rejects reviewer report outputs that would overwrite or create files inside source/package evidence files, re-hashes those summaries during file recheck, and must be bound to the source trial JSON for production signoff. The generated local-preflight-verification command rechecks the saved local evidence preflight report with file rehashing, gate reruns, source-trial and package-manifest claim-scope recomputation, package-readiness READY status/claim-scope/generated-time/package-name/workspace/manifest recomputation, package README-rendered readiness-scope and handoff-contract recomputation, and PASS enforcement before the stable-release gate exists. After the stable `v0.1.0` release is published, the generated stable-release-verification command writes the saved GitHub release verifier report outside the download directory, the generated saved-stable-release-verification command rechecks downloaded files, stable-report identity, git commit/tag resolution, expected tag, and expected `benngaihk/MorphoJet` repo, and the generated final-production-gate command supplies the trial report, evidence package, trial/package reviewer reports, saved GitHub release verifier report, stable tag, and final output paths to `benchmark/run_production_gate.py`; the wrapper itself then re-checks `production-claim.json` with `benchmark/verify_release_gate_report.py --require-report-pass --require-clean-git-metadata --verify-git-commit --require-production-claim-pass --expect-missing-checks none`, and the generated final-report-verification command repeats that check as a standalone saved-plan step. The production wrapper also checks that supplied saved trial/package reviewer reports point to the same `--external-trial-json`, `--external-trial-root`, and `--external-evidence-package-dir` used for the current run. Saved plan, readiness, trial-reviewer, package-reviewer, local-preflight, GitHub release, and final release-gate report verifiers reject `generated_at_utc` values whose offset is not UTC, and external L4 validators reject reviewer `reviewed_at_utc` values whose offset is not UTC. The package README must preserve the trial/signoff fields, dataset source, execution environment, reviewer identity/role, review timestamp, signoff statement, trial generation time, readiness status/time/hash/package name/workspace/manifest, exact validation detail, and every acceptance criterion; the artifact manifest must preserve UTC `packaged_at_utc`, canonical packager `argv` matching the source trial JSON, trial root, output directory, and package name, absolute source trial JSON/root metadata, source trial JSON size/SHA-256, the bound readiness report summary plus copied `readiness.json`, review-file size/SHA-256 entries, release-gate input matching, the exact external trial PASS detail, and map each source artifact to a unique package path; the package zip must contain exactly the required package files and declared artifacts with no duplicate or extra entries and with bytes matching the package directory, and its checksum file must contain a valid SHA-256 digest targeting that zip filename. Final production release gates should validate both the trial report and package with `--external-trial-json` and `--external-evidence-package-dir`.

The external L4 template declares `required_object_metadata_columns` for `Plate`, `Well`, and `Site`. Readiness checks enforce those columns on MorphoJet `Objects.csv`, so real handoff workspaces should generate `Objects.csv` with `measure --include-object-metadata` or intentionally update the manifest contract before review.

Generated external-workspace READMEs also tell reviewers that local preflight treats saved reviewer reports as validated only when both saved reviewer verifier gates pass; otherwise the saved reviewer report check stays in the skipped final checklist until the failing reviewer report is fixed and rechecked. They now also state that `verify_local_evidence_preflight` rehashes package `README.md` and `README.zh-CN.md`, recomputes package README-rendered readiness scope, binds the README-rendered handoff contract back to `rendered_manifest.json`, recomputes each package README `review_entrypoint_present` value before PASS can be accepted, and renders those values in the saved local preflight Markdown `Review Entrypoint` column.

External trial reports and saved external trial verifier reports are both labeled as non-final artifacts: the source trial report uses `claim_status=NOT_PRODUCTION_CLAIM`, `evidence_scope=EXTERNAL_L4_WORKFLOW_TRIAL`, and `final_production_signoff=false`, while the saved reviewer report uses `claim_status=NOT_PRODUCTION_CLAIM`, `evidence_scope=EXTERNAL_L4_WORKFLOW_TRIAL_REVIEW`, and `final_production_signoff=false`. The saved reviewer report copies the source trial claim-scope labels into `input_files.trial_json`, copies the bound readiness report's READY status, non-final claim-scope labels, UTC generation time, package name, workspace, and manifest into `input_files.readiness_report`, and file recheck recomputes them so a trial-reviewer JSON cannot be mistaken for final production signoff by itself. Saved trial reviewer signoff with `--require-report-pass` now fails unless `--verify-report-files` is also supplied. Evidence packages include both `README.md` and `README.zh-CN.md`. Both README files are listed in `artifact_manifest.review_files`, included in the package zip, checked by release gate for required signoff fields, and recorded by the standalone package verifier so file rechecks catch tampering in either language. The package `artifact_manifest.json` and both READMEs must also preserve `claim_status=NOT_PRODUCTION_CLAIM`, `evidence_scope=EXTERNAL_L4_EVIDENCE_PACKAGE`, and `final_production_signoff=false`; `artifact_manifest.json` also records the source trial's `trial_claim_status`, `trial_evidence_scope`, and `trial_final_production_signoff` so the package remains bound to a non-final trial report. Saved package verifier reports are independently labeled `claim_status=NOT_PRODUCTION_CLAIM`, `evidence_scope=EXTERNAL_L4_EVIDENCE_PACKAGE_REVIEW`, and `final_production_signoff=false`, copy the package manifest's package-scope and source-trial scope fields into `input_files.package_artifact_manifest`, copy the package readiness report's READY status, non-final claim-scope labels, UTC generation time, `package_name`, workspace, and manifest into `input_files.package_readiness`, copy the source trial labels into `input_files.source_trial_json` when `--trial-json` is supplied, and `--verify-report-files` recomputes them from the package manifest, package readiness report, and source trial report. Saved package reviewer signoff with `--require-report-pass` now fails unless `--verify-report-files` is also supplied.

Evidence-package `README.md` and `README.zh-CN.md` also preserve the copied readiness report's READY status, `claim_status=NOT_PRODUCTION_CLAIM`, `evidence_scope=EXTERNAL_L4_READINESS_PRECHECK`, `final_production_signoff=false`, UTC generation time, package name, workspace, and manifest. They also render the handoff contract from the trial's rendered manifest, including `morphojet_objects_csv`, `required_object_metadata_columns`, and each export's object set, channels, metadata columns, output CSV, expected CellProfiler CSV, and comparison artifact paths. Release gate checks those readiness and handoff-contract fields in both languages so the package README cannot be mistaken for final production signoff or silently lose the downstream CSV contract. Package READMEs also include a reviewer entrypoint that tells Chinese-community reviewers to use `README.zh-CN.md` as a first-class package review file and to bind the saved package verifier report into the final wrapper; standalone package verifier reports record `review_entrypoint_present` for both package READMEs, and saved-report file rechecks reject entrypoint tampering. Saved package verifier reports copy the same README-rendered fields into `input_files.package_readme` and `input_files.package_readme_zh` so saved-report review can bind the handoff contract back to the package READMEs and rendered manifest, and local evidence preflight now carries the same README handoff-contract summaries plus `review_entrypoint_present` into `input_artifacts.package_readme` and `input_artifacts.package_readme_zh`. Its Markdown report renders both the package README handoff-contract table and the reviewer-entrypoint status in the input artifact table, and saved local preflight verification rejects handoff-contract or reviewer-entrypoint tampering against both the package README files and `rendered_manifest.json`.

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
