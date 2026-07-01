# Benchmark

## Smoke Benchmark

The smoke benchmark is synthetic and does not prove CellProfiler parity.

```bash
python3 corpus/generate_smoke.py --images 16
benchmark/run.sh benchmark/data/smoke/images.csv benchmark/results/smoke
python3 benchmark/summarize.py benchmark/results/smoke
```

## CellProfiler Oracle

When a pinned `.cppipe` and oracle corpus are available, provide the complete CellProfiler command through `CELLPROFILER_CMD`.

Example:

```bash
CELLPROFILER_CMD='cellprofiler -c -r -p benchmark/cellprofiler/pipeline.cppipe -o benchmark/results/cellprofiler' \
CELLPROFILER_OBJECTS_CSV='benchmark/results/cellprofiler/Objects.csv' \
benchmark/run.sh benchmark/data/cellprofiler/images.csv benchmark/results/morphojet
```

`benchmark/run.sh` will:

1. Run MorphoJet.
2. Run the provided CellProfiler command.
3. Normalize both object CSVs when `CELLPROFILER_OBJECTS_CSV` is set.
4. Write `benchmark/results/parity/objects_parity.md`.

## Required Benchmark Metadata

Each real benchmark result should record:

- CellProfiler version.
- MorphoJet commit.
- OS and CPU.
- Image count.
- Object count.
- Wall-clock time.
- Peak RSS.
- Dataset source and license.
