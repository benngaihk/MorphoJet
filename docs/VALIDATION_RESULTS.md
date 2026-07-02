# Validation Results

Updated: 2026-07-02

## L2 ExampleHuman Oracle Snapshot

This is the first real CellProfiler oracle run. It proves row/schema alignment on a pinned public example, but it does not yet pass the L2 correctness gate.

Environment:

- CellProfiler Docker image: `cellprofiler/cellprofiler:4.2.6`
- CellProfiler examples commit: `4972b59e670a4ae96c3d453803c92eeff378d054`
- Dataset: `ExampleHuman`, 1 image set, CC-0 per upstream README
- Objects: `Cells`, `Cytoplasm`, `Nuclei`
- Channels compared: `DNA`, `PH3`
- MorphoJet commit under test: local run after `fa37e71`

Artifacts:

- CellProfiler long oracle CSV: `benchmark/results/cellprofiler-run-426-npy/Objects.long.csv`
- MorphoJet CSV: `benchmark/results/morphojet-run-426-labels-tiff/Objects.csv`
- Parity report: `benchmark/results/parity/example-human-objects-parity.md`
- Parity JSON: `benchmark/results/parity/example-human-objects-parity.json`

Result:

| Gate | Result |
|---|---:|
| Expected rows | 1734 |
| Actual rows | 1734 |
| Missing rows | 0 |
| Extra rows | 0 |
| Missing columns | 0 |
| Extra columns | 0 |
| Numeric compared | 29478 |
| Numeric failures | 3653 |
| Status | FAIL |

Passing columns:

- `AreaShape_Area`
- `AreaShape_Center_X`
- `AreaShape_Center_Y`
- `AreaShape_BoundingBoxMinimum_X`
- `AreaShape_BoundingBoxMinimum_Y`
- `AreaShape_BoundingBoxMaximum_X`
- `AreaShape_BoundingBoxMaximum_Y`
- `Intensity_MinIntensity`
- `Intensity_MaxIntensity`
- `Intensity_MeanIntensity`
- `Intensity_IntegratedIntensity`
- `AreaShape_Eccentricity`
- `AreaShape_MajorAxisLength`
- `AreaShape_MinorAxisLength`

Remaining mismatches:

| Column | Failures | Max Abs | Max Rel |
|---|---:|---:|---:|
| `Intensity_MedianIntensity` | 185 | 0.013725500786318956 | 0.013725500786318956 |
| `AreaShape_Perimeter` | 1734 | 134.04058453981608 | 0.5 |
| `AreaShape_Solidity` | 1734 | 0.08254269446774187 | 0.08254269446774187 |

Conclusion: L2 is not passed yet. The next compatibility work is exact CellProfiler median, perimeter, and solidity behavior.

## L1 Synthetic Scale Benchmark

These results validate MorphoJet's local release CLI path on deterministic synthetic data. They do not prove CellProfiler parity or industry impact by themselves.

Environment:

- system: `macOS-26.5.1-arm64-arm-64bit`
- machine: `arm64`
- processor: `arm`
- python: `3.11.6`
- threads: `12`
- MorphoJet commit: `c3363d8` plus local validation documentation changes

### 96x96 Images

| Images | Objects | Seconds | Images/s | Objects/s |
|---:|---:|---:|---:|---:|
| 16 | 64 | 0.009671 | 1654.36 | 6617.44 |
| 256 | 1024 | 0.012208 | 20970.43 | 83881.71 |
| 1024 | 4096 | 0.034798 | 29426.77 | 117707.07 |

### 512x512 Images

| Images | Objects | Seconds | Images/s | Objects/s |
|---:|---:|---:|---:|---:|
| 128 | 512 | 0.022137 | 5782.09 | 23128.35 |
| 512 | 2048 | 0.055200 | 9275.36 | 37101.42 |
| 1024 | 4096 | 0.102462 | 9993.95 | 39975.81 |

## Interpretation

L1 is now complete: the release binary can process deterministic synthetic batches at high throughput and produce stable CSV outputs. This is an engineering viability signal.

The industry-impact claim remains unproven until L2-L4 pass:

- L2: CellProfiler oracle parity on a public dataset.
- L3: >=10x speedup and <=50% RSS vs CellProfiler headless on >=1k images.
- L4: external lab workflow replacement.

## Reproduction

```bash
python3 benchmark/run_scale.py --cases 16,256,1024 --width 96 --height 96
python3 benchmark/run_scale.py --cases 128,512,1024 --width 512 --height 512 --out benchmark/results/scale_512
```
