# Validation Results

Updated: 2026-07-08

## Release-Gate Snapshot for `49203a0`

This snapshot records the clean `main` verification for the code commit that updates generated external L4 trial workspace READMEs with the current saved local-preflight verifier contract. `benchmark/prepare_external_l4_trial.py` now tells reviewers in both English and Chinese that `verify_local_evidence_preflight` requires required input-artifact summaries to remain `exists=true`, requires metadata-bound saved reviewer reports to keep matching gate entries and hash summaries, and recomputes package/source claim-scope fields plus readiness `package_name` before PASS can be accepted.

Environment:

- Branch: `main`
- Verified code commit: `49203a0`
- Release-gate command: `python3 benchmark/release_gate.py --require-clean-git --require-l3-provenance --out-json /tmp/morphojet-l3-release-report-main-49203a0.json --out-md /tmp/morphojet-l3-release-report-main-49203a0.md`
- Saved-report verifier command: `python3 benchmark/verify_release_gate_report.py /tmp/morphojet-l3-release-report-main-49203a0.json --require-report-pass --require-clean-git-metadata --verify-git-commit --expect-missing-checks external_l4_workflow_trial,external_l4_evidence_package,external_l4_saved_reviewer_reports,stable_github_release,stable_github_release_saved_report`

Result:

| Gate | Result |
|---|---:|
| External trial workspace preparation tests | PASS, 21 tests |
| Full Python unit test suite | PASS, 438 tests |
| Source claim-language guard | PASS |
| Whitespace diff check | PASS |
| Clean L3 release gate | PASS |
| Saved release-gate report verifier | PASS |
| English Workspace README Local Preflight Hash Coverage | PASS |
| Chinese Workspace README Local Preflight Hash Coverage | PASS |
| `claim_status` | `NOT_PRODUCTION_CLAIM` |
| `evidence_scope` | `RELEASE_GATE_PRECHECK` |
| `final_production_signoff` | `False` |
| `production_claim_status` | `INCOMPLETE` |
| Remaining production blockers | `external_l4_workflow_trial`, `external_l4_evidence_package`, `external_l4_saved_reviewer_reports`, `stable_github_release`, `stable_github_release_saved_report` |

## Release-Gate Snapshot for `f0d6d8e`

This snapshot records the clean `main` verification for the code commit that makes saved local evidence-preflight reports fail closed when required evidence hashes are removed. `benchmark/run_production_gate.py` now requires every required local-preflight input artifact to remain `exists=true` in the saved report, and requires metadata-bound saved reviewer reports to keep their input-artifact existence plus size/SHA-256 summaries. Production-wrapper regression tests cover tampering that changes the package zip summary or a bound saved reviewer report summary to `exists=false` while leaving metadata and gates intact.

Environment:

- Branch: `main`
- Verified code commit: `f0d6d8e`
- Release-gate command: `python3 benchmark/release_gate.py --require-clean-git --require-l3-provenance --out-json /tmp/morphojet-l3-release-report-main-f0d6d8e.json --out-md /tmp/morphojet-l3-release-report-main-f0d6d8e.md`
- Saved-report verifier command: `python3 benchmark/verify_release_gate_report.py /tmp/morphojet-l3-release-report-main-f0d6d8e.json --require-report-pass --require-clean-git-metadata --verify-git-commit --expect-missing-checks external_l4_workflow_trial,external_l4_evidence_package,external_l4_saved_reviewer_reports,stable_github_release,stable_github_release_saved_report`

Result:

| Gate | Result |
|---|---:|
| Production wrapper tests | PASS, 75 tests |
| Full Python unit test suite | PASS, 438 tests |
| Source claim-language guard | PASS |
| Whitespace diff check | PASS |
| Clean L3 release gate | PASS |
| Saved release-gate report verifier | PASS |
| Local Preflight Required Artifact Hash Binding | PASS |
| Local Preflight Bound Reviewer Hash Binding | PASS |
| English README Input Artifact Presence Coverage | PASS |
| Chinese README Input Artifact Presence Coverage | PASS |
| `claim_status` | `NOT_PRODUCTION_CLAIM` |
| `evidence_scope` | `RELEASE_GATE_PRECHECK` |
| `final_production_signoff` | `False` |
| `production_claim_status` | `INCOMPLETE` |
| Remaining production blockers | `external_l4_workflow_trial`, `external_l4_evidence_package`, `external_l4_saved_reviewer_reports`, `stable_github_release`, `stable_github_release_saved_report` |

## Release-Gate Snapshot for `6601914`

This snapshot records the clean `main` verification for the code commit that makes saved local evidence-preflight reports fail closed when saved external reviewer metadata is present but the matching verifier gate entries are removed. `benchmark/run_production_gate.py` now derives required local-preflight gate names from report metadata, requires both saved reviewer verifier gates when both saved reviewer report paths are bound, and reports missing required gates explicitly. The production-wrapper tests cover tampering that removes a saved evidence-package reviewer gate while leaving the saved reviewer metadata and `validated_checks` in place.

Environment:

- Branch: `main`
- Verified code commit: `6601914`
- Release-gate command: `python3 benchmark/release_gate.py --require-clean-git --require-l3-provenance --out-json /tmp/morphojet-l3-release-report-main-6601914.json --out-md /tmp/morphojet-l3-release-report-main-6601914.md`
- Saved-report verifier command: `python3 benchmark/verify_release_gate_report.py /tmp/morphojet-l3-release-report-main-6601914.json --require-report-pass --require-clean-git-metadata --verify-git-commit --expect-missing-checks external_l4_workflow_trial,external_l4_evidence_package,external_l4_saved_reviewer_reports,stable_github_release,stable_github_release_saved_report`

Result:

| Gate | Result |
|---|---:|
| Production wrapper tests | PASS, 73 tests |
| Full Python unit test suite | PASS, 436 tests |
| Source claim-language guard | PASS |
| Whitespace diff check | PASS |
| Clean L3 release gate | PASS |
| Saved release-gate report verifier | PASS |
| Local Preflight Saved Reviewer Gate Binding | PASS |
| Saved Reviewer Gate Removal Tamper Rejection | PASS |
| English README Saved Reviewer Gate Coverage | PASS |
| Chinese README Saved Reviewer Gate Coverage | PASS |
| `claim_status` | `NOT_PRODUCTION_CLAIM` |
| `evidence_scope` | `RELEASE_GATE_PRECHECK` |
| `final_production_signoff` | `False` |
| `production_claim_status` | `INCOMPLETE` |
| Remaining production blockers | `external_l4_workflow_trial`, `external_l4_evidence_package`, `external_l4_saved_reviewer_reports`, `stable_github_release`, `stable_github_release_saved_report` |

## Release-Gate Snapshot for `153792f`

This snapshot records the clean `main` verification for the code commit that makes local external L4 evidence preflight reports enumerate the remaining final production checks more completely. `benchmark/run_production_gate.py` now keeps `external_l4_saved_reviewer_reports` in `skipped_final_checklist` unless both saved external reviewer reports are supplied, moves that check into `validated_checks` only when both reports are present, and always keeps `stable_github_release` plus `stable_github_release_saved_report` out of local preflight scope. The saved local-preflight verifier derives the expected validated/skipped lists from report metadata and rejects checklist tampering. English and Chinese README coverage plus production readiness docs were updated to keep local preflight non-final.

Environment:

- Branch: `main`
- Verified code commit: `153792f`
- Release-gate command: `python3 benchmark/release_gate.py --require-clean-git --require-l3-provenance --out-json /tmp/morphojet-l3-release-report-main-153792f.json --out-md /tmp/morphojet-l3-release-report-main-153792f.md`
- Saved-report verifier command: `python3 benchmark/verify_release_gate_report.py /tmp/morphojet-l3-release-report-main-153792f.json --require-report-pass --require-clean-git-metadata --verify-git-commit --expect-missing-checks external_l4_workflow_trial,external_l4_evidence_package,external_l4_saved_reviewer_reports,stable_github_release,stable_github_release_saved_report`

Result:

| Gate | Result |
|---|---:|
| Production wrapper tests | PASS, 72 tests |
| Full Python unit test suite | PASS, 435 tests |
| Source claim-language guard | PASS |
| Whitespace diff check | PASS |
| Clean L3 release gate | PASS |
| Saved release-gate report verifier | PASS |
| Local Preflight Saved Reviewer Dynamic Validation | PASS |
| Local Preflight Saved Stable Release Skip Coverage | PASS |
| English README Local Preflight Scope Coverage | PASS |
| Chinese README Local Preflight Scope Coverage | PASS |
| `claim_status` | `NOT_PRODUCTION_CLAIM` |
| `evidence_scope` | `RELEASE_GATE_PRECHECK` |
| `final_production_signoff` | `False` |
| `production_claim_status` | `INCOMPLETE` |
| Remaining production blockers | `external_l4_workflow_trial`, `external_l4_evidence_package`, `external_l4_saved_reviewer_reports`, `stable_github_release`, `stable_github_release_saved_report` |

## Release-Gate Snapshot for `c717a4e`

This snapshot records the clean `main` verification for the code commit that makes generated external L4 trial plans bind the live stable GitHub release as a distinct final signoff requirement. `benchmark/prepare_external_l4_trial.py` now writes a separate `stable_github_release` row pointing to `https://github.com/benngaihk/MorphoJet/releases/tag/v0.1.0`, keeps `stable_github_release_saved_report` as a separate saved verifier artifact, and uses shared stable-release tag/repo constants for the generated commands. Saved plan verification regenerates and rejects tampered final signoff requirements, and generated English plus Chinese workspace READMEs render both stable-release rows.

Environment:

- Branch: `main`
- Verified code commit: `c717a4e`
- Release-gate command: `python3 benchmark/release_gate.py --require-clean-git --require-l3-provenance --out-json /tmp/morphojet-l3-release-report-main-c717a4e.json --out-md /tmp/morphojet-l3-release-report-main-c717a4e.md`
- Saved-report verifier command: `python3 benchmark/verify_release_gate_report.py /tmp/morphojet-l3-release-report-main-c717a4e.json --require-report-pass --require-clean-git-metadata --verify-git-commit --expect-missing-checks external_l4_workflow_trial,external_l4_evidence_package,external_l4_saved_reviewer_reports,stable_github_release,stable_github_release_saved_report`

Result:

| Gate | Result |
|---|---:|
| External trial workspace preparation tests | PASS, 21 tests |
| Full Python unit test suite | PASS, 435 tests |
| Source claim-language guard | PASS |
| Whitespace diff check | PASS |
| Clean L3 release gate | PASS |
| Saved release-gate report verifier | PASS |
| Live Stable GitHub Release Requirement Binding | PASS |
| Saved Stable Release Report Requirement Binding | PASS |
| English README Stable Release Requirement Coverage | PASS |
| Chinese README Stable Release Requirement Coverage | PASS |
| `claim_status` | `NOT_PRODUCTION_CLAIM` |
| `evidence_scope` | `RELEASE_GATE_PRECHECK` |
| `final_production_signoff` | `False` |
| `production_claim_status` | `INCOMPLETE` |
| Remaining production blockers | `external_l4_workflow_trial`, `external_l4_evidence_package`, `external_l4_saved_reviewer_reports`, `stable_github_release`, `stable_github_release_saved_report` |

## Release-Gate Snapshot for `14c6ac1`

This snapshot records the clean `main` verification for the code commit that adds machine-readable pre-signoff prerequisites to generated external L4 trial plans. `benchmark/prepare_external_l4_trial.py` now writes `pre_signoff_requirements` into `trial_plan.json`, binding the readiness report to `verify_readiness` before `run_trial` and the saved local evidence preflight report to `verify_local_evidence_preflight` before `verify_stable_release`. Saved plan verification regenerates and rejects tampered `pre_signoff_requirements`, and generated English plus Chinese workspace READMEs render the pre-signoff table alongside the final signoff table.

Environment:

- Branch: `main`
- Verified code commit: `14c6ac1`
- Release-gate command: `python3 benchmark/release_gate.py --require-clean-git --require-l3-provenance --out-json /tmp/morphojet-l3-release-report-main-14c6ac1.json --out-md /tmp/morphojet-l3-release-report-main-14c6ac1.md`
- Saved-report verifier command: `python3 benchmark/verify_release_gate_report.py /tmp/morphojet-l3-release-report-main-14c6ac1.json --require-report-pass --require-clean-git-metadata --verify-git-commit --expect-missing-checks external_l4_workflow_trial,external_l4_evidence_package,external_l4_saved_reviewer_reports,stable_github_release,stable_github_release_saved_report`

Result:

| Gate | Result |
|---|---:|
| External trial workspace preparation tests | PASS, 21 tests |
| Full Python unit test suite | PASS, 435 tests |
| Source claim-language guard | PASS |
| Whitespace diff check | PASS |
| Clean L3 release gate | PASS |
| Saved release-gate report verifier | PASS |
| Trial Plan Pre-Signoff Requirement Binding | PASS |
| Saved Plan Pre-Signoff Tamper Rejection | PASS |
| English README Pre-Signoff Table Coverage | PASS |
| Chinese README Pre-Signoff Table Coverage | PASS |
| `claim_status` | `NOT_PRODUCTION_CLAIM` |
| `evidence_scope` | `RELEASE_GATE_PRECHECK` |
| `final_production_signoff` | `False` |
| `production_claim_status` | `INCOMPLETE` |
| Remaining production blockers | `external_l4_workflow_trial`, `external_l4_evidence_package`, `external_l4_saved_reviewer_reports`, `stable_github_release`, `stable_github_release_saved_report` |

## Release-Gate Snapshot for `ba16c67`

This snapshot records the clean `main` verification for the code commit that updates generated external L4 trial workspaces. `benchmark/prepare_external_l4_trial.py` now writes both English and Chinese workspace READMEs that state saved local preflight reports are non-final evidence with `claim_status=NOT_PRODUCTION_CLAIM`, `evidence_scope=LOCAL_EXTERNAL_L4_PREFLIGHT`, and `final_evidence_acceptable=false`. The generated READMEs also tell reviewers that `verify_local_evidence_preflight` rehashes source/package trial files, package `artifact_manifest.json`, package `readiness.json`, zip/checksum files, reviewer reports, source/package trial claim-scope labels, package-manifest package/source-trial scope labels, and readiness `package_name` before accepting PASS; `--verify-plan-files` keeps those bilingual reviewer instructions fixed to the saved plan.

Environment:

- Branch: `main`
- Verified code commit: `ba16c67`
- Release-gate command: `python3 benchmark/release_gate.py --require-clean-git --require-l3-provenance --out-json /tmp/morphojet-l3-release-report-main-ba16c67.json --out-md /tmp/morphojet-l3-release-report-main-ba16c67.md`
- Saved-report verifier command: `python3 benchmark/verify_release_gate_report.py /tmp/morphojet-l3-release-report-main-ba16c67.json --require-report-pass --require-clean-git-metadata --verify-git-commit --expect-missing-checks external_l4_workflow_trial,external_l4_evidence_package,external_l4_saved_reviewer_reports,stable_github_release,stable_github_release_saved_report`

Result:

| Gate | Result |
|---|---:|
| External trial workspace preparation tests | PASS, 20 tests |
| Full Python unit test suite | PASS, 434 tests |
| Source claim-language guard | PASS |
| Whitespace diff check | PASS |
| Clean L3 release gate | PASS |
| Saved release-gate report verifier | PASS |
| Generated English Workspace README Local Preflight Scope Coverage | PASS |
| Generated Chinese Workspace README Local Preflight Scope Coverage | PASS |
| Saved Plan README File Recheck Coverage | PASS |
| `claim_status` | `NOT_PRODUCTION_CLAIM` |
| `evidence_scope` | `RELEASE_GATE_PRECHECK` |
| `final_production_signoff` | `False` |
| `production_claim_status` | `INCOMPLETE` |
| Remaining production blockers | `external_l4_workflow_trial`, `external_l4_evidence_package`, `external_l4_saved_reviewer_reports`, `stable_github_release`, `stable_github_release_saved_report` |

## Release-Gate Snapshot for `5a514f0`

This snapshot records the clean `main` verification for the code commit that binds local evidence preflight reports to the source trial, packaged trial, and package artifact-manifest claim-scope labels. `benchmark/run_production_gate.py` now writes `package_artifact_manifest_json` into local preflight `input_artifacts`, copies non-final claim-scope fields from the source and packaged trial reports, copies package-level and source-trial scope fields from `artifact_manifest.json`, rejects saved preflight reports whose copied fields are tampered, and recomputes those fields during `--verify-local-evidence-preflight-files`. English and Chinese README guidance now describe the local preflight scope and saved verifier behavior for reviewers.

Environment:

- Branch: `main`
- Verified code commit: `5a514f0`
- Release-gate command: `python3 benchmark/release_gate.py --require-clean-git --require-l3-provenance --out-json /tmp/morphojet-l3-release-report-main-5a514f0.json --out-md /tmp/morphojet-l3-release-report-main-5a514f0.md`
- Saved-report verifier command: `python3 benchmark/verify_release_gate_report.py /tmp/morphojet-l3-release-report-main-5a514f0.json --require-report-pass --require-clean-git-metadata --verify-git-commit --expect-missing-checks external_l4_workflow_trial,external_l4_evidence_package,external_l4_saved_reviewer_reports,stable_github_release,stable_github_release_saved_report`

Result:

| Gate | Result |
|---|---:|
| Production wrapper tests | PASS, 72 tests |
| Package external trial tests | PASS, 67 tests |
| Release-gate helper tests | PASS, 69 tests |
| Full Python unit test suite | PASS, 434 tests |
| Source claim-language guard | PASS |
| Whitespace diff check | PASS |
| Clean L3 release gate | PASS |
| Saved release-gate report verifier | PASS |
| Local Preflight Trial Scope Binding | PASS |
| Local Preflight Package Manifest Scope Binding | PASS |
| Local Preflight File Recheck Scope Recompute | PASS |
| English README Local Preflight Scope Coverage | PASS |
| Chinese README Local Preflight Scope Coverage | PASS |
| `claim_status` | `NOT_PRODUCTION_CLAIM` |
| `evidence_scope` | `RELEASE_GATE_PRECHECK` |
| `final_production_signoff` | `False` |
| `production_claim_status` | `INCOMPLETE` |
| Remaining production blockers | `external_l4_workflow_trial`, `external_l4_evidence_package`, `external_l4_saved_reviewer_reports`, `stable_github_release`, `stable_github_release_saved_report` |

## Release-Gate Snapshot for `7ffca9b`

This snapshot records the clean `main` verification for the code commit that binds evidence packages to the source trial report's claim-scope labels. `benchmark/package_external_trial.py` now writes `trial_claim_status`, `trial_evidence_scope`, and `trial_final_production_signoff` into `artifact_manifest.json`. `benchmark/release_gate.py` rejects packages whose artifact manifest drops or mutates those source trial labels, and `benchmark/verify_external_evidence_package.py` copies the source trial labels into `input_files.source_trial_json` so saved package-reviewer reports and file rechecks catch source trial claim-scope tampering. English and Chinese README guidance now describe the package manifest and saved package verifier as carrying the source trial's non-final scope.

Environment:

- Branch: `main`
- Verified code commit: `7ffca9b`
- Release-gate command: `python3 benchmark/release_gate.py --require-clean-git --require-l3-provenance --out-json /tmp/morphojet-l3-release-report-main-7ffca9b.json --out-md /tmp/morphojet-l3-release-report-main-7ffca9b.md`
- Saved-report verifier command: `python3 benchmark/verify_release_gate_report.py /tmp/morphojet-l3-release-report-main-7ffca9b.json --require-report-pass --require-clean-git-metadata --verify-git-commit --expect-missing-checks external_l4_workflow_trial,external_l4_evidence_package,external_l4_saved_reviewer_reports,stable_github_release,stable_github_release_saved_report`

Result:

| Gate | Result |
|---|---:|
| Package external trial tests | PASS, 67 tests |
| Release-gate helper tests | PASS, 69 tests |
| Production wrapper tests | PASS, 67 tests |
| Full Python unit test suite | PASS, 429 tests |
| Source claim-language guard | PASS |
| Whitespace diff check | PASS |
| Clean L3 release gate | PASS |
| Saved release-gate report verifier | PASS |
| Package Manifest Source-Trial Scope Binding | PASS |
| Saved Package Reviewer Source-Trial Scope Recheck | PASS |
| English README Package Source Scope Coverage | PASS |
| Chinese README Package Source Scope Coverage | PASS |
| `claim_status` | `NOT_PRODUCTION_CLAIM` |
| `evidence_scope` | `RELEASE_GATE_PRECHECK` |
| `final_production_signoff` | `False` |
| `production_claim_status` | `INCOMPLETE` |
| Remaining production blockers | `external_l4_workflow_trial`, `external_l4_evidence_package`, `external_l4_saved_reviewer_reports`, `stable_github_release`, `stable_github_release_saved_report` |

## Release-Gate Snapshot for `5a4de0d`

This snapshot records the clean `main` verification for the code commit that labels real external L4 trial reports as non-final evidence. `benchmark/run_handoff_trial.py` now writes `claim_status=NOT_PRODUCTION_CLAIM`, `evidence_scope=EXTERNAL_L4_WORKFLOW_TRIAL`, and `final_production_signoff=false` into source trial reports. `benchmark/release_gate.py` rejects trial reports that remove or weaken those labels, and `benchmark/verify_external_trial_report.py` copies the source trial claim-scope labels into `input_files.trial_json` so saved trial-reviewer reports and file rechecks catch source trial claim-scope tampering. English and Chinese README guidance now describe the source trial and saved trial-reviewer report as separate non-final artifacts.

Environment:

- Branch: `main`
- Verified code commit: `5a4de0d`
- Release-gate command: `python3 benchmark/release_gate.py --require-clean-git --require-l3-provenance --out-json /tmp/morphojet-l3-release-report-main-5a4de0d.json --out-md /tmp/morphojet-l3-release-report-main-5a4de0d.md`
- Saved-report verifier command: `python3 benchmark/verify_release_gate_report.py /tmp/morphojet-l3-release-report-main-5a4de0d.json --require-report-pass --require-clean-git-metadata --verify-git-commit --expect-missing-checks external_l4_workflow_trial,external_l4_evidence_package,external_l4_saved_reviewer_reports,stable_github_release,stable_github_release_saved_report`

Result:

| Gate | Result |
|---|---:|
| Release-gate helper tests | PASS, 69 tests |
| External trial verifier tests | PASS, 30 tests |
| Package external trial tests | PASS, 64 tests |
| Production wrapper tests | PASS, 67 tests |
| Full Python unit test suite | PASS, 426 tests |
| Source claim-language guard | PASS |
| Whitespace diff check | PASS |
| Clean L3 release gate | PASS |
| Saved release-gate report verifier | PASS |
| External Trial Source Non-Production Scope | PASS |
| Saved Trial Reviewer Source-Scope Recheck | PASS |
| English README Trial Scope Coverage | PASS |
| Chinese README Trial Scope Coverage | PASS |
| `claim_status` | `NOT_PRODUCTION_CLAIM` |
| `evidence_scope` | `RELEASE_GATE_PRECHECK` |
| `final_production_signoff` | `False` |
| `production_claim_status` | `INCOMPLETE` |
| Remaining production blockers | `external_l4_workflow_trial`, `external_l4_evidence_package`, `external_l4_saved_reviewer_reports`, `stable_github_release`, `stable_github_release_saved_report` |

## Release-Gate Snapshot for `0e66873`

This snapshot records the clean `main` verification for the code commit that binds direct live GitHub release verification to the production repository. `benchmark/release_gate.py --verify-github-release` now passes `--repo benngaihk/MorphoJet` to the live verifier, and `benchmark/verify_release_gate_report.py` rejects saved release-gate reports whose live release verifier command omits or changes that production-repo binding. English and Chinese README guidance now state the same direct/live repo-binding requirement.

Environment:

- Branch: `main`
- Verified code commit: `0e66873`
- Release-gate command: `python3 benchmark/release_gate.py --require-clean-git --require-l3-provenance --out-json /tmp/morphojet-l3-release-report-main-0e66873.json --out-md /tmp/morphojet-l3-release-report-main-0e66873.md`
- Saved-report verifier command: `python3 benchmark/verify_release_gate_report.py /tmp/morphojet-l3-release-report-main-0e66873.json --require-report-pass --require-clean-git-metadata --verify-git-commit --expect-missing-checks external_l4_workflow_trial,external_l4_evidence_package,external_l4_saved_reviewer_reports,stable_github_release,stable_github_release_saved_report`

Result:

| Gate | Result |
|---|---:|
| Release-gate helper tests | PASS, 68 tests |
| Saved release-gate verifier tests | PASS, 49 tests |
| Full Python unit test suite | PASS, 423 tests |
| Source claim-language guard | PASS |
| Whitespace diff check | PASS |
| Clean L3 release gate | PASS |
| Saved release-gate report verifier | PASS |
| Live GitHub Release Production Repo Binding | PASS |
| English README Repo-Binding Coverage | PASS |
| Chinese README Repo-Binding Coverage | PASS |
| `claim_status` | `NOT_PRODUCTION_CLAIM` |
| `evidence_scope` | `RELEASE_GATE_PRECHECK` |
| `final_production_signoff` | `False` |
| `production_claim_status` | `INCOMPLETE` |
| Remaining production blockers | `external_l4_workflow_trial`, `external_l4_evidence_package`, `external_l4_saved_reviewer_reports`, `stable_github_release`, `stable_github_release_saved_report` |

## Release-Gate Snapshot for `6608094`

This snapshot records the clean `main` verification for the code commit that updates generated external L4 trial workspace READMEs. Newly prepared English and Chinese workspaces now tell reviewers that the saved package verifier report produced by `verify_package` is itself a non-final review artifact with `claim_status=NOT_PRODUCTION_CLAIM`, `evidence_scope=EXTERNAL_L4_EVIDENCE_PACKAGE_REVIEW`, and `final_production_signoff=false`. `--verify-plan-files` re-renders and checks both generated README files, so weakening that package-review scope in either language is caught before an external L4 run.

Environment:

- Branch: `main`
- Verified code commit: `6608094`
- Release-gate command: `python3 benchmark/release_gate.py --require-clean-git --require-l3-provenance --out-json /tmp/morphojet-l3-release-report-main-6608094.json --out-md /tmp/morphojet-l3-release-report-main-6608094.md`
- Saved-report verifier command: `python3 benchmark/verify_release_gate_report.py /tmp/morphojet-l3-release-report-main-6608094.json --require-report-pass --require-clean-git-metadata --verify-git-commit --expect-missing-checks external_l4_workflow_trial,external_l4_evidence_package,external_l4_saved_reviewer_reports,stable_github_release,stable_github_release_saved_report`

Result:

| Gate | Result |
|---|---:|
| External trial workspace generator tests | PASS, 20 tests |
| Full Python unit test suite | PASS, 422 tests |
| Source claim-language guard | PASS |
| Whitespace diff check | PASS |
| Clean L3 release gate | PASS |
| Saved release-gate report verifier | PASS |
| Generated English README Package Review Scope | PASS |
| Generated Chinese README Package Review Scope | PASS |
| `claim_status` | `NOT_PRODUCTION_CLAIM` |
| `evidence_scope` | `RELEASE_GATE_PRECHECK` |
| `final_production_signoff` | `False` |
| `production_claim_status` | `INCOMPLETE` |
| Remaining production blockers | `external_l4_workflow_trial`, `external_l4_evidence_package`, `external_l4_saved_reviewer_reports`, `stable_github_release`, `stable_github_release_saved_report` |

## Release-Gate Snapshot for `5ad23ed`

This snapshot records the clean `main` verification for the code commit that labels saved external L4 evidence-package verifier reports as independent non-production review artifacts. The package verifier now writes top-level `claim_status=NOT_PRODUCTION_CLAIM`, `evidence_scope=EXTERNAL_L4_EVIDENCE_PACKAGE_REVIEW`, and `final_production_signoff=false`, and saved-report verification rejects reports tampered into final production-claim scope. This complements the package manifest's own `EXTERNAL_L4_EVIDENCE_PACKAGE` scope and keeps the reviewer JSON from being mistaken for final production signoff.

Environment:

- Branch: `main`
- Verified code commit: `5ad23ed`
- Release-gate command: `python3 benchmark/release_gate.py --require-clean-git --require-l3-provenance --out-json /tmp/morphojet-l3-release-report-main-5ad23ed.json --out-md /tmp/morphojet-l3-release-report-main-5ad23ed.md`
- Saved-report verifier command: `python3 benchmark/verify_release_gate_report.py /tmp/morphojet-l3-release-report-main-5ad23ed.json --require-report-pass --require-clean-git-metadata --verify-git-commit --expect-missing-checks external_l4_workflow_trial,external_l4_evidence_package,external_l4_saved_reviewer_reports,stable_github_release,stable_github_release_saved_report`

Result:

| Gate | Result |
|---|---:|
| Evidence package verifier tests | PASS, 64 tests |
| Full Python unit test suite | PASS, 422 tests |
| Source claim-language guard | PASS |
| Whitespace diff check | PASS |
| Clean L3 release gate | PASS |
| Saved release-gate report verifier | PASS |
| Saved Package Reviewer Non-Production Scope | PASS |
| `claim_status` | `NOT_PRODUCTION_CLAIM` |
| `evidence_scope` | `RELEASE_GATE_PRECHECK` |
| `final_production_signoff` | `False` |
| `production_claim_status` | `INCOMPLETE` |
| Remaining production blockers | `external_l4_workflow_trial`, `external_l4_evidence_package`, `external_l4_saved_reviewer_reports`, `stable_github_release`, `stable_github_release_saved_report` |

## Release-Gate Snapshot for `2fa2ee8`

This snapshot records the clean `main` verification for the code commit that makes `benchmark/validate_claim_language.py` scan top-level Markdown files plus recursive `docs/` and `corpus/` docs by default, includes `MORPHOJET-FEASIBILITY.md` and `corpus/README.md` in the default source-doc claim guard, rejects unguarded Chinese `生产级` / `生产就绪` / `生产可用` / `替代 CellProfiler` / `取代 CellProfiler` claims, keeps guarded Chinese caveats such as `不是`, `不能`, and `不替代` valid, makes release-gate JSON and Markdown reports carry top-level `claim_status`, `evidence_scope`, and `final_production_signoff` labels, requires saved release-gate verification to reject non-final reports tampered into final production claims and final reports weakened into precheck claims, makes `benchmark/run_production_gate.py` immediately re-check the saved final production-claim report after a successful final release gate, adds final saved production-claim report verification to generated external L4 trial plans, requires final production PASS reports to include saved external L4 trial/package reviewer reports and a saved stable GitHub release verifier report as independent production-audit checks, adds Chinese-community README coverage for that policy, treats top-level localized README files such as `README.zh-CN.md` as documentation-only compatible deltas for L3 provenance and external-trial commit checks, protects external L4 workspaces from stale execution outputs before preparation, keeps readiness, reviewer, release-gate, local-preflight, stable-release verifier, production-claim, and final wrapper report outputs from overwriting or creating files inside protected evidence paths, records and re-checks audit metadata on external L4 readiness reports and trial plans, generates bilingual English/Chinese workspace README files plus plan-verification, readiness-verification, saved local-preflight-verification, stable-release-verification, saved stable-release report verification, final-production-gate, and final-report-verification commands, records and rechecks `final_signoff_requirements` in prepared `trial_plan.json` files so every final signoff artifact is bound to a planned path, verification step, and final gate it is required for, labels saved external L4 trial plans with `claim_status=NOT_PRODUCTION_CLAIM`, `evidence_scope=EXTERNAL_L4_TRIAL_PLAN`, and `final_production_signoff=false`, renders those final signoff tables and plan scope fields in generated English and Chinese READMEs with localized Chinese table headers, labels saved external L4 readiness precheck reports with `claim_status=NOT_PRODUCTION_CLAIM`, `evidence_scope=EXTERNAL_L4_READINESS_PRECHECK`, and `final_production_signoff=false`, carries those readiness claim-scope labels into trial summaries, labels saved external trial verifier reports with `claim_status=NOT_PRODUCTION_CLAIM`, `evidence_scope=EXTERNAL_L4_WORKFLOW_TRIAL_REVIEW`, and `final_production_signoff=false`, labels saved GitHub release verifier reports with `claim_status=NOT_PRODUCTION_CLAIM`, `evidence_scope=GITHUB_STABLE_RELEASE_VERIFICATION`, and `final_production_signoff=false`, packages bilingual English/Chinese evidence-package README files as review files with release-gate content checks and saved verifier file summaries, requires external L4 evidence packages and package READMEs to preserve `claim_status=NOT_PRODUCTION_CLAIM`, `evidence_scope=EXTERNAL_L4_EVIDENCE_PACKAGE`, and `final_production_signoff=false` so the package alone cannot be accepted as final production signoff, requires saved evidence-package verifier reports to copy and file-recompute those package artifact-manifest claim-scope fields, binds readiness reports to a canonical package-name slug or null, requires generated external trial commands to verify and bind a pre-execution READY readiness report through `--readiness-report`, requires external trial reports to preserve that readiness report's absolute path, size, SHA-256, status, claim label, workspace, manifest, package-name summary, and UTC generation time, requires release gate to reject trial summaries whose readiness package-name field is missing or differs from the readiness file, requires evidence packages and package README files to preserve the bound readiness package name, requires release gate to reject package README files whose readiness package name line is missing, requires saved external trial reviewer reports to record and recompute the bound readiness report file summary including the package-name summary, requires saved trial reviewer reports to reject readiness package-name summaries that no longer match the source trial report, requires evidence packages to copy `readiness.json` and match it to the bound trial readiness summary, requires saved evidence-package reviewer reports to record and recompute the package copy of `readiness.json` including its package-name summary, requires saved package reviewer reports to reject packaged readiness package-name summaries that no longer match the package readiness report, requires local evidence preflight reports to bind the packaged `readiness.json` by absolute path, size, SHA-256, and package-name summary, requires local evidence preflight verifier file rechecks to recompute that package-name summary, requires local evidence preflight reports to include a machine-checkable `skipped_final_checklist`, requires prepared trial plans to include a fail-closed saved local-preflight verifier command with file rehashing, gate reruns, and PASS enforcement, requires prepared trial plans to include stable `v0.1.0` GitHub release verification, a fail-closed saved stable-release report verifier with file rehashing, stable-report enforcement, git commit verification, expected-tag binding, expected production repo binding, final production wrapper commands bound to the same trial/package/reviewer artifacts, and final release-gate report verification with production-claim PASS plus `--expect-missing-checks none`, requires both the final production wrapper and direct release gate to treat packaged `readiness.json` as a fixed protected evidence input, directly tests that tampered packaged `readiness.json`, unbound saved package-readiness paths, tampered saved package claim-scope summaries, tampered local-preflight package-readiness package names, tampered local-preflight skipped-final checklist rows, weakened readiness package-name argv bindings, removed generated local-preflight verification commands, removed generated stable-release report verification commands, localized README provenance compatibility, saved GitHub release reports for the wrong repo, stale final production outputs, tampered generated Chinese workspace README files, tampered packaged Chinese README files, tampered package final-production signoff scope, tampered saved readiness claim-scope labels, tampered saved trial-plan claim-scope labels, tampered saved trial verifier claim-scope labels, tampered saved GitHub release verifier claim-scope labels, and final/local-preflight report outputs targeting packaged `README.zh-CN.md` review files are rejected, rejects saved trial-plan command tampering and final-signoff-requirement tampering without requiring local file access, requires saved trial plan, readiness, trial-reviewer, package-reviewer, stable GitHub release verifier, saved release-gate, local evidence-preflight metadata timestamps, external trial generation timestamps, package artifact manifest timestamps, and external reviewer signoff timestamps to be UTC, binds generated README contents to saved trial plans, requires saved plan/readiness/reviewer/local-preflight/release reports to preserve absolute evidence/output paths plus absolute path-valued argv entries where those reports bind saved inputs, including trial reviewer `argv` trial/root paths, package reviewer `argv` package/source-trial paths, saved release-gate production evidence and output argv paths, requires saved release-gate boolean metadata flags to have matching gates, requires saved release-gate external L4 metadata paths to have matching validation gates, binds saved release-gate `--out-json` argv to the report under review, binds saved release-gate live GitHub release gate commands to recorded tag/kind/output JSON, requires saved release-gate reviewer metadata paths to have matching gates, binds saved release-gate reviewer gate commands to their fail-closed verifier flags and metadata path binding, and GitHub release verifier `out_dir`, expected tag, and expected repo, rejects saved stable-release PASS reports whose archive summaries record a failed checksum match, and writes `production_claim_checklist` into JSON so the Markdown Production Claim Checklist is machine-verifiable by the saved report verifier. It is not a production claim; it confirms that the committed release-gate evidence still passes L3 while exposing the exact final blockers.

Environment:

- Branch: `main`
- Verified code commit: `2fa2ee8`
- Release-gate command: `python3 benchmark/release_gate.py --require-clean-git --require-l3-provenance --out-json /tmp/morphojet-l3-release-report-main-2fa2ee8.json --out-md /tmp/morphojet-l3-release-report-main-2fa2ee8.md`
- Saved-report verifier command: `python3 benchmark/verify_release_gate_report.py /tmp/morphojet-l3-release-report-main-2fa2ee8.json --require-report-pass --require-clean-git-metadata --verify-git-commit --expect-missing-checks external_l4_workflow_trial,external_l4_evidence_package,external_l4_saved_reviewer_reports,stable_github_release,stable_github_release_saved_report`

Result:

| Gate | Result |
|---|---:|
| Full Python unit test suite | PASS, 421 tests |
| Source claim-language guard | PASS |
| Chinese README Claim-Language Guard | PASS |
| Recursive Source-Doc Claim-Language Guard | PASS |
| Whitespace diff check | PASS |
| Clean L3 release gate | PASS |
| Saved release-gate report verifier | PASS |
| Release Gate Final Claim Scope | PASS |
| JSON/Markdown Production Claim Checklist | PASS |
| Local Preflight Skipped-Final Checklist | PASS |
| Trial Plan Final Signoff Requirements | PASS |
| Trial Plan Non-Production Scope | PASS |
| Localized Final Signoff Tables | PASS |
| Saved Readiness Non-Production Scope | PASS |
| Saved Trial Non-Production Scope | PASS |
| Saved GitHub Release Non-Production Scope | PASS |
| Evidence Package Non-Production Scope | PASS |
| Saved Package Claim-Scope Summaries | PASS |
| `production_claim_status` | `INCOMPLETE` |
| Remaining production blockers | `external_l4_workflow_trial`, `external_l4_evidence_package`, `external_l4_saved_reviewer_reports`, `stable_github_release`, `stable_github_release_saved_report` |

The saved release-gate verifier checks production metadata and `metadata.argv` both ways: final metadata values must appear in the recorded command line, key production command-line arguments must be reflected back into metadata without duplicate critical flags or missing flag values, true boolean metadata flags must have matching gates, production evidence and reviewer-report metadata paths must be absolute, external L4 metadata paths must have matching validation gates, explicit report output argv paths must be absolute, recorded `--out-json` must match the report under review, live GitHub release gates must be bound to the recorded tag/kind/output JSON, saved reviewer-report metadata paths must have matching saved-reviewer gates, saved reviewer-report gate commands must retain their fail-closed verifier flags and metadata path binding, and final report `metadata.generated_at_utc` must be UTC. `benchmark/release_gate.py` canonicalizes those recorded path values, live GitHub verifier JSON paths, and saved reviewer command report paths to absolute paths when writing new reports. The local evidence preflight verifier, external trial reports, external reviewer verifier reports, and GitHub release verifier reports now apply the same binding discipline to their own canonical argv and timestamp metadata; external trial runner argv must preserve the source manifest, sorted `--var` values, readiness-report path, output paths, strict external-evidence flag, UTC trial generation timestamp, UTC readiness generation timestamp, and UTC reviewer signoff timestamp. `benchmark/prepare_external_l4_trial.py` now creates a concrete external trial workspace with the template manifest, input directories, bilingual generated README files, generated plan-verification/validation/readiness/readiness-verification/run/package/preflight/preflight-verification/stable-release/saved-release-verification/final-production/final-report-verification commands, stale execution-output checks including stable-release verifier and production-claim outputs, and a plan labeled `claim_status=NOT_PRODUCTION_CLAIM`, `evidence_scope=EXTERNAL_L4_TRIAL_PLAN`, and `final_production_signoff=false` so external reviewers can prepare real evidence without implying that the scaffold itself is evidence. The plan records UTC `generated_at_utc`, canonical generator `argv`, absolute template/workspace/manifest paths, template size, template SHA-256, and those claim-scope fields so the prepared scaffold source and target can be audited; plain `--verify-plan` re-checks the saved plan schema, generator command binding, UTC timestamp, absolute source paths, regenerated command set, regenerated final signoff requirements, and trial-plan claim-scope labels, while `--verify-plan-files` also re-checks the template hash, manifest presence, and English plus Chinese README contents. The generated command set and READMEs run `verify_plan` first, so reviewers can revalidate the saved plan before any external L4 execution step, then run `verify_readiness` before `run_trial`, finish the local evidence stage by verifying the saved local evidence preflight report with file rehashing, gate reruns, and PASS enforcement, verify the stable `v0.1.0` release assets into a saved GitHub release verifier report outside the download directory, re-check that saved release report with file rehashing, stable-report enforcement, git commit/tag resolution, expected-tag binding, expected `benngaihk/MorphoJet` repo binding, run the final production wrapper with the same trial/package/reviewer/GitHub evidence paths, and finally re-check the saved `production-claim.json` with production-claim PASS and `--expect-missing-checks none`. `benchmark/run_handoff_trial.py` now re-verifies a supplied READY readiness report before executing external L4 steps and records its path, size, SHA-256, status, claim label, workspace, manifest, package name, and UTC generation time in the trial report. `benchmark/check_external_l4_readiness.py` adds a pre-execution readiness report for filled external evidence, input files, MorphoJet Objects.csv and expected CellProfiler CSV schema/row coverage, absent manifest-declared trial outputs, absent planned reviewer/preflight report outputs, report output safety, package output paths, protected readiness report output paths and descendants, plus UTC `generated_at_utc`, absolute workspace/manifest paths, canonical package-name slug or null, and canonical checker `argv` with absolute saved `--json-out` before any real trial is run. Saved readiness, external trial reviewer, evidence package reviewer, GitHub release verifier, release-gate, and local evidence preflight reports can now be re-checked for schema, UTC timestamp, canonical `argv`, readiness package-name binding, absolute source/package path bindings, status/detail consistency, and file summaries before production signoff; release gate now rejects external trial readiness summaries whose package-name field is missing, non-canonical, or different from the readiness file; saved external trial reviewer reports now record and recompute the bound readiness report file size/SHA-256 and package-name summary in addition to the source trial JSON and resolved artifact summaries, saved trial reviewer reports reject readiness package-name summaries that no longer match the source trial report, saved evidence-package reviewer reports now record and recompute the package copy of `readiness.json` and its package-name summary, saved package reviewer reports reject packaged readiness package-name summaries that no longer match the package readiness report, local evidence preflight reports now record and recompute the package copy of `readiness.json` including its package-name summary alongside the package trial JSON and package archive checksums, and package validation has direct regression coverage for tampered package readiness files, unbound saved package-readiness paths, tampered local-preflight package-readiness package-name summaries, readiness reports whose package-name argv binding was removed or changed, package README output that preserves the readiness package name, and release-gate rejection when that README package-name line is removed. Package artifact manifests also require UTC `packaged_at_utc`, a copied `readiness.json`, and a readiness summary matching the source trial report; the final production wrapper and direct release gate now name packaged `readiness.json` as a fixed protected input, so final output reports fail before overwriting that bound readiness file. Saved plan/readiness/reviewer/local-preflight reports also require recorded absolute paths bound to the saved artifacts under review, the standalone readiness/trial/package/release reviewer tools reject outputs that would overwrite or create files inside protected evidence inputs/artifacts/assets, and release-gate plus production-wrapper reports apply the same path-safety rule to protected external evidence paths and release verifier reports. This prevents stale or hand-edited reports from silently appearing stronger than the command that produced them.

## Production Gate Wrapper Milestone

This milestone adds `benchmark/run_production_gate.py` as the final production-claim entrypoint. It does not replace the release gate; it assembles the required final checks into one command and rejects release-candidate tags before invoking release verification.
The wrapper is treated as a release-gate orchestration file for provenance compatibility, so changing it does not by itself require regenerating CellBinDB L3 artifacts; changes to measurement code or benchmark generators still do.
Actual wrapper runs now fail fast when the external trial JSON, trial root, or evidence package directory is missing; `--dry-run` remains available for command review before those external artifacts exist.
Release-gate JSON and Markdown reports now mirror `production_claim_status` and `missing_or_failed_checks` at the top level, so CI, release review, and signoff tooling can identify production blockers without parsing the full audit table.
Release gate now runs `benchmark/validate_claim_language.py` so source docs fail fast if they contain unsupported production-ready or CellProfiler-replacement claims before the final production audit passes.
Saved release-gate JSON reports can be re-checked with `benchmark/verify_release_gate_report.py`, which requires the top-level summary fields to match `production_claim_audit`, validates metadata and gate entry schemas, requires UTC `metadata.generated_at_utc`, requires the expected production-audit check list, can verify the recorded git commit is reachable, can require clean-git metadata, rejects production PASS reports missing required production gates or final production metadata flags/paths/stable-release identity, and can require both report PASS and production-claim PASS for final signoff.
External L4 evidence package validation now requires English and Chinese READMEs to preserve trial/signoff fields, requires canonical packager `argv` in the artifact manifest matching the source trial JSON, trial root, output directory, and package name, requires absolute trial JSON/root source metadata, source trial JSON size/SHA-256, review-file size/SHA-256 entries including `README.md` and `README.zh-CN.md`, release-gate input matching, and unique package paths in the artifact manifest, requires the package zip to contain exactly the required review files and manifest-declared artifacts, rejects duplicate, missing, and extra zip entries, checks zip entry bytes against the package directory, and validates the zip checksum digest format plus target filename. Saved external trial and evidence package verifier reports also record canonical verifier `argv` plus size/SHA-256 summaries for the source trial JSON, package review files, zip archive, and checksum file, require absolute trial/root and package/source-trial verifier `argv` path values plus an absolute `--json-out` bound to the saved report path under review, and `--verify-report-files` rejects reports whose saved summaries or verifier command bindings no longer match recomputed evidence files.
The package READMEs must preserve the dataset source, execution environment, reviewer identity/role, review timestamp, signoff statement, external trial generation time, exact validation detail, and every external evidence acceptance criterion, and the package artifact manifest must preserve the exact external trial PASS detail rendered by release gate; stale or tampered package review metadata is rejected during package review.
External L4 validators now reject `REPLACE_WITH` placeholders in `external_evidence.acceptance_criteria`, reviewer signoff fields, and the top-level external evidence strings; `reviewed_at_utc` must be an ISO UTC timestamp for real trials and must not be earlier than the trial generator timestamp. The repository template can still be schema-checked with the explicit placeholder allowance.
GitHub stable-release verification now rejects prerelease or non-semver tags in the lower-level verifier as well as in the final production wrapper.
Saved GitHub release verification JSON reports can now be re-checked with `benchmark/verify_github_release.py --verify-report`; reports include schema version, verifier identity, generation timestamp, canonical verifier `argv`, GitHub release ID/API identity, author, target commit-ish, created/published timestamps, immutable state, draft state, prerelease state, the full 40-character tag commit, the 12-character `doctor` commit prefix, and GitHub asset metadata records for asset name, GitHub asset ID, API URL, download URL, upload state, created/updated timestamps, size, content type, and `sha256:` digest, live verification and `--verify-report-files` recompute downloaded asset names, archive SHA-256 values, checksum file contents, and every recorded GitHub asset size/digest field from the report's absolute `out_dir`, `--verify-git-commit` confirms the saved commit and expected tag resolve in the current git checkout, saved-report validation rejects PASS reports marked as draft releases, rejects release and asset metadata URLs that are not bound to the saved repo/tag/asset names, rejects release or asset API URLs that are not bound to the saved repo, rejects invalid or reversed release timestamps, rejects duplicate asset IDs or API URLs, rejects asset metadata entries not marked `uploaded`, rejects invalid or reversed asset timestamps, rejects saved reports whose recorded `out_dir` would contain the saved verifier report itself or other non-release assets, rejects PASS archive summaries whose recorded `checksum_match` is not true, rejects archive SHA summaries that do not match the corresponding GitHub asset digest, rejects PASS reports whose expected/release/downloaded asset sets or archive summaries are incomplete, rejects verifier argv that is not bound to the saved tag, repo, absolute output directory, stable/prerelease expectation, and required absolute saved report path, rejects unbound full/doctor commit metadata and compatible archive `doctor` summaries that are not PASS/no-issues, `--require-stable-report` prevents prerelease verification JSON from satisfying production signoff, and `--expect-tag` prevents a saved report for another stable tag from satisfying the reviewer-report slot.
The wrapper also provides `--local-evidence-preflight-only` so a completed external L4 trial, evidence package, and supplied external L4 saved reviewer verification reports can be validated before the stable GitHub release exists, using the same release-gate validators that the final production claim uses, passes supplied reviewer reports into final release-gate reports, and writes local evidence-preflight JSON/Markdown reports labeled `NOT_PRODUCTION_CLAIM`, `evidence_scope=LOCAL_EXTERNAL_L4_PREFLIGHT`, and `final_evidence_acceptable=false` with skipped final checks, canonical wrapper `metadata.argv`, absolute evidence/reviewer paths, key input file hashes, and the package-readiness package-name summary. Local evidence preflight now rejects `--github-release-verification-report` so the report cannot imply stable-release evidence that it does not validate.
Saved local evidence preflight JSON reports can also be re-checked with `--verify-local-evidence-preflight-report`, which validates the report schema, metadata types/formats, UTC `metadata.generated_at_utc`, reachable git commit, claim-scope labels, final-evidence rejection flag, skipped/validated check lists, absolute metadata evidence paths, absolute input artifact paths, input artifact digest fields, package-readiness package-name shape/binding, absolute `metadata.argv` path bindings for effective preflight inputs, and expected external L4 gate entries. Add `--verify-local-evidence-preflight-files` to recompute recorded input artifact sizes, SHA-256 hashes, and the package-readiness package-name summary, `--verify-local-evidence-preflight-gates` to rerun the recorded external L4 and saved reviewer-report gates, and `--require-local-evidence-preflight-pass` for review/signoff.
External L4 trial reports can now be reviewed directly with `benchmark/verify_external_trial_report.py`. The standalone verifier reuses the release-gate external trial validator, requires an artifact root that resolves declared outputs, writes a machine-readable PASS/FAIL JSON report with schema/verifier/timestamp/argv audit fields before evidence packaging, records source trial JSON and resolved artifact file size/SHA-256 summaries, rejects report outputs that would overwrite or create files inside the source trial JSON or declared artifacts, and can re-check saved verifier reports with `--verify-report-files` so recorded gate status/detail, verifier command bindings including absolute trial JSON, `--trial-root`, and `--json-out` paths, and saved input summaries must match freshly recomputed validation.
External L4 evidence packages can now be reviewed directly with `benchmark/verify_external_evidence_package.py`. The standalone verifier reuses the release-gate package validator, optionally binds the package to the exact source `handoff_trial.json`, writes a machine-readable PASS/FAIL JSON report with schema/verifier/timestamp/argv audit fields for reviewer signoff, records package review files including both README files, rejects report outputs that would overwrite or create files inside source/package evidence files, and can re-check saved verifier reports with `--verify-report-files` so recorded gate status/detail and verifier command bindings including absolute `--json-out` must match freshly recomputed validation. Production signoff uses `--require-trial-json` so saved package reviewer reports cannot be accepted unless they are bound to the source trial JSON.

Required final command shape:

```bash
python3 benchmark/run_production_gate.py \
  --external-trial-json path/to/external/handoff_trial.json \
  --external-trial-root path/to/external \
  --external-evidence-package-dir path/to/evidence-packages/external-l4-trial \
  --github-release-verification-report path/to/github-release/verification.json \
  --github-release-tag v0.1.0
```

The wrapper invokes `benchmark/release_gate.py` with `--require-clean-git`, `--require-l3-provenance`, `--require-production-claim`, external L4 trial/package validation, saved reviewer report checks when supplied, `--verify-github-release`, and `--github-release-kind stable` in the same report. When that release gate succeeds, the wrapper immediately re-checks the saved final report with `benchmark/verify_release_gate_report.py --require-report-pass --require-clean-git-metadata --verify-git-commit --require-production-claim-pass --expect-missing-checks none`. Saved GitHub release verification JSON is rechecked with file hashes and stable-report requirements when supplied, but the current production claim remains incomplete until real external L4 evidence and a live stable release verification are supplied and that combined gate passes.
The production wrapper now also rejects saved external L4 trial/package reviewer reports that are valid by themselves but point to a different trial JSON, trial root, or evidence package directory than the current wrapper inputs.
The production wrapper, direct release gate, and generated external L4 trial plans now reject saved stable GitHub release reviewer reports that are valid by themselves but point to a repository other than `benngaihk/MorphoJet`, and saved release-gate report verification requires the recorded saved-GitHub-release gate command to preserve `--expect-repo benngaihk/MorphoJet`.

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
| `python3 tests/test_verify_github_release.py` with saved release expected-repo coverage | PASS |

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

Provenance: the scheduler-ready L3 release gate passed for commit `f5d0624545f5` with a clean worktree, `skip_cellprofiler=false`, 14 hashed artifacts. Under the current production-claim audit model, the L3 evidence still leaves `missing_or_failed_checks=["external_l4_workflow_trial", "external_l4_evidence_package", "external_l4_saved_reviewer_reports", "stable_github_release", "stable_github_release_saved_report"]`.

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
