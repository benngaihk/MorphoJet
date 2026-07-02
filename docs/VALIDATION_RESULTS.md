# Validation Results

Updated: 2026-07-02

## L2 ExampleHuman Oracle Snapshot

This is the first real CellProfiler oracle run. It passes the L2 correctness gate for the current measurement subset on a pinned public example.

Environment:

- CellProfiler Docker image: `cellprofiler/cellprofiler:4.2.6`
- CellProfiler examples commit: `4972b59e670a4ae96c3d453803c92eeff378d054`
- Dataset: `ExampleHuman`, 1 image set, CC-0 per upstream README
- Objects: `Cells`, `Cytoplasm`, `Nuclei`
- Channels compared: `DNA`, `PH3`
- MorphoJet commit under test: local run after `4c8313a` plus local parity fixes

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
| Numeric failures | 0 |
| Status | PASS |

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
- `Intensity_MedianIntensity`
- `Intensity_IntegratedIntensity`
- `AreaShape_Perimeter`
- `AreaShape_Eccentricity`
- `AreaShape_MajorAxisLength`
- `AreaShape_MinorAxisLength`
- `AreaShape_Solidity`

Max residual numeric differences are floating-point noise only:

| Column | Max Abs | Max Rel |
|---|---:|---:|
| `Intensity_IntegratedIntensity` | 0.000003457300295 | 0.00000004176837204 |
| `AreaShape_MajorAxisLength` | 0.00000000006598988023 | 0.000000000006470431086 |
| `AreaShape_Solidity` | 0.00000000004982936286 | 0.00000000004982936286 |

Conclusion: L2 passes for ExampleHuman and the current measurement subset. Production-grade status remains unproven until L3 performance/RSS and a larger public corpus pass.

## L3 ExampleHuman Smoke

This run exercises the same pinned ExampleHuman oracle path with elapsed-time and peak-RSS capture for both tools. It is a smoke benchmark, not the production L3 gate, because the dataset only materializes 6 MorphoJet image rows. The production L3 claim still requires >=1,000 real/public image rows.

Environment:

- CellProfiler Docker image: `cellprofiler/cellprofiler:4.2.6`
- CellProfiler platform: `linux/amd64`
- CellProfiler examples commit: `4972b59e670a4ae96c3d453803c92eeff378d054`
- Dataset: `ExampleHuman`, 1 image set, 3 object sets, 2 channels
- MorphoJet command: `target/release/morphojet measure --threads 8 --cellprofiler-compatible`
- CellProfiler RSS source: `docker stats MemUsage sampled during container run`
- MorphoJet RSS source: local process `ru_maxrss` captured by `benchmark/run_command_metrics.py`

Artifacts:

- Runner: `benchmark/run_examplehuman_oracle.py`
- Docker metrics wrapper: `benchmark/run_docker_metrics.py`
- CellProfiler metrics: `benchmark/results/metrics-examplehuman/cellprofiler-examplehuman.metrics.json`
- MorphoJet metrics: `benchmark/results/metrics-examplehuman/morphojet-examplehuman.metrics.json`
- Gate report: `benchmark/results/impact-examplehuman/summary.md`
- Gate JSON: `benchmark/results/impact-examplehuman/summary.json`

Result:

| Gate | Required | Observed | Status |
|---|---:|---:|---:|
| Scale | >=1000 image rows | 6 | FAIL |
| Object count parity | 100% | 100.0000% | PASS |
| Core numeric parity | >=99% | 100.0000% | PASS |
| Wall-clock speedup | >=10x | 196.74x | PASS |
| Peak RSS ratio | <=50% | 6.89% | PASS |

Raw metrics:

| Tool | Seconds | Peak RSS MB | Notes |
|---|---:|---:|---|
| CellProfiler | 7.191819 | 556.900 | Docker stats, 3 samples |
| MorphoJet | 0.036554 | 38.344 | Local release binary |

Conclusion: this is a strong smoke signal for the ExampleHuman path, but the overall L3 industry-impact gate remains FAIL until the same criteria pass on a >=1,000 image-row public benchmark with stronger memory sampling.

## CellBinDB MorphoJet-Only Scale Preflight

This is not an L3 PASS because it has no CellProfiler oracle/parity result yet. It proves the next public direct-mask corpus is downloaded, verified, tabled, and readable by MorphoJet at >=1,000 image rows.

Environment:

- Source: Zenodo record `15370205`, `CellBinDB.zip`
- License: Zenodo record reports `cc-zero`; bundled source licenses are listed in `mixed_licenses.txt`
- Archive size: 285,956,212 bytes
- MD5: `e770f1287619eb45e74d131430e20fe5`
- Image/mask layout: `*-img.tif`, `*-instancemask.tif`, `*-mask.tif`
- MorphoJet command: `target/release/morphojet measure --threads 8 --cellprofiler-compatible`

Result:

| Metric | Value |
|---|---:|
| Complete sample groups | 1,044 |
| MorphoJet image rows | 1,044 |
| MorphoJet object rows | 107,936 |
| Elapsed seconds | 0.879788 |
| Peak RSS MB | 89.875 |
| Gate status | PREFLIGHT ONLY |

Conclusion: CellBinDB is a viable L3 corpus candidate for the MorphoJet side. The remaining blocking item is a CellProfiler measurement-only oracle pipeline for the same `*-instancemask.tif` labels.

## CellBinDB Oracle Smoke

This is an 8-row CellProfiler oracle smoke for the CellBinDB direct-mask path. It proves the measurement-only CellProfiler pipeline can read `*-instancemask.tif` labels as objects, and that MorphoJet's CellProfiler-compatible compact object numbering matches the oracle on the tested subset.

Artifacts:

- Pipeline generator: `benchmark/build_cellbindb_cellprofiler_pipeline.py`
- Turnkey runner: `benchmark/run_cellbindb_oracle.py`
- Pipeline artifact: `benchmark/results/cellbindb/cellbindb-direct-mask.cppipe`
- CellProfiler output: `benchmark/results/cellbindb/cellprofiler-smoke/Cells.csv`
- MorphoJet output: `benchmark/results/cellbindb/morphojet-smoke/Objects.csv`
- Parity report: `benchmark/results/cellbindb/parity-smoke.md`
- Parity JSON: `benchmark/results/cellbindb/parity-smoke.json`

Result:

| Gate | Result |
|---|---:|
| Image rows | 8 |
| Expected object rows | 590 |
| Actual object rows | 590 |
| Missing rows | 0 |
| Extra rows | 0 |
| Numeric compared | 10,030 |
| Numeric failures | 0 |
| CellProfiler seconds | 7.168250 |
| MorphoJet seconds | 0.016173 |
| Speedup | 443.22x |
| CellProfiler peak RSS MB | 359.600 |
| MorphoJet peak RSS MB | 18.062 |
| RSS ratio | 5.02% |
| Status | PASS |

Conclusion: the L3 candidate now has a proven small CellProfiler oracle path. Production L3 remains unproven until the same runner passes on all 1,044 rows with CellProfiler/MorphoJet elapsed time and RSS metrics.

## L3 CellBinDB Benchmark

This is the first >=1,000 image-row public direct-mask CellProfiler oracle benchmark. It supports the narrow L3 claim for the tested measurement subset: MorphoJet matches CellProfiler object rows and core measurements on this reproducible benchmark while running much faster and with lower peak RSS.

Environment:

- Source: Zenodo record `15370205`, `CellBinDB.zip`
- Dataset rows: 1,044 image rows
- Object rows: 107,936
- CellProfiler Docker image: `cellprofiler/cellprofiler:4.2.6`
- CellProfiler platform: `linux/amd64`
- MorphoJet command: `target/release/morphojet measure --threads 8 --cellprofiler-compatible`
- CellProfiler RSS source: `docker stats MemUsage sampled during container run`
- MorphoJet RSS source: local process `ru_maxrss` captured by `benchmark/run_command_metrics.py`

Artifacts:

- Turnkey runner: `benchmark/run_cellbindb_oracle.py`
- CellProfiler pipeline generator: `benchmark/build_cellbindb_cellprofiler_pipeline.py`
- Image table: `benchmark/results/cellbindb/oracle-full/images.csv`
- CellProfiler long oracle: `benchmark/results/cellbindb/oracle-full/cellprofiler/Objects.long.csv`
- MorphoJet output: `benchmark/results/cellbindb/oracle-full/morphojet/Objects.csv`
- Parity report: `benchmark/results/cellbindb/oracle-full/parity.md`
- Impact report: `benchmark/results/cellbindb/oracle-full/impact.md`

Result:

| Gate | Required | Observed | Status |
|---|---:|---:|---:|
| Scale | >=1000 image rows | 1044 | PASS |
| Object count parity | 100% | 100.0000% | PASS |
| Core numeric parity | >=99% | 100.0000% | PASS |
| Wall-clock speedup | >=10x | 629.54x | PASS |
| Peak RSS ratio | <=50% | 11.84% | PASS |

Raw metrics:

| Tool | Seconds | Peak RSS MB |
|---|---:|---:|
| CellProfiler | 618.794942 | 724.700 |
| MorphoJet | 0.982925 | 85.828 |

Parity:

| Metric | Value |
|---|---:|
| Expected rows | 107,936 |
| Actual rows | 107,936 |
| Missing rows | 0 |
| Extra rows | 0 |
| Numeric compared | 2,590,464 |
| Numeric failures | 0 |

Conclusion: L3 passes for this CellBinDB direct-mask measurement benchmark. This does not prove full CellProfiler replacement, upstream segmentation replacement, or external lab workflow fit; those remain L4/production-readiness work.

## CellBinDB Handoff Preflight Snapshot

This snapshot validates MorphoJet's supported measurement subset in a CellProfiler-style per-object wide CSV shape and runs it through a manifest-driven handoff trial. It is a workflow-fit preflight for downstream tools that expect files such as `Cells.csv`; it does not claim full CellProfiler object CSV feature coverage or external lab replacement.

Artifacts:

- Handoff manifest: `benchmark/handoff/cellbindb_supported_columns.json`
- External lab template: `benchmark/handoff/external_lab_template.json`
- Handoff report: `benchmark/results/cellbindb/oracle-full/handoff_trial.md`
- Handoff JSON: `benchmark/results/cellbindb/oracle-full/handoff_trial.json`
- Contract JSON: `benchmark/results/cellbindb/oracle-full/handoff_contract.json`
- MorphoJet long input: `benchmark/results/cellbindb/oracle-full/morphojet/Objects.csv`
- MorphoJet wide output: `benchmark/results/cellbindb/oracle-full/morphojet/Cells.wide.csv`
- CellProfiler oracle CSV: `benchmark/results/cellbindb/oracle-full/cellprofiler/Cells.csv`
- Bridge report: `benchmark/results/cellbindb/oracle-full/workflow_bridge.md`
- Bridge JSON: `benchmark/results/cellbindb/oracle-full/workflow_bridge.json`
- Handoff runner: `benchmark/run_handoff_trial.py`
- Handoff manifest validator: `benchmark/validate_handoff_manifest.py`
- Materializer: `benchmark/materialize_morphojet_cellprofiler_wide.py`
- Comparator: `benchmark/compare_cellprofiler_wide_subset.py`
- Contract checker: `benchmark/check_cellprofiler_wide_contract.py`

Result:

| Gate | Result |
|---|---:|
| Handoff trial steps | 3 |
| CellBinDB manifest schema | PASS |
| External lab template schema | PASS |
| CellProfiler rows | 107,936 |
| MorphoJet wide rows | 107,936 |
| Missing rows | 0 |
| Extra rows | 0 |
| Compared columns | 31 |
| Ignored CellProfiler columns | 19 |
| Unsupported MorphoJet columns | 0 |
| Numeric compared | 3,346,016 |
| Numeric failures | 0 |
| Required contract columns | 33 |
| Duplicate keys | 0 |
| Empty keys | 0 |
| Status | PASS |

Compared columns include supported area/center/bounding-box/perimeter/eccentricity/axis/solidity fields, derived `ConvexArea`, `EquivalentDiameter`, and `Extent`, `Location_Center_X/Y`, `Number_Object_Number`, channel-suffixed intensity fields including quartiles, population standard deviation, and median absolute deviation, plus channel-suffixed center-of-mass intensity locations. Ignored CellProfiler columns include feature families MorphoJet does not yet emit, such as edge intensity, Feret diameter, compactness, orientation, and max-intensity locations.

Conclusion: this removes one CSV-shape and handoff-automation blocker for workflow trials on the supported subset. L4 remains incomplete until an external lab workflow consumes these files without manual CSV editing.

## Local Release Artifact Preflight

This preflight validates the local release archive shape before a GitHub `v*` tag builds macOS/Linux release assets.

Artifacts:

- Builder: `benchmark/build_release_archive.py`
- Verifier: `benchmark/verify_release_archive.py`
- Release gate flag: `python3 benchmark/release_gate.py --build-release-artifact --release-version local`
- Local archive: `benchmark/results/release-artifacts/morphojet-local-macos-arm64.tar.gz`
- Checksum: `benchmark/results/release-artifacts/morphojet-local-macos-arm64.tar.gz.sha256`
- Verification JSON: `benchmark/results/release-artifacts/verification.json`

Result:

| Gate | Result |
|---|---:|
| Archive contains `morphojet` | PASS |
| Archive contains `README.md` | PASS |
| Archive contains `LICENSE` | PASS |
| SHA-256 verification | PASS |
| Packaged `morphojet doctor` smoke | PASS |
| Packaged commit matches HEAD | PASS |
| Local platform | macOS arm64 |
| SHA-256 | Recorded in `benchmark/results/release-artifacts/verification.json` |

Conclusion: local release artifact shape is validated. Production release evidence still requires a tagged GitHub release with published macOS and Linux archives and checksums.

## GitHub Release Candidate Snapshot

This snapshot validates the first tagged GitHub prerelease artifact set.

Artifacts:

- Tag: `v0.1.0-rc.1`
- Release URL: `https://github.com/benngaihk/MorphoJet/releases/tag/v0.1.0-rc.1`
- GitHub Actions run: `28576021744`
- Verifier: `benchmark/verify_github_release.py`
- Release gate command: `python3 benchmark/release_gate.py --verify-github-release v0.1.0-rc.1`
- Verification JSON: `benchmark/results/github-release/v0.1.0-rc.1/verification.json`

Result:

| Gate | Result |
|---|---:|
| Release is marked prerelease | PASS |
| Asset count | 4 |
| Linux archive checksum | PASS |
| macOS archive checksum | PASS |
| Linux archive contains `morphojet`, `README.md`, `LICENSE` | PASS |
| macOS archive contains `morphojet`, `README.md`, `LICENSE` | PASS |
| macOS packaged `morphojet doctor` smoke | PASS |
| Packaged commit matches tag commit `e7d0b6a5b44b` | PASS |

Conclusion: the release workflow can publish verifiable Linux and macOS archives for a tagged release candidate. This satisfies the RC artifact gate; stable release still waits on external workflow-fit evidence.

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

The broad industry-impact claim remains unproven until the remaining L4 gate passes:

- L4: external lab workflow replacement.

## Reproduction

```bash
python3 benchmark/run_scale.py --cases 16,256,1024 --width 96 --height 96
python3 benchmark/run_scale.py --cases 128,512,1024 --width 512 --height 512 --out benchmark/results/scale_512
python3 benchmark/run_examplehuman_oracle.py --threads 8
```
