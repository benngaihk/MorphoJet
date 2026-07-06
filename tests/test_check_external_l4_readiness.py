#!/usr/bin/env python3
"""Unit tests for external L4 workspace readiness checks."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmark"))

import check_external_l4_readiness  # noqa: E402
import prepare_external_l4_trial  # noqa: E402


TEMPLATE = ROOT / "benchmark/handoff/external_lab_template.json"


def fill_external_evidence(manifest: dict) -> None:
    evidence = manifest["external_evidence"]
    evidence.update(
        {
            "lab_or_org": "External Lab",
            "workflow_owner": "Assay Owner",
            "dataset_name": "Batch 42",
            "dataset_source": "LIMS export",
            "downstream_workflow": "Existing analysis notebook",
            "execution_environment": "macOS 15, Python 3.12",
            "reviewer_name_or_role": "External QA Reviewer",
            "reviewed_at_utc": "2026-07-03T01:02:03+00:00",
            "signoff_statement": "Reviewed against the lab workflow acceptance criteria.",
        }
    )


class ExternalL4ReadinessTest(unittest.TestCase):
    def test_unfilled_workspace_is_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "external-trial"
            prepare_external_l4_trial.prepare_workspace(TEMPLATE, workspace)

            payload = check_external_l4_readiness.readiness_report(workspace)

            self.assertEqual("NOT_READY", payload["status"])
            self.assertEqual("NOT_PRODUCTION_CLAIM", payload["claim_status"])
            self.assertIn(
                "external_evidence.lab_or_org must replace template placeholder text",
                payload["issues"],
            )
            self.assertIn(
                f"required input file does not exist: {workspace}/morphojet/Objects.csv",
                payload["issues"],
            )

    def test_filled_workspace_with_inputs_is_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "external-trial"
            prepare_external_l4_trial.prepare_workspace(TEMPLATE, workspace)
            manifest_path = workspace / "external_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            fill_external_evidence(manifest)
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            (workspace / "morphojet" / "Objects.csv").write_text("ok\n", encoding="utf-8")
            (workspace / "cellprofiler" / "Cells.csv").write_text("ok\n", encoding="utf-8")

            payload = check_external_l4_readiness.readiness_report(workspace)

            self.assertEqual("READY", payload["status"])
            self.assertEqual([], payload["issues"])
            self.assertTrue(all(check["status"] == "PASS" for check in payload["checks"]))

    def test_existing_package_output_blocks_default_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "external-trial"
            prepare_external_l4_trial.prepare_workspace(TEMPLATE, workspace)
            manifest_path = workspace / "external_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            fill_external_evidence(manifest)
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            (workspace / "morphojet" / "Objects.csv").write_text("ok\n", encoding="utf-8")
            (workspace / "cellprofiler" / "Cells.csv").write_text("ok\n", encoding="utf-8")
            package_dir = workspace / "evidence-package" / "external-l4-external-lab-supported-columns-handoff"
            package_dir.mkdir()

            payload = check_external_l4_readiness.readiness_report(workspace)

            self.assertEqual("NOT_READY", payload["status"])
            self.assertIn(f"package output already exists: {package_dir}", payload["issues"])


if __name__ == "__main__":
    unittest.main()
