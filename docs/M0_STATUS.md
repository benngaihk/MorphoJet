# M0 Status

Updated: 2026-07-02

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
- CLI safety hardening: thread validation, non-empty input table, duplicate row identity detection, readable path preflight, overwrite protection.
- CLI integration tests for success and major failure modes.
- Output staging writes: final `Image.csv` and `Objects.csv` are published only after both staging files are written.
- Clippy quality gate in CI.
- Tagged release workflow for macOS/Linux binary archives and SHA-256 checksums.
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

## Verified Locally

```bash
$HOME/.cargo/bin/cargo fmt
$HOME/.cargo/bin/cargo test
python3 -m py_compile benchmark/summarize.py corpus/generate_smoke.py tests/parity/*.py
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

## Not Yet Achieved

- Manifest-driven bridge-aware pinned CellProfiler oracle parity run.
- Public tutorial or Cell Painting corpus.
- CellProfiler measurement-only oracle pipeline for the >=1k direct-mask corpus.
- 1k real/public CellProfiler benchmark.
- 10x speedup claim on >=1k real/public image rows.
- Peak RSS comparison on >=1k real/public image rows.
- Broader CellProfiler coordinate and shape formula parity beyond ExampleHuman.
- L3-L4 industry-impact evidence.
- Production release workflow and output-safety hardening.

## Next Gate

M0 should only be called complete after a pinned CellProfiler oracle dataset produces:

- 100% object count parity.
- >=99% core numeric parity within documented tolerance.
- >=10x wall-clock speedup on >=1k real/public image rows.
- Peak RSS <=50% of CellProfiler on the same machine.
