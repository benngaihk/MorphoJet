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
import check_cellprofiler_wide_contract  # noqa: E402
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


def write_valid_inputs(workspace: Path) -> None:
    object_columns = check_external_l4_readiness.required_morphojet_objects_columns()
    rows = []
    for channel in ["DNA", "PH3"]:
        row = {column: "1" for column in object_columns}
        row.update(
            {
                "ImageNumber": "1",
                "ObjectNumber": "1",
                "Channel": channel,
                "ObjectSet": "Cells",
                "AreaShape_BoundingBoxMinimum_X": "0",
                "AreaShape_BoundingBoxMinimum_Y": "0",
                "AreaShape_BoundingBoxMaximum_X": "2",
                "AreaShape_BoundingBoxMaximum_Y": "2",
                "AreaShape_Solidity": "1",
            }
        )
        rows.append(row)
    objects_path = workspace / "morphojet" / "Objects.csv"
    objects_path.write_text(
        ",".join(object_columns)
        + "\n"
        + "\n".join(",".join(row[column] for column in object_columns) for row in rows)
        + "\n",
        encoding="utf-8",
    )
    expected_columns = check_cellprofiler_wide_contract.required_columns(["DNA", "PH3"])
    (workspace / "cellprofiler" / "Cells.csv").write_text(
        ",".join(expected_columns)
        + "\n"
        + ",".join("1" for _ in expected_columns)
        + "\n",
        encoding="utf-8",
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
            write_valid_inputs(workspace)

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
            write_valid_inputs(workspace)
            package_dir = workspace / "evidence-package" / "external-l4-external-lab-supported-columns-handoff"
            package_dir.mkdir()

            payload = check_external_l4_readiness.readiness_report(workspace)

            self.assertEqual("NOT_READY", payload["status"])
            self.assertIn(f"package output already exists: {package_dir}", payload["issues"])

    def test_invalid_input_csv_schema_is_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "external-trial"
            prepare_external_l4_trial.prepare_workspace(TEMPLATE, workspace)
            manifest_path = workspace / "external_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            fill_external_evidence(manifest)
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            (workspace / "morphojet" / "Objects.csv").write_text("ImageNumber,ObjectNumber\n1,1\n", encoding="utf-8")
            (workspace / "cellprofiler" / "Cells.csv").write_text("ImageNumber,ObjectNumber\n1,1\n", encoding="utf-8")

            payload = check_external_l4_readiness.readiness_report(workspace)

            self.assertEqual("NOT_READY", payload["status"])
            self.assertTrue(
                any(issue.startswith("MorphoJet objects CSV missing columns") for issue in payload["issues"])
            )
            self.assertTrue(
                any(issue.startswith("expected CellProfiler CSV missing columns") for issue in payload["issues"])
            )


if __name__ == "__main__":
    unittest.main()
