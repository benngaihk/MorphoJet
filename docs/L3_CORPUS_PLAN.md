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

## Next Implementation Gates

1. Inspect the archive layout without committing data files.
2. Build a CellBinDB image/mask table generator.
3. Build a CellProfiler measurement-only oracle pipeline that consumes existing masks as objects.
4. Run a small subset first to prove row identity and parity.
5. Run the full >=1,000 image-row benchmark with the existing metrics wrappers.

## Claim Boundary

Do not claim production-grade or broad industry improvement until CellBinDB or an equivalent >=1,000 public direct-mask corpus passes:

- 100% object count parity.
- >=99% core numeric parity.
- >=10x wall-clock speedup.
- Peak RSS <=50% of CellProfiler on the same machine.
