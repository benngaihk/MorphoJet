# Roadmap

## M-1: Target Validation

- Pick 3 real CellProfiler pipelines.
- Run CellProfiler headless and preserve raw CSV outputs.
- Build a small Python/NumPy baseline for speed sanity checks.
- Confirm at least one pipeline spends meaningful time in measurement.

## M0: Public Benchmark CLI

- [x] Rust workspace with `morphojet-core` and `morphojet` CLI.
- [x] Common 2D image reading through the Rust `image` crate.
- [x] Label mask traversal.
- [x] Intensity and size/shape starter features.
- [x] CSV writer.
- [x] Synthetic smoke corpus generator.
- [x] CellProfiler output normalizer and CSV comparator.
- [x] CI smoke benchmark and parity self-check.
- [x] `benchmark/run.sh` configurable CellProfiler oracle hook.
- [x] Pinned public CellProfiler oracle dataset and `.cppipe`.
- [x] `docs/PARITY.md` compatibility ledger.
- [x] Industry-impact validation gate document.
- [x] L2/L3 oracle validation checklist and impact gate reporter.

## M1: Lab Trial

- Production hardening before any lab trial:
  - [x] CLI overwrite protection.
  - [x] Output atomicity.
  - [x] CLI integration failure-mode tests.
  - [x] Release packaging and checksums.
  - [x] Local release archive verifier.
  - [x] Verified `v0.1.0-rc.1` GitHub prerelease assets.
  - [x] Public CellProfiler oracle benchmark.
  - [x] Manual release gate command for code checks plus CellBinDB L3.
  - [x] Supported-column CellProfiler-style wide CSV bridge.
  - [x] Manifest-driven handoff trial preflight.
  - [x] Handoff manifest validator and external lab template.
  - [x] Scheduler-ready CellBinDB L3 validation script.
  - [x] Structured measure success/failure JSON reports.
  - [x] GitHub scheduled CellBinDB L3 workflow.
  - [x] Optional object-level image-table metadata export for plate/well/site handoff context.
  - [x] External L4 manifest/readiness contract for required object metadata columns.
  - [x] CellProfiler-style wide export carries declared object metadata columns.
  - [x] Evidence-package READMEs render and gate-check the handoff contract for reviewers.
  - [x] Saved package verifier reports bind README handoff contracts to the rendered manifest.
  - [x] Local evidence preflight reports bind README handoff contracts to package READMEs and the rendered manifest.
  - [x] Generated external L4 workspace READMEs describe and plan-file-verify the local-preflight handoff-contract recheck.
  - [x] Final production wrapper fail-fast requires saved trial, package, and stable-release verifier reports.
  - [x] Generated final signoff requirements bind each artifact to the exact final wrapper argument it satisfies.
  - [x] Saved trial-plan verification checks final signoff rows against final wrapper command flags and values.
  - [x] Saved trial-plan verification checks pre-signoff readiness and local-preflight rows against command flags and values.
  - [x] Saved trial-plan verification checks external trial, package, reviewer-report, release-report, and final-report command path flow.
  - [x] Saved trial-plan verification checks stable release tag/repo/report identity and final-wrapper tag binding.
  - [x] Saved trial-plan verification checks external evidence reviewer/signoff requirements and renders them in English/Chinese workspace READMEs.
  - [x] Generated external L4 plans include standalone saved trial/package reviewer-report recheck commands before local preflight and final signoff.
  - [x] Saved trial-plan verification marks saved reviewer-report rechecks as local-preflight prerequisites.
  - [x] Root and generated external L4 READMEs now expose a Chinese-community review entrypoint, and the source-doc guard requires it to remain present.
  - [x] Evidence-package READMEs now expose a package-level Chinese reviewer entrypoint, and saved package verifier reports record plus recheck that entrypoint.
  - [ ] External workflow trial.

- Multi-channel and plate/well/site metadata polish: object-level metadata export is available behind `measure --include-object-metadata`, the external L4 template/readiness checker can require `Plate`, `Well`, and `Site`, the wide-export bridge can carry those declared metadata columns through to downstream CSVs, and local preflight now preserves the README-rendered handoff contract for review; remaining work is external L4 confirmation that the handoff shape matches real lab systems.
- More morphology features.
- Better error reporting.
- macOS/Linux binaries.
- Python wrapper only after CLI behavior is stable.
