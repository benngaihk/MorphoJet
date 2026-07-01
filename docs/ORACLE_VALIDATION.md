# Oracle Validation Checklist

This checklist turns MorphoJet's industry-impact claim into a reproducible L2/L3 validation package.

## Candidate Sources

Use public sources first so every result can be reproduced:

- CellProfiler examples and tutorials: https://cellprofiler.org/examples
- CellProfiler documentation: https://cellprofiler-manual.s3.amazonaws.com/
- Cell Painting / JUMP public data for larger follow-up benchmarks: https://jump-cellpainting.broadinstitute.org/
- Nyxus as a high-performance feature extraction reference: https://nyxus.readthedocs.io/

## L2 Package: Correctness

Required files:

- `benchmark/cellprofiler/VERSION.txt`
- `benchmark/cellprofiler/pipeline.cppipe`
- `benchmark/cellprofiler/images.csv`
- `benchmark/results/cellprofiler/Objects.csv`
- `benchmark/results/morphojet/Objects.csv`
- `benchmark/results/parity/objects_parity.md`

Checklist:

1. Pin CellProfiler version.
2. Select a public image/mask corpus with clear license and download URL.
3. Run CellProfiler headless with `ExportToSpreadsheet`.
4. Run MorphoJet on the equivalent image table.
5. Normalize both object CSV files.
6. Generate parity report.
7. Record every mismatch in `docs/PARITY.md`.

Pass condition:

- 100% object count parity.
- >=99% core numeric parity within documented tolerance.

## L3 Package: Performance and Memory

Required files:

- `benchmark/results/impact/summary.md`
- `benchmark/results/impact/summary.json`
- Raw timing logs for CellProfiler and MorphoJet.
- Peak RSS logs for CellProfiler and MorphoJet.

Checklist:

1. Use the same machine, dataset, and storage path for both tools.
2. Run at least 1k image rows.
3. Measure wall-clock time.
4. Measure peak RSS.
5. Capture both tools through the same metrics wrapper:

```bash
python3 benchmark/run_command_metrics.py --name cellprofiler --out benchmark/results/metrics --fail-on-nonzero -- cellprofiler -c -r -p benchmark/cellprofiler/pipeline.cppipe -o benchmark/results/cellprofiler
python3 benchmark/run_command_metrics.py --name morphojet --out benchmark/results/metrics --fail-on-nonzero -- target/release/morphojet measure --images benchmark/cellprofiler/images.csv --out benchmark/results/morphojet --cellprofiler-compatible --overwrite
```

6. Generate impact gate report:

```bash
python3 benchmark/impact_report.py \
  --image-rows 1000 \
  --object-count-parity 1.0 \
  --numeric-parity 0.99 \
  --cellprofiler-seconds 600 \
  --morphojet-seconds 60 \
  --cellprofiler-rss-mb 8000 \
  --morphojet-rss-mb 4000 \
  --fail-on-gap
```

Pass condition:

- >=10x wall-clock speedup.
- MorphoJet peak RSS <=50% of CellProfiler.

## Claim Language

Allowed only after L2 and L3 pass:

> MorphoJet is 10x faster than CellProfiler headless on this reproducible measurement-only benchmark while matching the tested measurement subset within documented tolerance.

Not allowed before L2 and L3 pass:

> MorphoJet replaces CellProfiler.
> MorphoJet is better than Nyxus.
> MorphoJet is generally faster for microscopy analysis.
