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
  --overwrite
```

## Release Builds

Tagged releases (`v*`) build macOS and Linux CLI archives with SHA-256 checksums through GitHub Actions.

## Diagnostics

```bash
morphojet doctor
```

The `doctor` command prints version, commit, platform, thread, and executable-path context for reproducible bug reports.

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

Production-readiness gates are tracked in [docs/PRODUCTION_READINESS.md](docs/PRODUCTION_READINESS.md). MorphoJet should be treated as an M0 candidate until those gates pass.
