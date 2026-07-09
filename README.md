# MorphoJet

Language: English | [简体中文](README.zh-CN.md)

The Simplified Chinese README is a first-class review entrypoint for Chinese-community users and mirrors the same evidence-chain guardrails, not a shortened summary.

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

Tagged releases (`v*`) build macOS and Linux CLI archives with SHA-256 checksums through GitHub Actions. Release archives include `README.md`, `README.zh-CN.md`, and `LICENSE` so Chinese-community reviewers receive the same release package context.

To validate the local release archive shape before tagging:

```bash
python3 benchmark/release_gate.py --build-release-artifact --release-version local
```

Local archive verification checks the archive checksum digest, checksum target filename, traversal-safe extraction, `morphojet doctor`, and required package files including `README.zh-CN.md`.

To verify a published GitHub release candidate:

```bash
python3 benchmark/release_gate.py --verify-github-release v0.1.0-rc.1
```

After external workflow evidence has passed, verify a stable non-RC release with:

```bash
python3 benchmark/release_gate.py --verify-github-release v0.1.0 --github-release-kind stable
```

GitHub release verification checks release tag identity, release URL, GitHub release ID/API identity, author, target commit-ish, UTC created/published timestamps, draft/prerelease/immutable state, stable non-prerelease semver tags for stable gates, exact release/download asset sets, records schema version, verifier identity, UTC generation timestamp, canonical verifier `argv`, the full 40-character tag commit, the 12-character `doctor` commit prefix, asset lists, and GitHub asset metadata in JSON, requires saved release API URLs to match the recorded release database ID, requires GitHub assets to be `uploaded`, preserves unique GitHub asset IDs, API URLs, and UTC created/updated timestamps, applies the release identity and verifier-command checks during live verification and saved-report review, binds live release-gate verification to the production repo `benngaihk/MorphoJet`, binds generated external L4 stable-release verification to `trial_plan.json git_commit` with `--expect-commit`, binds saved stable-release report review to the same planned commit with `--expect-commit`, binds saved release and asset URLs to the recorded repo/tag/asset names, rejects saved reports that do not match an explicit `--expect-repo` or `--expect-commit` when supplied, requires saved reports to record absolute `out_dir`, `--out-dir`, and `--json-out` paths with `--json-out` bound to the report path under review, records and re-checks GitHub asset size and `sha256:` digest metadata against downloaded files and archive summaries, verifies `.sha256` digest values, checksum target filenames, package contents, and requires a compatible archive to pass `morphojet doctor` with the expected commit prefix.

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

For a fast audit of already-generated L3 artifacts, run `python3 benchmark/release_gate.py`. Release-gate JSON and Markdown reports include the run timestamp, git commit, dirty-worktree status, invoked arguments, top-level `claim_status`, `evidence_scope`, `final_production_signoff`, `production_claim_status`, and top-level `missing_or_failed_checks`; JSON also includes `production_claim_checklist`, and the Markdown report renders that checklist to map each audit check to the required evidence and next reviewer action. Markdown reports also include a `Production Claim Boundary` section that says when a report is not production signoff and repeats the current production blockers for human reviewers. Non-final reports are labeled `claim_status=NOT_PRODUCTION_CLAIM`, `evidence_scope=RELEASE_GATE_PRECHECK`, and `final_production_signoff=false`; only a passing report generated with `--require-production-claim` and a complete production audit is labeled `claim_status=FINAL_PRODUCTION_CLAIM`, `evidence_scope=FINAL_PRODUCTION_RELEASE_GATE`, and `final_production_signoff=true`. The standard gate set includes the full CellBinDB direct-mask inspection, existing L3 artifacts, workflow bridge artifacts, and handoff trial artifacts. The saved report verifier rejects missing or tampered checklist rows and claim-scope labels. External L4 trial-plan, readiness, trial, package, reviewer-report, stable-release verifier, local-preflight, and production-evidence-audit labels reuse the same release-gate-owned non-final claim-scope contracts, so intermediate evidence cannot drift into final production wording. Production audit check statuses (`PASS`, `FAIL`, `MISSING`) and top-level production-claim statuses (`PASS`, `INCOMPLETE`) also come from the same release-gate contract used by saved report review. The planned stable tag (`v0.1.0`), stable release URL, and stable semver matcher also come from the release-gate contract used by the external L4 plan generator, final wrapper, GitHub verifier, and saved report verifier. The gate also scans top-level Markdown files plus recursive `docs/` and `corpus/` documentation, including `README.zh-CN.md` and `MORPHOJET-FEASIBILITY.md`, for unsupported English or Chinese production-ready, production-grade, CellProfiler-replacement, or CellProfiler-substitution claims and refuses report output paths that would overwrite or create files inside external evidence inputs, packaged evidence files including `readiness.json`, reviewer reports, or the GitHub release verifier report. Formal release reports should include `--require-l3-provenance`, which checks the CellBinDB provenance file written by a full non-`--skip-cellprofiler` L3 run and re-hashes the recorded artifacts. Final production or stable-release gates should add `--require-production-claim`, which now fails at the CLI contract layer unless `--require-clean-git` and `--require-l3-provenance` are also present, and still fails unless the external L4 workflow trial, matching evidence package, saved external reviewer reports, live stable release, and saved stable-release verifier report checks are all present and passing.

Direct final-claim release-gate use must also keep external L4 evidence bound as a complete input group: `--external-trial-json` requires `--external-trial-root`, trial evidence requires `--external-evidence-package-dir`, and `--external-evidence-package-dir` requires `--external-trial-json`. Complete raw external L4 evidence also requires saved reviewer evidence, and saved reviewer evidence must bind to those same final inputs as a complete reviewer pair: `--external-trial-verification-report` requires the same command to supply `--external-trial-json`, `--external-trial-root`, and `--external-evidence-package-verification-report`; `--external-evidence-package-verification-report` requires `--external-evidence-package-dir`, `--external-trial-json`, and `--external-trial-verification-report`. Live GitHub release checks must stay stable and bound too: `benchmark/release_gate.py --require-production-claim --verify-github-release <tag>` rejects prerelease/RC gates unless `--github-release-kind stable` is supplied, and `--github-release-verification-report` is rejected unless the same command also supplies `--verify-github-release`.

The direct final-claim contract also makes stable-release evidence mandatory rather than optional: `benchmark/release_gate.py --require-production-claim` requires live `--verify-github-release <tag>`, requires that live check to use `--github-release-kind stable`, and requires `--github-release-verification-report` in the same command. This keeps missing live stable-release evidence or missing saved stable-release verifier evidence out of the final production-claim path before any heavier audit work starts.
Release-gate tests enumerate the live tag, stable-kind flag, and saved stable-release verifier report combinations and accept only the complete three-input group, so a partial stable-release evidence bundle cannot satisfy final-claim argument validation.

The same direct final-claim contract now requires the external L4 evidence group to be present before the heavier audit starts: `--external-trial-json`, `--external-trial-root`, `--external-evidence-package-dir`, `--external-trial-verification-report`, and `--external-evidence-package-verification-report` are all required for `--require-production-claim`. Partial groups still get the more specific binding errors above, including rejecting `--external-trial-root` unless `--external-trial-json` is supplied in the same command.
Release-gate tests enumerate all 32 combinations of those five external L4 inputs and accept only the complete five-input group, so partial final-claim evidence groups cannot silently reappear.
Release-gate tests also enumerate all 2048 combinations of the full direct final-claim contract: clean git, L3 provenance, stable-release evidence, saved workflow evidence, and external L4 evidence. Only the complete eleven-condition contract is accepted.
Saved final-report verification applies the same discipline to production PASS metadata and `metadata.argv`: verifier tests enumerate the full saved-report final contract and reject partial clean-git, L3 provenance, stable-release, or external L4 metadata/argv bundles.
The final production wrapper also has regression coverage for saved reviewer/verifier inputs: final commands, including `--dry-run`, require `--external-trial-verification-report`, `--external-evidence-package-verification-report`, `--github-release-verification-report`, `--github-workflow-verification-report`, and `--production-evidence-audit-report` together, while dry-run skips file-existence checks and local-preflight mode remains the explicitly non-final exception.

The same source-doc guard treats the root bilingual README contract as release evidence: it requires the English README to link to `README.zh-CN.md` and requires the Chinese README to keep the external L4 workflow, local preflight, final production wrapper, current blocker list, package README evidence path, and the [README 中文版维护承诺](README.zh-CN.md#readme-中文版维护承诺) visible for Chinese-community review. The guard also requires both root READMEs to preserve the same shared audit anchors, including `claim_status=NOT_PRODUCTION_CLAIM`, `evidence_scope=RELEASE_GATE_PRECHECK`, `final_production_signoff=false`, `production_claim_status=INCOMPLETE`, `benchmark/run_production_gate.py`, and the saved final wrapper report flags. Generated external L4 workspace READMEs now have the same explicit shared-anchor guard during `--verify-plan-files`, so English and Chinese trial instructions must both retain the non-final labels, saved reviewer report flags, local-preflight signoff flag, external trial/package saved reviewer `--expect-commit <trial_plan git_commit>` bindings, stable-release and saved stable-release-report `--expect-commit <trial_plan git_commit>` bindings, final wrapper saved-report flags, and final saved-report verification flags. Chinese reviewers can start from the [中文社区验证入口](README.zh-CN.md#中文社区验证入口), which points to the same non-final evidence chain and final blockers instead of a weaker parallel path.

To re-check a saved release-gate JSON report during review:

```bash
python3 benchmark/verify_release_gate_report.py benchmark/results/release-gate/report.json
python3 benchmark/verify_release_gate_report.py benchmark/results/release-gate/report.json --verify-git-commit
python3 benchmark/verify_release_gate_report.py benchmark/results/release-gate/production-claim.json --require-report-pass --require-clean-git-metadata --verify-git-commit --require-production-claim-pass --expect-missing-checks none
```

The saved release-gate verifier checks top-level summary fields and claim-scope labels against `production_claim_audit`, validates metadata and gate-entry schemas, requires `metadata.generated_at_utc` to be UTC, requires the expected production-audit check list, can verify the recorded git commit is reachable, can require clean-git metadata, rejects `github_release_kind=stable` metadata unless it is paired with a stable release tag, and rejects production PASS reports that omit required clean-git, L3 provenance, external L4, saved external reviewer, stable GitHub release, or saved stable-release verifier gates. Production PASS reports must also carry metadata and `metadata.argv` proving the final flags, absolute external L4 paths, saved reviewer/verifier report paths, and stable release tag/kind were used; the verifier checks this both ways so recorded metadata must appear in `argv` and key production arguments in `argv` must be reflected back into metadata. Saved release-gate reports also reject relative production evidence paths and relative path-valued `metadata.argv` entries for external L4 evidence, reviewer reports, and explicit `--out-json` / `--out-md` outputs; when `--out-json` is recorded it must match the report file under review. The production evidence metadata keys and path-valued `metadata.argv` flags are release-gate-owned contracts shared by the writer and saved report verifier. Boolean metadata flags such as clean-git, L3 provenance, L3 rerun, and release-archive build must have their matching gates. External L4 metadata paths must have matching validation gates. `metadata.verify_github_release` must have a matching live GitHub release gate whose command binds the same tag, stable/prerelease expectation, and verifier JSON output. Saved reviewer-report metadata must have the matching saved-reviewer gate, and those gates must preserve the fail-closed verifier commands bound to metadata paths, including file rechecks, PASS requirements, package `--require-trial-json`, external trial/package expected commit binding, stable GitHub release checks, git commit verification, expected release tag binding, expected final commit binding, and expected repo binding. `release_gate.py` canonicalizes those recorded path values to absolute paths when it writes a report.
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
  --github-workflow-verification-report path/to/github-workflows.json \
  --production-evidence-audit-report path/to/production-evidence-audit.json \
  --github-release-tag v0.1.0
```

The wrapper requires a stable non-RC tag and fail-fast requires all five saved final-input report arguments, including in `--dry-run`: `--external-trial-verification-report`, `--external-evidence-package-verification-report`, `--github-release-verification-report`, `--github-workflow-verification-report`, and `--production-evidence-audit-report`. Non-dry-run final execution checks that the external trial JSON, trial root, evidence package directory, and saved verifier/audit reports exist before invoking the final gate, fail-closed re-checks those saved verifier reports with `--verify-report-files --require-report-pass` where file-backed evidence exists, re-checks the saved production evidence audit with `--verify-report-files --require-ready`, rejects final output paths that would overwrite package review files such as `README.md` or `README.zh-CN.md`, requires saved package reviewer reports to include `trial_json`, requires saved trial/package reviewer reports to match the current external inputs, current final commit, and the same external-evidence identity summary, requires `--require-report-pass`, `--require-stable-report`, `--verify-report-files`, `--verify-git-commit`, the final tag, the `benngaihk/MorphoJet` repo, and the current final commit for the saved GitHub release verifier report, requires the saved GitHub workflow report to bind `benngaihk/MorphoJet`, `main`, the current git commit, `ci.yml`, and `external-l4-rehearsal.yml`, and passes those reviewer reports through to `benchmark/release_gate.py` so the final JSON/Markdown includes the reviewer-report gates alongside clean-git, L3 provenance, GitHub Actions workflow verification, external L4 trial, external L4 evidence package, live stable GitHub release, and `--require-production-claim` checks. If that release gate passes, the wrapper immediately re-checks the saved final report with `benchmark/verify_release_gate_report.py --require-report-pass --require-clean-git-metadata --verify-git-commit --require-production-claim-pass --expect-missing-checks none`. Direct `benchmark/release_gate.py` saved reviewer-report gates also bind saved external trial/package reports to the current external evidence inputs, current final commit, and matching external-evidence identity, re-check saved GitHub release reports with `--verify-git-commit`, require `--expect-tag <final-tag>`, `--expect-repo benngaihk/MorphoJet`, and `--expect-commit <final-commit>`, bind saved GitHub reports to `--verify-github-release` when a live tag is supplied, and require the saved GitHub workflow report for production claims. The saved GitHub release verifier report is labeled `claim_status=NOT_PRODUCTION_CLAIM`, `evidence_scope=GITHUB_STABLE_RELEASE_VERIFICATION`, and `final_production_signoff=false`; the saved GitHub workflow verifier report is also non-final with `evidence_scope=GITHUB_ACTIONS_WORKFLOW_VERIFICATION`; the production evidence audit remains `evidence_scope=PRODUCTION_EVIDENCE_READINESS_AUDIT`, not final signoff. These are audit artifacts and do not replace the live stable-release check, real external L4 evidence, or final production gate. The saved GitHub verifier treats `--require-stable-report` as signoff mode and rejects it unless PASS enforcement, file rechecks, git commit/tag verification, expected tag, expected repo, and expected commit are all present. Use `--dry-run` to inspect the assembled release-gate and final-report verifier commands without requiring those supplied external paths to exist yet; use `--local-evidence-preflight-only` for the earlier non-final path where external saved reviewer reports may still be absent.

Direct `benchmark/release_gate.py` final-claim runs enforce those same bindings at argument validation: external trial JSON requires a current trial root and evidence package directory, external package directories require the source trial JSON, complete external L4 evidence requires both saved reviewer reports, saved external reviewer reports require the current trial/package inputs and the matching saved reviewer report, live `--verify-github-release` requires `--github-release-kind stable`, `--github-release-verification-report` requires a live `--verify-github-release` tag, and `--github-workflow-verification-report` is required for production claims. These checks match the final wrapper's stable non-RC release, remote CI, and evidence-binding requirements.

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

The verifier also confirms that the report's `metadata.generated_at_utc` is UTC, `metadata.git_commit` is a reachable commit in the current checkout, `metadata.github_release_tag` is a stable non-RC release tag, metadata evidence paths, input artifact paths, and path-valued `metadata.argv` entries are absolute, `skipped_final_checklist` matches the preflight contract, saved reviewer metadata paths have matching saved reviewer gate entries and existing input-artifact hash summaries, and `metadata.argv` matches the recorded preflight inputs so path, stable-tag, local-preflight flag, duplicate critical flags, missing flag values, and local preflight claim-scope summaries cannot be tampered independently from metadata. Required trial/package input artifacts must remain `exists=true` with size/SHA-256 summaries. It rejects packaged readiness `package_name`, workspace, or manifest tampering when the referenced package is available, and binds the saved package README handoff-contract summaries and `review_entrypoint_present` values back to the current package `README.md`, package `README.zh-CN.md`, and `rendered_manifest.json`. With `--verify-local-evidence-preflight-files`, it recomputes the source trial, packaged trial, and package artifact-manifest claim-scope summaries, the packaged readiness JSON `package_name`, workspace, and manifest summary, and the package README scope, handoff-contract summaries, and reviewer-entrypoint status in addition to file sizes and SHA-256 hashes. With `--verify-local-evidence-preflight-gates`, it reruns the recorded external L4 trial, package, and saved reviewer-report gates from the report metadata and rejects stale gate status/detail/command data; path aliases that resolve to the same absolute location, such as `/tmp` and `/private/tmp` on macOS, are normalized only for detail/command comparison so legitimate saved reports are portable while non-path tampering still fails. `--require-local-evidence-preflight-pass` is a signoff-mode flag and now requires `metadata.git_dirty=false`, empty `metadata.git_status`, `--verify-local-evidence-preflight-files`, and `--verify-local-evidence-preflight-gates`, so a dirty, structurally valid, or un-rehashed saved preflight JSON cannot be accepted as reviewer-ready evidence.

After local preflight and after saving the GitHub workflow and stable-release verifier reports, run a lightweight production evidence audit before invoking the final wrapper:

```bash
python3 benchmark/audit_production_evidence.py \
  --external-trial-json path/to/external/handoff_trial.json \
  --external-trial-root path/to/external \
  --external-evidence-package-dir path/to/evidence-packages/external-l4-trial \
  --external-trial-verification-report path/to/external/trial-verification.json \
  --external-evidence-package-verification-report path/to/evidence-packages/package-verification.json \
  --github-release-verification-report path/to/github-release/verification.json \
  --github-workflow-verification-report path/to/github-workflows.json \
  --github-release-tag v0.1.0 \
  --verify-live-github-release \
  --out-json path/to/production-evidence-audit.json \
  --out-md path/to/production-evidence-audit.md
```

The audit report records `claim_status=NOT_PRODUCTION_CLAIM`, `evidence_scope=PRODUCTION_EVIDENCE_READINESS_AUDIT`, `final_production_signoff=false`, `production_claim_status=PASS|INCOMPLETE`, and the same production blocker names used by release gate. It also records `input_files` size/SHA-256 summaries for the external trial JSON and each supplied saved final-input reviewer, workflow, and stable-release report. Re-check it with `python3 benchmark/audit_production_evidence.py --verify-report path/to/production-evidence-audit.json --verify-report-files --require-ready` before running the final wrapper; the final wrapper also requires the same saved file through `--production-evidence-audit-report` and reruns that recheck itself. This reruns the saved audit from its metadata paths and rejects stale commit, argv, input-path, input-file hash, or final-wrapper-command tampering. It is still a reviewer checklist and path-binding guard, not a replacement for `benchmark/run_production_gate.py` or the saved final `verify_release_gate_report.py --require-production-claim-pass --expect-missing-checks none` signoff.

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

Use `benchmark/handoff/external_lab_template.json` as the starting point for real lab handoff files. To create a concrete workspace with the template manifest, input directories, bilingual English/Chinese README files, and the exact plan-verification/validation/readiness/readiness-verification/run/trial-review/trial-review-recheck/package/package-review/package-review-recheck/preflight/preflight-verification/stable-release/saved-release-verification/workflow-verification/production-evidence-audit/final-production/final-report-verification commands, run `python3 benchmark/prepare_external_l4_trial.py --workspace path/to/external-trial`. The saved plan verifies that `audit_production_evidence` consumes the same trial, package, reviewer, stable-release, and workflow verifier paths as `final_production_gate`, writes `production-evidence-audit.json` / `.md`, and that `verify_production_evidence_audit --verify-report-files --require-ready` passes before the final wrapper. This production-evidence audit is still `claim_status=NOT_PRODUCTION_CLAIM` and `evidence_scope=PRODUCTION_EVIDENCE_READINESS_AUDIT`; it is a final-input readiness checklist, not production signoff. The rest of the generated plan still records UTC provenance, non-final claim labels, external evidence requirements, pre-signoff requirements, final signoff requirements, production blockers, stale-output protection, bilingual README checks, saved reviewer report file rechecks, stable-release verification, saved workflow verification, final production gate execution, and saved final report verification. Final production release gates should validate both the trial report and package with `--external-trial-json` and `--external-evidence-package-dir`.

For an internal rehearsal of that chain on the committed CellBinDB full artifacts, run the wrapper below from a clean worktree. It prepares the workspace, copies the committed MorphoJet/CellProfiler CSV inputs, runs the generated plan/readiness/trial/package/local-preflight commands through saved report verification, and writes a summary labeled `claim_status=NOT_PRODUCTION_CLAIM`, `evidence_scope=EXTERNAL_L4_INTERNAL_REHEARSAL`, `final_production_signoff=false`, and `final_evidence_acceptable=false`. Re-check the saved summary with `--verify-report-files --require-report-pass` so the input/output file summaries, local-preflight status, and non-final labels are rebound before review. It intentionally skips the stable GitHub release, saved stable-release report, final production gate, and final saved-report verifier; it is a rehearsal of the evidence mechanics, not external L4 signoff.

```bash
python3 benchmark/run_external_l4_rehearsal.py \
  --workspace /tmp/morphojet-external-l4-rehearsal \
  --overwrite
python3 benchmark/run_external_l4_rehearsal.py \
  --verify-report /tmp/morphojet-external-l4-rehearsal/external-l4-rehearsal-summary.json \
  --verify-report-files \
  --require-report-pass
```

The same internal rehearsal machinery is wired into `.github/workflows/external-l4-rehearsal.yml` for pushes to `main`, weekly scheduled runs, and manual `workflow_dispatch`. That workflow generates a minimal CI fixture outside the git checkout, runs the rehearsal, immediately re-checks the saved summary with file hashes and PASS enforcement, writes the Markdown summary to the GitHub Actions step summary, and uploads the summary, trial plan, bilingual README files, readiness report, trial report, saved trial/package verifier reports, local preflight report, and evidence package as a 30-day artifact. It is continuous non-final rehearsal evidence and still does not satisfy real external L4 signoff, the stable GitHub release, or final production-claim gates.

After pushing a candidate commit, save and re-check the required GitHub Actions workflow evidence with:

```bash
python3 benchmark/verify_github_workflows.py \
  --commit "$(git rev-parse HEAD)" \
  --json-out path/to/github-workflows.json
python3 benchmark/verify_github_workflows.py \
  --verify-report path/to/github-workflows.json \
  --require-report-pass \
  --expect-repo benngaihk/MorphoJet \
  --expect-branch main \
  --expect-commit "$(git rev-parse HEAD)" \
  --expect-workflow ci.yml \
  --expect-workflow external-l4-rehearsal.yml
```

Generated external L4 trial plans use the same explicit commit binding: `verify_github_workflows` writes the saved report with `--commit <trial_plan git_commit>`, and `verify_github_workflows_report` rechecks it with `--expect-commit <trial_plan git_commit>`. This prevents a later `main` branch movement from silently replacing the remote-CI evidence intended for final review.

The external L4 template declares `required_object_metadata_columns` for `Plate`, `Well`, and `Site`. Readiness checks enforce those columns on MorphoJet `Objects.csv`, so real handoff workspaces should generate `Objects.csv` with `measure --include-object-metadata` or intentionally update the manifest contract before review.

Generated external-workspace READMEs also tell reviewers that local preflight treats saved reviewer reports as validated only when the saved trial verifier, saved package verifier, and reviewer-report pair gates pass with `--expect-commit <trial_plan git_commit>` and matching external-evidence identity summaries; otherwise the saved reviewer report check stays in the skipped final checklist until the failing reviewer report is fixed and rechecked. They now also state that `verify_local_evidence_preflight` rehashes package `README.md` and `README.zh-CN.md`, recomputes package README-rendered readiness scope, binds the README-rendered handoff contract back to `rendered_manifest.json`, recomputes each package README `review_entrypoint_present` value before PASS can be accepted, and renders those values in the saved local preflight Markdown `Review Entrypoint` column.

External trial reports and saved external trial verifier reports are both labeled as non-final artifacts: the source trial report uses `claim_status=NOT_PRODUCTION_CLAIM`, `evidence_scope=EXTERNAL_L4_WORKFLOW_TRIAL`, and `final_production_signoff=false`, while the saved reviewer report uses `claim_status=NOT_PRODUCTION_CLAIM`, `evidence_scope=EXTERNAL_L4_WORKFLOW_TRIAL_REVIEW`, and `final_production_signoff=false`. Real external evidence must include at least three non-placeholder acceptance criteria; readiness and release-gate validation both reject weaker signoff. The saved reviewer report copies the source trial claim-scope labels and `metadata.git_commit` into `input_files.trial_json`, copies the external-evidence identity summary into `input_files.external_evidence`, copies the bound readiness report's READY status, non-final claim-scope labels, UTC generation time, package name, workspace, and manifest into `input_files.readiness_report`, and file recheck recomputes them so a trial-reviewer JSON cannot be mistaken for final production signoff by itself. Saved trial reviewer signoff with `--require-report-pass` now fails unless `--verify-report-files` is also supplied; final saved reviewer signoff also requires `--expect-commit <final-commit>` so an older trial report cannot satisfy the final reviewer slot. Evidence packages include both `README.md` and `README.zh-CN.md`. Both README files are listed in `artifact_manifest.review_files`, included in the package zip, checked by release gate for required signoff fields, and recorded by the standalone package verifier so file rechecks catch tampering in either language. The package `artifact_manifest.json` and both READMEs must also preserve `claim_status=NOT_PRODUCTION_CLAIM`, `evidence_scope=EXTERNAL_L4_EVIDENCE_PACKAGE`, and `final_production_signoff=false`; `artifact_manifest.json` also records the source trial's `trial_claim_status`, `trial_evidence_scope`, and `trial_final_production_signoff` so the package remains bound to a non-final trial report. Saved package verifier reports are independently labeled `claim_status=NOT_PRODUCTION_CLAIM`, `evidence_scope=EXTERNAL_L4_EVIDENCE_PACKAGE_REVIEW`, and `final_production_signoff=false`, copy the package external-evidence identity summary into `input_files.package_external_evidence`, copy the package manifest's package-scope and source-trial scope fields into `input_files.package_artifact_manifest`, copy the packaged trial `metadata.git_commit` into `input_files.package_handoff_trial`, copy package README `trial_git_commit` values for both English and Chinese READMEs, copy the package readiness report's READY status, non-final claim-scope labels, UTC generation time, `package_name`, workspace, and manifest into `input_files.package_readiness`, copy the source trial labels and git commit into `input_files.source_trial_json` when `--trial-json` is supplied, and `--verify-report-files` recomputes them from the package external evidence, package manifest, package readiness report, package READMEs, and source trial report. The final wrapper and local preflight add a reviewer-report pair gate that rejects saved trial/package reviewer reports whose reviewer identity, review timestamp, acceptance-criteria hash, or full external-evidence digest differ. Saved package reviewer signoff with `--require-report-pass` now fails unless `--verify-report-files` is also supplied, and final saved package reviewer signoff also requires `--expect-commit <final-commit>`.

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

Saved production-evidence snapshot: commit `8edfd2ffc07c728ea68ce6a9ff1f36bb07637e6f` has saved GitHub workflow verification for `ci.yml` and `external-l4-rehearsal.yml` on `main`. The same commit was rechecked with `benchmark/release_gate.py --require-clean-git --require-l3-provenance --github-workflow-verification-report ...`, so clean git metadata, CellBinDB L3 provenance hashes, and remote workflow evidence are bound in one saved release-gate report. That report verifies as PASS while preserving `claim_status=NOT_PRODUCTION_CLAIM` and `production_claim_status=INCOMPLETE`; the remaining blockers are now only the real external L4 workflow trial, matching evidence package, saved external reviewer reports, live stable GitHub release, and saved stable-release verifier report. See [docs/VALIDATION_RESULTS.md](docs/VALIDATION_RESULTS.md) for the exact commands.

The current `main` external L4 workspace plan was also regenerated with `benchmark/prepare_external_l4_trial.py --verify-plan-files --require-plan-files`, confirming that the bilingual trial workspace, saved reviewer report steps, local preflight, production evidence audit, stable-release verifier, saved workflow verifier, and final wrapper commands remain bound as non-final evidence. It is ready for a real external trial owner to replace placeholder evidence, but it is not final production signoff.
