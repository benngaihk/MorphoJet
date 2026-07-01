# M0 Status

Updated: 2026-07-01

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

## Not Yet Achieved

- Pinned CellProfiler headless oracle run.
- Public tutorial or Cell Painting corpus.
- Real CellProfiler CSV parity report.
- 1k real/public CellProfiler benchmark.
- 10x speedup claim.
- Peak RSS comparison.
- Full CellProfiler coordinate and shape formula parity.
- L2-L4 industry-impact evidence.
- Production release workflow and output-safety hardening.

## Next Gate

M0 should only be called complete after a pinned CellProfiler oracle dataset produces:

- 100% object count parity.
- >=99% core numeric parity within documented tolerance.
- >=10x wall-clock speedup on 1k images.
- Peak RSS <=50% of CellProfiler on the same machine.
