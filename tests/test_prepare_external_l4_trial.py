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
            requirements = plan["final_signoff_requirements"]
            requirement_by_name = {requirement["name"]: requirement for requirement in requirements}
            self.assertEqual(
                str((workspace / "handoff_trial.json").resolve()),
                requirement_by_name["external_l4_workflow_trial"]["planned_path"],
            )
            self.assertEqual("verify_trial", requirement_by_name["external_l4_workflow_trial"]["verification_step"])
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
                "verify_final_production_report",
                requirement_by_name["final_production_claim_report"]["verification_step"],
            )
            readme = (workspace / "README.md").read_text(encoding="utf-8")
            self.assertIn("Language: English | [简体中文](README.zh-CN.md)", readme)
            self.assertIn("## final_signoff_requirements", readme)
            self.assertIn("external_l4_workflow_trial", readme)
            self.assertLess(readme.index("## verify_plan"), readme.index("## validate_manifest"))
            self.assertLess(readme.index("## verify_readiness"), readme.index("## run_trial"))
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
            self.assertIn("## final_signoff_requirements", readme_zh)
            self.assertLess(readme_zh.index("## verify_plan"), readme_zh.index("## validate_manifest"))
            self.assertLess(readme_zh.index("## verify_readiness"), readme_zh.index("## run_trial"))
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
