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
