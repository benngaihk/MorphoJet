# Roadmap

## M-1: Target Validation

- Pick 3 real CellProfiler pipelines.
- Run CellProfiler headless and preserve raw CSV outputs.
- Build a small Python/NumPy baseline for speed sanity checks.
- Confirm at least one pipeline spends meaningful time in measurement.

## M0: Public Benchmark CLI

- Rust workspace with `morphojet-core` and `morphojet` CLI.
- TIFF and common 2D image reading.
- Label mask traversal.
- Intensity and size/shape core features.
- CSV writer.
- CellProfiler output normalizer.
- `benchmark/run.sh` for CellProfiler vs MorphoJet.
- `docs/PARITY.md` compatibility ledger.

## M1: Lab Trial

- Multi-channel and plate/well/site metadata polish.
- More morphology features.
- Better error reporting.
- macOS/Linux binaries.
- Python wrapper only after CLI behavior is stable.
