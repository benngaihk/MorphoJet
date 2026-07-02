# L3 Corpus Plan

Updated: 2026-07-02

## Current Decision

The official CellProfiler examples are now proven too small for the L3 gate. The next L3 candidate is CellBinDB from Zenodo record `15370205`.

Why CellBinDB:

- The record describes 1,044 annotated microscope images and 109,083 cell annotations.
- The record includes semantic and instance masks.
- The record license is CC0, with `mixed_licenses.txt` covering bundled third-party datasets.
- `CellBinDB.zip` is 286 MB with MD5 `e770f1287619eb45e74d131430e20fe5`.
- The scale is just above the required >=1,000 public image-row threshold, so it is a better next gate than repeating ExampleHuman.

Source:

- `https://zenodo.org/records/15370205`

## Reproduction Scaffold

Fetch metadata only:

```bash
python3 benchmark/fetch_zenodo_file.py \
  --record 15370205 \
  --file CellBinDB.zip \
  --metadata-out benchmark/results/cellbindb/metadata.json \
  --metadata-only
```

Download and verify the archive:

```bash
python3 benchmark/fetch_zenodo_file.py \
  --record 15370205 \
  --file CellBinDB.zip \
  --out-dir benchmark/data/cellbindb \
  --metadata-out benchmark/results/cellbindb/metadata.json \
  --skip-existing
```

Inspect and prepare a small MorphoJet smoke table:

```bash
python3 benchmark/prepare_cellbindb.py \
  --zip benchmark/data/cellbindb/CellBinDB.zip \
  --extract-dir benchmark/data/cellbindb/extracted-smoke \
  --out benchmark/results/cellbindb/images-smoke.csv \
  --summary-json benchmark/results/cellbindb/summary-smoke.json \
  --limit 8 \
  --extract \
  --overwrite
```

Prepare the full >=1,000 row image table after the archive has been verified:

```bash
python3 benchmark/prepare_cellbindb.py \
  --zip benchmark/data/cellbindb/CellBinDB.zip \
  --extract-dir benchmark/data/cellbindb/extracted \
  --out benchmark/results/cellbindb/images.csv \
  --summary-json benchmark/results/cellbindb/summary.json \
  --extract \
  --overwrite
```

Build the CellProfiler measurement-only pipeline for the same direct masks:

```bash
python3 benchmark/build_cellbindb_cellprofiler_pipeline.py \
  --out benchmark/results/cellbindb/cellbindb-direct-mask.cppipe
```

Run the turnkey 8-row CellProfiler oracle smoke:

```bash
python3 benchmark/run_cellbindb_oracle.py --limit 8 --run-name smoke --threads 8
```

Run the full candidate L3 benchmark:

```bash
python3 benchmark/run_cellbindb_oracle.py --threads 8
```

Run MorphoJet on the full direct-mask table:

```bash
python3 benchmark/run_command_metrics.py \
  --name morphojet-cellbindb-full \
  --out benchmark/results/cellbindb \
  --fail-on-nonzero \
  -- target/release/morphojet measure \
    --images benchmark/results/cellbindb/images.csv \
    --out benchmark/results/cellbindb/morphojet-full \
    --threads 8 \
    --cellprofiler-compatible \
    --overwrite
```

## Local Preflight Results

Verified locally on 2026-07-02:

| Check | Result |
|---|---:|
| Zenodo metadata fetch | PASS |
| `CellBinDB.zip` download | PASS |
| MD5 verification | PASS |
| ZIP sample groups | 1,044 complete groups |
| Image files | 1,044 `*-img.tif` |
| Instance masks | 1,044 `*-instancemask.tif` |
| Semantic masks | 1,044 `*-mask.tif` |
| MorphoJet image rows | 1,044 |
| MorphoJet object rows | 107,936 |
| MorphoJet elapsed seconds | 0.879788 |
| MorphoJet peak RSS MB | 89.875 |

Stain breakdown from the generated table:

| Stain | Rows |
|---|---:|
| DAPI | 303 |
| HE | 405 |
| mIF | 60 |
| ssDNA | 276 |

This is a MorphoJet-side scale preflight only. It does not prove L3 until CellProfiler reads the same direct masks as objects, emits the same measurement subset, and passes parity plus speed/RSS gates.

Verified CellProfiler oracle smoke:

| Metric | Value |
|---|---:|
| Image rows | 8 |
| Object rows | 590 |
| CellProfiler direct-mask pipeline | PASS |
| MorphoJet compact ObjectNumber mode | PASS |
| Parity missing rows | 0 |
| Parity extra rows | 0 |
| Numeric failures | 0 |
| CellProfiler smoke seconds | 7.168250 |
| CellProfiler smoke peak RSS MB | 359.600 |
| MorphoJet smoke seconds | 0.016173 |
| MorphoJet smoke peak RSS MB | 18.062 |
| Smoke speedup | 443.22x |
| Smoke RSS ratio | 5.02% |

The smoke confirms that CellProfiler `ConvertImageToObjects` must use compact labels (`Preserve original labels: No`) for parity with `morphojet measure --cellprofiler-compatible`.

Verified full L3 candidate:

| Gate | Required | Observed | Status |
|---|---:|---:|---:|
| Scale | >=1000 image rows | 1044 | PASS |
| Object count parity | 100% | 100.0000% | PASS |
| Core numeric parity | >=99% | 100.0000% | PASS |
| Wall-clock speedup | >=10x | 707.94x | PASS |
| Peak RSS ratio | <=50% | 11.65% | PASS |

Raw full-run metrics:

| Tool | Seconds | Peak RSS MB |
|---|---:|---:|
| CellProfiler | 602.903886 | 723.700 |
| MorphoJet | 0.851634 | 84.328 |

## Next Implementation Gates

1. Inspect the archive layout without committing data files.
2. Build a CellBinDB image/mask table generator.
3. Promote the full L3 command into a CI/nightly or release validation job.
4. Prepare an external lab workflow trial for L4.

## Claim Boundary

Do not claim production-grade or broad industry improvement until CellBinDB or an equivalent >=1,000 public direct-mask corpus passes:

- 100% object count parity.
- >=99% core numeric parity.
- >=10x wall-clock speedup.
- Peak RSS <=50% of CellProfiler on the same machine.
