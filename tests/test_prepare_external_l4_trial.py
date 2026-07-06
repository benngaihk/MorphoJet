#!/usr/bin/env python3
"""Unit tests for external L4 trial workspace preparation."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmark"))

import prepare_external_l4_trial  # noqa: E402


TEMPLATE = ROOT / "benchmark/handoff/external_lab_template.json"


class PrepareExternalL4TrialTest(unittest.TestCase):
    def test_prepare_workspace_writes_manifest_plan_and_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "external-trial"

            plan = prepare_external_l4_trial.prepare_workspace(TEMPLATE, workspace)

            self.assertEqual("NOT_PRODUCTION_CLAIM", plan["claim_status"])
            generated_at = datetime.fromisoformat(plan["generated_at_utc"])
            self.assertIsNotNone(generated_at.tzinfo)
            self.assertEqual(
                [
                    "benchmark/prepare_external_l4_trial.py",
                    "--workspace",
                    str(workspace),
                    "--template",
                    str(TEMPLATE),
                ],
                plan["argv"],
            )
            self.assertEqual(TEMPLATE.stat().st_size, plan["template_size_bytes"])
            self.assertEqual(prepare_external_l4_trial.sha256(TEMPLATE), plan["template_sha256"])
            self.assertTrue((workspace / "external_manifest.json").is_file())
            self.assertTrue((workspace / "trial_plan.json").is_file())
            self.assertTrue((workspace / "README.md").is_file())
            self.assertTrue((workspace / "morphojet").is_dir())
            self.assertTrue((workspace / "cellprofiler").is_dir())
            self.assertTrue((workspace / "evidence-package").is_dir())
            self.assertEqual(
                json.loads(TEMPLATE.read_text(encoding="utf-8")),
                json.loads((workspace / "external_manifest.json").read_text(encoding="utf-8")),
            )
            run_command = plan["commands"]["run_trial"]
            self.assertIn("--require-external-evidence", run_command)
            self.assertIn(f"base_dir={workspace}", run_command)
            self.assertEqual(str(workspace / "handoff_trial.json"), run_command[run_command.index("--out-json") + 1])
            self.assertEqual(str(workspace), plan["commands"]["check_readiness"][3])
            self.assertEqual(plan["package_name"], plan["commands"]["check_readiness"][5])
            verify_readiness = plan["commands"]["verify_readiness"]
            self.assertEqual(
                str(workspace / "readiness.json"),
                verify_readiness[verify_readiness.index("--verify-report") + 1],
            )
            self.assertIn("--verify-report-files", verify_readiness)
            self.assertIn("--require-ready", verify_readiness)
            self.assertIn("--local-evidence-preflight-only", plan["commands"]["local_evidence_preflight"])
            readme = (workspace / "README.md").read_text(encoding="utf-8")
            self.assertLess(readme.index("## verify_readiness"), readme.index("## run_trial"))

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
                    str(workspace),
                    "--template",
                    str(TEMPLATE),
                    "--package-name",
                    "external review package",
                ],
                plan["argv"],
            )

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

            self.assertEqual(str(workspace / "external_manifest.json"), plan["manifest"])

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


if __name__ == "__main__":
    unittest.main()
