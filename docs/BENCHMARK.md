# Benchmark

## Smoke Benchmark

The smoke benchmark is synthetic and does not prove CellProfiler parity.

```bash
python3 corpus/generate_smoke.py --images 16
benchmark/run.sh benchmark/data/smoke/images.csv benchmark/results/smoke
python3 benchmark/summarize.py benchmark/results/smoke
```

## Synthetic Scale Benchmark

The scale benchmark validates local release-path throughput on deterministic synthetic data. It is useful for regression tracking, but it is not a CellProfiler oracle comparison.

```bash
python3 benchmark/run_scale.py --cases 16,256,1024 --width 96 --height 96
cat benchmark/results/scale/summary.md
```

Outputs:

- `benchmark/results/scale/scale.csv`
- `benchmark/results/scale/summary.md`
- `benchmark/results/scale/metadata.json`

Committed validation summaries are tracked in `docs/VALIDATION_RESULTS.md`.

## CellProfiler Oracle

When a pinned `.cppipe` and oracle corpus are available, prefer the manifest-driven oracle runner.

Example:

```bash
cp benchmark/cellprofiler/manifest.example.json benchmark/cellprofiler/manifest.json
python3 benchmark/validate_benchmark_manifest.py benchmark/cellprofiler/manifest.json --check-files
python3 benchmark/run_oracle_benchmark.py benchmark/cellprofiler/manifest.json
```

The runner will:

1. Build MorphoJet release binary.
2. Run CellProfiler through either `cellprofiler.command` or `cellprofiler.docker_image`.
3. Run MorphoJet on the manifest image table.
4. Capture elapsed time and peak RSS for both tools.
5. Normalize both object CSV files.
6. Write Markdown and JSON parity reports.

`benchmark/run.sh` still supports ad hoc runs through `CELLPROFILER_CMD`, but the manifest path is the production validation path.

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

## Impact Gate Report

After a real CellProfiler oracle run, generate the final gate report with:

```bash
python3 benchmark/impact_report.py \
  --image-rows 1000 \
  --parity-json benchmark/results/parity/objects_parity.json \
  --cellprofiler-metrics-json benchmark/results/metrics/cellprofiler.metrics.json \
  --morphojet-metrics-json benchmark/results/metrics/morphojet.metrics.json \
  --fail-on-gap
```

## Command Metrics

Use one metrics wrapper for both CellProfiler and MorphoJet when collecting production evidence:

```bash
python3 benchmark/run_command_metrics.py \
  --name morphojet \
  --out benchmark/results/metrics \
  --fail-on-nonzero \
  -- target/release/morphojet measure \
    --images benchmark/data/smoke/images.csv \
    --out benchmark/results/smoke \
    --cellprofiler-compatible \
    --overwrite
```

The wrapper writes stdout/stderr logs plus `<name>.metrics.json` with elapsed seconds and peak RSS.
