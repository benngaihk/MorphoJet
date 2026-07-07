# Validation Results

Updated: 2026-07-07

## Release-Gate Snapshot for `db65fa8`

This snapshot records the clean `main` verification for the code commit that protects external L4 workspaces from stale execution outputs before preparation, keeps readiness, reviewer, release-gate, local-preflight, and final wrapper report outputs from overwriting or creating files inside protected evidence paths, records and re-checks audit metadata on external L4 readiness reports and trial plans, generates plan-verification and readiness-verification steps before trial execution, binds generated README contents to saved trial plans, and rejects saved stable-release PASS reports whose archive summaries record a failed checksum match. It is not a production claim; it confirms that the committed release-gate evidence still passes L3 while exposing the exact final blockers.

Environment:

- Branch: `main`
- Verified code commit: `db65fa8`
- Release-gate command: `PATH="$HOME/.cargo/bin:$PATH" python3 benchmark/release_gate.py --require-clean-git --require-l3-provenance --out-json /tmp/morphojet-l3-release-report-main-db65fa8.json --out-md /tmp/morphojet-l3-release-report-main-db65fa8.md`
- Saved-report verifier command: `python3 benchmark/verify_release_gate_report.py /tmp/morphojet-l3-release-report-main-db65fa8.json --require-report-pass --require-clean-git-metadata --verify-git-commit --expect-missing-checks external_l4_workflow_trial,external_l4_evidence_package,stable_github_release`

Result:

| Gate | Result |
|---|---:|
| Full Python unit test suite | PASS, 312 tests |
| Source claim-language guard | PASS |
| Whitespace diff check | PASS |
| Clean L3 release gate | PASS |
| Saved release-gate report verifier | PASS |
| `production_claim_status` | `INCOMPLETE` |
| Remaining production blockers | `external_l4_workflow_trial`, `external_l4_evidence_package`, `stable_github_release` |

The saved release-gate verifier checks production metadata and `metadata.argv` both ways: final metadata values must appear in the recorded command line, and key production command-line arguments must be reflected back into metadata without duplicate critical flags or missing flag values. The local evidence preflight verifier, external trial reports, external reviewer verifier reports, and GitHub release verifier reports now apply the same binding discipline to their own canonical argv; external trial runner argv must preserve the source manifest, sorted `--var` values, output paths, and strict external-evidence flag. `benchmark/prepare_external_l4_trial.py` now creates a concrete external trial workspace with the template manifest, input directories, generated plan-verification/validation/readiness/readiness-verification/run/package/preflight commands, stale execution-output checks, and a `NOT_PRODUCTION_CLAIM` plan so external reviewers can prepare real evidence without implying that the scaffold itself is evidence. The plan records `generated_at_utc`, canonical generator `argv`, template size, and template SHA-256 so the prepared scaffold source can be audited; `--verify-plan-files` re-checks the saved plan schema, generator command binding, template hash, manifest presence, README contents, and regenerated command set. The generated command set and README run `verify_plan` first, so reviewers can revalidate the saved plan before any external L4 execution step, then run `verify_readiness` before `run_trial`, making the saved readiness report recheck part of the planned external execution sequence. `benchmark/check_external_l4_readiness.py` adds a pre-execution readiness report for filled external evidence, input files, MorphoJet Objects.csv and expected CellProfiler CSV schema/row coverage, absent manifest-declared trial outputs, absent planned reviewer/preflight report outputs, report output safety, package output paths, protected readiness report output paths and descendants, plus `generated_at_utc` and canonical checker `argv` before any real trial is run. Saved readiness reports can now be re-checked for schema, timestamp, `NOT_PRODUCTION_CLAIM`, canonical `argv`, status/issues/check consistency, and rerun workspace readiness with `--verify-report-files --require-ready`. Saved reviewer reports also require exactly one recorded `--json-out` value bound to the saved report path under review, the standalone trial/package reviewer tools reject reviewer outputs that would overwrite or create files inside protected evidence inputs/artifacts, and release-gate plus production-wrapper reports apply the same path-safety rule to protected external evidence paths. This prevents stale or hand-edited reports from silently appearing stronger than the command that produced them.

## Production Gate Wrapper Milestone

This milestone adds `benchmark/run_production_gate.py` as the final production-claim entrypoint. It does not replace the release gate; it assembles the required final checks into one command and rejects release-candidate tags before invoking release verification.
The wrapper is treated as a release-gate orchestration file for provenance compatibility, so changing it does not by itself require regenerating CellBinDB L3 artifacts; changes to measurement code or benchmark generators still do.
Actual wrapper runs now fail fast when the external trial JSON, trial root, or evidence package directory is missing; `--dry-run` remains available for command review before those external artifacts exist.
Release-gate JSON and Markdown reports now mirror `production_claim_status` and `missing_or_failed_checks` at the top level, so CI, release review, and signoff tooling can identify production blockers without parsing the full audit table.
Release gate now runs `benchmark/validate_claim_language.py` so source docs fail fast if they contain unsupported production-ready or CellProfiler-replacement claims before the final production audit passes.
Saved release-gate JSON reports can be re-checked with `benchmark/verify_release_gate_report.py`, which requires the top-level summary fields to match `production_claim_audit`, validates metadata and gate entry schemas, requires the expected production-audit check list, can verify the recorded git commit is reachable, can require clean-git metadata, rejects production PASS reports missing required production gates or final production metadata flags/paths/stable-release identity, and can require both report PASS and production-claim PASS for final signoff.
External L4 evidence package validation now requires the README to preserve trial/signoff fields, requires canonical packager `argv` in the artifact manifest matching the source trial JSON, trial root, output directory, and package name, requires absolute trial JSON/root source metadata, source trial JSON size/SHA-256, review-file size/SHA-256 entries, release-gate input matching, and unique package paths in the artifact manifest, requires the package zip to contain exactly the required review files and manifest-declared artifacts, rejects duplicate, missing, and extra zip entries, checks zip entry bytes against the package directory, and validates the zip checksum digest format plus target filename. Saved external trial and evidence package verifier reports also record canonical verifier `argv` plus size/SHA-256 summaries for the source trial JSON, package review files, zip archive, and checksum file, require `--json-out` bound to the saved report path under review, and `--verify-report-files` rejects reports whose saved summaries or verifier command bindings no longer match recomputed evidence files.
The package README must preserve the dataset source, execution environment, reviewer identity/role, review timestamp, signoff statement, external trial generation time, exact validation detail, and every external evidence acceptance criterion, and the package artifact manifest must preserve the exact external trial PASS detail rendered by release gate; stale or tampered package review metadata is rejected during package review.
External L4 validators now reject `REPLACE_WITH` placeholders in `external_evidence.acceptance_criteria`, reviewer signoff fields, and the top-level external evidence strings; `reviewed_at_utc` must be an ISO timestamp with timezone for real trials and must not be earlier than the trial generator timestamp. The repository template can still be schema-checked with the explicit placeholder allowance.
GitHub stable-release verification now rejects prerelease or non-semver tags in the lower-level verifier as well as in the final production wrapper.
Saved GitHub release verification JSON reports can now be re-checked with `benchmark/verify_github_release.py --verify-report`; reports include schema version, verifier identity, generation timestamp, canonical verifier `argv`, GitHub release ID/API identity, author, target commit-ish, created/published timestamps, immutable state, draft state, prerelease state, the full 40-character tag commit, the 12-character `doctor` commit prefix, and GitHub asset metadata records for asset name, GitHub asset ID, API URL, download URL, upload state, created/updated timestamps, size, content type, and `sha256:` digest, live verification and `--verify-report-files` recompute downloaded asset names, archive SHA-256 values, checksum file contents, and every recorded GitHub asset size/digest field from the report's `out_dir`, `--verify-git-commit` confirms the saved commit and expected tag resolve in the current git checkout, saved-report validation rejects PASS reports marked as draft releases, rejects release and asset metadata URLs that are not bound to the saved repo/tag/asset names, rejects release or asset API URLs that are not bound to the saved repo, rejects invalid or reversed release timestamps, rejects duplicate asset IDs or API URLs, rejects asset metadata entries not marked `uploaded`, rejects invalid or reversed asset timestamps, rejects saved reports whose recorded `out_dir` would contain the saved verifier report itself or other non-release assets, rejects PASS archive summaries whose recorded `checksum_match` is not true, rejects archive SHA summaries that do not match the corresponding GitHub asset digest, rejects PASS reports whose expected/release/downloaded asset sets or archive summaries are incomplete, rejects verifier argv that is not bound to the saved tag, repo, output directory, stable/prerelease expectation, and required saved report path, rejects unbound full/doctor commit metadata and compatible archive `doctor` summaries that are not PASS/no-issues, `--require-stable-report` prevents prerelease verification JSON from satisfying production signoff, and `--expect-tag` prevents a saved report for another stable tag from satisfying the reviewer-report slot.
The wrapper also provides `--local-evidence-preflight-only` so a completed external L4 trial, evidence package, and supplied external L4 saved reviewer verification reports can be validated before the stable GitHub release exists, using the same release-gate validators that the final production claim uses, passes supplied reviewer reports into final release-gate reports, and writes local evidence-preflight JSON/Markdown reports labeled `NOT_PRODUCTION_CLAIM`, `evidence_scope=LOCAL_EXTERNAL_L4_PREFLIGHT`, and `final_evidence_acceptable=false` with skipped final checks, canonical wrapper `metadata.argv`, and key input file hashes. Local evidence preflight now rejects `--github-release-verification-report` so the report cannot imply stable-release evidence that it does not validate.
Saved local evidence preflight JSON reports can also be re-checked with `--verify-local-evidence-preflight-report`, which validates the report schema, metadata types/formats, reachable git commit, claim-scope labels, final-evidence rejection flag, skipped/validated check lists, input artifact digest fields, `metadata.argv` bindings for effective preflight inputs, and expected external L4 gate entries. Add `--verify-local-evidence-preflight-files` to recompute recorded input artifact sizes and SHA-256 hashes, `--verify-local-evidence-preflight-gates` to rerun the recorded external L4 and saved reviewer-report gates, and `--require-local-evidence-preflight-pass` for review/signoff.
External L4 trial reports can now be reviewed directly with `benchmark/verify_external_trial_report.py`. The standalone verifier reuses the release-gate external trial validator, requires an artifact root that resolves declared outputs, writes a machine-readable PASS/FAIL JSON report with schema/verifier/timestamp/argv audit fields before evidence packaging, records source trial JSON and resolved artifact file size/SHA-256 summaries, rejects report outputs that would overwrite or create files inside the source trial JSON or declared artifacts, and can re-check saved verifier reports with `--verify-report-files` so recorded gate status/detail, verifier command bindings including `--json-out`, and saved input summaries must match freshly recomputed validation.
External L4 evidence packages can now be reviewed directly with `benchmark/verify_external_evidence_package.py`. The standalone verifier reuses the release-gate package validator, optionally binds the package to the exact source `handoff_trial.json`, writes a machine-readable PASS/FAIL JSON report with schema/verifier/timestamp/argv audit fields for reviewer signoff, rejects report outputs that would overwrite or create files inside source/package evidence files, and can re-check saved verifier reports with `--verify-report-files` so recorded gate status/detail and verifier command bindings including `--json-out` must match freshly recomputed validation. Production signoff uses `--require-trial-json` so saved package reviewer reports cannot be accepted unless they are bound to the source trial JSON.

Required final command shape:

```bash
python3 benchmark/run_production_gate.py \
  --external-trial-json path/to/external/handoff_trial.json \
  --external-trial-root path/to/external \
  --external-evidence-package-dir path/to/evidence-packages/external-l4-trial \
  --github-release-verification-report path/to/github-release/verification.json \
  --github-release-tag v0.1.0
```

The wrapper invokes `benchmark/release_gate.py` with `--require-clean-git`, `--require-l3-provenance`, `--require-production-claim`, external L4 trial/package validation, saved reviewer report checks when supplied, `--verify-github-release`, and `--github-release-kind stable` in the same report. Saved GitHub release verification JSON is rechecked with file hashes and stable-report requirements when supplied, but the current production claim remains incomplete until real external L4 evidence and a live stable release verification are supplied and that combined gate passes.
The production wrapper now also rejects saved external L4 trial/package reviewer reports that are valid by themselves but point to a different trial JSON, trial root, or evidence package directory than the current wrapper inputs.
The production wrapper now rejects saved stable GitHub release reviewer reports that are valid by themselves but point to a repository other than `benngaihk/MorphoJet`.

Local validation for the wrapper:

| Command | Result |
|---|---:|
| `python3 -m py_compile benchmark/run_production_gate.py tests/test_run_production_gate.py` | PASS |
| `python3 tests/test_run_production_gate.py` | PASS |
| `python3 -m unittest discover -s tests -p 'test_run_production_gate.py'` | PASS |
| `python3 benchmark/run_production_gate.py --external-trial-json path/to/external/handoff_trial.json --external-trial-root path/to/external --external-evidence-package-dir path/to/evidence-packages/external-l4-trial --github-release-tag v0.1.0 --dry-run` | PASS |
| `python3 benchmark/run_production_gate.py --external-trial-json missing/handoff_trial.json --external-trial-root missing/root --external-evidence-package-dir missing/package --github-release-tag v0.1.0` | FAIL as expected before release-gate execution |
| `python3 tests/test_run_production_gate.py` with local evidence preflight report coverage | PASS |
| `python3 tests/test_run_production_gate.py` with saved report verifier coverage | PASS |
| `python3 tests/test_package_external_trial.py` with standalone evidence package verifier coverage | PASS |
| `python3 tests/test_verify_external_trial_report.py` with standalone external trial report verifier coverage | PASS |

## L2 ExampleHuman Oracle Snapshot

This is the first real CellProfiler oracle run. It passes the L2 correctness gate for the current measurement subset on a pinned public example.

Environment:

- CellProfiler Docker image: `cellprofiler/cellprofiler:4.2.6`
- CellProfiler examples commit: `4972b59e670a4ae96c3d453803c92eeff378d054`
- Dataset: `ExampleHuman`, 1 image set, CC-0 per upstream README
- Objects: `Cells`, `Cytoplasm`, `Nuclei`
- Channels compared: `DNA`, `PH3`
- MorphoJet commit under test: local run after `4c8313a` plus local parity fixes

Artifacts:

- CellProfiler long oracle CSV: `benchmark/results/cellprofiler-run-426-npy/Objects.long.csv`
- MorphoJet CSV: `benchmark/results/morphojet-run-426-labels-tiff/Objects.csv`
- Parity report: `benchmark/results/parity/example-human-objects-parity.md`
- Parity JSON: `benchmark/results/parity/example-human-objects-parity.json`

Result:

| Gate | Result |
|---|---:|
| Expected rows | 1734 |
| Actual rows | 1734 |
| Missing rows | 0 |
| Extra rows | 0 |
| Missing columns | 0 |
| Extra columns | 0 |
| Numeric compared | 29478 |
| Numeric failures | 0 |
| Status | PASS |

Passing columns:

- `AreaShape_Area`
- `AreaShape_Center_X`
- `AreaShape_Center_Y`
- `AreaShape_BoundingBoxMinimum_X`
- `AreaShape_BoundingBoxMinimum_Y`
- `AreaShape_BoundingBoxMaximum_X`
- `AreaShape_BoundingBoxMaximum_Y`
- `Intensity_MinIntensity`
- `Intensity_MaxIntensity`
- `Intensity_MeanIntensity`
- `Intensity_MedianIntensity`
- `Intensity_IntegratedIntensity`
- `AreaShape_Perimeter`
- `AreaShape_Eccentricity`
- `AreaShape_MajorAxisLength`
- `AreaShape_MinorAxisLength`
- `AreaShape_Solidity`

Max residual numeric differences are floating-point noise only:

| Column | Max Abs | Max Rel |
|---|---:|---:|
| `Intensity_IntegratedIntensity` | 0.000003457300295 | 0.00000004176837204 |
| `AreaShape_MajorAxisLength` | 0.00000000006598988023 | 0.000000000006470431086 |
| `AreaShape_Solidity` | 0.00000000004982936286 | 0.00000000004982936286 |

Conclusion: L2 passes for ExampleHuman and the current measurement subset. Production-grade status remains unproven until L3 performance/RSS and a larger public corpus pass.

## L3 ExampleHuman Smoke

This run exercises the same pinned ExampleHuman oracle path with elapsed-time and peak-RSS capture for both tools. It is a smoke benchmark, not the production L3 gate, because the dataset only materializes 6 MorphoJet image rows. The production L3 claim still requires >=1,000 real/public image rows.

Environment:

- CellProfiler Docker image: `cellprofiler/cellprofiler:4.2.6`
- CellProfiler platform: `linux/amd64`
- CellProfiler examples commit: `4972b59e670a4ae96c3d453803c92eeff378d054`
- Dataset: `ExampleHuman`, 1 image set, 3 object sets, 2 channels
- MorphoJet command: `target/release/morphojet measure --threads 8 --cellprofiler-compatible`
- CellProfiler RSS source: `docker stats MemUsage sampled during container run`
- MorphoJet RSS source: local process `ru_maxrss` captured by `benchmark/run_command_metrics.py`

Artifacts:

- Runner: `benchmark/run_examplehuman_oracle.py`
- Docker metrics wrapper: `benchmark/run_docker_metrics.py`
- CellProfiler metrics: `benchmark/results/metrics-examplehuman/cellprofiler-examplehuman.metrics.json`
- MorphoJet metrics: `benchmark/results/metrics-examplehuman/morphojet-examplehuman.metrics.json`
- Gate report: `benchmark/results/impact-examplehuman/summary.md`
- Gate JSON: `benchmark/results/impact-examplehuman/summary.json`

Result:

| Gate | Required | Observed | Status |
|---|---:|---:|---:|
| Scale | >=1000 image rows | 6 | FAIL |
| Object count parity | 100% | 100.0000% | PASS |
| Core numeric parity | >=99% | 100.0000% | PASS |
| Wall-clock speedup | >=10x | 196.74x | PASS |
| Peak RSS ratio | <=50% | 6.89% | PASS |

Raw metrics:

| Tool | Seconds | Peak RSS MB | Notes |
|---|---:|---:|---|
| CellProfiler | 7.191819 | 556.900 | Docker stats, 3 samples |
| MorphoJet | 0.036554 | 38.344 | Local release binary |

Conclusion: this is a strong smoke signal for the ExampleHuman path, but the overall L3 industry-impact gate remains FAIL until the same criteria pass on a >=1,000 image-row public benchmark with stronger memory sampling.

## CellBinDB MorphoJet-Only Scale Preflight

This is not an L3 PASS because it has no CellProfiler oracle/parity result yet. It proves the next public direct-mask corpus is downloaded, verified, tabled, and readable by MorphoJet at >=1,000 image rows.

Environment:

- Source: Zenodo record `15370205`, `CellBinDB.zip`
- License: Zenodo record reports `cc-zero`; bundled source licenses are listed in `mixed_licenses.txt`
- Archive size: 285,956,212 bytes
- MD5: `e770f1287619eb45e74d131430e20fe5`
- Image/mask layout: `*-img.tif`, `*-instancemask.tif`, `*-mask.tif`
- MorphoJet command: `target/release/morphojet measure --threads 8 --cellprofiler-compatible`

Result:

| Metric | Value |
|---|---:|
| Complete sample groups | 1,044 |
| MorphoJet image rows | 1,044 |
| MorphoJet object rows | 107,936 |
| Elapsed seconds | 0.879788 |
| Peak RSS MB | 89.875 |
| Gate status | PREFLIGHT ONLY |

Conclusion: CellBinDB is a viable L3 corpus candidate for the MorphoJet side. The remaining blocking item is a CellProfiler measurement-only oracle pipeline for the same `*-instancemask.tif` labels.

## CellBinDB Oracle Smoke

This is an 8-row CellProfiler oracle smoke for the CellBinDB direct-mask path. It proves the measurement-only CellProfiler pipeline can read `*-instancemask.tif` labels as objects, and that MorphoJet's CellProfiler-compatible compact object numbering matches the oracle on the tested subset.

Artifacts:

- Pipeline generator: `benchmark/build_cellbindb_cellprofiler_pipeline.py`
- Turnkey runner: `benchmark/run_cellbindb_oracle.py`
- Pipeline artifact: `benchmark/results/cellbindb/cellbindb-direct-mask.cppipe`
- CellProfiler output: `benchmark/results/cellbindb/cellprofiler-smoke/Cells.csv`
- MorphoJet output: `benchmark/results/cellbindb/morphojet-smoke/Objects.csv`
- Parity report: `benchmark/results/cellbindb/parity-smoke.md`
- Parity JSON: `benchmark/results/cellbindb/parity-smoke.json`

Result:

| Gate | Result |
|---|---:|
| Image rows | 8 |
| Expected object rows | 590 |
| Actual object rows | 590 |
| Missing rows | 0 |
| Extra rows | 0 |
| Numeric compared | 10,030 |
| Numeric failures | 0 |
| CellProfiler seconds | 7.168250 |
| MorphoJet seconds | 0.016173 |
| Speedup | 443.22x |
| CellProfiler peak RSS MB | 359.600 |
| MorphoJet peak RSS MB | 18.062 |
| RSS ratio | 5.02% |
| Status | PASS |

Conclusion: the L3 candidate now has a proven small CellProfiler oracle path. Production L3 remains unproven until the same runner passes on all 1,044 rows with CellProfiler/MorphoJet elapsed time and RSS metrics.

## L3 CellBinDB Benchmark

This is the first >=1,000 image-row public direct-mask CellProfiler oracle benchmark. It supports the narrow L3 claim for the tested measurement subset: MorphoJet matches CellProfiler object rows and core measurements on this reproducible benchmark while running much faster and with lower peak RSS.

Environment:

- Source: Zenodo record `15370205`, `CellBinDB.zip`
- Dataset rows: 1,044 image rows
- Object rows: 107,936
- CellProfiler Docker image: `cellprofiler/cellprofiler:4.2.6`
- CellProfiler platform: `linux/amd64`
- MorphoJet command: `target/release/morphojet measure --threads 8 --cellprofiler-compatible`
- CellProfiler RSS source: `docker stats MemUsage sampled during container run`
- MorphoJet RSS source: local process `ru_maxrss` captured by `benchmark/run_command_metrics.py`

Artifacts:

- Turnkey runner: `benchmark/run_cellbindb_oracle.py`
- CellProfiler pipeline generator: `benchmark/build_cellbindb_cellprofiler_pipeline.py`
- Image table: `benchmark/results/cellbindb/oracle-full/images.csv`
- CellProfiler long oracle: `benchmark/results/cellbindb/oracle-full/cellprofiler/Objects.long.csv`
- MorphoJet output: `benchmark/results/cellbindb/oracle-full/morphojet/Objects.csv`
- Parity report: `benchmark/results/cellbindb/oracle-full/parity.md`
- Impact report: `benchmark/results/cellbindb/oracle-full/impact.md`
- Provenance report: `benchmark/results/cellbindb/oracle-full/provenance.json`
- Release gate report: `benchmark/results/release-gate/l3-cellbindb.md`

Result:

| Gate | Required | Observed | Status |
|---|---:|---:|---:|
| Scale | >=1000 image rows | 1044 | PASS |
| Object count parity | 100% | 100.0000% | PASS |
| Core numeric parity | >=99% | 100.0000% | PASS |
| Wall-clock speedup | >=10x | 589.29x | PASS |
| Peak RSS ratio | <=50% | 11.71% | PASS |

Raw metrics:

| Tool | Seconds | Peak RSS MB |
|---|---:|---:|
| CellProfiler | 555.301663 | 712.200 |
| MorphoJet | 0.942318 | 83.406 |

Parity:

| Metric | Value |
|---|---:|
| Expected rows | 107,936 |
| Actual rows | 107,936 |
| Missing rows | 0 |
| Extra rows | 0 |
| Numeric compared | 2,806,336 |
| Numeric failures | 0 |

Provenance: the scheduler-ready L3 release gate passed for commit `f5d0624545f5` with a clean worktree, `skip_cellprofiler=false`, 14 hashed artifacts. Under the current production-claim audit model, the L3 evidence still leaves `missing_or_failed_checks=["external_l4_workflow_trial", "external_l4_evidence_package", "stable_github_release"]`.

Conclusion: L3 passes for this CellBinDB direct-mask measurement benchmark with artifact provenance. This does not prove full CellProfiler replacement, upstream segmentation replacement, or external lab workflow fit; those remain L4/production-readiness work.

## CellBinDB Handoff Preflight Snapshot

This snapshot validates MorphoJet's supported measurement subset in a CellProfiler-style per-object wide CSV shape and runs it through a manifest-driven handoff trial. It is a workflow-fit preflight for downstream tools that expect files such as `Cells.csv`; it does not claim full CellProfiler object CSV feature coverage or external lab replacement.

Artifacts:

- Handoff manifest: `benchmark/handoff/cellbindb_supported_columns.json`
- External lab template: `benchmark/handoff/external_lab_template.json`
- Handoff report: `benchmark/results/cellbindb/oracle-full/handoff_trial.md`
- Handoff JSON: `benchmark/results/cellbindb/oracle-full/handoff_trial.json`
- Contract JSON: `benchmark/results/cellbindb/oracle-full/handoff_contract.json`
- MorphoJet long input: `benchmark/results/cellbindb/oracle-full/morphojet/Objects.csv`
- MorphoJet wide output: `benchmark/results/cellbindb/oracle-full/morphojet/Cells.wide.csv`
- CellProfiler oracle CSV: `benchmark/results/cellbindb/oracle-full/cellprofiler/Cells.csv`
- Bridge report: `benchmark/results/cellbindb/oracle-full/workflow_bridge.md`
- Bridge JSON: `benchmark/results/cellbindb/oracle-full/workflow_bridge.json`
- Handoff runner: `benchmark/run_handoff_trial.py`
- Handoff manifest validator: `benchmark/validate_handoff_manifest.py`
- External evidence gate: `--require-external-evidence` requires clean-git generator metadata for the current or compatible commit, a source manifest path, canonical `metadata.argv` bindings for that manifest plus sorted `--var` values, `--out-json` bound to the current trial JSON path, `--out-md`, and exactly one strict external-evidence flag, lab/workflow owner, dataset source, downstream workflow, execution environment, acceptance criteria, `manual_csv_editing=false`, a rendered manifest snapshot, a step list, commands, runtimes, and execution details that match the manifest-declared actions, an artifact list that exactly matches the manifest-declared outputs, and one SHA-256/size provenance entry for each listed artifact for real external trials.
- Materializer: `benchmark/materialize_morphojet_cellprofiler_wide.py`
- Comparator: `benchmark/compare_cellprofiler_wide_subset.py`
- Contract checker: `benchmark/check_cellprofiler_wide_contract.py`

Result:

| Gate | Result |
|---|---:|
| Handoff trial steps | 3 |
| CellBinDB manifest schema | PASS |
| External lab template schema | PASS |
| CellProfiler rows | 107,936 |
| MorphoJet wide rows | 107,936 |
| Missing rows | 0 |
| Extra rows | 0 |
| Compared columns | 33 |
| Ignored CellProfiler columns | 17 |
| Unsupported MorphoJet columns | 0 |
| Numeric compared | 3,561,888 |
| Numeric failures | 0 |
| Required contract columns | 35 |
| Duplicate keys | 0 |
| Empty keys | 0 |
| Status | PASS |

Compared columns include supported area/center/bounding-box/perimeter/eccentricity/axis/solidity fields, derived `ConvexArea`, `EquivalentDiameter`, and `Extent`, `Location_Center_X/Y/Z`, `Number_Object_Number`, channel-suffixed intensity fields including quartiles, population standard deviation, and median absolute deviation, channel-suffixed center-of-mass intensity locations, and the 2D-safe `Location_MaxIntensity_Z` value. Ignored CellProfiler columns include feature families MorphoJet does not yet emit, such as edge intensity, Feret diameter, compactness, orientation, and max-intensity X/Y locations.

Conclusion: this removes one CSV-shape and handoff-automation blocker for workflow trials on the supported subset. L4 remains incomplete until an external lab workflow consumes these files without manual CSV editing and the generated report preserves clean-git generator metadata for the current or compatible commit, the required external evidence fields, rendered manifest snapshot, exact manifest-declared step command/runtime/detail and artifact coverage, and one-to-one artifact provenance hashes.

## Local Release Artifact Preflight

This preflight validates the local release archive shape before a GitHub `v*` tag builds macOS/Linux release assets.

Artifacts:

- Builder: `benchmark/build_release_archive.py`
- Verifier: `benchmark/verify_release_archive.py`
- Release gate flag: `python3 benchmark/release_gate.py --build-release-artifact --release-version local`
- Local archive: `benchmark/results/release-artifacts/morphojet-local-macos-arm64.tar.gz`
- Checksum: `benchmark/results/release-artifacts/morphojet-local-macos-arm64.tar.gz.sha256`
- Verification JSON: `benchmark/results/release-artifacts/verification.json`

Result:

| Gate | Result |
|---|---:|
| Archive contains `morphojet` | PASS |
| Archive contains `README.md` | PASS |
| Archive contains `LICENSE` | PASS |
| SHA-256 verification | PASS |
| Packaged `morphojet doctor` smoke | PASS |
| Packaged commit matches HEAD | PASS |
| Local platform | macOS arm64 |
| SHA-256 | Recorded in `benchmark/results/release-artifacts/verification.json` |

Conclusion: local release artifact shape is validated. Production release evidence still requires a tagged GitHub release with published macOS and Linux archives and checksums.

## GitHub Release Candidate Snapshot

This snapshot validates the first tagged GitHub prerelease artifact set.

Artifacts:

- Tag: `v0.1.0-rc.1`
- Release URL: `https://github.com/benngaihk/MorphoJet/releases/tag/v0.1.0-rc.1`
- GitHub Actions run: `28576021744`
- Verifier: `benchmark/verify_github_release.py`
- Release gate command: `python3 benchmark/release_gate.py --verify-github-release v0.1.0-rc.1`
- Verification JSON: `benchmark/results/github-release/v0.1.0-rc.1/verification.json`

Result:

| Gate | Result |
|---|---:|
| Release is marked prerelease | PASS |
| Asset count | 4 |
| Linux archive checksum | PASS |
| macOS archive checksum | PASS |
| Linux archive contains `morphojet`, `README.md`, `LICENSE` | PASS |
| macOS archive contains `morphojet`, `README.md`, `LICENSE` | PASS |
| macOS packaged `morphojet doctor` smoke | PASS |
| Packaged commit matches tag commit `e7d0b6a5b44b` | PASS |

Conclusion: the release workflow can publish verifiable Linux and macOS archives for a tagged release candidate. This satisfies the RC artifact gate; stable release still waits on external workflow-fit evidence.

## L1 Synthetic Scale Benchmark

These results validate MorphoJet's local release CLI path on deterministic synthetic data. They do not prove CellProfiler parity or industry impact by themselves.

Environment:

- system: `macOS-26.5.1-arm64-arm-64bit`
- machine: `arm64`
- processor: `arm`
- python: `3.11.6`
- threads: `12`
- MorphoJet commit: `c3363d8` plus local validation documentation changes

### 96x96 Images

| Images | Objects | Seconds | Images/s | Objects/s |
|---:|---:|---:|---:|---:|
| 16 | 64 | 0.009671 | 1654.36 | 6617.44 |
| 256 | 1024 | 0.012208 | 20970.43 | 83881.71 |
| 1024 | 4096 | 0.034798 | 29426.77 | 117707.07 |

### 512x512 Images

| Images | Objects | Seconds | Images/s | Objects/s |
|---:|---:|---:|---:|---:|
| 128 | 512 | 0.022137 | 5782.09 | 23128.35 |
| 512 | 2048 | 0.055200 | 9275.36 | 37101.42 |
| 1024 | 4096 | 0.102462 | 9993.95 | 39975.81 |

## Interpretation

L1 is now complete: the release binary can process deterministic synthetic batches at high throughput and produce stable CSV outputs. This is an engineering viability signal.

The broad industry-impact claim remains unproven until the remaining L4 gate passes:

- L4: external lab workflow replacement.

## Reproduction

```bash
python3 benchmark/run_scale.py --cases 16,256,1024 --width 96 --height 96
python3 benchmark/run_scale.py --cases 128,512,1024 --width 512 --height 512 --out benchmark/results/scale_512
python3 benchmark/run_examplehuman_oracle.py --threads 8
```
