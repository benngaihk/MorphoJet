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
If the public pipeline segments objects internally, first generate a patched copy that exports label masks:

```bash
python3 benchmark/export_cellprofiler_masks.py \
  benchmark/data/cellprofiler/prepared/ExampleHuman/ExampleHuman.cppipe \
  --out benchmark/results/cellprofiler/example-human-masks.cppipe \
  --bridge-json benchmark/results/cellprofiler/example-human-masks.json
```

After CellProfiler writes the `.npy` masks, convert them to uint16 TIFF and materialize the multi-channel, multi-object-set MorphoJet image table:

```bash
python3 benchmark/convert_npy_masks_to_tiff.py \
  --base-dir benchmark/results/cellprofiler-run-426-npy \
  --out-dir benchmark/results/cellprofiler-run-426-labels-tiff

python3 benchmark/build_oracle_image_table.py \
  --base-dir . \
  --bridge-json benchmark/results/cellprofiler/example-human-masks.json \
  --channel DNA 'benchmark/data/cellprofiler/prepared/ExampleHuman/images/*d0.tif' '(.+)d0\\.tif$' \
  --channel PH3 'benchmark/data/cellprofiler/prepared/ExampleHuman/images/*d1.tif' '(.+)d1\\.tif$' \
  --mask-glob-template 'benchmark/results/cellprofiler-run-426-labels-tiff/morphojet_masks/{safe_name}/*_MorphoJetMask_{safe_name}.tif' \
  --mask-key-regex-template '(.+)d0_MorphoJetMask_{safe_name}\\.tif$' \
  --out benchmark/results/cellprofiler-run-426-labels-tiff/morphojet-images.csv
```

Materialize CellProfiler's per-object CSVs into MorphoJet's long object format before parity comparison:

```bash
python3 benchmark/materialize_cellprofiler_oracle.py \
  --object Cells=benchmark/results/cellprofiler-run-426-npy/Cells.csv \
  --object Cytoplasm=benchmark/results/cellprofiler-run-426-npy/Cytoplasm.csv \
  --object Nuclei=benchmark/results/cellprofiler-run-426-npy/Nuclei.csv \
  --channels DNA,PH3 \
  --out benchmark/results/cellprofiler-run-426-npy/Objects.long.csv
```

Materialize MorphoJet's long output back into a CellProfiler-style per-object wide CSV when validating downstream workflow fit for the supported subset:

```bash
python3 benchmark/materialize_morphojet_cellprofiler_wide.py \
  --objects benchmark/results/cellbindb/oracle-full/morphojet/Objects.csv \
  --object-set Cells \
  --channels Intensity \
  --out benchmark/results/cellbindb/oracle-full/morphojet/Cells.wide.csv

python3 benchmark/compare_cellprofiler_wide_subset.py \
  benchmark/results/cellbindb/oracle-full/cellprofiler/Cells.csv \
  benchmark/results/cellbindb/oracle-full/morphojet/Cells.wide.csv \
  --out benchmark/results/cellbindb/oracle-full/workflow_bridge.md \
  --json-out benchmark/results/cellbindb/oracle-full/workflow_bridge.json \
  --fail-on-gap
```

This bridge compares only columns MorphoJet currently emits or can derive without adding new feature semantics. Unsupported CellProfiler columns are reported as ignored, not silently claimed.

For a no-manual-CSV-edit handoff preflight, use a manifest so the same structure can be rerun on real lab handoff files:

```bash
python3 benchmark/validate_handoff_manifest.py benchmark/handoff/cellbindb_supported_columns.json \
  --var base_dir=benchmark/results/cellbindb/oracle-full \
  --require-downstream-check \
  --check-files

python3 benchmark/run_handoff_trial.py benchmark/handoff/cellbindb_supported_columns.json \
  --var base_dir=benchmark/results/cellbindb/oracle-full \
  --out-json benchmark/results/cellbindb/oracle-full/handoff_trial.json \
  --out-md benchmark/results/cellbindb/oracle-full/handoff_trial.md
```

The CellBinDB handoff manifest materializes `Cells.wide.csv`, compares the supported columns to CellProfiler, then runs `benchmark/check_cellprofiler_wide_contract.py` as a downstream contract check.

For an external lab trial, copy `benchmark/handoff/external_lab_template.json`, point `base_dir` at the lab handoff directory, update `object_set`, `channels`, downstream checks, and the `external_evidence` block, then run the validator with `--require-external-evidence` before the same trial runner. Do not use `--allow-external-evidence-placeholders` for a real trial; it exists only so the repository template can be schema-checked before the placeholder values are replaced. Full L4 is not complete until that external manifest runs without manual CSV editing, the generated report records the external evidence fields, rendered manifest snapshot, and artifact provenance hashes, and `python3 benchmark/release_gate.py --external-trial-json path/to/handoff_trial.json --external-trial-root path/to/external` passes with the snapshot schema-valid and all listed artifacts present, non-empty, and hash-matched.

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
6. Validate the handoff manifest and run the manifest-driven handoff trial for the supported CellProfiler-style wide object CSV subset.
7. Write Markdown and JSON parity, workflow-bridge, handoff-trial, impact, and provenance reports.

`benchmark/run.sh` still supports ad hoc runs through `CELLPROFILER_CMD`, but the manifest path is the production validation path.

## ExampleHuman Oracle Smoke

Use the turnkey smoke runner to reproduce the current pinned ExampleHuman path, including CellProfiler mask export, MorphoJet measurement, parity comparison, and an impact-gate report:

```bash
python3 benchmark/run_examplehuman_oracle.py --threads 8
```

When the CellProfiler outputs and Docker metrics already exist, rerun only the MorphoJet/parity/report side with:

```bash
python3 benchmark/run_examplehuman_oracle.py --skip-cellprofiler --threads 8
```

Outputs:

- `benchmark/results/metrics-examplehuman/cellprofiler-examplehuman.metrics.json`
- `benchmark/results/metrics-examplehuman/morphojet-examplehuman.metrics.json`
- `benchmark/results/parity/example-human-objects-parity.md`
- `benchmark/results/impact-examplehuman/summary.md`

The CellProfiler metrics path uses `benchmark/run_docker_metrics.py`, which samples `docker stats` while the named container is running. Short runs can have few RSS samples, so treat this as smoke evidence; the production L3 run should use a larger corpus and longer sampling window.

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

For Dockerized tools, use:

```bash
python3 benchmark/run_docker_metrics.py \
  --name cellprofiler-examplehuman \
  --container-name morphojet-examplehuman-cellprofiler \
  --image cellprofiler/cellprofiler:4.2.6 \
  --platform linux/amd64 \
  --volume "$PWD:/work" \
  --workdir /work \
  --out benchmark/results/metrics-examplehuman \
  --fail-on-nonzero \
  -- cellprofiler -c -r \
    -p benchmark/results/cellprofiler/example-human-masks.cppipe \
    -i benchmark/data/cellprofiler/prepared/ExampleHuman/images \
    -o benchmark/results/cellprofiler-run-426-npy
```
