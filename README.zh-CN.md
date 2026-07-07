# MorphoJet

[English README](README.md)

MorphoJet 是面向显微图像批量测量的高速命令行工具，目标是兼容一部分 CellProfiler 风格的数据交付流程。

MorphoJet 目前不是 CellProfiler 的替代品。CellProfiler 仍然是 pipeline 设计和完整特性行为的基准；MorphoJet 当前聚焦于把稳定的、只做测量的批处理任务跑得更快，并降低部署和交付摩擦。

## 当前范围

M0 支持一条刻意收窄的路径：

- Rust `image` crate 可读取的 2D 强度图像，包括常见 TIFF 文件。
- 已有 label mask，其中 `0` 是背景，正整数 label 是对象。
- Image table CSV，包含 `ImageNumber`、`ImagePath`、`MaskPath`，可选 `Channel` 和元数据列。
- 输出 `Image.csv` 和 `Objects.csv`。
- 已存在的输出默认受保护，只有传入 `--overwrite` 才会覆盖。
- 会拒绝重复表头，以及与 MorphoJet 输出保留列冲突的元数据列，例如 `Count_Objects`、`Width`、`Height`。

暂不支持：

- GUI。
- 完整 `.cppipe` 解析。
- 分割、阈值、照明校正、追踪、3D、WSI 或 OME-Zarr。
- 完整 CellProfiler 特性等价。

## 快速开始

```bash
cargo run -p morphojet -- measure \
  --images images.csv \
  --out measurements \
  --threads 16 \
  --cellprofiler-compatible \
  --summary-json measurements/run-summary.json \
  --overwrite
```

`images.csv` 示例：

```csv
ImageNumber,ImagePath,MaskPath,Channel,Plate,Well,Site
1,images/A01_s1_DAPI.tif,masks/A01_s1_cells.tif,DAPI,P001,A01,1
2,images/A01_s1_CD3.tif,masks/A01_s1_cells.tif,CD3,P001,A01,1
```

## 诊断与可观测性

```bash
morphojet doctor
```

`doctor` 会输出版本、commit、平台、线程和可执行文件路径，方便复现实验和问题报告。

批处理监控可以使用 `measure --summary-json path/to/run-summary.json`。它会在成功测量后写入机器可读的运行摘要，包括版本、commit、平台、耗时、图像行数、对象行数、观测到的 channel/object set、输出路径、兼容模式和有效线程数。

失败监控可以使用 `measure --error-json path/to/error.json`。它会在参数解析之后的非零退出中写入机器可读失败报告，包括版本、commit、命令、稳定错误码、顶层错误信息和 cause chain，同时保留面向人的 stderr。

## 基准与验证

烟雾基准：

```bash
python3 corpus/generate_smoke.py --images 16
benchmark/run.sh benchmark/data/smoke/images.csv benchmark/results/smoke
python3 benchmark/summarize.py benchmark/results/smoke
```

真实 CellProfiler oracle 基准见 [docs/BENCHMARK.md](docs/BENCHMARK.md)。

发布候选前的完整门禁：

```bash
python3 benchmark/release_gate.py --require-clean-git --require-l3-provenance --run-l3 --build-release-artifact --release-version rc-preflight
```

快速审计已生成的 L3 产物：

```bash
python3 benchmark/release_gate.py
```

Release-gate JSON 和 Markdown 报告会记录运行时间、git commit、工作区是否 dirty、调用参数、顶层 `production_claim_status` 和 `missing_or_failed_checks`。在真实外部 L4 workflow trial、匹配 evidence package、外部 trial/package saved reviewer reports、稳定 GitHub release、以及 saved stable-release verifier report 都进入同一份生产声明门禁之前，`production_claim_status` 应保持 `INCOMPLETE`。

审查已保存的 release-gate JSON：

```bash
python3 benchmark/verify_release_gate_report.py benchmark/results/release-gate/report.json
python3 benchmark/verify_release_gate_report.py benchmark/results/release-gate/report.json --verify-git-commit
python3 benchmark/verify_release_gate_report.py benchmark/results/release-gate/production-claim.json --require-report-pass --require-clean-git-metadata --verify-git-commit --require-production-claim-pass
```

## 发布验证

打 `v*` tag 后，GitHub Actions 会构建 macOS 和 Linux CLI archive，并发布 SHA-256 checksum。

本地验证 release archive 形状：

```bash
python3 benchmark/release_gate.py --build-release-artifact --release-version local
```

验证已发布的 GitHub release candidate：

```bash
python3 benchmark/release_gate.py --verify-github-release v0.1.0-rc.1
```

外部 workflow evidence 通过后，再验证稳定非 RC release：

```bash
python3 benchmark/release_gate.py --verify-github-release v0.1.0 --github-release-kind stable
```

GitHub release verifier 会检查 tag 身份、release URL、GitHub release ID/API 身份、作者、target commit-ish、UTC 时间戳、draft/prerelease/immutable 状态、稳定 semver tag、发布资产集合、下载文件 checksum、archive 内容，并要求当前机器兼容的 archive 能通过 `morphojet doctor` 且 commit 前缀匹配。复核 saved report 时可用 `--expect-repo benngaihk/MorphoJet` 防止其他仓库的 release 报告进入签核链。

## CellProfiler 风格宽表导出

MorphoJet 原生 `Objects.csv` 是长表，键为 `ImageNumber`、`ObjectSet`、`ObjectNumber` 和 `Channel`。如果下游工具需要 CellProfiler object CSV，例如 `Cells.csv`，可以把当前支持的测量子集物化为宽表：

```bash
python3 benchmark/materialize_morphojet_cellprofiler_wide.py \
  --objects measurements/Objects.csv \
  --object-set Cells \
  --channels DNA,PH3 \
  --out measurements/Cells.wide.csv
```

对照 CellProfiler object CSV 验证支持列：

```bash
python3 benchmark/compare_cellprofiler_wide_subset.py CellProfiler/Cells.csv measurements/Cells.wide.csv --fail-on-gap
```

## 外部 L4 试验与生产门禁

真实实验室交付从模板开始：

```bash
python3 benchmark/prepare_external_l4_trial.py --workspace path/to/external-trial
```

生成的 workspace 包含模板 manifest、输入目录和一组按顺序执行的命令：plan 验证、manifest 验证、readiness、readiness 报告复核、trial 运行、evidence package、local preflight、local preflight 报告复核、stable release 验证、saved stable release 报告复核、final production gate、final production report 复核。

在真实 trial 前，先运行 readiness：

```bash
python3 benchmark/check_external_l4_readiness.py \
  --workspace path/to/external-trial \
  --json-out path/to/external-trial/readiness.json
```

真实 L4 run 必须填完整 `external_evidence`，包括非占位 acceptance criteria、reviewer 身份或角色、UTC review 时间和 signoff statement，并使用 `--require-external-evidence`：

```bash
python3 benchmark/run_handoff_trial.py path/to/external-trial/external_lab_template.json \
  --var base_dir=path/to/external-trial \
  --readiness-report path/to/external-trial/readiness.json \
  --require-external-evidence \
  --out-json path/to/external-trial/handoff_trial.json \
  --out-md path/to/external-trial/handoff_trial.md
```

外部 trial 通过后，生成 evidence package：

```bash
python3 benchmark/package_external_trial.py \
  --trial-json path/to/external-trial/handoff_trial.json \
  --trial-root path/to/external-trial \
  --out-dir path/to/evidence-packages
```

稳定 release 存在后，用 production wrapper 把所有必需证据绑定到同一份最终报告：

```bash
python3 benchmark/run_production_gate.py \
  --external-trial-json path/to/external-trial/handoff_trial.json \
  --external-trial-root path/to/external-trial \
  --external-evidence-package-dir path/to/evidence-packages/external-l4-trial \
  --external-trial-verification-report path/to/external-trial/trial-verification.json \
  --external-evidence-package-verification-report path/to/evidence-packages/package-verification.json \
  --github-release-verification-report path/to/github-release/verification.json \
  --github-release-tag v0.1.0
```

这个 wrapper 要求稳定非 RC tag，复核外部 trial/package reviewer 报告，要求 saved GitHub release verifier report 是同一 final tag 和 `benngaihk/MorphoJet` repo 的 stable PASS 报告，并委托 `benchmark/release_gate.py --require-production-claim`。最终生产声明现在会把 saved trial/package reviewer reports 和 saved stable-release verifier report 作为独立审计项；生成的 trial plan 还会在 final gate 后复核 `production-claim.json`，要求 `--require-production-claim-pass` 和 `--expect-missing-checks none`。direct release gate 复核 saved GitHub release report 时也会带上 `--expect-repo benngaihk/MorphoJet`。它通过之前，项目不能宣称 production-ready。

## 当前里程碑状态

当前代码已经具备：

- L3 public direct-mask benchmark PASS。
- 已验证的 `v0.1.0-rc.1` prerelease。
- L4-preflight handoff harness。
- 外部 L4 trial、evidence package、local evidence preflight、GitHub release saved-report verification、final production gate 和 final report verification 的审计脚手架。

仍未完成最终生产声明：

- 真实外部 L4 workflow trial。
- 匹配的外部 L4 evidence package。
- 外部 L4 trial/package saved reviewer reports。
- live stable GitHub release。
- saved stable-release verifier report。

更多状态见：

- [docs/VALIDATION_RESULTS.md](docs/VALIDATION_RESULTS.md)
- [docs/PRODUCTION_READINESS.md](docs/PRODUCTION_READINESS.md)
- [docs/INDUSTRY_VALIDATION.md](docs/INDUSTRY_VALIDATION.md)
- [docs/M0_STATUS.md](docs/M0_STATUS.md)
- [docs/PARITY.md](docs/PARITY.md)
