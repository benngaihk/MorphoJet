# M0 Status

Updated: 2026-07-03

## Achieved

- Rust workspace with `morphojet-core` and `morphojet` CLI.
- `morphojet measure --images ... --out ... --threads ... --cellprofiler-compatible`.
- Image table parsing with relative path resolution.
- Existing label mask measurement for positive labels.
- `Image.csv` and `Objects.csv` output.
- Starter features:
  - object count
  - area
  - centroid
  - bounding box
  - min, max, mean, median, integrated intensity
  - 4-neighbor perimeter approximation
  - eccentricity, major axis, minor axis from second moments
  - solidity from convex hull over pixel square corners
- Synthetic smoke corpus generator.
- Benchmark smoke path.
- Normalization and parity comparison scripts.
- Configurable CellProfiler oracle benchmark hook.
- CI workflow for formatting, tests, smoke benchmark, and parity self-check.
- Industry-impact validation gates in `docs/INDUSTRY_VALIDATION.md`.
- L1 synthetic scale benchmark results in `docs/VALIDATION_RESULTS.md`.
- L2/L3 oracle validation checklist in `docs/ORACLE_VALIDATION.md`.
- Production readiness checklist in `docs/PRODUCTION_READINESS.md`.
- CLI safety hardening: thread validation, non-empty input table, duplicate header rejection, reserved output-column metadata rejection, duplicate row identity detection, readable path preflight, overwrite protection.
- CLI integration tests for success and major failure modes.
- Output staging writes: final `Image.csv` and `Objects.csv` are published only after both staging files are written; non-file final/report targets are rejected before publish.
- Clippy quality gate in CI.
- Tagged release workflow for macOS/Linux binary archives and SHA-256 checksums.
- Local release archive builder and verifier for pre-tag package validation.
- Runtime diagnostics via `morphojet doctor`.
- Reusable command metrics wrapper for elapsed time and peak RSS capture.
- Impact gate report can consume metrics JSON directly.
- Manifest-driven CellProfiler oracle benchmark runner and manifest validator.
- Impact gate report can derive parity metrics from parity JSON.
- Public CellProfiler examples candidate catalog and fetch script.
- `example-human` CellProfiler candidate fetch preflight: 3 CC-0 TIFF images and pipeline materialized, but still not direct M0 oracle because masks are not provided.
- CellProfiler pipeline inspector for identifying measured objects and missing label exports.
- Image table materializer for pairing exported label masks with intensity images.
- Oracle runner now refuses benchmark manifests unless `dataset.m0_status` is explicitly `direct`.
- CellProfiler mask-export bridge can generate a patched pipeline copy that converts missing measured objects to label matrices and saves `.npy` labels.
- NPY-to-TIFF converter can turn exported label matrices into MorphoJet-readable uint16 masks.
- `ObjectSet` is now a first-class image-table, output, and parity key for multi-object pipelines.
- Multi-channel oracle image-table materializer can combine bridge objects, intensity channels, and emitted masks into one MorphoJet table.
- MorphoJet long `Objects.csv` can be materialized into a CellProfiler-style per-object wide CSV for the supported measurement subset.
- Wide CSV bridge comparator validates supported columns against full CellProfiler object CSVs while reporting unsupported CellProfiler columns as out of scope.
- Manifest-driven handoff trial runner can materialize wide CSVs, compare supported columns, and run downstream contract checks without manual CSV editing.
- Handoff manifest validator and external lab template define the acceptance package for real workflow trials, including required external L4 evidence fields when `--require-external-evidence` is used.

## Verified Locally

```bash
$HOME/.cargo/bin/cargo fmt
$HOME/.cargo/bin/cargo test
python3 -m py_compile benchmark/*.py corpus/generate_smoke.py tests/*.py tests/parity/*.py
python3 -m unittest discover -s tests
python3 corpus/generate_smoke.py --images 16
benchmark/run.sh benchmark/data/smoke/images.csv benchmark/results/smoke
python3 benchmark/summarize.py benchmark/results/smoke
python3 tests/parity/compare_measurements.py benchmark/results/smoke/Objects.csv benchmark/results/smoke/Objects.csv --fail-on-gap
git diff --check
```

Smoke output from local run:

- image rows: 16
- object rows: 64
- parity self-check: PASS

Latest M0 oracle gate verification:

- `benchmark/cellprofiler/manifest.example.json --require-m0-ready`: PASS.
- `example-human` generated candidate manifest with `m0_status=not_direct`: correctly rejected by `--require-m0-ready`.
- `export_cellprofiler_masks.py` patched fixture and ExampleHuman pipelines; inspector accepted both patched copies as M0-ready.
- Multi-object-set smoke keeps 16 image rows and 64 object rows, with parity keys `ImageNumber,ObjectSet,ObjectNumber,Channel`: PASS.
- `build_oracle_image_table.py` fixture wrote 8 rows for 2 samples x 2 object sets x 2 channels.
- Docker `cellprofiler/cellprofiler:4.2.6` ran patched ExampleHuman headlessly and exported non-zero NPY label matrices for Cells, Cytoplasm, and Nuclei.
- Converted ExampleHuman NPY labels to uint16 TIFF; MorphoJet measured 6 image rows and 1734 object rows from those masks.
- Materialized CellProfiler object CSVs into a long oracle CSV with 1734 rows.
- ExampleHuman parity now passes: 1734 expected rows, 1734 actual rows, 0 row/schema gaps, 0 numeric failures.
- ExampleHuman oracle smoke runner captures CellProfiler Docker metrics and MorphoJet release metrics end-to-end.
- ExampleHuman L3 smoke report: scale FAIL at 6 image rows, object parity PASS at 100%, numeric parity PASS at 100%, speedup PASS at 196.74x, RSS ratio PASS at 6.89%.
- Local CellProfiler examples scan is tool-backed: 21 pipelines, 408 raw image files total, best rough image-row upper bound 90, so official examples alone cannot prove L3 scale.
- CellBinDB is registered as the next L3 direct-mask candidate: 1,044 annotated microscope images, semantic and instance masks, CC0 Zenodo record, 286 MB primary archive with MD5 verification metadata.
- CellBinDB preparation script can pair `*-img.tif` with `*-instancemask.tif`, extract selected rows, and write a MorphoJet image table.
- CellBinDB archive was downloaded locally and MD5 verified; MorphoJet processed the full 1,044-row direct-mask table into 107,936 object rows in 0.879788 seconds with 89.875 MB peak RSS.
- CellBinDB 8-row CellProfiler oracle smoke passes: 590 expected rows, 590 actual rows, 0 row gaps, 0 numeric failures.
- CellBinDB full L3 benchmark passes: 1,044 image rows, 107,936 expected rows, 107,936 actual rows, 0 row gaps, 0 numeric failures, 609.82x speedup, 13.98% RSS ratio.
- CellBinDB workflow bridge passes: 107,936 CellProfiler rows, 107,936 MorphoJet wide rows, 33 compared value columns, 3,561,888 numeric comparisons, 0 numeric failures. The comparator records 17 unsupported CellProfiler columns as ignored, not claimed.
- CellBinDB handoff preflight passes: 3 manifest steps, 107,936 wide rows, 35 required contract columns, 0 missing columns, 0 duplicate keys, 0 empty keys.
- CellBinDB oracle runner writes `provenance.json` after full runs, capturing git commit, dirty status, command arguments, tool context, and SHA-256 hashes for the L3 parity, impact, workflow-bridge, handoff, CellProfiler, and MorphoJet artifacts. The latest scheduler-ready L3 run passed the provenance gate for commit `abf6b31413f0` with 14 hashed artifacts and `skip_cellprofiler=false`.
- Handoff manifest gates pass for the CellBinDB preflight manifest and the external lab template; the external template is validated with required lab/workflow owner, dataset source, downstream workflow, execution environment, acceptance criteria, and `manual_csv_editing=false` evidence fields.
- Release gate script can run code gates and validate or rerun the CellBinDB L3 benchmark plus the workflow bridge and handoff trial artifacts, writing JSON and Markdown reports with run timestamp, git commit, dirty-worktree status, invoked arguments, optional L3 provenance/hash validation, and a production-claim audit that remains `INCOMPLETE` until clean-git, external L4, and stable release checks are included.
- Scheduler-ready CellBinDB L3 validation script is implemented with Zenodo archive verification, pinned MD5/size fallback for existing local archives, pinned CellProfiler Docker image pull, and full oracle execution.
- CLI observability includes `morphojet doctor`, optional `measure --summary-json` run metadata, and optional `measure --error-json` failure reports with basic stable error codes for machine-readable batch monitoring.
- Local release artifact preflight passes on macOS arm64: archive checksum verified and packaged `morphojet doctor` reports version, current commit, OS, and architecture.
- GitHub release candidate `v0.1.0-rc.1` passes: release workflow built Linux/macOS archives, all published checksums match, release is marked prerelease, and the macOS packaged binary reports the tag commit.

## Not Yet Achieved

- Manifest-driven bridge-aware pinned CellProfiler oracle parity run.
- Public tutorial or Cell Painting corpus.
- Scheduled/nightly validation job for the 1k real/public CellProfiler benchmark.
- Broader CellProfiler coordinate and shape formula parity beyond ExampleHuman.
- L4 external lab workflow replacement evidence beyond the supported-column handoff preflight.
- A stable non-RC GitHub release validated after external workflow evidence.

## Next Gate

The next gate toward production readiness is no longer L3 evidence; it is repeatability and L4 workflow fit:

- Re-run `python3 benchmark/release_gate.py --require-clean-git --require-l3-provenance --run-l3 --build-release-artifact --release-version rc-preflight` before promoting from RC to stable release.
- After external workflow evidence passes, verify the stable release with `python3 benchmark/release_gate.py --verify-github-release v0.1.0 --github-release-kind stable`.
- Promote the CellBinDB full benchmark into scheduled/nightly validation.
- Run an external lab workflow trial with real handoff files.
- Copy `benchmark/handoff/external_lab_template.json`, fill the external evidence block, exercise the manifest-driven handoff trial in that external workflow without manual CSV editing, and validate the resulting report plus clean-git generator metadata for the current or compatible commit, rendered manifest snapshot, exact manifest-declared step command/runtime/detail/artifact coverage, and artifact provenance hashes with `python3 benchmark/release_gate.py --external-trial-json path/to/handoff_trial.json --external-trial-root path/to/external`.
- Broaden compatibility beyond the current measurement subset.
