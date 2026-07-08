# MorphoJet

语言：[English](README.md) | 简体中文

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
把公开数据源推进到 oracle 路径之前，先生成非最终的候选集 triage 报告，方便中文社区 reviewer 复核为什么某个数据源能进入或还不能进入 M0 direct-mask 合同：

```bash
python3 benchmark/triage_oracle_candidates.py \
  --json-out benchmark/results/cellprofiler/oracle-candidate-triage.json \
  --md-out benchmark/results/cellprofiler/oracle-candidate-triage.md
```

这个报告会写入 `claim_status=NOT_PRODUCTION_CLAIM`、`evidence_scope=ORACLE_CANDIDATE_TRIAGE`、`final_production_signoff=false`。它会把仍需导出 label masks 的官方 CellProfiler examples，与 CellBinDB 这类仍需检查文件布局、license、mask background=0 和正整数 instance labels 的 direct-mask 候选分开，不能被当作最终生产签核。

对 CellBinDB，可以把这一步推进成保存下来的 direct-mask 合同检查报告：

```bash
python3 benchmark/inspect_cellbindb_direct_masks.py \
  --full \
  --verify-md5 \
  --require-pass \
  --json-out benchmark/results/cellbindb/direct-mask-inspection.json \
  --md-out benchmark/results/cellbindb/direct-mask-inspection.md
```

这个报告同样是非最终证据，会写入 `claim_status=NOT_PRODUCTION_CLAIM`、`evidence_scope=CELLBINDB_DIRECT_MASK_INSPECTION`、`final_production_signoff=false`。它会检查 archive size/checksum 元数据、image 与 instance-mask 配对数量、尺寸一致、背景 label `0`、正整数 labels，以及 source/license 元数据，然后才把 CellBinDB 作为 direct-mask oracle 输入。`benchmark/release_gate.py` 也会把同一套 full + MD5 direct-mask inspection 作为标准 gate 运行，所以 L3 release precheck 会在输入 mask 合同漂移时失败。

发布候选前的完整门禁：

```bash
python3 benchmark/release_gate.py --require-clean-git --require-l3-provenance --run-l3 --build-release-artifact --release-version rc-preflight
```

快速审计已生成的 L3 产物：

```bash
python3 benchmark/release_gate.py
```

Release-gate JSON 和 Markdown 报告会记录运行时间、git commit、工作区是否 dirty、调用参数、顶层 `claim_status`、`evidence_scope`、`final_production_signoff`、`production_claim_status` 和 `missing_or_failed_checks`；JSON 还会写入 `production_claim_checklist`，Markdown 报告会渲染同一份 checklist，把每个 audit check 对应到必须提交的 evidence 和 reviewer 下一步动作。非最终报告会标记为 `claim_status=NOT_PRODUCTION_CLAIM`、`evidence_scope=RELEASE_GATE_PRECHECK`、`final_production_signoff=false`；只有带 `--require-production-claim`、整体 PASS、且 production audit 完整通过的报告，才会标记为 `claim_status=FINAL_PRODUCTION_CLAIM`、`evidence_scope=FINAL_PRODUCTION_RELEASE_GATE`、`final_production_signoff=true`。标准 gate 集合包含 full CellBinDB direct-mask inspection、已有 L3 artifacts、workflow bridge artifacts 和 handoff trial artifacts。Saved report verifier 会拒绝缺失或被篡改的 checklist rows 和 claim-scope labels。Claim-language guard 也会默认扫描顶层 Markdown、递归 `docs/` 和 `corpus/` 文档，包括 `README.zh-CN.md` 和 `MORPHOJET-FEASIBILITY.md`，拒绝没有否定或条件语境保护的中文“生产级 / 生产就绪 / 替代 CellProfiler / 取代 CellProfiler”表述。在真实外部 L4 workflow trial、匹配 evidence package、外部 trial/package saved reviewer reports、稳定 GitHub release、以及 saved stable-release verifier report 都进入同一份生产声明门禁之前，`production_claim_status` 应保持 `INCOMPLETE`。

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

GitHub release verifier 会检查 tag 身份、release URL、GitHub release ID/API 身份、作者、target commit-ish、UTC 时间戳、draft/prerelease/immutable 状态、稳定 semver tag、发布资产集合、下载文件 checksum、archive 内容，并要求当前机器兼容的 archive 能通过 `morphojet doctor` 且 commit 前缀匹配。Direct release gate 的 live GitHub release verification 会绑定生产仓库 `benngaihk/MorphoJet`；Saved GitHub release verifier report 会标记 `claim_status=NOT_PRODUCTION_CLAIM`、`evidence_scope=GITHUB_STABLE_RELEASE_VERIFICATION`、`final_production_signoff=false`；复核 saved report 时可用 `--expect-repo benngaihk/MorphoJet` 防止其他仓库的 release 报告进入签核链。

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

生成的 workspace 包含模板 manifest、输入目录、中英文 README，以及一组按顺序执行的命令：plan 验证、manifest 验证、readiness、readiness 报告复核、trial 运行、evidence package、local preflight、local preflight 报告复核、stable release 验证、saved stable release 报告复核、final production gate、final production report 复核。`trial_plan.json` 还会记录 `claim_status=NOT_PRODUCTION_CLAIM`、`evidence_scope=EXTERNAL_L4_TRIAL_PLAN`、`final_production_signoff=false`、`pre_signoff_requirements` 和 `final_signoff_requirements`，分别把 readiness/local-preflight 前置证据和最终签核 artifact 绑定到计划路径、验证步骤，以及它们阻塞的后续步骤或最终门禁；最终签核表会单独记录 `stable_github_release` 指向 `https://github.com/benngaihk/MorphoJet/releases/tag/v0.1.0`，并把 `stable_github_release_saved_report` 作为另一项 saved verifier JSON，避免把线上 release 本身和保存的验证报告混为一项。生成的中英文 README 还会说明 `verify_package` 产出的 saved package verifier report 自身也是 `claim_status=NOT_PRODUCTION_CLAIM`、`evidence_scope=EXTERNAL_L4_EVIDENCE_PACKAGE_REVIEW`、`final_production_signoff=false`，并说明 `local_evidence_preflight` 产出的 saved local preflight report 也必须保持 `claim_status=NOT_PRODUCTION_CLAIM`、`evidence_scope=LOCAL_EXTERNAL_L4_PREFLIGHT`、`final_evidence_acceptable=false`，不能被误读成最终生产签核；`--verify-plan-files` 会同时复核英文和中文 README 内容，防止真实 L4 执行说明、package-review scope、local-preflight scope 或最终签核要求被改弱或改错。`check_readiness` 在返回 READY 前也会复核 saved `trial_plan.json`、template hash、manifest 是否存在，以及英文和中文 README 内容；如果 workspace 准备后执行说明或计划被改弱，readiness 会失败。`run_handoff_trial.py` 在执行 trial step 前还会重新验证 saved READY report，并拒绝 manifest 或 workspace 与当前 trial manifest 和 `base_dir` 不一致的报告。

生成的外部工作区中英文 README 也会告诉 reviewer：只有两条 saved reviewer verifier gates 都 PASS 时，local preflight 才会把 saved reviewer reports 当作 validated；否则这个检查会继续留在 skipped final checklist，直到失败的 reviewer report 被修复并重新复核。

在真实 trial 前，先运行 readiness；saved readiness report 会标记 `claim_status=NOT_PRODUCTION_CLAIM`、`evidence_scope=EXTERNAL_L4_READINESS_PRECHECK`、`final_production_signoff=false`，并绑定 saved plan、双语 README、输入 CSV、输出路径和 package 输出路径，防止预执行检查被误读成最终生产签核：

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

External trial report 本身会标记 `claim_status=NOT_PRODUCTION_CLAIM`、`evidence_scope=EXTERNAL_L4_WORKFLOW_TRIAL`、`final_production_signoff=false`；Saved external trial verifier report 也会标记 `claim_status=NOT_PRODUCTION_CLAIM`、`evidence_scope=EXTERNAL_L4_WORKFLOW_TRIAL_REVIEW`、`final_production_signoff=false`，并把源 trial report 的三项 claim-scope 字段复制到 `input_files.trial_json`，`--verify-report-files` 会重新计算它们，防止 trial 或 trial reviewer JSON 被单独误读成最终生产签核。Saved external trial verifier report 还会记录并复核 bound readiness report 的 workspace、manifest、package_name、size 和 SHA-256，确保 reviewer report 绑定的是同一份 trial readiness。Evidence package 会包含 `README.md` 和 `README.zh-CN.md`。两份 README 都会进入 `artifact_manifest.review_files` 和 package zip，release gate 会检查关键 signoff 字段和 readiness `package_name`、workspace、manifest 字段，standalone package verifier 也会记录它们的 path/size/SHA-256，方便中英文 reviewer 复核。Package 的 `artifact_manifest.json` 和两份 README 还必须保留 `claim_status=NOT_PRODUCTION_CLAIM`、`evidence_scope=EXTERNAL_L4_EVIDENCE_PACKAGE`、`final_production_signoff=false`；`artifact_manifest.json` 还会记录源 trial 的 `trial_claim_status`、`trial_evidence_scope`、`trial_final_production_signoff`，把 package 绑定到非最终 trial report。Saved package verifier report 自身也会标记 `claim_status=NOT_PRODUCTION_CLAIM`、`evidence_scope=EXTERNAL_L4_EVIDENCE_PACKAGE_REVIEW`、`final_production_signoff=false`，并把 package manifest 的三项 package-scope 字段复制到 `input_files.package_artifact_manifest`，把 package readiness report 的 `package_name`、workspace 和 manifest 复制到 `input_files.package_readiness`；如果提供 `--trial-json`，还会把源 trial 的三项 claim-scope 字段复制到 `input_files.source_trial_json`；`--verify-report-files` 会从 package manifest、package readiness report 和 source trial report 重新计算它们。

稳定 release 还不存在时，可以先对外部 trial 和 evidence package 做本地证据预检：

```bash
python3 benchmark/run_production_gate.py \
  --external-trial-json path/to/external-trial/handoff_trial.json \
  --external-trial-root path/to/external-trial \
  --external-evidence-package-dir path/to/evidence-packages/external-l4-trial \
  --external-trial-verification-report path/to/external-trial/trial-verification.json \
  --external-evidence-package-verification-report path/to/evidence-packages/package-verification.json \
  --github-release-tag v0.1.0 \
  --local-evidence-preflight-only
```

Local evidence preflight 会写出 JSON/Markdown 报告，并标记 `claim_status=NOT_PRODUCTION_CLAIM`、`evidence_scope=LOCAL_EXTERNAL_L4_PREFLIGHT`、`final_evidence_acceptable=false`。报告会列出被刻意跳过的最终生产门禁，记录 `skipped_final_checklist`，并用绝对路径、size 和 SHA-256 绑定 source trial JSON、package 内 `handoff_trial.json`、`artifact_manifest.json`、`readiness.json`、package zip、checksum 和可选 saved reviewer reports；这些必需 evidence summaries 必须保持 `exists=true`，不能被改成 missing 来移除 hash。只有两份 saved external reviewer reports 都提供、且两条 saved reviewer verifier gates 都 PASS 时，`external_l4_saved_reviewer_reports` 才会进入 `validated_checks`；否则它会留在 `skipped_final_checklist`。`stable_github_release` 和 `stable_github_release_saved_report` 在 local preflight 中始终保持 skipped，因为稳定 release 与 saved stable-release verifier report 必须在最终 production wrapper 中验证。它还会把 source/package trial 的三项 claim-scope 字段、package artifact manifest 的 package-scope 和 source-trial scope 字段，以及 readiness `package_name`、workspace、manifest 写入 `input_artifacts`；Markdown 的 input-artifact 表也会显示这些 readiness 字段，方便中文 reviewer 不打开 JSON 也能复核 readiness 上下文。Saved preflight verifier 在 `--verify-local-evidence-preflight-files` 下会从文件重新计算这些字段，防止本地预检报告被误改成最终生产签核。

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

这个 wrapper 要求稳定非 RC tag，复核外部 trial/package reviewer 报告，拒绝 final output 覆盖 package review files（包括 `README.md` 和 `README.zh-CN.md`），要求 saved GitHub release verifier report 是同一 final tag 和 `benngaihk/MorphoJet` repo 的 stable PASS 报告，并委托 `benchmark/release_gate.py --require-production-claim`。如果 final release gate 通过，wrapper 会立刻复核 `production-claim.json`，要求 `--require-production-claim-pass` 和 `--expect-missing-checks none`；生成的 trial plan 也保留同一条 final report verification 作为独立签核步骤。最终生产声明现在会把 saved trial/package reviewer reports 和 saved stable-release verifier report 作为独立审计项；saved GitHub release verifier report 自身仍标记 `claim_status=NOT_PRODUCTION_CLAIM`、`evidence_scope=GITHUB_STABLE_RELEASE_VERIFICATION`、`final_production_signoff=false`，direct release gate 的 live GitHub release verification 和 saved GitHub release report 复核都会绑定 `benngaihk/MorphoJet`。它通过之前，项目不能宣称 production-ready。

## 当前里程碑状态

当前代码已经具备：

- L3 public direct-mask benchmark PASS。
- 已验证的 `v0.1.0-rc.1` prerelease。
- L4-preflight handoff harness。
- 外部 L4 trial、evidence package、local evidence preflight、GitHub release saved-report verification、final production gate 和 final report verification 的审计脚手架；local preflight 也会写入可机器复核的 `skipped_final_checklist`，并绑定 source/package trial 与 package manifest 的 claim-scope 字段，防止把预检误读成最终生产证据。

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
