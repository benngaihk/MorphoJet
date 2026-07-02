# CellProfiler Parity Ledger

This file is the public compatibility ledger. Do not claim full parity from benchmark speed alone.

## Current Status

| Feature | Status | Notes |
|---|---|---|
| Image table ingestion | FIX | Supports `ImageNumber`, `ImagePath`, `MaskPath`, optional `Channel`, optional `ObjectSet`, and metadata passthrough. |
| Object count | FIX | Counts positive labels in an existing mask. |
| Area | FIX | Counts pixels per label. |
| Centroid | FIX | ExampleHuman oracle matches CellProfiler within tolerance. |
| Bounding box | FIX | Writes CellProfiler-style exclusive maximum X/Y bounds. |
| Intensity min/max/mean/median/integrated | FIX | Normalizes grayscale 8-bit and 16-bit image intensities to CellProfiler's 0-1 measurement scale and uses CellProfiler's quantile interpolation for median. |
| 32-bit float label masks | GAP | Not supported yet; M0 starter expects 8-bit or 16-bit label masks. |
| Normalized CSV comparison | FIX | `tests/parity/normalize_measurements.py` and `tests/parity/compare_measurements.py` provide deterministic parity reports. |
| Perimeter | FIX | Matches scikit-image 0.18.3 / CellProfiler 4.2.6 4-neighborhood perimeter lookup weights. |
| Eccentricity and axis lengths | FIX | ExampleHuman oracle matches CellProfiler within tolerance. |
| Solidity | FIX | Matches scikit-image 0.18.3 convex-hull-image pixel count behavior on ExampleHuman. |
| CellProfiler-style wide object CSV | PARTIAL | `benchmark/materialize_morphojet_cellprofiler_wide.py` emits supported columns in a per-object wide shape; unsupported CellProfiler columns remain explicit gaps. |

## Default Numeric Tolerance

- Absolute tolerance: `1e-6`
- Relative tolerance: `1e-5`

Each benchmark dataset should record exact CellProfiler version, MorphoJet commit, OS, CPU, image count, object count, wall-clock time, and peak RSS.

## Parity Tooling

```bash
python3 tests/parity/normalize_measurements.py CellProfiler_Objects.csv normalized/cp_objects.csv
python3 tests/parity/normalize_measurements.py measurements/Objects.csv normalized/morphojet_objects.csv
python3 benchmark/materialize_cellprofiler_oracle.py \
  --object Cells=benchmark/results/cellprofiler-run-426-npy/Cells.csv \
  --object Cytoplasm=benchmark/results/cellprofiler-run-426-npy/Cytoplasm.csv \
  --object Nuclei=benchmark/results/cellprofiler-run-426-npy/Nuclei.csv \
  --channels DNA,PH3 \
  --out benchmark/results/cellprofiler-run-426-npy/Objects.long.csv
python3 tests/parity/compare_measurements.py \
  normalized/cp_objects.csv \
  normalized/morphojet_objects.csv \
  --keys ImageNumber,ObjectSet,ObjectNumber,Channel \
  --out reports/objects_parity.md \
  --fail-on-gap
python3 benchmark/materialize_morphojet_cellprofiler_wide.py \
  --objects measurements/Objects.csv \
  --object-set Cells \
  --channels DNA,PH3 \
  --out measurements/Cells.wide.csv
python3 benchmark/compare_cellprofiler_wide_subset.py \
  CellProfiler/Cells.csv \
  measurements/Cells.wide.csv \
  --fail-on-gap
```
