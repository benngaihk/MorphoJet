#!/usr/bin/env python3
"""Unit tests for production evidence readiness audits."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmark"))

import audit_production_evidence  # noqa: E402
import release_gate  # noqa: E402


def pass_gate(name: str) -> release_gate.Gate:
    return release_gate.Gate(name=name, command=None, status="PASS", elapsed_seconds=0.0, detail=f"{name} ok")


class AuditProductionEvidenceTest(unittest.TestCase):
    COMMIT = "a" * 40

    def patch_repo_state(self):
        return (
            patch.object(audit_production_evidence.release_gate, "git_commit", return_value=self.COMMIT),
            patch.object(audit_production_evidence.release_gate, "git_status_porcelain", return_value=[]),
            patch.object(
                audit_production_evidence.release_gate,
                "validate_clean_git_worktree",
                return_value=pass_gate("Require clean git worktree"),
            ),
            patch.object(
                audit_production_evidence.release_gate,
                "validate_l3_provenance_artifact",
                return_value=pass_gate("Validate CellBinDB L3 provenance"),
            ),
        )

    def test_missing_evidence_stays_non_final_and_incomplete(self) -> None:
        args = audit_production_evidence.parse_args([])

        with self.patch_repo_state()[0], self.patch_repo_state()[1], self.patch_repo_state()[2], self.patch_repo_state()[3]:
            payload = audit_production_evidence.build_payload(args)

        self.assertEqual("PASS", payload["status"])
        self.assertEqual("INCOMPLETE", payload["production_claim_status"])
        self.assertEqual("NOT_PRODUCTION_CLAIM", payload["claim_status"])
        self.assertEqual("PRODUCTION_EVIDENCE_READINESS_AUDIT", payload["evidence_scope"])
        self.assertIs(payload["final_production_signoff"], False)
        self.assertEqual(
            [
                "github_actions_workflow_verification",
                "external_l4_workflow_trial",
                "external_l4_evidence_package",
                "external_l4_saved_reviewer_reports",
                "stable_github_release",
                "stable_github_release_saved_report",
            ],
            payload["missing_or_failed_checks"],
        )
        self.assertEqual([], audit_production_evidence.validate_payload(payload))

    def test_all_audited_evidence_passes_and_renders_final_wrapper_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "production-evidence-audit.json"
            final_input_files = [
                root / "external" / "handoff_trial.json",
                root / "reports" / "trial-review.json",
                root / "reports" / "package-review.json",
                root / "reports" / "github-release.json",
                root / "reports" / "github-workflows.json",
            ]
            for path in final_input_files:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(f"{path.name}\n", encoding="utf-8")
            expected_trial_sha = release_gate.sha256_file(root / "external" / "handoff_trial.json")
            args = audit_production_evidence.parse_args(
                [
                    "--external-trial-json",
                    str(root / "external" / "handoff_trial.json"),
                    "--external-trial-root",
                    str(root / "external"),
                    "--external-evidence-package-dir",
                    str(root / "evidence" / "external-l4-trial"),
                    "--external-trial-verification-report",
                    str(root / "reports" / "trial-review.json"),
                    "--external-evidence-package-verification-report",
                    str(root / "reports" / "package-review.json"),
                    "--github-release-verification-report",
                    str(root / "reports" / "github-release.json"),
                    "--github-workflow-verification-report",
                    str(root / "reports" / "github-workflows.json"),
                    "--verify-live-github-release",
                    "--out-json",
                    str(report),
                    "--out-md",
                    str(root / "production-evidence-audit.md"),
                ]
            )

            with (
                self.patch_repo_state()[0],
                self.patch_repo_state()[1],
                self.patch_repo_state()[2],
                self.patch_repo_state()[3],
                patch.object(
                    audit_production_evidence.release_gate,
                    "validate_external_trial_report",
                    return_value=pass_gate("Validate external L4 workflow trial report"),
                ),
                patch.object(
                    audit_production_evidence.release_gate,
                    "validate_external_evidence_package",
                    return_value=pass_gate("Validate external L4 evidence package"),
                ),
                patch.object(
                    audit_production_evidence,
                    "external_saved_reviewer_gates",
                    return_value=[
                        pass_gate("Verify saved external L4 trial report"),
                        pass_gate("Verify saved external L4 evidence package report"),
                    ],
                ),
                patch.object(
                    audit_production_evidence,
                    "verify_saved_github_workflow_gate",
                    return_value=pass_gate("Verify saved GitHub Actions workflow report"),
                ),
                patch.object(
                    audit_production_evidence,
                    "live_github_release_gate",
                    return_value=pass_gate("Verify GitHub release assets"),
                ),
                patch.object(
                    audit_production_evidence,
                    "verify_saved_github_release_gate",
                    return_value=pass_gate("Verify saved stable GitHub release report"),
                ),
            ):
                payload = audit_production_evidence.build_payload(args)
                failures = audit_production_evidence.validate_payload(
                    payload,
                    require_ready=True,
                    verify_files=True,
                    report_path=report,
                )

        self.assertEqual("PASS", payload["status"])
        self.assertEqual("PASS", payload["production_claim_status"])
        self.assertEqual([], payload["missing_or_failed_checks"])
        command = payload["metadata"]["final_wrapper_command"]
        self.assertIn("benchmark/run_production_gate.py", command)
        self.assertIn("--github-workflow-verification-report", command)
        self.assertIn("--production-evidence-audit-report", command)
        self.assertEqual(
            str(report.resolve()),
            command[command.index("--production-evidence-audit-report") + 1],
        )
        input_file_by_name = {item["name"]: item for item in payload["input_files"]}
        self.assertEqual(
            expected_trial_sha,
            input_file_by_name["external_trial_json"]["sha256"],
        )
        self.assertTrue(input_file_by_name["github_workflow_verification_report"]["exists"])
        self.assertEqual([], failures)

    def test_require_ready_requires_file_recheck(self) -> None:
        args = audit_production_evidence.parse_args([])
        with self.patch_repo_state()[0], self.patch_repo_state()[1], self.patch_repo_state()[2], self.patch_repo_state()[3]:
            payload = audit_production_evidence.build_payload(args)

        failures = audit_production_evidence.validate_payload(payload, require_ready=True)

        self.assertIn("--require-ready requires --verify-report-files", failures)

    def test_file_recheck_rejects_audit_argv_tampering(self) -> None:
        args = audit_production_evidence.parse_args([])
        with self.patch_repo_state()[0], self.patch_repo_state()[1], self.patch_repo_state()[2], self.patch_repo_state()[3]:
            payload = audit_production_evidence.build_payload(args)

        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "audit.json"
            payload["metadata"]["argv"][payload["metadata"]["argv"].index("--out-json") + 1] = str(
                Path(tmp) / "other-audit.json"
            )

            failures = audit_production_evidence.validate_payload(
                payload,
                verify_files=True,
                report_path=report,
            )

        self.assertIn(
            f"metadata.argv --out-json must match verified audit report path: {Path(tmp) / 'other-audit.json'}",
            failures,
        )

    def test_file_recheck_rejects_final_wrapper_command_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "production-evidence-audit.json"
            args = audit_production_evidence.parse_args(
                [
                    "--external-trial-json",
                    str(root / "external" / "handoff_trial.json"),
                    "--external-trial-root",
                    str(root / "external"),
                    "--external-evidence-package-dir",
                    str(root / "evidence" / "external-l4-trial"),
                    "--external-trial-verification-report",
                    str(root / "reports" / "trial-review.json"),
                    "--external-evidence-package-verification-report",
                    str(root / "reports" / "package-review.json"),
                    "--github-release-verification-report",
                    str(root / "reports" / "github-release.json"),
                    "--github-workflow-verification-report",
                    str(root / "reports" / "github-workflows.json"),
                    "--out-json",
                    str(report),
                    "--out-md",
                    str(root / "production-evidence-audit.md"),
                ]
            )

            with (
                self.patch_repo_state()[0],
                self.patch_repo_state()[1],
                self.patch_repo_state()[2],
                self.patch_repo_state()[3],
            ):
                payload = audit_production_evidence.build_payload(args)
                payload["metadata"]["final_wrapper_command"][
                    payload["metadata"]["final_wrapper_command"].index("--external-trial-json") + 1
                ] = str(root / "other" / "handoff_trial.json")
                failures = audit_production_evidence.validate_payload(
                    payload,
                    verify_files=True,
                    report_path=report,
                )

        self.assertIn("metadata.final_wrapper_command changed after recomputing audit evidence", failures)

    def test_file_recheck_rejects_input_file_hash_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = root / "external" / "handoff_trial.json"
            trial_json.parent.mkdir(parents=True, exist_ok=True)
            trial_json.write_text("{}\n", encoding="utf-8")
            report = root / "production-evidence-audit.json"
            args = audit_production_evidence.parse_args(
                [
                    "--external-trial-json",
                    str(trial_json),
                    "--out-json",
                    str(report),
                    "--out-md",
                    str(root / "production-evidence-audit.md"),
                ]
            )

            with (
                self.patch_repo_state()[0],
                self.patch_repo_state()[1],
                self.patch_repo_state()[2],
                self.patch_repo_state()[3],
            ):
                payload = audit_production_evidence.build_payload(args)
                payload["input_files"][0]["sha256"] = "0" * 64
                failures = audit_production_evidence.validate_payload(
                    payload,
                    verify_files=True,
                    report_path=report,
                )

        self.assertIn("input_files changed after recomputing audit evidence", failures)

    def test_saved_report_verifier_rejects_final_signoff_claim(self) -> None:
        payload = {
            "schema_version": 1,
            "auditor": "benchmark/audit_production_evidence.py",
            "generated_at_utc": "2026-07-03T00:00:00+00:00",
            "claim_status": "NOT_PRODUCTION_CLAIM",
            "evidence_scope": "PRODUCTION_EVIDENCE_READINESS_AUDIT",
            "final_production_signoff": True,
            "status": "PASS",
            "production_claim_status": "INCOMPLETE",
            "missing_or_failed_checks": [],
            "checks": [],
            "input_files": [],
            "metadata": {"argv": ["benchmark/audit_production_evidence.py"]},
        }

        failures = audit_production_evidence.validate_payload(payload)

        self.assertIn("final_production_signoff must be false", failures)

    def test_verify_report_accepts_saved_non_final_audit(self) -> None:
        args = audit_production_evidence.parse_args([])
        with self.patch_repo_state()[0], self.patch_repo_state()[1], self.patch_repo_state()[2], self.patch_repo_state()[3]:
            payload = audit_production_evidence.build_payload(args)

        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "audit.json"
            report.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            status = audit_production_evidence.verify_report(report)

        self.assertEqual(0, status)


if __name__ == "__main__":
    unittest.main()
