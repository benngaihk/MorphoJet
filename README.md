# MorphoJet

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

To verify a published GitHub release candidate:

```bash
python3 benchmark/release_gate.py --verify-github-release v0.1.0-rc.1
```

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
python3 benchmark/release_gate.py --run-l3 --build-release-artifact --release-version rc-preflight
```

For a fast audit of already-generated L3 artifacts, run `python3 benchmark/release_gate.py`.

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

Use `benchmark/handoff/external_lab_template.json` as the starting point for real lab handoff files. External workflow trials must fill the `external_evidence` block and pass validation with `--require-external-evidence`; the trial report preserves those fields for L4 review.

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

Production-readiness gates are tracked in [docs/PRODUCTION_READINESS.md](docs/PRODUCTION_READINESS.md). MorphoJet has a passing L3 public direct-mask benchmark, a verified `v0.1.0-rc.1` prerelease, and an L4-preflight handoff harness, but should not be described as production-ready until an external workflow-fit trial passes.
