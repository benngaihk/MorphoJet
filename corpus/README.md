# Corpus

This directory contains reproducible corpus helpers. Generated data is written under `benchmark/data/` and is not committed.

## Smoke Corpus

```bash
python3 corpus/generate_smoke.py --images 16
benchmark/run.sh benchmark/data/smoke/images.csv benchmark/results/smoke
python3 benchmark/summarize.py benchmark/results/smoke
```

The smoke corpus uses deterministic grayscale PNG intensity images and 8-bit label masks. It is designed to exercise CLI wiring and CSV output, not to prove CellProfiler parity.
