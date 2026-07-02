# MorphoJet Design

## Principle

CellProfiler is the oracle. MorphoJet is a measurement-only execution engine for stable batch workflows.

## M0 Data Flow

1. Read an image table CSV.
2. Resolve relative image and mask paths from the CSV location.
3. Load an intensity image and label mask.
4. Scan the label mask once and accumulate object features.
5. Stream `Image.csv` and `Objects.csv`.

## Current Feature Set

- Object count.
- Area.
- Geometric centroid.
- Bounding box.
- Min, max, mean, median, and integrated intensity using CellProfiler-compatible scaling and quantile interpolation.
- scikit-image / CellProfiler-compatible 4-neighborhood perimeter.
- Major axis, minor axis, and eccentricity from second central moments.
- Solidity from CellProfiler-compatible convex-hull-image pixel count.

## Compatibility Notes

The first implementation uses zero-based pixel coordinates internally and writes deterministic CSV rows sorted by image table order and object label. CellProfiler compatibility is a target, not a finished claim; every observed difference belongs in `docs/PARITY.md`.
