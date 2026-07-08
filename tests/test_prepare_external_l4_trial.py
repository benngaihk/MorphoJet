#!/usr/bin/env python3
"""Unit tests for external L4 trial workspace preparation."""

from __future__ import annotations

import os
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmark"))

import prepare_external_l4_trial  # noqa: E402


TEMPLATE = ROOT / "benchmark/handoff/external_lab_template.json"


@contextmanager
def temporary_cwd(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


class PrepareExternalL4TrialTest(unittest.TestCase):
    def test_prepare_workspace_writes_manifest_plan_and_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "external-trial"

            plan = prepare_external_l4_trial.prepare_workspace(TEMPLATE, workspace)

            self.assertEqual("NOT_PRODUCTION_CLAIM", plan["claim_status"])
            self.assertEqual("EXTERNAL_L4_TRIAL_PLAN", plan["evidence_scope"])
            self.assertFalse(plan["final_production_signoff"])
            generated_at = datetime.fromisoformat(plan["generated_at_utc"])
            self.assertIsNotNone(generated_at.tzinfo)
            self.assertEqual(timezone.utc.utcoffset(generated_at), generated_at.utcoffset())
            self.assertEqual(
                [
                    "benchmark/prepare_external_l4_trial.py",
                    "--workspace",
                    str(workspace.resolve()),
                ],
                plan["argv"],
            )
            self.assertEqual(str(TEMPLATE.resolve()), plan["template"])
            self.assertEqual(str(workspace.resolve()), plan["workspace"])
            self.assertEqual(str((workspace / "external_manifest.json").resolve()), plan["manifest"])
            self.assertEqual(TEMPLATE.stat().st_size, plan["template_size_bytes"])
            self.assertEqual(prepare_external_l4_trial.sha256(TEMPLATE), plan["template_sha256"])
            self.assertTrue((workspace / "external_manifest.json").is_file())
            self.assertTrue((workspace / "trial_plan.json").is_file())
            self.assertTrue((workspace / "README.md").is_file())
            self.assertTrue((workspace / "README.zh-CN.md").is_file())
            self.assertTrue((workspace / "morphojet").is_dir())
            self.assertTrue((workspace / "cellprofiler").is_dir())
            self.assertTrue((workspace / "evidence-package").is_dir())
            self.assertEqual(
                json.loads(TEMPLATE.read_text(encoding="utf-8")),
                json.loads((workspace / "external_manifest.json").read_text(encoding="utf-8")),
            )
            verify_plan = plan["commands"]["verify_plan"]
            self.assertEqual(
                [
                    "python3",
                    "benchmark/prepare_external_l4_trial.py",
                    "--verify-plan",
                    str((workspace / "trial_plan.json").resolve()),
                    "--verify-plan-files",
                ],
                verify_plan,
            )
            run_command = plan["commands"]["run_trial"]
            self.assertIn("--require-external-evidence", run_command)
            self.assertEqual(
                str((workspace / "readiness.json").resolve()),
                run_command[run_command.index("--readiness-report") + 1],
            )
            self.assertIn(f"base_dir={workspace.resolve()}", run_command)
            self.assertEqual(
                str((workspace / "handoff_trial.json").resolve()),
                run_command[run_command.index("--out-json") + 1],
            )
            verify_trial_report = plan["commands"]["verify_trial_report"]
            self.assertEqual(
                str((workspace / "handoff_trial-verification.json").resolve()),
                verify_trial_report[verify_trial_report.index("--verify-report") + 1],
            )
            self.assertIn("--verify-report-files", verify_trial_report)
            self.assertIn("--require-report-pass", verify_trial_report)
            verify_package_report = plan["commands"]["verify_package_report"]
            self.assertEqual(
                str((workspace / "evidence-package-verification.json").resolve()),
                verify_package_report[verify_package_report.index("--verify-report") + 1],
            )
            self.assertIn("--verify-report-files", verify_package_report)
            self.assertIn("--require-report-pass", verify_package_report)
            self.assertIn("--require-trial-json", verify_package_report)
            self.assertEqual(str(workspace.resolve()), plan["commands"]["check_readiness"][3])
            self.assertEqual(plan["package_name"], plan["commands"]["check_readiness"][5])
            verify_readiness = plan["commands"]["verify_readiness"]
            self.assertEqual(
                str((workspace / "readiness.json").resolve()),
                verify_readiness[verify_readiness.index("--verify-report") + 1],
            )
            self.assertIn("--verify-report-files", verify_readiness)
            self.assertIn("--require-ready", verify_readiness)
            self.assertIn("--local-evidence-preflight-only", plan["commands"]["local_evidence_preflight"])
            verify_preflight = plan["commands"]["verify_local_evidence_preflight"]
            self.assertEqual(
                str((workspace / "local-evidence-preflight.json").resolve()),
                verify_preflight[verify_preflight.index("--verify-local-evidence-preflight-report") + 1],
            )
            self.assertIn("--verify-local-evidence-preflight-files", verify_preflight)
            self.assertIn("--verify-local-evidence-preflight-gates", verify_preflight)
            self.assertIn("--require-local-evidence-preflight-pass", verify_preflight)
            stable_release = plan["commands"]["verify_stable_release"]
            self.assertEqual("v0.1.0", stable_release[2])
            self.assertEqual("benngaihk/MorphoJet", stable_release[stable_release.index("--repo") + 1])
            self.assertEqual(
                str((workspace / "github-release").resolve()),
                stable_release[stable_release.index("--out-dir") + 1],
            )
            self.assertIn("--expect-stable", stable_release)
            self.assertEqual(
                str((workspace / "github-release-verification.json").resolve()),
                stable_release[stable_release.index("--json-out") + 1],
            )
            stable_report = plan["commands"]["verify_stable_release_report"]
            self.assertEqual(
                str((workspace / "github-release-verification.json").resolve()),
                stable_report[stable_report.index("--verify-report") + 1],
            )
            self.assertIn("--verify-report-files", stable_report)
            self.assertIn("--require-report-pass", stable_report)
            self.assertIn("--require-stable-report", stable_report)
            self.assertIn("--verify-git-commit", stable_report)
            self.assertEqual("v0.1.0", stable_report[stable_report.index("--expect-tag") + 1])
            self.assertEqual("benngaihk/MorphoJet", stable_report[stable_report.index("--expect-repo") + 1])
            final_gate = plan["commands"]["final_production_gate"]
            self.assertEqual(
                str((workspace / "handoff_trial.json").resolve()),
                final_gate[final_gate.index("--external-trial-json") + 1],
            )
            self.assertEqual(
                str(
                    (
                        workspace
                        / "evidence-package"
                        / "external-l4-external-lab-supported-columns-handoff"
                    ).resolve()
                ),
                final_gate[final_gate.index("--external-evidence-package-dir") + 1],
            )
            self.assertEqual(
                str((workspace / "github-release-verification.json").resolve()),
                final_gate[final_gate.index("--github-release-verification-report") + 1],
            )
            self.assertEqual("v0.1.0", final_gate[final_gate.index("--github-release-tag") + 1])
            self.assertEqual(
                str((workspace / "production-claim.json").resolve()),
                final_gate[final_gate.index("--out-json") + 1],
            )
            final_report = plan["commands"]["verify_final_production_report"]
            self.assertEqual(
                str((workspace / "production-claim.json").resolve()),
                final_report[2],
            )
            self.assertIn("--require-report-pass", final_report)
            self.assertIn("--require-clean-git-metadata", final_report)
            self.assertIn("--verify-git-commit", final_report)
            self.assertIn("--require-production-claim-pass", final_report)
            self.assertEqual("none", final_report[final_report.index("--expect-missing-checks") + 1])
            pre_requirements = plan["pre_signoff_requirements"]
            pre_requirement_by_name = {requirement["name"]: requirement for requirement in pre_requirements}
            self.assertEqual(
                str((workspace / "readiness.json").resolve()),
                pre_requirement_by_name["external_l4_readiness_precheck"]["planned_path"],
            )
            self.assertEqual(
                "verify_readiness",
                pre_requirement_by_name["external_l4_readiness_precheck"]["verification_step"],
            )
            self.assertEqual(
                "run_trial",
                pre_requirement_by_name["external_l4_readiness_precheck"]["required_before"],
            )
            self.assertEqual(
                str((workspace / "local-evidence-preflight.json").resolve()),
                pre_requirement_by_name["local_evidence_preflight_report"]["planned_path"],
            )
            self.assertEqual(
                "verify_local_evidence_preflight",
                pre_requirement_by_name["local_evidence_preflight_report"]["verification_step"],
            )
            self.assertEqual(
                "verify_stable_release",
                pre_requirement_by_name["local_evidence_preflight_report"]["required_before"],
            )
            self.assertEqual(
                str((workspace / "handoff_trial-verification.json").resolve()),
                pre_requirement_by_name["external_l4_trial_saved_reviewer_report"]["planned_path"],
            )
            self.assertEqual(
                "verify_trial_report",
                pre_requirement_by_name["external_l4_trial_saved_reviewer_report"]["verification_step"],
            )
            self.assertEqual(
                "local_evidence_preflight",
                pre_requirement_by_name["external_l4_trial_saved_reviewer_report"]["required_before"],
            )
            self.assertEqual(
                str((workspace / "evidence-package-verification.json").resolve()),
                pre_requirement_by_name["external_l4_package_saved_reviewer_report"]["planned_path"],
            )
            self.assertEqual(
                "verify_package_report",
                pre_requirement_by_name["external_l4_package_saved_reviewer_report"]["verification_step"],
            )
            self.assertEqual(
                "local_evidence_preflight",
                pre_requirement_by_name["external_l4_package_saved_reviewer_report"]["required_before"],
            )
            evidence_requirements = plan["external_evidence_requirements"]
            self.assertEqual(
                [
                    "lab_or_org",
                    "workflow_owner",
                    "dataset_name",
                    "dataset_source",
                    "downstream_workflow",
                    "execution_environment",
                    "reviewer_name_or_role",
                    "reviewed_at_utc",
                    "signoff_statement",
                ],
                evidence_requirements["required_fields"],
            )
            self.assertEqual("required_utc_timestamp", evidence_requirements["reviewed_at_utc"])
            self.assertEqual("required_non_placeholder", evidence_requirements["signoff_statement"])
            self.assertIs(False, evidence_requirements["manual_csv_editing"])
            self.assertEqual(3, evidence_requirements["acceptance_criteria_min_count"])
            self.assertEqual("non_empty_non_placeholder", evidence_requirements["acceptance_criteria_policy"])
            self.assertEqual(
                "all_REPLACE_WITH_values_must_be_replaced_before_trial",
                evidence_requirements["placeholder_policy"],
            )
            self.assertEqual(["validate_manifest", "run_trial"], evidence_requirements["enforced_by"])
            requirements = plan["final_signoff_requirements"]
            requirement_by_name = {requirement["name"]: requirement for requirement in requirements}
            self.assertEqual(
                str((workspace / "handoff_trial.json").resolve()),
                requirement_by_name["external_l4_workflow_trial"]["planned_path"],
            )
            self.assertEqual("verify_trial", requirement_by_name["external_l4_workflow_trial"]["verification_step"])
            self.assertEqual(
                "final_production_gate --external-trial-json",
                requirement_by_name["external_l4_workflow_trial"]["required_for"],
            )
            self.assertEqual(
                str(
                    (
                        workspace
                        / "evidence-package"
                        / "external-l4-external-lab-supported-columns-handoff"
                    ).resolve()
                ),
                requirement_by_name["external_l4_evidence_package"]["planned_path"],
            )
            self.assertEqual(
                "final_production_gate --external-evidence-package-dir",
                requirement_by_name["external_l4_evidence_package"]["required_for"],
            )
            self.assertEqual(
                "final_production_gate --external-trial-verification-report",
                requirement_by_name["external_l4_trial_saved_reviewer_report"]["required_for"],
            )
            self.assertEqual(
                "verify_trial_report",
                requirement_by_name["external_l4_trial_saved_reviewer_report"]["verification_step"],
            )
            self.assertEqual(
                "final_production_gate --external-evidence-package-verification-report",
                requirement_by_name["external_l4_package_saved_reviewer_report"]["required_for"],
            )
            self.assertEqual(
                "verify_package_report",
                requirement_by_name["external_l4_package_saved_reviewer_report"]["verification_step"],
            )
            self.assertEqual(
                "https://github.com/benngaihk/MorphoJet/releases/tag/v0.1.0",
                requirement_by_name["stable_github_release"]["planned_path"],
            )
            self.assertEqual(
                "verify_stable_release",
                requirement_by_name["stable_github_release"]["verification_step"],
            )
            self.assertEqual(
                "final_production_gate --github-release-tag",
                requirement_by_name["stable_github_release"]["required_for"],
            )
            self.assertEqual(
                str((workspace / "github-release-verification.json").resolve()),
                requirement_by_name["stable_github_release_saved_report"]["planned_path"],
            )
            self.assertEqual(
                "verify_stable_release_report",
                requirement_by_name["stable_github_release_saved_report"]["verification_step"],
            )
            self.assertEqual(
                "final_production_gate --github-release-verification-report",
                requirement_by_name["stable_github_release_saved_report"]["required_for"],
            )
            self.assertEqual(
                "verify_final_production_report",
                requirement_by_name["final_production_claim_report"]["verification_step"],
            )
            blockers = plan["production_claim_blockers"]
            self.assertEqual(
                [
                    "clean_git_worktree",
                    "l3_provenance_hashes",
                    "external_l4_workflow_trial",
                    "external_l4_evidence_package",
                    "external_l4_saved_reviewer_reports",
                    "stable_github_release",
                    "stable_github_release_saved_report",
                ],
                [blocker["name"] for blocker in blockers],
            )
            blocker_by_name = {blocker["name"]: blocker for blocker in blockers}
            self.assertEqual("PENDING_FINAL_GATE", blocker_by_name["clean_git_worktree"]["status"])
            self.assertEqual("PENDING_FINAL_GATE", blocker_by_name["l3_provenance_hashes"]["status"])
            self.assertEqual(
                "PENDING_EXTERNAL_EVIDENCE",
                blocker_by_name["external_l4_workflow_trial"]["status"],
            )
            self.assertEqual(
                "PENDING_EXTERNAL_REVIEW",
                blocker_by_name["external_l4_saved_reviewer_reports"]["status"],
            )
            self.assertEqual(
                "PENDING_STABLE_RELEASE",
                blocker_by_name["stable_github_release"]["status"],
            )
            self.assertIn(
                str((workspace / "handoff_trial.json").resolve()),
                blocker_by_name["external_l4_workflow_trial"]["planned_paths"],
            )
            self.assertIn(
                str((workspace / "evidence-package-verification.json").resolve()),
                blocker_by_name["external_l4_saved_reviewer_reports"]["planned_paths"],
            )
            self.assertIn(
                "final_production_gate --github-release-verification-report",
                blocker_by_name["stable_github_release_saved_report"]["final_gate_bindings"],
            )
            readme = (workspace / "README.md").read_text(encoding="utf-8")
            self.assertIn("Language: English | [简体中文](README.zh-CN.md)", readme)
            self.assertIn("## pre_signoff_requirements", readme)
            self.assertIn("| Requirement | Status | Planned Path | Verification Step | Required Before |", readme)
            self.assertIn("local_evidence_preflight_report", readme)
            self.assertIn("## final_signoff_requirements", readme)
            self.assertIn("| Requirement | Status | Planned Path | Verification Step | Required For |", readme)
            self.assertIn("external_l4_workflow_trial", readme)
            self.assertIn("final_production_gate --external-trial-json", readme)
            self.assertIn("final_production_gate --external-evidence-package-dir", readme)
            self.assertIn("final_production_gate --external-trial-verification-report", readme)
            self.assertIn("final_production_gate --external-evidence-package-verification-report", readme)
            self.assertIn("stable_github_release", readme)
            self.assertIn("https://github.com/benngaihk/MorphoJet/releases/tag/v0.1.0", readme)
            self.assertIn("final_production_gate --github-release-tag", readme)
            self.assertIn("stable_github_release_saved_report", readme)
            self.assertIn("final_production_gate --github-release-verification-report", readme)
            self.assertIn("final_production_gate", readme)
            self.assertIn("## production_claim_blockers", readme)
            self.assertIn("| Blocker | Status | Required Evidence | Next Action | Planned Paths | Final Gate Binding |", readme)
            self.assertIn("clean_git_worktree", readme)
            self.assertIn("l3_provenance_hashes", readme)
            self.assertIn("external_l4_saved_reviewer_reports", readme)
            self.assertIn("External evidence requirements recorded in `trial_plan.json`", readme)
            self.assertIn("| `reviewer_name_or_role` | required, non-placeholder value |", readme)
            self.assertIn("| `reviewed_at_utc` | must include a UTC timezone offset |", readme)
            self.assertIn("| `manual_csv_editing` | must be `False` |", readme)
            self.assertIn("| `acceptance_criteria` | at least 3 non-placeholder items |", readme)
            self.assertIn(
                "`verify_plan` rejects a saved plan whose external evidence contract has been removed or weakened",
                readme,
            )
            self.assertIn(
                "The saved package verifier report produced by `verify_package` is also not final production signoff",
                readme,
            )
            self.assertIn("evidence_scope=EXTERNAL_L4_EVIDENCE_PACKAGE_REVIEW", readme)
            self.assertIn(
                "The saved local preflight report produced by `local_evidence_preflight` is also not final production signoff",
                readme,
            )
            self.assertIn("Chinese-community reviewers can use `README.zh-CN.md`", readme)
            self.assertIn("same command order, non-final claim labels, pre-signoff requirements", readme)
            self.assertIn("evidence_scope=LOCAL_EXTERNAL_L4_PREFLIGHT", readme)
            self.assertIn("final_evidence_acceptable=false", readme)
            self.assertIn("`check_readiness` also verifies the saved `trial_plan.json`", readme)
            self.assertIn("both English and Chinese README files before returning READY", readme)
            self.assertIn("`required_object_metadata_columns`", readme)
            self.assertIn("`measure --include-object-metadata`", readme)
            self.assertIn("passes declared object metadata columns through to the wide CSV", readme)
            self.assertIn("`verify_trial_report` and `verify_package_report` re-check", readme)
            self.assertIn("PASS enforcement before local preflight or final signoff", readme)
            self.assertIn("required input-artifact summaries to remain `exists=true`", readme)
            self.assertIn("package `README.md`", readme)
            self.assertIn("package `README.zh-CN.md`", readme)
            self.assertIn("both saved reviewer verifier gates pass", readme)
            self.assertIn("metadata-bound saved reviewer reports", readme)
            self.assertIn("matching gate entries and hash summaries", readme)
            self.assertIn("package-manifest package/source-trial scope labels", readme)
            self.assertIn("packaged readiness READY status", readme)
            self.assertIn("claim_status=NOT_PRODUCTION_CLAIM", readme)
            self.assertIn("evidence_scope=EXTERNAL_L4_READINESS_PRECHECK", readme)
            self.assertIn("final_production_signoff=false", readme)
            self.assertIn("UTC generation time", readme)
            self.assertIn("package README-rendered readiness scope", readme)
            self.assertIn("package README-rendered handoff contract binding to `rendered_manifest.json`", readme)
            self.assertIn("package README `review_entrypoint_present` values", readme)
            self.assertIn("both `README.md` and `README.zh-CN.md`", readme)
            self.assertIn("saved local preflight Markdown", readme)
            self.assertIn("`Review Entrypoint` input-artifact column", readme)
            self.assertLess(readme.index("## verify_plan"), readme.index("## validate_manifest"))
            self.assertLess(readme.index("## verify_readiness"), readme.index("## run_trial"))
            self.assertLess(readme.index("## verify_trial"), readme.index("## verify_trial_report"))
            self.assertLess(readme.index("## verify_trial_report"), readme.index("## package_evidence"))
            self.assertLess(readme.index("## verify_package"), readme.index("## verify_package_report"))
            self.assertLess(
                readme.index("## verify_package_report"),
                readme.index("## local_evidence_preflight"),
            )
            self.assertLess(
                readme.index("## local_evidence_preflight"),
                readme.index("## verify_local_evidence_preflight"),
            )
            self.assertLess(
                readme.index("## verify_stable_release"),
                readme.index("## verify_stable_release_report"),
            )
            self.assertLess(
                readme.index("## verify_stable_release_report"),
                readme.index("## final_production_gate"),
            )
            self.assertLess(
                readme.index("## final_production_gate"),
                readme.index("## verify_final_production_report"),
            )
            readme_zh = (workspace / "README.zh-CN.md").read_text(encoding="utf-8")
            self.assertIn("Language: [English](README.md) | 简体中文", readme_zh)
            self.assertIn("这个工作区只是准备脚手架，不是外部 L4 证据。", readme_zh)
            self.assertIn("## pre_signoff_requirements", readme_zh)
            self.assertIn("| 要求 | 状态 | 计划路径 | 验证步骤 | 前置于 |", readme_zh)
            self.assertIn("local_evidence_preflight_report", readme_zh)
            self.assertIn("## final_signoff_requirements", readme_zh)
            self.assertIn("| 要求 | 状态 | 计划路径 | 验证步骤 | 用于 |", readme_zh)
            self.assertIn("stable_github_release", readme_zh)
            self.assertIn("final_production_gate --external-trial-json", readme_zh)
            self.assertIn("final_production_gate --external-evidence-package-dir", readme_zh)
            self.assertIn("final_production_gate --external-trial-verification-report", readme_zh)
            self.assertIn("final_production_gate --external-evidence-package-verification-report", readme_zh)
            self.assertIn("https://github.com/benngaihk/MorphoJet/releases/tag/v0.1.0", readme_zh)
            self.assertIn("final_production_gate --github-release-tag", readme_zh)
            self.assertIn("stable_github_release_saved_report", readme_zh)
            self.assertIn("final_production_gate --github-release-verification-report", readme_zh)
            self.assertIn("production_signoff", readme_zh)
            self.assertIn("## production_claim_blockers", readme_zh)
            self.assertIn("| 阻塞项 | 状态 | 必需证据 | 下一步 | 计划路径 | Final gate binding |", readme_zh)
            self.assertIn("clean_git_worktree", readme_zh)
            self.assertIn("l3_provenance_hashes", readme_zh)
            self.assertIn("external_l4_saved_reviewer_reports", readme_zh)
            self.assertIn("`trial_plan.json` 记录的外部证据要求", readme_zh)
            self.assertIn("| `reviewer_name_or_role` | 必填，且不能保留 placeholder |", readme_zh)
            self.assertIn("| `reviewed_at_utc` | 必须包含 UTC 时区偏移 |", readme_zh)
            self.assertIn("| `manual_csv_editing` | 必须是 `False` |", readme_zh)
            self.assertIn("| `acceptance_criteria` | 至少 3 条非 placeholder 项 |", readme_zh)
            self.assertIn("外部证据合同被删除或改弱，`verify_plan` 会拒绝通过", readme_zh)
            self.assertIn("saved package verifier report 也不是最终生产签核", readme_zh)
            self.assertIn("evidence_scope=EXTERNAL_L4_EVIDENCE_PACKAGE_REVIEW", readme_zh)
            self.assertIn("saved local preflight report 也不是最终生产签核", readme_zh)
            self.assertIn("中文社区 reviewer 可以把 `README.zh-CN.md` 作为一等复核入口", readme_zh)
            self.assertIn("相同的命令顺序、非最终 claim labels、pre-signoff requirements", readme_zh)
            self.assertIn("evidence_scope=LOCAL_EXTERNAL_L4_PREFLIGHT", readme_zh)
            self.assertIn("final_evidence_acceptable=false", readme_zh)
            self.assertIn("`check_readiness` 在返回 READY 前也会复核 saved `trial_plan.json`", readme_zh)
            self.assertIn("英文和中文 README 文件", readme_zh)
            self.assertIn("`required_object_metadata_columns`", readme_zh)
            self.assertIn("`measure --include-object-metadata`", readme_zh)
            self.assertIn("把声明过的 object metadata columns 带进宽表", readme_zh)
            self.assertIn("`verify_trial_report` 和 `verify_package_report`", readme_zh)
            self.assertIn("local preflight 或最终签核", readme_zh)
            self.assertIn("input-artifact summaries 保持 `exists=true`", readme_zh)
            self.assertIn("package `README.md`", readme_zh)
            self.assertIn("package `README.zh-CN.md`", readme_zh)
            self.assertIn("两条 saved reviewer verifier gates 都 PASS", readme_zh)
            self.assertIn("metadata 绑定的 saved reviewer reports", readme_zh)
            self.assertIn("对应 gate entries 和 hash summaries", readme_zh)
            self.assertIn("package manifest 的 package/source-trial scope labels", readme_zh)
            self.assertIn("packaged readiness 的 READY 状态", readme_zh)
            self.assertIn("claim_status=NOT_PRODUCTION_CLAIM", readme_zh)
            self.assertIn("evidence_scope=EXTERNAL_L4_READINESS_PRECHECK", readme_zh)
            self.assertIn("final_production_signoff=false", readme_zh)
            self.assertIn("UTC 生成时间", readme_zh)
            self.assertIn("package README 渲染出的 readiness scope", readme_zh)
            self.assertIn("package README 渲染出的 handoff contract 与 `rendered_manifest.json` 的绑定", readme_zh)
            self.assertIn("package README `review_entrypoint_present` 值", readme_zh)
            self.assertIn("`README.md` 和 `README.zh-CN.md`", readme_zh)
            self.assertIn("Saved local preflight Markdown", readme_zh)
            self.assertIn("`Review Entrypoint` input-artifact 列", readme_zh)
            self.assertLess(readme_zh.index("## verify_plan"), readme_zh.index("## validate_manifest"))
            self.assertLess(readme_zh.index("## verify_readiness"), readme_zh.index("## run_trial"))
            self.assertLess(readme_zh.index("## verify_trial"), readme_zh.index("## verify_trial_report"))
            self.assertLess(readme_zh.index("## verify_trial_report"), readme_zh.index("## package_evidence"))
            self.assertLess(readme_zh.index("## verify_package"), readme_zh.index("## verify_package_report"))
            self.assertLess(
                readme_zh.index("## verify_package_report"),
                readme_zh.index("## local_evidence_preflight"),
            )
            self.assertLess(
                readme_zh.index("## final_production_gate"),
                readme_zh.index("## verify_final_production_report"),
            )

    def test_prepare_workspace_records_custom_generator_argv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "external-trial"

            plan = prepare_external_l4_trial.prepare_workspace(
                TEMPLATE,
                workspace,
                package_name="external review package",
            )

            self.assertEqual(
                [
                    "benchmark/prepare_external_l4_trial.py",
                    "--workspace",
                    str(workspace.resolve()),
                    "--package-name",
                    "external review package",
                ],
                plan["argv"],
            )

    def test_cli_records_absolute_paths_for_relative_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "external-trial"

            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "benchmark/prepare_external_l4_trial.py"),
                    "--workspace",
                    "external-trial",
                ],
                cwd=root,
                text=True,
                capture_output=True,
            )
            plan_path = workspace / "trial_plan.json"
            plan = json.loads(plan_path.read_text(encoding="utf-8"))

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual(str(workspace.resolve()), plan["workspace"])
        self.assertEqual(str(TEMPLATE.resolve()), plan["template"])
        self.assertEqual(str((workspace / "external_manifest.json").resolve()), plan["manifest"])
        self.assertIn(str(workspace.resolve()), plan["argv"])
        self.assertIn(str((workspace / "trial_plan.json").resolve()), plan["commands"]["verify_plan"])

    def test_saved_trial_plan_can_be_verified_with_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "external-trial"
            prepare_external_l4_trial.prepare_workspace(TEMPLATE, workspace)
            plan_path = workspace / "trial_plan.json"

            completed = subprocess.run(
                [
                    sys.executable,
                    "benchmark/prepare_external_l4_trial.py",
                    "--verify-plan",
                    str(plan_path),
                    "--verify-plan-files",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertIn("claim_status=NOT_PRODUCTION_CLAIM", completed.stdout)
            self.assertIn("evidence_scope=EXTERNAL_L4_TRIAL_PLAN", completed.stdout)
            self.assertIn("final_production_signoff=False", completed.stdout)

    def test_saved_trial_plan_rejects_claim_scope_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "external-trial"
            prepare_external_l4_trial.prepare_workspace(TEMPLATE, workspace)
            plan_path = workspace / "trial_plan.json"
            payload = json.loads(plan_path.read_text(encoding="utf-8"))
            payload["claim_status"] = "PASS"
            payload["evidence_scope"] = "FINAL_PRODUCTION_CLAIM"
            payload["final_production_signoff"] = True
            plan_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    "benchmark/prepare_external_l4_trial.py",
                    "--verify-plan",
                    str(plan_path),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )

        self.assertNotEqual(0, completed.returncode)
        self.assertIn("claim_status=PASS", completed.stderr)
        self.assertIn("evidence_scope=FINAL_PRODUCTION_CLAIM", completed.stderr)
        self.assertIn("final_production_signoff must be false", completed.stderr)

    def test_saved_trial_plan_rejects_non_utc_generated_at(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "external-trial"
            prepare_external_l4_trial.prepare_workspace(TEMPLATE, workspace)
            plan_path = workspace / "trial_plan.json"
            payload = json.loads(plan_path.read_text(encoding="utf-8"))
            payload["generated_at_utc"] = "2026-07-07T12:00:00+08:00"
            plan_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    "benchmark/prepare_external_l4_trial.py",
                    "--verify-plan",
                    str(plan_path),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(0, completed.returncode)
            self.assertIn("generated_at_utc must be UTC", completed.stderr)

    def test_saved_trial_plan_rejects_command_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "external-trial"
            prepare_external_l4_trial.prepare_workspace(TEMPLATE, workspace)
            plan_path = workspace / "trial_plan.json"
            payload = json.loads(plan_path.read_text(encoding="utf-8"))
            payload["commands"]["run_trial"].remove("--require-external-evidence")
            plan_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    "benchmark/prepare_external_l4_trial.py",
                    "--verify-plan",
                    str(plan_path),
                    "--verify-plan-files",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(0, completed.returncode)
            self.assertIn("commands changed after plan was written", completed.stderr)

    def test_saved_trial_plan_rejects_relative_top_level_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "external-trial"
            prepare_external_l4_trial.prepare_workspace(TEMPLATE, workspace)
            plan_path = workspace / "trial_plan.json"
            payload = json.loads(plan_path.read_text(encoding="utf-8"))
            payload["template"] = "benchmark/handoff/external_lab_template.json"
            payload["workspace"] = "external-trial"
            payload["manifest"] = "external-trial/external_manifest.json"
            plan_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    "benchmark/prepare_external_l4_trial.py",
                    "--verify-plan",
                    str(plan_path),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )

        self.assertNotEqual(0, completed.returncode)
        self.assertIn("template must be an absolute path", completed.stderr)
        self.assertIn("workspace must be an absolute path", completed.stderr)
        self.assertIn("manifest must be an absolute path", completed.stderr)

    def test_saved_trial_plan_rejects_relative_generator_argv_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "external-trial"
            prepare_external_l4_trial.prepare_workspace(TEMPLATE, workspace)
            plan_path = workspace / "trial_plan.json"
            payload = json.loads(plan_path.read_text(encoding="utf-8"))
            payload["argv"][payload["argv"].index("--workspace") + 1] = "external-trial"
            payload["argv"].extend(["--template", "benchmark/handoff/external_lab_template.json"])
            plan_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with temporary_cwd(workspace):
                completed = subprocess.run(
                    [
                        sys.executable,
                        str(ROOT / "benchmark/prepare_external_l4_trial.py"),
                        "--verify-plan",
                        str(plan_path),
                    ],
                    text=True,
                    capture_output=True,
                )

        self.assertNotEqual(0, completed.returncode)
        self.assertIn("argv --workspace must be an absolute path", completed.stderr)
        self.assertIn("argv --template must be an absolute path", completed.stderr)

    def test_saved_trial_plan_rejects_command_tampering_without_file_checks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "external-trial"
            prepare_external_l4_trial.prepare_workspace(TEMPLATE, workspace)
            plan_path = workspace / "trial_plan.json"
            payload = json.loads(plan_path.read_text(encoding="utf-8"))
            payload["commands"]["validate_manifest"].remove("--check-files")
            plan_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    "benchmark/prepare_external_l4_trial.py",
                    "--verify-plan",
                    str(plan_path),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )

        self.assertNotEqual(0, completed.returncode)
        self.assertIn("commands changed after plan was written", completed.stderr)

    def test_saved_trial_plan_rejects_final_signoff_requirement_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "external-trial"
            prepare_external_l4_trial.prepare_workspace(TEMPLATE, workspace)
            plan_path = workspace / "trial_plan.json"
            payload = json.loads(plan_path.read_text(encoding="utf-8"))
            payload["final_signoff_requirements"][0]["status"] = "COMPLETE"
            plan_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    "benchmark/prepare_external_l4_trial.py",
                    "--verify-plan",
                    str(plan_path),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )

        self.assertNotEqual(0, completed.returncode)
        self.assertIn("final_signoff_requirements changed after plan was written", completed.stderr)

    def test_saved_trial_plan_rejects_final_signoff_command_binding_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "external-trial"
            prepare_external_l4_trial.prepare_workspace(TEMPLATE, workspace)
            plan_path = workspace / "trial_plan.json"
            payload = json.loads(plan_path.read_text(encoding="utf-8"))
            payload["final_signoff_requirements"][0]["required_for"] = "final_production_gate --out-json"
            final_gate = payload["commands"]["final_production_gate"]
            final_gate[final_gate.index("--external-trial-json") + 1] = str(workspace / "wrong-trial.json")
            plan_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    "benchmark/prepare_external_l4_trial.py",
                    "--verify-plan",
                    str(plan_path),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )

        self.assertNotEqual(0, completed.returncode)
        self.assertIn(
            "final_signoff_requirements.external_l4_workflow_trial required_for must be "
            "final_production_gate --external-trial-json",
            completed.stderr,
        )
        self.assertIn(
            "final_signoff_requirements.external_l4_workflow_trial planned_path must match "
            "final_production_gate --external-trial-json",
            completed.stderr,
        )

    def test_saved_trial_plan_rejects_pre_signoff_requirement_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "external-trial"
            prepare_external_l4_trial.prepare_workspace(TEMPLATE, workspace)
            plan_path = workspace / "trial_plan.json"
            payload = json.loads(plan_path.read_text(encoding="utf-8"))
            payload["pre_signoff_requirements"][1]["required_before"] = "production_signoff"
            plan_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    "benchmark/prepare_external_l4_trial.py",
                    "--verify-plan",
                    str(plan_path),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )

        self.assertNotEqual(0, completed.returncode)
        self.assertIn("pre_signoff_requirements changed after plan was written", completed.stderr)

    def test_saved_trial_plan_rejects_pre_signoff_command_binding_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "external-trial"
            prepare_external_l4_trial.prepare_workspace(TEMPLATE, workspace)
            plan_path = workspace / "trial_plan.json"
            payload = json.loads(plan_path.read_text(encoding="utf-8"))
            payload["pre_signoff_requirements"][0]["required_before"] = "verify_stable_release"
            payload["pre_signoff_requirements"][2]["required_before"] = "verify_stable_release"
            check_readiness = payload["commands"]["check_readiness"]
            check_readiness[check_readiness.index("--json-out") + 1] = str(workspace / "wrong-readiness.json")
            local_preflight = payload["commands"]["local_evidence_preflight"]
            local_preflight[local_preflight.index("--local-evidence-preflight-json") + 1] = str(
                workspace / "wrong-preflight.json"
            )
            trial_report = payload["commands"]["verify_trial_report"]
            trial_report[trial_report.index("--verify-report") + 1] = str(workspace / "wrong-trial-review.json")
            plan_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    "benchmark/prepare_external_l4_trial.py",
                    "--verify-plan",
                    str(plan_path),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )

        self.assertNotEqual(0, completed.returncode)
        self.assertIn(
            "pre_signoff_requirements.external_l4_readiness_precheck required_before must be run_trial",
            completed.stderr,
        )
        self.assertIn(
            "pre_signoff_requirements.external_l4_readiness_precheck planned_path must match "
            "check_readiness --json-out",
            completed.stderr,
        )
        self.assertIn(
            "pre_signoff_requirements.local_evidence_preflight_report planned_path must match "
            "local_evidence_preflight --local-evidence-preflight-json",
            completed.stderr,
        )
        self.assertIn(
            "pre_signoff_requirements.external_l4_trial_saved_reviewer_report required_before must be "
            "local_evidence_preflight",
            completed.stderr,
        )
        self.assertIn(
            "pre_signoff_requirements.external_l4_trial_saved_reviewer_report planned_path must match "
            "verify_trial_report --verify-report",
            completed.stderr,
        )

    def test_saved_trial_plan_rejects_external_evidence_command_flow_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "external-trial"
            prepare_external_l4_trial.prepare_workspace(TEMPLATE, workspace)
            plan_path = workspace / "trial_plan.json"
            payload = json.loads(plan_path.read_text(encoding="utf-8"))
            verify_trial = payload["commands"]["verify_trial"]
            verify_trial[verify_trial.index("--json-out") + 1] = str(workspace / "wrong-trial-review.json")
            verify_trial_report = payload["commands"]["verify_trial_report"]
            verify_trial_report[verify_trial_report.index("--verify-report") + 1] = str(
                workspace / "wrong-trial-review.json"
            )
            verify_trial_report.remove("--require-report-pass")
            verify_package = payload["commands"]["verify_package"]
            verify_package[2] = str(workspace / "wrong-package")
            verify_package_report = payload["commands"]["verify_package_report"]
            verify_package_report[verify_package_report.index("--verify-report") + 1] = str(
                workspace / "wrong-package-review.json"
            )
            verify_package_report.remove("--require-trial-json")
            final_report = payload["commands"]["verify_final_production_report"]
            final_report[2] = str(workspace / "wrong-production-claim.json")
            plan_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    "benchmark/prepare_external_l4_trial.py",
                    "--verify-plan",
                    str(plan_path),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )

        self.assertNotEqual(0, completed.returncode)
        self.assertIn("commands.verify_trial --json-out must match trial reviewer report", completed.stderr)
        self.assertIn("commands.verify_trial_report --verify-report must match trial reviewer report", completed.stderr)
        self.assertIn(
            "commands.verify_trial_report must include exactly one --require-report-pass",
            completed.stderr,
        )
        self.assertIn(
            "commands.verify_package positional evidence package directory must match",
            completed.stderr,
        )
        self.assertIn(
            "commands.verify_package_report --verify-report must match package reviewer report",
            completed.stderr,
        )
        self.assertIn(
            "commands.verify_package_report must include exactly one --require-trial-json",
            completed.stderr,
        )
        self.assertIn(
            "commands.verify_final_production_report positional final production claim report must match",
            completed.stderr,
        )

    def test_saved_trial_plan_rejects_stable_release_command_binding_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "external-trial"
            prepare_external_l4_trial.prepare_workspace(TEMPLATE, workspace)
            plan_path = workspace / "trial_plan.json"
            payload = json.loads(plan_path.read_text(encoding="utf-8"))
            verify_release = payload["commands"]["verify_stable_release"]
            verify_release[2] = "v0.1.0-rc.1"
            verify_release[verify_release.index("--repo") + 1] = "example/MorphoJet"
            stable_report = payload["commands"]["verify_stable_release_report"]
            stable_report.remove("--require-stable-report")
            stable_report[stable_report.index("--expect-tag") + 1] = "v0.1.0-rc.1"
            final_gate = payload["commands"]["final_production_gate"]
            final_gate[final_gate.index("--github-release-tag") + 1] = "v0.1.0-rc.1"
            plan_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    "benchmark/prepare_external_l4_trial.py",
                    "--verify-plan",
                    str(plan_path),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )

        self.assertNotEqual(0, completed.returncode)
        self.assertIn("commands.verify_stable_release tag must be v0.1.0", completed.stderr)
        self.assertIn("commands.verify_stable_release --repo must be benngaihk/MorphoJet", completed.stderr)
        self.assertIn(
            "commands.verify_stable_release_report must include exactly one --require-stable-report",
            completed.stderr,
        )
        self.assertIn("commands.verify_stable_release_report --expect-tag must be v0.1.0", completed.stderr)
        self.assertIn("commands.final_production_gate --github-release-tag must be v0.1.0", completed.stderr)

    def test_saved_trial_plan_rejects_external_evidence_requirement_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "external-trial"
            prepare_external_l4_trial.prepare_workspace(TEMPLATE, workspace)
            plan_path = workspace / "trial_plan.json"
            payload = json.loads(plan_path.read_text(encoding="utf-8"))
            payload["external_evidence_requirements"]["required_fields"].remove("reviewer_name_or_role")
            payload["external_evidence_requirements"]["manual_csv_editing"] = True
            payload["external_evidence_requirements"]["acceptance_criteria_min_count"] = 1
            payload["external_evidence_requirements"]["reviewed_at_utc"] = "optional"
            payload["external_evidence_requirements"]["placeholder_policy"] = "allow_placeholders"
            payload["external_evidence_requirements"]["enforced_by"] = ["validate_manifest"]
            plan_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    "benchmark/prepare_external_l4_trial.py",
                    "--verify-plan",
                    str(plan_path),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )

        self.assertNotEqual(0, completed.returncode)
        self.assertIn("external_evidence_requirements changed after plan was written", completed.stderr)
        self.assertIn(
            "external_evidence_requirements.required_fields must match the external signoff contract",
            completed.stderr,
        )
        self.assertIn("external_evidence_requirements.manual_csv_editing must be false", completed.stderr)
        self.assertIn("external_evidence_requirements.acceptance_criteria_min_count must be 3", completed.stderr)
        self.assertIn("external_evidence_requirements.reviewed_at_utc must require a UTC timestamp", completed.stderr)
        self.assertIn(
            "external_evidence_requirements.placeholder_policy must require replacing template placeholders",
            completed.stderr,
        )
        self.assertIn(
            "external_evidence_requirements.enforced_by must bind validate_manifest and run_trial",
            completed.stderr,
        )

    def test_saved_trial_plan_rejects_production_blocker_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "external-trial"
            prepare_external_l4_trial.prepare_workspace(TEMPLATE, workspace)
            plan_path = workspace / "trial_plan.json"
            payload = json.loads(plan_path.read_text(encoding="utf-8"))
            payload["production_claim_blockers"][0]["name"] = "external_l4_workflow_trial"
            payload["production_claim_blockers"][1]["status"] = "PASS"
            payload["production_claim_blockers"][2]["planned_paths"] = []
            payload["production_claim_blockers"].pop()
            plan_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    "benchmark/prepare_external_l4_trial.py",
                    "--verify-plan",
                    str(plan_path),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )

        self.assertNotEqual(0, completed.returncode)
        self.assertIn("production_claim_blockers changed after plan was written", completed.stderr)
        self.assertIn("production_claim_blockers must preserve the release-gate blocker order", completed.stderr)
        self.assertIn("production_claim_blockers.l3_provenance_hashes has invalid status", completed.stderr)
        self.assertIn(
            "production_claim_blockers.external_l4_workflow_trial planned_paths must be a non-empty string list",
            completed.stderr,
        )

    def test_saved_trial_plan_rejects_template_hash_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "external-trial"
            template = Path(tmp) / "template.json"
            template.write_text(TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8")
            prepare_external_l4_trial.prepare_workspace(template, workspace)
            plan_path = workspace / "trial_plan.json"
            payload = json.loads(template.read_text(encoding="utf-8"))
            payload["trial_id"] = "external-lab-supported-columns-handoff-v2"
            template.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    "benchmark/prepare_external_l4_trial.py",
                    "--verify-plan",
                    str(plan_path),
                    "--verify-plan-files",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(0, completed.returncode)
            self.assertIn("template_sha256 changed after plan was written", completed.stderr)

    def test_saved_trial_plan_rejects_readme_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "external-trial"
            prepare_external_l4_trial.prepare_workspace(TEMPLATE, workspace)
            plan_path = workspace / "trial_plan.json"
            readme_path = workspace / "README.md"
            readme_path.write_text(
                readme_path.read_text(encoding="utf-8").replace("--verify-plan-files", "--tampered"),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    "benchmark/prepare_external_l4_trial.py",
                    "--verify-plan",
                    str(plan_path),
                    "--verify-plan-files",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(0, completed.returncode)
            self.assertIn("README changed after plan was written", completed.stderr)

    def test_saved_trial_plan_rejects_chinese_readme_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "external-trial"
            prepare_external_l4_trial.prepare_workspace(TEMPLATE, workspace)
            plan_path = workspace / "trial_plan.json"
            readme_path = workspace / "README.zh-CN.md"
            readme_path.write_text(
                readme_path.read_text(encoding="utf-8").replace("--verify-plan-files", "--tampered"),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    "benchmark/prepare_external_l4_trial.py",
                    "--verify-plan",
                    str(plan_path),
                    "--verify-plan-files",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(0, completed.returncode)
            self.assertIn("Chinese README changed after plan was written", completed.stderr)

    def test_prepare_workspace_binds_custom_package_name_into_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "external-trial"

            plan = prepare_external_l4_trial.prepare_workspace(
                TEMPLATE,
                workspace,
                package_name="external review package",
            )

            self.assertEqual("external-review-package", plan["package_name"])
            command = plan["commands"]["check_readiness"]
            self.assertEqual("external-review-package", command[command.index("--package-name") + 1])

    def test_prepare_workspace_refuses_to_overwrite_generated_files_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "external-trial"
            prepare_external_l4_trial.prepare_workspace(TEMPLATE, workspace)

            with self.assertRaisesRegex(
                prepare_external_l4_trial.PrepareError,
                "generated workspace files already exist",
            ):
                prepare_external_l4_trial.prepare_workspace(TEMPLATE, workspace)

    def test_prepare_workspace_allows_explicit_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "external-trial"
            prepare_external_l4_trial.prepare_workspace(TEMPLATE, workspace)

            plan = prepare_external_l4_trial.prepare_workspace(TEMPLATE, workspace, overwrite=True)

            self.assertEqual(str((workspace / "external_manifest.json").resolve()), plan["manifest"])

    def test_prepare_workspace_refuses_stale_trial_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "external-trial"
            workspace.mkdir()
            (workspace / "handoff_trial.json").write_text("{}\n", encoding="utf-8")

            with self.assertRaisesRegex(
                prepare_external_l4_trial.PrepareError,
                "stale external L4 execution outputs already exist",
            ):
                prepare_external_l4_trial.prepare_workspace(TEMPLATE, workspace)

    def test_prepare_workspace_overwrite_refuses_stale_package_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "external-trial"
            prepare_external_l4_trial.prepare_workspace(TEMPLATE, workspace)
            package_dir = workspace / "evidence-package" / "external-l4-external-lab-supported-columns-handoff"
            package_dir.mkdir()

            with self.assertRaisesRegex(
                prepare_external_l4_trial.PrepareError,
                "stale external L4 execution outputs already exist",
            ):
                prepare_external_l4_trial.prepare_workspace(TEMPLATE, workspace, overwrite=True)

    def test_prepare_workspace_refuses_stale_final_production_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "external-trial"
            workspace.mkdir()
            (workspace / "github-release-verification.json").write_text("{}\n", encoding="utf-8")

            with self.assertRaisesRegex(
                prepare_external_l4_trial.PrepareError,
                "stale external L4 execution outputs already exist",
            ):
                prepare_external_l4_trial.prepare_workspace(TEMPLATE, workspace)


if __name__ == "__main__":
    unittest.main()
