#!/usr/bin/env python3
"""Unit tests for the internal external-L4 rehearsal runner."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmark"))
sys.path.insert(0, str(ROOT / "tests"))

import run_external_l4_rehearsal  # noqa: E402
from test_check_external_l4_readiness import write_valid_inputs  # noqa: E402


def write_rehearsal_template(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "trial_id": "minimal-rehearsal",
                "description": "Minimal internal rehearsal template.",
                "morphojet_objects_csv": "{base_dir}/morphojet/Objects.csv",
                "required_object_metadata_columns": ["Plate", "Well", "Site"],
                "exports": [
                    {
                        "name": "Cells",
                        "object_set": "Cells",
                        "channels": ["DNA", "PH3"],
                        "out_csv": "{base_dir}/morphojet/Cells.wide.csv",
                    }
                ],
                "downstream_checks": [
                    {
                        "name": "Validate Cells wide CSV downstream contract",
                        "command": [
                            "python3",
                            "benchmark/check_cellprofiler_wide_contract.py",
                            "{base_dir}/morphojet/Cells.wide.csv",
                            "--channels",
                            "DNA,PH3",
                            "--metadata-columns",
                            "Plate,Well,Site",
                            "--min-rows",
                            "1",
                            "--json-out",
                            "{base_dir}/handoff_contract.json",
                        ],
                        "artifacts": ["{base_dir}/handoff_contract.json"],
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


class RunExternalL4RehearsalTest(unittest.TestCase):
    def fake_command_sequence(self, plan: dict) -> list[run_external_l4_rehearsal.CommandResult]:
        workspace = Path(plan["workspace"])
        package_dir = workspace / "evidence-package" / plan["package_name"]
        package_dir.mkdir(parents=True, exist_ok=True)
        (workspace / "readiness.json").write_text(
            json.dumps(
                {
                    "status": "READY",
                    "claim_status": "NOT_PRODUCTION_CLAIM",
                    "evidence_scope": "EXTERNAL_L4_READINESS_PRECHECK",
                    "final_production_signoff": False,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        (package_dir / "artifact_manifest.json").write_text(
            json.dumps(
                {
                    "claim_status": "NOT_PRODUCTION_CLAIM",
                    "evidence_scope": "EXTERNAL_L4_EVIDENCE_PACKAGE",
                    "final_production_signoff": False,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        (package_dir / "README.md").write_text("English review entrypoint\n", encoding="utf-8")
        (package_dir / "README.zh-CN.md").write_text("中文 review entrypoint\n", encoding="utf-8")
        external_evidence = json.loads((workspace / "external_manifest.json").read_text(encoding="utf-8"))[
            "external_evidence"
        ]
        (workspace / "handoff_trial.json").write_text(
            json.dumps(
                {
                    "status": "PASS",
                    "claim_status": "NOT_PRODUCTION_CLAIM",
                    "evidence_scope": "EXTERNAL_L4_WORKFLOW_TRIAL",
                    "final_production_signoff": False,
                    "external_evidence": external_evidence,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        (workspace / "handoff_trial-verification.json").write_text('{"status":"PASS"}\n', encoding="utf-8")
        (workspace / "evidence-package-verification.json").write_text('{"status":"PASS"}\n', encoding="utf-8")
        (workspace / "local-evidence-preflight.json").write_text(
            json.dumps(
                {
                    "status": "PASS",
                    "validated_checks": [
                        "external_l4_workflow_trial",
                        "external_l4_evidence_package",
                        "external_l4_saved_reviewer_reports",
                    ],
                    "skipped_final_checks": [
                        "stable_github_release",
                        "stable_github_release_saved_report",
                        "production_claim_enforcement",
                    ],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return [
            run_external_l4_rehearsal.CommandResult(
                name=name,
                command=plan["commands"][name],
                status="PASS",
                elapsed_seconds=0.01,
                stdout="ok\n",
                stderr="",
            )
            for name in run_external_l4_rehearsal.COMMAND_SEQUENCE
        ]

    def test_runs_internal_rehearsal_through_local_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_inputs = root / "source-inputs"
            source_inputs.mkdir()
            (source_inputs / "morphojet").mkdir()
            (source_inputs / "cellprofiler").mkdir()
            write_valid_inputs(source_inputs)
            workspace = root / "rehearsal"
            template = root / "minimal-template.json"
            write_rehearsal_template(template)

            with (
                patch.object(run_external_l4_rehearsal.release_gate, "git_status_porcelain", return_value=[]),
                patch.object(run_external_l4_rehearsal, "run_command_sequence", side_effect=self.fake_command_sequence),
                contextlib.redirect_stdout(io.StringIO()) as stdout,
            ):
                status = run_external_l4_rehearsal.main(
                    [
                        "--workspace",
                        str(workspace),
                        "--template",
                        str(template),
                        "--morphojet-objects",
                        str(source_inputs / "morphojet" / "Objects.csv"),
                        "--cellprofiler-cells",
                        str(source_inputs / "cellprofiler" / "Cells.csv"),
                        "--package-name",
                        "external-l4-demo",
                    ]
                )

            self.assertEqual(0, status)
            self.assertIn("status=PASS", stdout.getvalue())
            summary = json.loads((workspace / "external-l4-rehearsal-summary.json").read_text(encoding="utf-8"))
            self.assertEqual("PASS", summary["status"])
            self.assertEqual("NOT_PRODUCTION_CLAIM", summary["claim_status"])
            self.assertEqual("EXTERNAL_L4_INTERNAL_REHEARSAL", summary["evidence_scope"])
            self.assertFalse(summary["final_production_signoff"])
            self.assertFalse(summary["final_evidence_acceptable"])
            self.assertEqual("PASS", summary["local_evidence_preflight_status"])
            self.assertEqual(run_external_l4_rehearsal.COMMAND_SEQUENCE, [entry["name"] for entry in summary["commands"]])
            self.assertEqual(run_external_l4_rehearsal.SKIPPED_FINAL_COMMANDS, summary["skipped_final_commands"])
            self.assertIn("stable_github_release", summary["skipped_final_checks"])
            self.assertIn("stable_github_release_saved_report", summary["skipped_final_checks"])
            self.assertTrue((workspace / "handoff_trial-verification.json").is_file())
            self.assertTrue((workspace / "evidence-package-verification.json").is_file())
            self.assertTrue((workspace / "local-evidence-preflight.json").is_file())
            self.assertTrue((workspace / "evidence-package" / "external-l4-demo" / "README.zh-CN.md").is_file())
            self.assertEqual("PASS", summary["output_files"]["package_readme_zh"]["exists"] and "PASS")
            self.assertRegex(summary["output_files"]["package_readme_zh"]["sha256"], r"^[0-9a-f]{64}$")

            trial = json.loads((workspace / "handoff_trial.json").read_text(encoding="utf-8"))
            self.assertEqual("NOT_PRODUCTION_CLAIM", trial["claim_status"])
            self.assertEqual("EXTERNAL_L4_WORKFLOW_TRIAL", trial["evidence_scope"])
            self.assertFalse(trial["final_production_signoff"])
            self.assertIn("Internal rehearsal only", trial["external_evidence"]["signoff_statement"])

    def test_saved_report_verification_rechecks_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_inputs = root / "source-inputs"
            source_inputs.mkdir()
            (source_inputs / "morphojet").mkdir()
            (source_inputs / "cellprofiler").mkdir()
            write_valid_inputs(source_inputs)
            workspace = root / "rehearsal"
            template = root / "minimal-template.json"
            write_rehearsal_template(template)

            with (
                patch.object(run_external_l4_rehearsal.release_gate, "git_status_porcelain", return_value=[]),
                patch.object(run_external_l4_rehearsal, "run_command_sequence", side_effect=self.fake_command_sequence),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                status = run_external_l4_rehearsal.main(
                    [
                        "--workspace",
                        str(workspace),
                        "--template",
                        str(template),
                        "--morphojet-objects",
                        str(source_inputs / "morphojet" / "Objects.csv"),
                        "--cellprofiler-cells",
                        str(source_inputs / "cellprofiler" / "Cells.csv"),
                        "--package-name",
                        "external-l4-demo",
                    ]
                )
            self.assertEqual(0, status)

            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                verify_status = run_external_l4_rehearsal.main(
                    [
                        "--verify-report",
                        str(workspace / "external-l4-rehearsal-summary.json"),
                        "--verify-report-files",
                        "--require-report-pass",
                    ]
                )

            self.assertEqual(0, verify_status)
            self.assertIn("external L4 rehearsal report ok", stdout.getvalue())

    def test_saved_report_verification_rejects_tampered_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_inputs = root / "source-inputs"
            source_inputs.mkdir()
            (source_inputs / "morphojet").mkdir()
            (source_inputs / "cellprofiler").mkdir()
            write_valid_inputs(source_inputs)
            workspace = root / "rehearsal"
            template = root / "minimal-template.json"
            write_rehearsal_template(template)

            with (
                patch.object(run_external_l4_rehearsal.release_gate, "git_status_porcelain", return_value=[]),
                patch.object(run_external_l4_rehearsal, "run_command_sequence", side_effect=self.fake_command_sequence),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                status = run_external_l4_rehearsal.main(
                    [
                        "--workspace",
                        str(workspace),
                        "--template",
                        str(template),
                        "--morphojet-objects",
                        str(source_inputs / "morphojet" / "Objects.csv"),
                        "--cellprofiler-cells",
                        str(source_inputs / "cellprofiler" / "Cells.csv"),
                        "--package-name",
                        "external-l4-demo",
                    ]
                )
            self.assertEqual(0, status)
            (workspace / "evidence-package" / "external-l4-demo" / "README.zh-CN.md").write_text(
                "tampered\n",
                encoding="utf-8",
            )

            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                verify_status = run_external_l4_rehearsal.main(
                    [
                        "--verify-report",
                        str(workspace / "external-l4-rehearsal-summary.json"),
                        "--verify-report-files",
                        "--require-report-pass",
                    ]
                )

            self.assertEqual(1, verify_status)
            self.assertIn("output_files.package_readme_zh.sha256", stderr.getvalue())

    def test_require_report_pass_requires_file_recheck(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summary = root / "summary.json"
            summary.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runner": run_external_l4_rehearsal.RUNNER,
                        "status": "PASS",
                        "claim_status": "NOT_PRODUCTION_CLAIM",
                        "evidence_scope": "EXTERNAL_L4_INTERNAL_REHEARSAL",
                        "final_production_signoff": False,
                        "final_evidence_acceptable": False,
                        "skipped_final_commands": run_external_l4_rehearsal.SKIPPED_FINAL_COMMANDS,
                        "commands": [
                            {"name": name, "status": "PASS"} for name in run_external_l4_rehearsal.COMMAND_SEQUENCE
                        ],
                        "metadata": {
                            "generated_at_utc": "2026-07-09T00:00:00+00:00",
                            "git_commit": "a" * 40,
                            "git_dirty": False,
                            "git_status": [],
                            "argv": [run_external_l4_rehearsal.RUNNER],
                        },
                        "workspace": str(root),
                        "source_template": str(root / "template.json"),
                        "prepared_template": str(root / "prepared.json"),
                        "trial_plan": str(root / "trial_plan.json"),
                        "handoff_trial_json": str(root / "handoff_trial.json"),
                        "evidence_package_dir": str(root / "package"),
                        "local_evidence_preflight_json": str(root / "local-evidence-preflight.json"),
                        "input_file_summaries": {},
                        "output_files": {},
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                verify_status = run_external_l4_rehearsal.main(
                    ["--verify-report", str(summary), "--require-report-pass"]
                )

            self.assertEqual(1, verify_status)
            self.assertIn("--require-report-pass requires --verify-report-files", stderr.getvalue())

    def test_overwrite_replaces_existing_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "rehearsal"
            workspace.mkdir()
            stale = workspace / "stale.txt"
            stale.write_text("stale\n", encoding="utf-8")

            source_inputs = root / "source-inputs"
            source_inputs.mkdir()
            (source_inputs / "morphojet").mkdir()
            (source_inputs / "cellprofiler").mkdir()
            write_valid_inputs(source_inputs)
            template = root / "minimal-template.json"
            write_rehearsal_template(template)

            with (
                patch.object(run_external_l4_rehearsal.release_gate, "git_status_porcelain", return_value=[]),
                patch.object(run_external_l4_rehearsal, "run_command_sequence", side_effect=self.fake_command_sequence),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                status = run_external_l4_rehearsal.main(
                    [
                        "--workspace",
                        str(workspace),
                        "--template",
                        str(template),
                        "--morphojet-objects",
                        str(source_inputs / "morphojet" / "Objects.csv"),
                        "--cellprofiler-cells",
                        str(source_inputs / "cellprofiler" / "Cells.csv"),
                        "--package-name",
                        "external-l4-demo",
                        "--overwrite",
                    ]
                )

            self.assertEqual(0, status)
            self.assertFalse(stale.exists())
            self.assertTrue((workspace / "external-l4-rehearsal-summary.json").is_file())

    def test_rejects_dirty_worktree_before_generating_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "rehearsal"
            template = root / "minimal-template.json"
            write_rehearsal_template(template)

            with (
                patch.object(run_external_l4_rehearsal.release_gate, "git_status_porcelain", return_value=[" M file"]),
                contextlib.redirect_stderr(io.StringIO()) as stderr,
            ):
                status = run_external_l4_rehearsal.main(
                    [
                        "--workspace",
                        str(workspace),
                        "--template",
                        str(template),
                    ]
                )

            self.assertEqual(1, status)
            self.assertIn("requires a clean git worktree", stderr.getvalue())
            self.assertFalse(workspace.exists())


if __name__ == "__main__":
    unittest.main()
