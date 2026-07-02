# Oracle Validation Checklist

This checklist turns MorphoJet's industry-impact claim into a reproducible L2/L3 validation package.

## Candidate Sources

Use public sources first so every result can be reproduced:

- CellProfiler examples and tutorials: https://cellprofiler.org/examples
- CellProfiler documentation: https://cellprofiler-manual.s3.amazonaws.com/
- Cell Painting / JUMP public data for larger follow-up benchmarks: https://jump-cellpainting.broadinstitute.org/
- CellBinDB direct-mask candidate for the first >=1k benchmark: https://zenodo.org/records/15370205
- Nyxus as a high-performance feature extraction reference: https://nyxus.readthedocs.io/

The tracked candidate catalog is `benchmark/cellprofiler/candidates.json`.

Current finding: official CellProfiler examples provide public images and measurement pipelines, but the inspected candidates segment objects inside CellProfiler and do not provide pre-existing label masks. They are useful public oracle candidates only after a mask-export bridge is added, or after a separate public label-mask dataset is selected.

Scan the local pinned examples checkout for measured objects, image counts, and missing label exports:

```bash
python3 benchmark/scan_cellprofiler_examples.py \
  --repo-dir benchmark/data/cellprofiler/examples-repo \
  --md-out benchmark/results/cellprofiler/examples-scan.md \
  --json-out benchmark/results/cellprofiler/examples-scan.json
```

Latest local scan summary:

- 21 pipelines scanned.
- 408 total raw image files across the official examples checkout.
- Best rough image-row upper bound: 90 rows (`ExampleImagingFlowCytometryObjectsInGrid`).
- Largest measured-object candidate by raw images: `ExampleTrackObjects`, 63 raw images and 1 measured object set.
- Conclusion: the official examples are enough for L2 correctness smoke/parity work, but not enough to prove L3 >=1,000 image-row performance/RSS. L3 needs a larger public corpus such as Cell Painting/JUMP or a separately licensed mask dataset.

The current L3 direct-mask target is tracked in `benchmark/cellprofiler/public_corpora.json` and `docs/L3_CORPUS_PLAN.md`.

Fetch a pinned candidate for inspection:

```bash
python3 benchmark/fetch_cellprofiler_examples.py --candidate example-human
```

Verified local preflight:

- `example-human` fetches from `CellProfiler/examples` commit `4972b59e670a4ae96c3d453803c92eeff378d054`.
- It materializes `ExampleHuman.cppipe`, README, and 3 TIFF images.
- Its README states the images are CC-0.
- It remains `m0_status=not_direct` because the pipeline identifies objects internally and does not ship label masks.

Inspect a CellProfiler pipeline for M0 readiness:

```bash
python3 benchmark/inspect_cellprofiler_pipeline.py \
  benchmark/data/cellprofiler/prepared/ExampleHuman/ExampleHuman.cppipe \
  --md-out benchmark/results/cellprofiler/example-human-inspection.md \
  --json-out benchmark/results/cellprofiler/example-human-inspection.json
```

For `ExampleHuman`, the inspector finds measured objects `Nuclei`, `Cells`, and `Cytoplasm`; all currently need label-image export before MorphoJet can run a fair M0 oracle comparison. `PH3` is an image channel measured across those objects.

CI covers the inspector with `benchmark/cellprofiler/fixtures/example_human_minimal.cppipe`.

Generate a patched copy of a CellProfiler pipeline that saves measured objects as TIFF label masks:

```bash
python3 benchmark/export_cellprofiler_masks.py \
  benchmark/data/cellprofiler/prepared/ExampleHuman/ExampleHuman.cppipe \
  --out benchmark/results/cellprofiler/example-human-masks.cppipe \
  --bridge-json benchmark/results/cellprofiler/example-human-masks.json
```

The bridge does not mutate the public pipeline. It appends `ConvertObjectsToImage` modules with label-matrix output plus `SaveImages` modules that write `.npy` masks for missing measured objects, then writes a JSON manifest describing expected mask suffixes. Re-run the inspector against the patched copy:

```bash
python3 benchmark/inspect_cellprofiler_pipeline.py \
  benchmark/results/cellprofiler/example-human-masks.cppipe \
  --fail-if-not-m0-ready
```

After label masks are exported, build a MorphoJet image table with paired image/mask keys:

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

Use `benchmark/build_image_table.py` only for single-object, single-channel ad hoc fixtures.

## L2 Package: Correctness

Required files:

- `benchmark/cellprofiler/VERSION.txt`
- `benchmark/cellprofiler/pipeline.cppipe`
- `benchmark/cellprofiler/images.csv`
- `benchmark/results/cellprofiler/Objects.csv`
- `benchmark/results/morphojet/Objects.csv`
- `benchmark/results/parity/objects_parity.md`
- `benchmark/results/parity/objects_parity.json`

Checklist:

1. Copy `benchmark/cellprofiler/manifest.example.json` to a real manifest.
2. Use pinned Docker image `cellprofiler/cellprofiler:4.2.6` unless intentionally updating the oracle baseline.
3. Select a public image/mask corpus with clear license and download URL.
4. Run the manifest-driven oracle benchmark:

```bash
python3 benchmark/run_oracle_benchmark.py benchmark/cellprofiler/manifest.json
```

5. The runner requires manifests to declare `dataset.m0_status: "direct"`; export label masks or select a direct mask dataset first.
6. Record every mismatch in `docs/PARITY.md`.

Pass condition:

- 100% object count parity.
- >=99% core numeric parity within documented tolerance.
- Parity keys include `ImageNumber,ObjectSet,ObjectNumber,Channel` for multi-object pipelines.

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
  --parity-json benchmark/results/parity/objects_parity.json \
  --cellprofiler-metrics-json benchmark/results/metrics/cellprofiler.metrics.json \
  --morphojet-metrics-json benchmark/results/metrics/morphojet.metrics.json \
  --fail-on-gap
```

Pass condition:

- >=10x wall-clock speedup.
- MorphoJet peak RSS <=50% of CellProfiler.

Current full L3 result:

- Dataset: CellBinDB direct-mask benchmark.
- Image rows: 1,044.
- Object rows: 107,936.
- Object count parity: 100%.
- Core numeric parity: 100%.
- Wall-clock speedup: 701.66x.
- Peak RSS ratio: 11.72%.
- Artifact: `benchmark/results/cellbindb/oracle-full/impact.md`.

## L4 Package: Workflow Fit

The first workflow-fit preflight is a manifest-driven handoff trial for MorphoJet output:

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

The CellBinDB preflight manifest runs three no-manual-edit steps:

1. Materialize MorphoJet `Objects.csv` into `Cells.wide.csv`.
2. Compare supported wide columns against CellProfiler `Cells.csv`.
3. Validate the downstream CSV contract with `benchmark/check_cellprofiler_wide_contract.py`.

The repository also includes `benchmark/handoff/external_lab_template.json` as the starting manifest for real lab handoff files. It is schema-validated by the release gate, but it is not L4 evidence until it is copied, filled with real paths/checks, and executed on an external lab workflow.

Current handoff preflight result:

- Rows: 107,936 CellProfiler rows and 107,936 MorphoJet wide rows.
- Compared columns: 28.
- Numeric comparisons: 3,022,208.
- Numeric failures: 0.
- Ignored CellProfiler columns: 22 unsupported columns are reported as out of scope.
- Contract columns: 30 required columns.
- Duplicate keys: 0.
- Empty keys: 0.

Pass condition for full L4 remains stricter: an external lab batch workflow must consume MorphoJet's input table and CellProfiler-style CSV outputs without manual CSV editing.

## Claim Language

Allowed for the CellBinDB direct-mask benchmark after L2 and L3 pass:

> MorphoJet is 10x faster than CellProfiler headless on this reproducible measurement-only benchmark while matching the tested measurement subset within documented tolerance.

Not allowed before L2 and L3 pass:

> MorphoJet replaces CellProfiler.
> MorphoJet is better than Nyxus.
> MorphoJet is generally faster for microscopy analysis.
