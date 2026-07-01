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
- [ ] CellProfiler output normalizer.
- [ ] `benchmark/run.sh` CellProfiler oracle leg.
- [x] `docs/PARITY.md` compatibility ledger.

## M1: Lab Trial

- Multi-channel and plate/well/site metadata polish.
- More morphology features.
- Better error reporting.
- macOS/Linux binaries.
- Python wrapper only after CLI behavior is stable.
