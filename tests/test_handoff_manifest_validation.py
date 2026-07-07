#!/usr/bin/env python3
"""Unit tests for handoff manifest validation."""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmark"))

import validate_handoff_manifest  # noqa: E402
import run_handoff_trial  # noqa: E402


def valid_manifest() -> dict:
    return {
        "trial_id": "external-lab-supported-columns-handoff",
        "morphojet_objects_csv": "morphojet/Objects.csv",
        "external_evidence": {
            "lab_or_org": "External Lab",
            "workflow_owner": "Assay Owner",
            "dataset_name": "Batch 42",
            "dataset_source": "LIMS export",
            "downstream_workflow": "Existing analysis notebook",
            "execution_environment": "macOS 15, Python 3.12",
            "reviewer_name_or_role": "External QA Reviewer",
            "reviewed_at_utc": "2026-07-03T01:02:03+00:00",
            "signoff_statement": "Reviewed against the lab workflow acceptance criteria.",
            "manual_csv_editing": False,
            "acceptance_criteria": [
                "Existing downstream workflow consumes MorphoJet output without manual CSV edits."
            ],
        },
        "exports": [
            {
                "name": "Cells",
                "object_set": "Cells",
                "channels": ["DNA"],
                "out_csv": "morphojet/Cells.wide.csv",
                "expected_cellprofiler_csv": "cellprofiler/Cells.csv",
                "comparison_report": "workflow_bridge.md",
                "comparison_json": "workflow_bridge.json",
            }
        ],
        "downstream_checks": [
            {
                "name": "Validate downstream contract",
                "command": ["python3", "benchmark/check_cellprofiler_wide_contract.py"],
                "artifacts": ["handoff_contract.json"],
            }
        ],
    }


class HandoffManifestValidationTest(unittest.TestCase):
    def test_external_evidence_manifest_passes(self) -> None:
        issues = validate_handoff_manifest.validate_schema(
            valid_manifest(),
            require_downstream_check=True,
            require_external_evidence=True,
        )

        self.assertEqual([], issues)

    def test_external_evidence_is_required_for_l4_trial(self) -> None:
        manifest = valid_manifest()
        del manifest["external_evidence"]

        issues = validate_handoff_manifest.validate_schema(
            manifest,
            require_downstream_check=True,
            require_external_evidence=True,
        )

        self.assertIn(
            "manifest.external_evidence must be an object for an external workflow trial",
            issues,
        )

    def test_handoff_runner_strict_mode_requires_external_evidence_before_execution(self) -> None:
        manifest = valid_manifest()
        del manifest["external_evidence"]

        with self.assertRaises(SystemExit) as context:
            run_handoff_trial.validate_manifest(manifest, require_external_evidence=True)

        self.assertIn(
            "ERROR: manifest.external_evidence must be an object for an external workflow trial",
            str(context.exception),
        )

    def test_handoff_runner_default_mode_keeps_local_preflight_compatible(self) -> None:
        manifest = valid_manifest()
        del manifest["external_evidence"]

        run_handoff_trial.validate_manifest(manifest)

    def test_handoff_runner_records_canonical_argv(self) -> None:
        args = Namespace(
            manifest=Path("manifest.json"),
            out_json=Path("reports/handoff_trial.json"),
            out_md=Path("reports/handoff_trial.md"),
            readiness_report=Path("reports/readiness.json"),
            require_external_evidence=True,
        )

        argv = run_handoff_trial.canonical_argv(args, {"z": "last", "a": "first"})

        self.assertEqual(
            [
                "benchmark/run_handoff_trial.py",
                "manifest.json",
                "--var",
                "a=first",
                "--var",
                "z=last",
                "--readiness-report",
                "reports/readiness.json",
                "--out-json",
                "reports/handoff_trial.json",
                "--out-md",
                "reports/handoff_trial.md",
                "--require-external-evidence",
            ],
            argv,
        )

    def test_handoff_runner_readiness_summary_preserves_package_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "readiness.json"
            report.write_text(
                json.dumps(
                    {
                        "status": "READY",
                        "claim_status": "NOT_PRODUCTION_CLAIM",
                        "generated_at_utc": "2026-07-07T01:02:03+00:00",
                        "workspace": str(Path(tmp).resolve()),
                        "manifest": str((Path(tmp) / "external_manifest.json").resolve()),
                        "package_name": "external-l4-demo",
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            with patch("run_handoff_trial.subprocess.run") as run:
                run.return_value.returncode = 0
                run.return_value.stdout = "readiness report ok\n"
                run.return_value.stderr = ""
                summary = run_handoff_trial.validate_readiness_report(report)

        self.assertEqual("external-l4-demo", summary["package_name"])

    def test_handoff_runner_rejects_report_output_over_manifest_input(self) -> None:
        with self.assertRaises(SystemExit) as context:
            run_handoff_trial.validate_report_outputs(
                Path("manifest.json"),
                valid_manifest(),
                Path("morphojet/Objects.csv"),
                Path("handoff_trial.md"),
            )

        self.assertIn(
            "ERROR: report output --out-json must not overwrite manifest input: morphojet/Objects.csv",
            str(context.exception),
        )

    def test_handoff_runner_rejects_report_output_over_declared_artifact(self) -> None:
        with self.assertRaises(SystemExit) as context:
            run_handoff_trial.validate_report_outputs(
                Path("manifest.json"),
                valid_manifest(),
                Path("handoff_trial.json"),
                Path("workflow_bridge.md"),
            )

        self.assertIn(
            "ERROR: report output --out-md must not overwrite manifest artifact: workflow_bridge.md",
            str(context.exception),
        )

    def test_handoff_runner_report_outputs_must_be_distinct(self) -> None:
        with self.assertRaises(SystemExit) as context:
            run_handoff_trial.validate_report_outputs(
                Path("manifest.json"),
                valid_manifest(),
                Path("handoff_trial.json"),
                Path("./handoff_trial.json"),
            )

        self.assertIn(
            "ERROR: report outputs --out-json and --out-md must be different paths",
            str(context.exception),
        )

    def test_manual_csv_editing_must_be_false(self) -> None:
        manifest = copy.deepcopy(valid_manifest())
        manifest["external_evidence"]["manual_csv_editing"] = True

        issues = validate_handoff_manifest.validate_schema(
            manifest,
            require_downstream_check=True,
            require_external_evidence=True,
        )

        self.assertIn("external_evidence.manual_csv_editing must be false", issues)

    def test_external_evidence_placeholders_are_rejected_for_real_trials(self) -> None:
        manifest = copy.deepcopy(valid_manifest())
        manifest["external_evidence"]["dataset_source"] = "REPLACE_WITH_SOURCE"

        issues = validate_handoff_manifest.validate_schema(
            manifest,
            require_downstream_check=True,
            require_external_evidence=True,
        )

        self.assertIn(
            "external_evidence.dataset_source must replace template placeholder text",
            issues,
        )

    def test_acceptance_criteria_placeholders_are_rejected_for_real_trials(self) -> None:
        manifest = copy.deepcopy(valid_manifest())
        manifest["external_evidence"]["acceptance_criteria"] = ["REPLACE_WITH_ACCEPTANCE_CRITERION"]

        issues = validate_handoff_manifest.validate_schema(
            manifest,
            require_downstream_check=True,
            require_external_evidence=True,
        )

        self.assertIn(
            "external_evidence.acceptance_criteria[0] must replace template placeholder text",
            issues,
        )

    def test_external_signoff_fields_are_required_for_real_trials(self) -> None:
        manifest = copy.deepcopy(valid_manifest())
        del manifest["external_evidence"]["reviewer_name_or_role"]
        manifest["external_evidence"]["reviewed_at_utc"] = "2026-07-03T01:02:03"
        manifest["external_evidence"]["signoff_statement"] = "REPLACE_WITH_SIGNOFF"

        issues = validate_handoff_manifest.validate_schema(
            manifest,
            require_downstream_check=True,
            require_external_evidence=True,
        )

        self.assertIn("external_evidence.reviewer_name_or_role must be a non-empty string", issues)
        self.assertIn("external_evidence.reviewed_at_utc must include timezone", issues)
        self.assertIn("external_evidence.signoff_statement must replace template placeholder text", issues)

    def test_external_reviewed_at_must_be_iso_datetime(self) -> None:
        manifest = copy.deepcopy(valid_manifest())
        manifest["external_evidence"]["reviewed_at_utc"] = "not-a-date"

        issues = validate_handoff_manifest.validate_schema(
            manifest,
            require_downstream_check=True,
            require_external_evidence=True,
        )

        self.assertIn("external_evidence.reviewed_at_utc is invalid: not-a-date", issues)

    def test_external_reviewed_at_must_be_utc(self) -> None:
        manifest = copy.deepcopy(valid_manifest())
        manifest["external_evidence"]["reviewed_at_utc"] = "2026-07-03T09:02:03+08:00"

        issues = validate_handoff_manifest.validate_schema(
            manifest,
            require_downstream_check=True,
            require_external_evidence=True,
        )

        self.assertIn("external_evidence.reviewed_at_utc must be UTC", issues)

    def test_external_evidence_placeholders_are_allowed_for_template_validation(self) -> None:
        manifest = copy.deepcopy(valid_manifest())
        manifest["external_evidence"]["dataset_source"] = "REPLACE_WITH_SOURCE"
        manifest["external_evidence"]["acceptance_criteria"] = ["REPLACE_WITH_ACCEPTANCE_CRITERION"]
        manifest["external_evidence"]["reviewed_at_utc"] = "REPLACE_WITH_REVIEWED_AT"

        issues = validate_handoff_manifest.validate_schema(
            manifest,
            require_downstream_check=True,
            require_external_evidence=True,
            allow_external_evidence_placeholders=True,
        )

        self.assertEqual([], issues)

    def test_output_paths_must_not_be_duplicated(self) -> None:
        manifest = copy.deepcopy(valid_manifest())
        manifest["downstream_checks"][0]["artifacts"] = ["workflow_bridge.json"]

        issues = validate_handoff_manifest.validate_schema(
            manifest,
            require_downstream_check=True,
            require_external_evidence=True,
        )

        self.assertIn("output path is duplicated: workflow_bridge.json", issues)

    def test_equivalent_output_paths_must_not_be_duplicated(self) -> None:
        manifest = copy.deepcopy(valid_manifest())
        manifest["downstream_checks"][0]["artifacts"] = ["./workflow_bridge.json"]

        issues = validate_handoff_manifest.validate_schema(
            manifest,
            require_downstream_check=True,
            require_external_evidence=True,
        )

        self.assertIn("output path is duplicated: ./workflow_bridge.json", issues)

    def test_output_paths_must_not_overwrite_inputs(self) -> None:
        manifest = copy.deepcopy(valid_manifest())
        manifest["exports"][0]["out_csv"] = "cellprofiler/Cells.csv"

        issues = validate_handoff_manifest.validate_schema(
            manifest,
            require_downstream_check=True,
            require_external_evidence=True,
        )

        self.assertIn("output path must not overwrite an input file: cellprofiler/Cells.csv", issues)

    def test_missing_top_level_objects_csv_reports_schema_issue_without_crashing(self) -> None:
        manifest = copy.deepcopy(valid_manifest())
        del manifest["morphojet_objects_csv"]

        issues = validate_handoff_manifest.validate_schema(
            manifest,
            require_downstream_check=True,
            require_external_evidence=True,
        )

        self.assertIn("manifest.morphojet_objects_csv must be a non-empty string", issues)


if __name__ == "__main__":
    unittest.main()
