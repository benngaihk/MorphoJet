# CellProfiler Parity Ledger

This file is the public compatibility ledger. Do not claim full parity from benchmark speed alone.

## Current Status

| Feature | Status | Notes |
|---|---|---|
| Image table ingestion | FIX | Supports `ImageNumber`, `ImagePath`, `MaskPath`, optional `Channel`, and metadata passthrough. |
| Object count | FIX | Counts positive labels in an existing mask. |
| Area | FIX | Counts pixels per label. |
| Centroid | GAP | Uses zero-based geometric centroid; CellProfiler coordinate convention still needs oracle comparison. |
| Bounding box | GAP | Uses inclusive min/max pixel coordinates; CellProfiler exact export convention needs comparison. |
| Intensity min/max/mean/median/integrated | FIX | Preserves raw values for grayscale 8-bit and 16-bit images; non-grayscale conversion needs explicit oracle comparison. |
| 32-bit float label masks | GAP | Not supported yet; M0 starter expects 8-bit or 16-bit label masks. |
| Perimeter | GAP | Current value is a 4-neighbor boundary-edge approximation. |
| Eccentricity and axis lengths | GAP | Derived from second central moments; CellProfiler formula and tolerance need oracle comparison. |
| Solidity | GAP | Not implemented in M0 starter. |

## Default Numeric Tolerance

- Absolute tolerance: `1e-6`
- Relative tolerance: `1e-5`

Each benchmark dataset should record exact CellProfiler version, MorphoJet commit, OS, CPU, image count, object count, wall-clock time, and peak RSS.
