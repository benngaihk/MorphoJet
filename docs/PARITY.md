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
| Intensity min/max/mean/integrated | FIX | Normalizes grayscale 8-bit and 16-bit image intensities to CellProfiler's 0-1 measurement scale. |
| Intensity median | GAP | ExampleHuman has 185 median mismatches; CellProfiler median handling needs exact replication. |
| 32-bit float label masks | GAP | Not supported yet; M0 starter expects 8-bit or 16-bit label masks. |
| Normalized CSV comparison | FIX | `tests/parity/normalize_measurements.py` and `tests/parity/compare_measurements.py` provide deterministic parity reports. |
| Perimeter | GAP | Current value is a 4-neighbor boundary-edge approximation. |
| Eccentricity and axis lengths | FIX | ExampleHuman oracle matches CellProfiler within tolerance. |
| Solidity | GAP | Implemented as area divided by convex hull area over pixel square corners; CellProfiler formula and tolerance need oracle comparison. |

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
```
