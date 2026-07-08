# MorphoJet

语言：[English](README.md) | 简体中文

MorphoJet 是面向显微图像批量测量的高速命令行工具，目标是兼容一部分 CellProfiler 风格的数据交付流程。

MorphoJet 目前不是 CellProfiler 的替代品。CellProfiler 仍然是 pipeline 设计和完整特性行为的基准；MorphoJet 当前聚焦于把稳定的、只做测量的批处理任务跑得更快，并降低部署和交付摩擦。

## README 中文版维护承诺

`README.zh-CN.md` 是中文社区的一等入口，不是英文 README 的简短摘要。英文 README 中与当前范围、发布验证、外部 L4 workflow、local preflight、final production wrapper、当前阻塞项和 package README evidence path 相关的审计合同，也必须在这里保留中文上下文。

Release gate 会运行 `benchmark/validate_claim_language.py`，检查英文 README 指向 `README.zh-CN.md`，并检查中文 README 保留中文社区验证入口、外部 L4 试验、最终生产门禁和当前里程碑状态。这样中文 reviewer 可以按同一条 evidence chain 复核项目，而不是依赖一条更弱或过期的并行说明。

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

`Image.csv` 会一直保留非空的 image-table 元数据列，例如 `Plate`、`Well`、`Site`。`Objects.csv` 默认保持稳定的测量 schema；如果下游分组、交付或 L4 handoff 希望每个 object row 都重复这些元数据，可以显式传入 `--include-object-metadata`：

```bash
cargo run -p morphojet -- measure \
  --images images.csv \
  --out measurements \
  --cellprofiler-compatible \
  --include-object-metadata \
  --overwrite
```

打开 object metadata 导出时，如果元数据列名与对象测量列冲突，例如 `AreaShape_Area`，MorphoJet 会拒绝输出，避免生成重复 CSV 表头。

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

同一条完整 CellBinDB L3 gate 现在也接入 `.github/workflows/cellbindb-l3.yml`，支持每周定时运行和手动 `workflow_dispatch`。这个 workflow 会执行 `benchmark/run_cellbindb_l3_validation.sh`，刷新 pinned CellBinDB oracle evidence，写出 `benchmark/results/release-gate/l3-cellbindb.json` / `.md`，并把 L3 parity、impact、provenance、workflow bridge 和 handoff trial 报告作为保留 30 天的 GitHub artifact 上传。定时 L3 evidence 是公开 oracle 路径的持续回归信号；它仍然不能替代真实外部 L4 workflow trial 或稳定 release 生产声明门禁。

快速审计已生成的 L3 产物：

```bash
python3 benchmark/release_gate.py
```

Release-gate JSON 和 Markdown 报告会记录运行时间、git commit、工作区是否 dirty、调用参数、顶层 `claim_status`、`evidence_scope`、`final_production_signoff`、`production_claim_status` 和 `missing_or_failed_checks`；JSON 还会写入 `production_claim_checklist`，Markdown 报告会渲染同一份 checklist，把每个 audit check 对应到必须提交的 evidence 和 reviewer 下一步动作。非最终报告会标记为 `claim_status=NOT_PRODUCTION_CLAIM`、`evidence_scope=RELEASE_GATE_PRECHECK`、`final_production_signoff=false`；只有带 `--require-production-claim`、整体 PASS、且 production audit 完整通过的报告，才会标记为 `claim_status=FINAL_PRODUCTION_CLAIM`、`evidence_scope=FINAL_PRODUCTION_RELEASE_GATE`、`final_production_signoff=true`。标准 gate 集合包含 full CellBinDB direct-mask inspection、已有 L3 artifacts、workflow bridge artifacts 和 handoff trial artifacts。Saved report verifier 会拒绝缺失或被篡改的 checklist rows 和 claim-scope labels。外部 L4 trial plan、readiness、trial、package、reviewer report、stable-release verifier 和 local-preflight 的标签也复用 release-gate 持有的非最终 claim-scope 合同，防止中间证据漂移成最终生产表述。Production audit check 状态（`PASS`、`FAIL`、`MISSING`）和顶层 production-claim 状态（`PASS`、`INCOMPLETE`）也来自同一份 release-gate 合同，并被 saved report reviewer 复用。计划中的稳定 tag（`v0.1.0`）、stable release URL 和 stable semver matcher 也来自同一份 release-gate 合同，并被外部 L4 plan generator、final wrapper、GitHub verifier 和 saved report verifier 共同使用。Claim-language guard 也会默认扫描顶层 Markdown、递归 `docs/` 和 `corpus/` 文档，包括 `README.zh-CN.md` 和 `MORPHOJET-FEASIBILITY.md`，拒绝没有否定或条件语境保护的中文“生产级 / 生产就绪 / 替代 CellProfiler / 取代 CellProfiler”表述。直接运行 `benchmark/release_gate.py --require-production-claim` 时，CLI 现在会先要求同时带上 `--require-clean-git` 和 `--require-l3-provenance`，否则在重型 gate 开始前失败；在真实外部 L4 workflow trial、匹配 evidence package、外部 trial/package saved reviewer reports、稳定 GitHub release、以及 saved stable-release verifier report 都进入同一份生产声明门禁之前，`production_claim_status` 应保持 `INCOMPLETE`。

同一个 source-doc guard 现在也把根目录双语 README 合同纳入 release evidence：英文 README 必须链接 `README.zh-CN.md`；中文 README 必须保留外部 L4 workflow、local preflight、final production wrapper、当前阻塞项和 package README evidence path，让中文社区可以直接按同一条验证链复核项目状态。

## 中文社区验证入口

中文 reviewer 可以先按下面顺序复核，不需要从英文 README 重新拼上下文：

1. 先看 [当前里程碑状态](#当前里程碑状态)，确认仍未完成真实外部 L4 workflow trial、匹配 evidence package、外部 L4 trial/package saved reviewer reports、live stable GitHub release 和 saved stable-release verifier report。
2. 用 `python3 benchmark/prepare_external_l4_trial.py --workspace path/to/external-trial` 生成外部 L4 workspace，并先运行生成的 `verify_plan --verify-plan-files --require-plan-files`，确认中英文 README、外部证据合同、local preflight、stable release 和 final wrapper 命令没有被改弱。
3. 用 `check_readiness`、`verify_readiness`、`run_trial`、`verify_trial_report`、`package_evidence`、`verify_package_report` 和 `local_evidence_preflight` 串起非最终证据。所有这些中间报告都必须保持 `claim_status=NOT_PRODUCTION_CLAIM`，不能单独当作最终生产签核。
4. evidence package 里的 `README.md` 和 `README.zh-CN.md` 都是 review files，会被 hash、写入 `artifact_manifest.review_files`、进入 zip，并在 saved package verifier 与 local preflight 中重新绑定到 readiness scope 和 handoff contract。
5. 只有最终 wrapper 同时绑定外部 trial、evidence package、trial/package saved reviewer reports、稳定 release tag、saved stable-release verifier report，并且 final report verifier 通过 `--require-report-pass --require-clean-git-metadata --verify-git-commit --require-production-claim-pass --expect-missing-checks none` 时，才可以进入最终生产声明讨论。

审查已保存的 release-gate JSON：

```bash
python3 benchmark/verify_release_gate_report.py benchmark/results/release-gate/report.json
python3 benchmark/verify_release_gate_report.py benchmark/results/release-gate/report.json --verify-git-commit
python3 benchmark/verify_release_gate_report.py benchmark/results/release-gate/production-claim.json --require-report-pass --require-clean-git-metadata --verify-git-commit --require-production-claim-pass --expect-missing-checks none
```

保存版 release-gate verifier 会把顶层摘要、`production_claim_audit`、claim-scope labels、UTC metadata、git commit、clean-git metadata、production evidence 路径和 `metadata.argv` 互相绑定起来复核。Production evidence metadata keys 和带路径值的 `metadata.argv` flags 由 `benchmark/release_gate.py` 统一持有，writer 和 saved report verifier 复用同一份合同，所以外部 L4 evidence、saved reviewer reports、saved GitHub release verifier report、`--out-json` 和 `--out-md` 的绝对路径要求不会在两边漂移。
最终 saved report 签核现在把 `--require-production-claim-pass` 当作 fail-closed 模式：必须同时提供 `--require-report-pass`、`--require-clean-git-metadata`、`--verify-git-commit` 和 `--expect-missing-checks none`，否则 verifier 会拒绝通过，避免 production-claim PASS 被半验证。

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

GitHub release verifier 会检查 tag 身份、release URL、GitHub release ID/API 身份、作者、target commit-ish、UTC 时间戳、draft/prerelease/immutable 状态、稳定 semver tag、发布资产集合、下载文件 checksum、archive 内容，并要求 saved release API URL 与记录的 release database ID 匹配、当前机器兼容的 archive 能通过 `morphojet doctor` 且 commit 前缀匹配。Direct release gate 的 live GitHub release verification 会绑定生产仓库 `benngaihk/MorphoJet`；Saved GitHub release verifier report 会标记 `claim_status=NOT_PRODUCTION_CLAIM`、`evidence_scope=GITHUB_STABLE_RELEASE_VERIFICATION`、`final_production_signoff=false`；复核 saved report 时可用 `--expect-repo benngaihk/MorphoJet` 防止其他仓库的 release 报告进入签核链。

直接使用 `benchmark/release_gate.py --require-production-claim --verify-github-release <tag>` 时，还必须显式提供 `--github-release-kind stable`；如果 live GitHub release gate 仍是 prerelease/RC，命令会在参数合同层失败，不会进入最终生产声明路径。直接 production-claim 命令如果提供 `--github-release-verification-report`，也必须同时提供 live `--verify-github-release <tag>`，避免 saved stable report 没有绑定最终 live tag 就进入签核链。

## CellProfiler 风格宽表导出

MorphoJet 原生 `Objects.csv` 是长表，键为 `ImageNumber`、`ObjectSet`、`ObjectNumber` 和 `Channel`。如果下游工具需要 CellProfiler object CSV，例如 `Cells.csv`，可以把当前支持的测量子集物化为宽表：

```bash
python3 benchmark/materialize_morphojet_cellprofiler_wide.py \
  --objects measurements/Objects.csv \
  --object-set Cells \
  --channels DNA,PH3 \
  --metadata-columns Plate,Well,Site \
  --out measurements/Cells.wide.csv
```

对照 CellProfiler object CSV 验证支持列：

```bash
python3 benchmark/compare_cellprofiler_wide_subset.py CellProfiler/Cells.csv measurements/Cells.wide.csv \
  --allow-extra-columns Plate,Well,Site \
  --fail-on-gap
```

使用 `--metadata-columns` 时，materializer 会把这些列从 `Objects.csv` 带到宽表；如果同一个 object 在不同 channel 行上的元数据值不一致，会直接失败。Subset comparer 可以把这些声明过的元数据列当作 MorphoJet-only pass-through 字段允许通过，同时仍会拒绝未声明的额外列。

## 外部 L4 试验与生产门禁

真实实验室交付从模板开始：

```bash
python3 benchmark/prepare_external_l4_trial.py --workspace path/to/external-trial
```

生成的 workspace 包含模板 manifest、输入目录、中英文 README，以及一组按顺序执行的命令：plan 验证、manifest 验证、readiness、readiness 报告复核、trial 运行、trial reviewer report 生成、trial reviewer report 复核、evidence package、package reviewer report 生成、package reviewer report 复核、local preflight、local preflight 报告复核、stable release 验证、saved stable release 报告复核、final production gate、final production report 复核。`trial_plan.json` 还会记录 `claim_status=NOT_PRODUCTION_CLAIM`、`evidence_scope=EXTERNAL_L4_TRIAL_PLAN`、`final_production_signoff=false`、`external_evidence_requirements`、`pre_signoff_requirements`、`final_signoff_requirements` 和 `production_claim_blockers`；其中 `external_evidence_requirements` 固定 reviewer/signoff 必填字段、UTC review timestamp、`manual_csv_editing=false` 和至少 3 条 acceptance criteria，防止真实 trial workspace 被改成弱化版签核表。`pre_signoff_requirements` 会把 readiness、saved reviewer report 复核和 local-preflight 前置证据绑定到计划路径、验证步骤和它们阻塞的后续步骤；`final_signoff_requirements` 会把最终签核 artifact 绑定到计划路径、验证步骤和精确 final wrapper 参数。`production_claim_blockers` 会把 release gate 生产审计里的阻塞项机器化记录下来，包括 `clean_git_worktree`、`l3_provenance_hashes`、外部 L4 trial/package/reviewer reports、stable release 和 saved stable-release report，并为每项写入 required evidence、next action、planned paths 和 final-gate binding。最终签核表会把外部 trial、evidence package、trial/package saved reviewer reports、稳定 release tag、saved stable-release verifier report 分别绑定到 `final_production_gate --external-trial-json`、`--external-evidence-package-dir`、`--external-trial-verification-report`、`--external-evidence-package-verification-report`、`--github-release-tag` 和 `--github-release-verification-report`，并单独记录 `stable_github_release` 指向 `https://github.com/benngaihk/MorphoJet/releases/tag/v0.1.0`，把 `stable_github_release_saved_report` 作为另一项 saved verifier JSON，避免把线上 release 本身和保存的验证报告混为一项。普通 `--verify-plan` 会确认 external evidence contract 没有被删除或改弱，确认 production blockers 没有被删除或改成更弱的清单，确认 readiness planned path 同时匹配 `check_readiness --json-out`、`verify_readiness --verify-report` 和 `run_trial --readiness-report`，确认 trial/package saved reviewer report 前置行指向 `verify_trial_report` / `verify_package_report`、前置于 `local_evidence_preflight`，并匹配 local-preflight 的 reviewer-report 输入，确认 local-preflight planned path 同时匹配 `local_evidence_preflight --local-evidence-preflight-json` 和 `verify_local_evidence_preflight --verify-local-evidence-preflight-report`，确认 trial JSON、package directory、reviewer-report JSON、GitHub release verifier JSON 和 final production-claim JSON 在生成的 run/verify/package/preflight/stable-release/final-wrapper 命令之间保持同一条路径流，确认 trial/package saved reviewer report 复核命令指向计划中的 reviewer JSON，并保留 file recheck、PASS enforcement，以及 package review 的 source-trial binding，确认 stable-release 验证命令绑定到 `v0.1.0`、`benngaihk/MorphoJet`、stable-report enforcement、git-commit verification 和同一个 final-wrapper tag，也会确认每个 final-signoff `required_for` wrapper flag 在生成的 `final_production_gate` 命令中恰好出现一次，并确认每个计划 artifact path 与该 flag 的命令值一致；`--verify-plan-files` 还会同时复核英文和中文 README 内容，防止真实 L4 执行说明、package-review scope、local-preflight scope、外部证据合同、最终签核要求或生产阻塞项被改弱或改错；`--require-plan-files` 会拒绝没有做这一步文件复核的 saved plan 签核。生成的中英文 README 还会渲染这些 external evidence requirements 和 production claim blockers，说明 saved trial-plan 签核必须把 `--require-plan-files` 和 `--verify-plan-files` 配对使用，说明 saved readiness 签核必须把 `--require-ready` 和 `--verify-report-files` 配对使用，并说明 `verify_package` 产出的 saved package verifier report 自身也是 `claim_status=NOT_PRODUCTION_CLAIM`、`evidence_scope=EXTERNAL_L4_EVIDENCE_PACKAGE_REVIEW`、`final_production_signoff=false`，说明 saved trial/package reviewer reports 必须先用 `verify_trial_report` 和 `verify_package_report` 复核，local preflight 或最终签核才可把它们当成 reviewer evidence，并说明这些 saved-report 签核命令必须把 `--require-report-pass` 和 `--verify-report-files` 配对使用；它们也说明 `local_evidence_preflight` 产出的 saved local preflight report 必须保持 `claim_status=NOT_PRODUCTION_CLAIM`、`evidence_scope=LOCAL_EXTERNAL_L4_PREFLIGHT`、`final_evidence_acceptable=false`，不能被误读成最终生产签核。`check_readiness` 在返回 READY 前也会复核 saved `trial_plan.json`、template hash、manifest 是否存在，以及英文和中文 README 内容；如果 workspace 准备后执行说明或计划被改弱，readiness 会失败。`run_handoff_trial.py` 在执行 trial step 前还会重新验证 saved READY report，并拒绝 manifest 或 workspace 与当前 trial manifest 和 `base_dir` 不一致的报告。

生成的外部工作区中英文 README 也会告诉 reviewer：只有两条 saved reviewer verifier gates 都 PASS 时，local preflight 才会把 saved reviewer reports 当作 validated；否则这个检查会继续留在 skipped final checklist，直到失败的 reviewer report 被修复并重新复核。它们还会说明 `verify_local_evidence_preflight` 会重新 hash package `README.md` 和 `README.zh-CN.md`，并重新计算 packaged readiness 的 READY 状态、`claim_status=NOT_PRODUCTION_CLAIM`、`evidence_scope=EXTERNAL_L4_READINESS_PRECHECK`、`final_production_signoff=false`、UTC 生成时间、`package_name`、workspace、manifest、package README 渲染出的 readiness scope、README handoff contract 与 `rendered_manifest.json` 的绑定，以及两份 package README 的 `review_entrypoint_present` 值，还会在 saved local preflight Markdown 的 `Review Entrypoint` 列显示这些值，防止本地预检被误读成最终生产签核、丢失下游 CSV 合同，或删掉中文社区 reviewer 入口。

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

External trial report 本身会标记 `claim_status=NOT_PRODUCTION_CLAIM`、`evidence_scope=EXTERNAL_L4_WORKFLOW_TRIAL`、`final_production_signoff=false`；Saved external trial verifier report 也会标记 `claim_status=NOT_PRODUCTION_CLAIM`、`evidence_scope=EXTERNAL_L4_WORKFLOW_TRIAL_REVIEW`、`final_production_signoff=false`，并把源 trial report 的三项 claim-scope 字段复制到 `input_files.trial_json`，把 bound readiness report 的 READY 状态、三项非最终 claim-scope 字段、UTC 生成时间、workspace、manifest、package_name、size 和 SHA-256 复制到 `input_files.readiness_report`，`--verify-report-files` 会重新计算它们，防止 trial、readiness summary 或 trial reviewer JSON 被单独误读成最终生产签核。Saved trial reviewer 签核模式下，`--require-report-pass` 现在必须同时带 `--verify-report-files`，否则会直接失败。Evidence package 会包含 `README.md` 和 `README.zh-CN.md`。两份 README 都会进入 `artifact_manifest.review_files` 和 package zip，release gate 会检查关键 signoff 字段，以及 readiness 的 READY 状态、`claim_status=NOT_PRODUCTION_CLAIM`、`evidence_scope=EXTERNAL_L4_READINESS_PRECHECK`、`final_production_signoff=false`、UTC 生成时间、`package_name`、workspace 和 manifest 字段。两份 README 也会渲染 trial rendered manifest 里的 handoff contract，包括 `morphojet_objects_csv`、`required_object_metadata_columns`，以及每个 export 的 object set、channels、metadata columns、输出 CSV、预期 CellProfiler CSV 和 comparison artifact paths；release gate 会检查中英文 README 中这些 contract 字段，防止 package 悄悄丢失下游 CSV 合同。Package README 也会写明中文社区 reviewer 可把 `README.zh-CN.md` 作为一等 package review file，并提醒 saved package verifier report 仍必须绑定进 final wrapper；standalone package verifier 会为两份 package README 记录 `review_entrypoint_present`，saved-report file recheck 会拒绝 reviewer entrypoint 被删或改弱。Standalone package verifier 也会记录 README 的 path/size/SHA-256，并把 README 渲染出的 readiness scope 和 handoff contract 字段复制到 `input_files.package_readme` 和 `input_files.package_readme_zh`，让 saved-report review 能把 handoff contract 重新绑定到 package README 和 rendered manifest；local evidence preflight 也会把同一批 README handoff contract 字段写入 `input_artifacts.package_readme` 和 `input_artifacts.package_readme_zh`，并在 Markdown 报告中渲染 handoff-contract 表和 input artifact 表里的 reviewer-entrypoint 状态，方便中文 reviewer 直接复核；`--verify-report-files` 还会重新绑定当前 package files、artifact manifest 和 copied `readiness.json`，方便中英文 reviewer 复核。Package 的 `artifact_manifest.json` 和两份 README 还必须保留 `claim_status=NOT_PRODUCTION_CLAIM`、`evidence_scope=EXTERNAL_L4_EVIDENCE_PACKAGE`、`final_production_signoff=false`；`artifact_manifest.json` 还会记录源 trial 的 `trial_claim_status`、`trial_evidence_scope`、`trial_final_production_signoff`，把 package 绑定到非最终 trial report。Saved package verifier report 自身也会标记 `claim_status=NOT_PRODUCTION_CLAIM`、`evidence_scope=EXTERNAL_L4_EVIDENCE_PACKAGE_REVIEW`、`final_production_signoff=false`，并把 package manifest 的 package-scope 和 source-trial scope 字段复制到 `input_files.package_artifact_manifest`，把 package readiness report 的 READY 状态、非最终 claim-scope 字段、UTC 生成时间、`package_name`、workspace 和 manifest 复制到 `input_files.package_readiness`；如果提供 `--trial-json`，还会把源 trial 的三项 claim-scope 字段复制到 `input_files.source_trial_json`；`--verify-report-files` 会从 package manifest、package readiness report 和 source trial report 重新计算它们。Saved package reviewer 签核模式下，`--require-report-pass` 现在也必须同时带 `--verify-report-files`，避免未重新 hash 文件的 saved package JSON 被当成可签核证据。

外部 L4 模板会声明 `required_object_metadata_columns`，默认要求 `Plate`、`Well`、`Site`。Readiness 会在 MorphoJet `Objects.csv` 上强制检查这些列，所以真实 handoff workspace 应该用 `measure --include-object-metadata` 生成 `Objects.csv`，或者在 reviewer 复核前有意识地修改 manifest 合同。

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

Local evidence preflight 会写出 JSON/Markdown 报告，并标记 `claim_status=NOT_PRODUCTION_CLAIM`、`evidence_scope=LOCAL_EXTERNAL_L4_PREFLIGHT`、`final_evidence_acceptable=false`。报告会列出被刻意跳过的最终生产门禁，记录 `skipped_final_checklist`，并用绝对路径、size 和 SHA-256 绑定 source trial JSON、package 内 `handoff_trial.json`、`artifact_manifest.json`、`readiness.json`、`README.md`、`README.zh-CN.md`、package zip、checksum 和可选 saved reviewer reports；这些必需 evidence summaries 必须保持 `exists=true`，不能被改成 missing 来移除 hash。只有两份 saved external reviewer reports 都提供、且两条 saved reviewer verifier gates 都 PASS 时，`external_l4_saved_reviewer_reports` 才会进入 `validated_checks`；否则它会留在 `skipped_final_checklist`。`stable_github_release` 和 `stable_github_release_saved_report` 在 local preflight 中始终保持 skipped，因为稳定 release 与 saved stable-release verifier report 必须在最终 production wrapper 中验证。它还会把 source/package trial 的三项 claim-scope 字段、package artifact manifest 的 package-scope 和 source-trial scope 字段、packaged readiness 的 READY 状态、`claim_status=NOT_PRODUCTION_CLAIM`、`evidence_scope=EXTERNAL_L4_READINESS_PRECHECK`、`final_production_signoff=false`、UTC 生成时间、`package_name`、workspace、manifest，以及两份 package README 渲染出的 readiness scope、handoff contract 和 `review_entrypoint_present` 写入 `input_artifacts`；Markdown 报告会显示 readiness 字段、每份 package README 的 reviewer-entrypoint 状态，并额外渲染 package README handoff-contract 表，方便中文 reviewer 不打开 JSON 也能复核 readiness 上下文、中文入口和下游 CSV 合同。Saved preflight verifier 会确认 `metadata.github_release_tag` 仍是稳定非 RC release tag，并把这些 README handoff-contract summaries 和 reviewer entrypoint 重新绑定到当前 package README 文件和 `rendered_manifest.json`；在 `--verify-local-evidence-preflight-files` 下也会从文件重新计算这些字段，防止本地预检报告被误改成最终生产签核、悄悄丢失下游 CSV 合同、替换成 RC tag，或删掉中文 reviewer 入口。`--require-local-evidence-preflight-pass` 现在是签核模式参数，必须同时要求 `metadata.git_dirty=false`、`metadata.git_status=[]`、`--verify-local-evidence-preflight-files` 和 `--verify-local-evidence-preflight-gates`，避免 dirty worktree 产出的报告、只检查 JSON 结构、或没有重新 hash 文件和重跑 gate 的弱复核被当成 reviewer-ready evidence。

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

这个 wrapper 要求稳定非 RC tag；真实 final run 会 fail-fast 要求三份 saved verifier reports 都显式提供：`--external-trial-verification-report`、`--external-evidence-package-verification-report` 和 `--github-release-verification-report`。它会在调用 final gate 前检查外部 trial JSON、trial root、evidence package dir 和三份 saved verifier reports 都存在，复核外部 trial/package reviewer 报告，拒绝 final output 覆盖 package review files（包括 `README.md` 和 `README.zh-CN.md`），要求 saved GitHub release verifier report 是同一 final tag 和 `benngaihk/MorphoJet` repo 的 stable PASS 报告，并带有 PASS enforcement、stable-report、file recheck、git commit、expected tag 和 expected repo 绑定，再委托 `benchmark/release_gate.py --require-production-claim`。如果 final release gate 通过，wrapper 会立刻复核 `production-claim.json`，要求 `--require-report-pass --require-clean-git-metadata --verify-git-commit --require-production-claim-pass --expect-missing-checks none`；生成的 trial plan 也保留同一条 final report verification 作为独立签核步骤。最终生产声明现在会把 saved trial/package reviewer reports 和 saved stable-release verifier report 作为独立审计项；saved GitHub release verifier report 自身仍标记 `claim_status=NOT_PRODUCTION_CLAIM`、`evidence_scope=GITHUB_STABLE_RELEASE_VERIFICATION`、`final_production_signoff=false`，direct release gate 的 live GitHub release verification 和 saved GitHub release report 复核都会绑定 `benngaihk/MorphoJet` 和 final tag。GitHub release verifier 现在也把 `--require-stable-report` 当作签核模式参数；没有同时提供 `--require-report-pass`、`--verify-report-files`、`--verify-git-commit`、`--expect-tag` 和 `--expect-repo` 时会直接失败，避免 saved stable-release report 被弱复核。`--dry-run` 仍可用来查看组装后的命令而不要求这些外部路径存在；`--local-evidence-preflight-only` 仍是较早的非最终路径，允许外部 saved reviewer reports 还未齐。它通过之前，项目不能宣称 production-ready。

## 当前里程碑状态

当前代码已经具备：

- L3 public direct-mask benchmark PASS。
- 已验证的 `v0.1.0-rc.1` prerelease。
- L4-preflight handoff harness。
- 每周和手动触发的 GitHub scheduled CellBinDB L3 workflow，用于持续刷新公开 oracle 路径的 L3 回归证据。
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
