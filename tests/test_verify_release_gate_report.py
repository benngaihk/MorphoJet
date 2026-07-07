#!/usr/bin/env python3
"""Unit tests for saved release-gate report verification."""

from __future__ import annotations

import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmark"))

import release_gate  # noqa: E402
import verify_release_gate_report  # noqa: E402


class VerifyReleaseGateReportTest(unittest.TestCase):
    def production_args(self, **overrides: object) -> Namespace:
        values = {
            "require_clean_git": False,
            "require_l3_provenance": False,
            "external_trial_json": None,
            "external_trial_root": None,
            "external_evidence_package_dir": None,
            "external_trial_verification_report": None,
            "external_evidence_package_verification_report": None,
            "verify_github_release": None,
            "github_release_kind": "prerelease",
            "github_release_verification_report": None,
            "require_production_claim": False,
            "out_json": Path("release-gate.json"),
            "out_md": Path("release-gate.md"),
        }
        values.update(overrides)
        return Namespace(**values)

    def production_gates(self, names: list[str]) -> list[release_gate.Gate]:
        return [release_gate.Gate(name, None, "PASS", 0.0, "ok") for name in names]

    def production_metadata(self) -> dict:
        return {
            "generated_at_utc": "2026-07-03T00:00:00+00:00",
            "git_commit": "a" * 40,
            "git_dirty": False,
            "git_status": [],
            "argv": ["benchmark/release_gate.py"],
            "run_l3": False,
            "build_release_artifact": False,
            "release_version": "local",
            "verify_github_release": None,
            "github_release_kind": "prerelease",
            "require_clean_git": False,
            "require_l3_provenance": False,
            "require_production_claim": False,
            "external_trial_json": None,
            "external_trial_root": None,
            "external_evidence_package_dir": None,
            "external_trial_verification_report": None,
            "external_evidence_package_verification_report": None,
            "github_release_verification_report": None,
        }

    def valid_payload(self) -> dict:
        gates = self.production_gates(
            [
                "Rust formatting",
                "Rust tests",
                "Rust clippy",
                "Python helper compilation",
                "Python helper tests",
                "Validate claim language",
                "Validate handoff manifests",
                "Validate external lab handoff template",
                "Validate existing CellBinDB L3 artifacts",
                "Validate CellBinDB workflow bridge artifacts",
                "Validate CellBinDB handoff trial artifacts",
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            return release_gate.write_report(
                self.production_args(out_json=root / "report.json", out_md=root / "report.md"),
                gates,
                self.production_metadata(),
            )

    def complete_production_claim_payload(self) -> dict:
        gates = self.production_gates(
            [
                "Require clean git worktree",
                "Rust formatting",
                "Rust tests",
                "Rust clippy",
                "Python helper compilation",
                "Python helper tests",
                "Validate claim language",
                "Validate handoff manifests",
                "Validate external lab handoff template",
                "Validate existing CellBinDB L3 artifacts",
                "Validate CellBinDB L3 provenance",
                "Validate CellBinDB workflow bridge artifacts",
                "Validate CellBinDB handoff trial artifacts",
                "Validate external L4 workflow trial report",
                "Validate external L4 evidence package",
                "Verify saved external L4 trial report",
                "Verify saved external L4 evidence package report",
                "Verify GitHub release assets",
                "Verify saved stable GitHub release report",
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_report = root / "review" / "trial-verification.json"
            package_report = root / "review" / "package-verification.json"
            github_report = root / "review" / "github-release-verification.json"
            for gate in gates:
                if gate.name == "Verify GitHub release assets":
                    gate.command = verify_release_gate_report.live_github_release_gate_command("v0.1.0", "stable")
                elif gate.name == "Verify saved external L4 trial report":
                    gate.command = [
                        "python3",
                        "benchmark/verify_external_trial_report.py",
                        "--verify-report",
                        str(trial_report),
                        "--verify-report-files",
                        "--require-report-pass",
                    ]
                elif gate.name == "Verify saved external L4 evidence package report":
                    gate.command = [
                        "python3",
                        "benchmark/verify_external_evidence_package.py",
                        "--verify-report",
                        str(package_report),
                        "--verify-report-files",
                        "--require-report-pass",
                        "--require-trial-json",
                    ]
                elif gate.name == "Verify saved stable GitHub release report":
                    gate.command = verify_release_gate_report.saved_github_release_report_command(
                        str(github_report),
                        "v0.1.0",
                    )
            trial_json = root / "external" / "handoff_trial.json"
            trial_root = root / "external"
            package_dir = root / "evidence" / "external-l4-trial"
            return release_gate.write_report(
                self.production_args(
                    require_clean_git=True,
                    require_l3_provenance=True,
                    require_production_claim=True,
                    external_trial_json=trial_json,
                    external_trial_root=trial_root,
                    external_evidence_package_dir=package_dir,
                    external_trial_verification_report=trial_report,
                    external_evidence_package_verification_report=package_report,
                    verify_github_release="v0.1.0",
                    github_release_kind="stable",
                    github_release_verification_report=github_report,
                    out_json=root / "report.json",
                    out_md=root / "report.md",
                ),
                gates,
                {
                    **self.production_metadata(),
                    "argv": [
                        "benchmark/release_gate.py",
                        "--require-clean-git",
                        "--require-l3-provenance",
                        "--require-production-claim",
                        "--external-trial-json",
                        str(trial_json),
                        "--external-trial-root",
                        str(trial_root),
                        "--external-evidence-package-dir",
                        str(package_dir),
                        "--external-trial-verification-report",
                        str(trial_report),
                        "--external-evidence-package-verification-report",
                        str(package_report),
                        "--verify-github-release",
                        "v0.1.0",
                        "--github-release-kind",
                        "stable",
                        "--github-release-verification-report",
                        str(github_report),
                    ],
                    "verify_github_release": "v0.1.0",
                    "github_release_kind": "stable",
                    "require_clean_git": True,
                    "require_l3_provenance": True,
                    "require_production_claim": True,
                    "external_trial_json": str(trial_json),
                    "external_trial_root": str(trial_root),
                    "external_evidence_package_dir": str(package_dir),
                    "external_trial_verification_report": str(trial_report),
                    "external_evidence_package_verification_report": str(package_report),
                    "github_release_verification_report": str(github_report),
                },
            )

    def payload_with_saved_reviewer_gate_commands(self) -> dict:
        payload = self.valid_payload()
        root = ROOT / "tmp" / "saved-reviewer-gates"
        trial_report = root / "trial-verification.json"
        package_report = root / "package-verification.json"
        github_report = root / "github-release-verification.json"
        payload["metadata"].update(
            {
                "argv": [
                    "benchmark/release_gate.py",
                    "--external-trial-verification-report",
                    str(trial_report),
                    "--external-evidence-package-verification-report",
                    str(package_report),
                    "--github-release-verification-report",
                    str(github_report),
                    "--verify-github-release",
                    "v0.1.0",
                    "--github-release-kind",
                    "stable",
                ],
                "external_trial_verification_report": str(trial_report),
                "external_evidence_package_verification_report": str(package_report),
                "github_release_verification_report": str(github_report),
                "verify_github_release": "v0.1.0",
                "github_release_kind": "stable",
            }
        )
        payload["gates"].extend(
            [
                {
                    "name": "Verify saved external L4 trial report",
                    "command": [
                        "python3",
                        "benchmark/verify_external_trial_report.py",
                        "--verify-report",
                        str(trial_report),
                        "--verify-report-files",
                        "--require-report-pass",
                    ],
                    "status": "PASS",
                    "elapsed_seconds": 0.0,
                    "detail": "ok",
                },
                {
                    "name": "Verify saved external L4 evidence package report",
                    "command": [
                        "python3",
                        "benchmark/verify_external_evidence_package.py",
                        "--verify-report",
                        str(package_report),
                        "--verify-report-files",
                        "--require-report-pass",
                        "--require-trial-json",
                    ],
                    "status": "PASS",
                    "elapsed_seconds": 0.0,
                    "detail": "ok",
                },
                {
                    "name": "Verify saved stable GitHub release report",
                    "command": [
                        "python3",
                        "benchmark/verify_github_release.py",
                        "--verify-report",
                        str(github_report),
                        "--verify-report-files",
                        "--require-report-pass",
                        "--require-stable-report",
                        "--verify-git-commit",
                        "--expect-repo",
                        "benngaihk/MorphoJet",
                        "--expect-tag",
                        "v0.1.0",
                    ],
                    "status": "PASS",
                    "elapsed_seconds": 0.0,
                    "detail": "ok",
                },
                {
                    "name": "Verify GitHub release assets",
                    "command": verify_release_gate_report.live_github_release_gate_command("v0.1.0", "stable"),
                    "status": "PASS",
                    "elapsed_seconds": 0.0,
                    "detail": "ok",
                },
            ]
        )
        return payload

    def test_accepts_release_gate_report_with_matching_top_level_summary(self) -> None:
        self.assertEqual([], verify_release_gate_report.validate_release_gate_report_payload(self.valid_payload()))

    def test_rejects_mismatched_top_level_claim_status(self) -> None:
        payload = self.valid_payload()
        payload["production_claim_status"] = "PASS"

        failures = verify_release_gate_report.validate_release_gate_report_payload(payload)

        self.assertIn(
            "production_claim_status does not match production_claim_audit.status: PASS != INCOMPLETE",
            failures,
        )

    def test_rejects_mismatched_missing_checks(self) -> None:
        payload = self.valid_payload()
        payload["missing_or_failed_checks"] = []

        failures = verify_release_gate_report.validate_release_gate_report_payload(payload)

        self.assertIn("missing_or_failed_checks does not match production_claim_audit", failures)
        self.assertIn("missing_or_failed_checks does not match audit check statuses", failures)

    def test_can_require_report_pass(self) -> None:
        payload = self.valid_payload()
        payload["status"] = "FAIL"

        self.assertIn(
            "release-gate report status is not PASS: FAIL",
            verify_release_gate_report.validate_release_gate_report_payload(payload, require_report_pass=True),
        )

    def test_rejects_non_utc_metadata_timestamp(self) -> None:
        payload = self.valid_payload()
        payload["metadata"]["generated_at_utc"] = "2026-07-07T12:00:00+08:00"

        failures = verify_release_gate_report.validate_release_gate_report_payload(payload)

        self.assertIn("metadata.generated_at_utc must be UTC", failures)

    def test_rejects_passing_report_with_failed_gate(self) -> None:
        payload = self.valid_payload()
        payload["gates"][0]["status"] = "FAIL"

        failures = verify_release_gate_report.validate_release_gate_report_payload(payload)

        self.assertIn("passing release-gate report has failed gates: Rust formatting", failures)
        self.assertIn(
            "release-gate status does not match gate and production-claim statuses: PASS != FAIL",
            failures,
        )

    def test_rejects_passing_report_when_required_production_claim_is_incomplete(self) -> None:
        payload = self.valid_payload()
        payload["metadata"]["require_production_claim"] = True

        failures = verify_release_gate_report.validate_release_gate_report_payload(payload)

        self.assertIn(
            "release-gate status does not match gate and production-claim statuses: PASS != FAIL",
            failures,
        )

    def test_rejects_duplicate_gate_names(self) -> None:
        payload = self.valid_payload()
        payload["gates"][1]["name"] = payload["gates"][0]["name"]

        failures = verify_release_gate_report.validate_release_gate_report_payload(payload)

        self.assertIn("duplicate gate name: Rust formatting", failures)

    def test_can_require_production_claim_pass(self) -> None:
        self.assertIn(
            "production_claim_status is not PASS: INCOMPLETE",
            verify_release_gate_report.validate_release_gate_report_payload(
                self.valid_payload(),
                require_production_claim_pass=True,
            ),
        )

    def test_can_require_exact_missing_checks(self) -> None:
        self.assertEqual(
            [],
            verify_release_gate_report.validate_release_gate_report_payload(
                self.valid_payload(),
                expected_missing_checks=[
                    "clean_git_worktree",
                    "l3_provenance_hashes",
                    "external_l4_workflow_trial",
                    "external_l4_evidence_package",
                    "external_l4_saved_reviewer_reports",
                    "stable_github_release",
                    "stable_github_release_saved_report",
                ],
            ),
        )

    def test_rejects_unexpected_missing_checks(self) -> None:
        failures = verify_release_gate_report.validate_release_gate_report_payload(
            self.valid_payload(),
            expected_missing_checks=[
                "external_l4_workflow_trial",
                "external_l4_evidence_package",
                "external_l4_saved_reviewer_reports",
                "stable_github_release",
                "stable_github_release_saved_report",
            ],
        )

        self.assertIn(
            "missing_or_failed_checks does not match expected checks: "
            "['clean_git_worktree', 'l3_provenance_hashes', 'external_l4_workflow_trial', "
            "'external_l4_evidence_package', 'external_l4_saved_reviewer_reports', "
            "'stable_github_release', 'stable_github_release_saved_report'] != "
            "['external_l4_workflow_trial', 'external_l4_evidence_package', "
            "'external_l4_saved_reviewer_reports', 'stable_github_release', "
            "'stable_github_release_saved_report']",
            failures,
        )

    def test_can_require_clean_git_metadata(self) -> None:
        payload = self.valid_payload()
        payload["metadata"]["git_dirty"] = True
        payload["metadata"]["git_status"] = [" M docs/DEVELOPMENT.md"]

        failures = verify_release_gate_report.validate_release_gate_report_payload(
            payload,
            require_clean_git_metadata=True,
        )

        self.assertIn("metadata.git_dirty is not false", failures)
        self.assertIn("metadata.git_status is not empty", failures)

    def test_can_verify_reachable_git_commit(self) -> None:
        payload = self.valid_payload()
        payload["metadata"]["git_commit"] = release_gate.git_commit()

        self.assertEqual(
            [],
            verify_release_gate_report.validate_release_gate_report_payload(
                payload,
                verify_git_commit=True,
            ),
        )

    def test_rejects_unreachable_git_commit_when_requested(self) -> None:
        payload = self.valid_payload()
        payload["metadata"]["git_commit"] = "0" * 40

        failures = verify_release_gate_report.validate_release_gate_report_payload(
            payload,
            verify_git_commit=True,
        )

        self.assertIn("metadata.git_commit is not reachable: " + "0" * 40, failures)

    def test_parses_expected_missing_checks(self) -> None:
        self.assertEqual(
            ["external_l4_workflow_trial", "stable_github_release"],
            verify_release_gate_report.parse_expected_missing_checks(
                "external_l4_workflow_trial,stable_github_release"
            ),
        )
        self.assertEqual([], verify_release_gate_report.parse_expected_missing_checks("none"))
        with self.assertRaisesRegex(Exception, "unknown expected check"):
            verify_release_gate_report.parse_expected_missing_checks("not_a_gate")

    def test_accepts_complete_production_claim_report(self) -> None:
        payload = self.complete_production_claim_payload()

        self.assertEqual(
            [],
            verify_release_gate_report.validate_release_gate_report_payload(
                payload,
                require_report_pass=True,
                require_production_claim_pass=True,
            ),
        )

    def test_rejects_passing_production_claim_missing_required_gates(self) -> None:
        payload = self.complete_production_claim_payload()
        payload["gates"] = [
            gate for gate in payload["gates"] if gate["name"] != "Verify GitHub release assets"
        ]

        failures = verify_release_gate_report.validate_release_gate_report_payload(payload)

        self.assertIn("passing production claim missing gates: Verify GitHub release assets", failures)
        self.assertIn("metadata.verify_github_release requires gate: Verify GitHub release assets", failures)

    def test_rejects_verify_github_release_metadata_without_live_gate(self) -> None:
        payload = self.valid_payload()
        payload["metadata"]["argv"] = [
            "benchmark/release_gate.py",
            "--verify-github-release",
            "v0.1.0-rc.1",
        ]
        payload["metadata"]["verify_github_release"] = "v0.1.0-rc.1"

        failures = verify_release_gate_report.validate_release_gate_report_payload(payload)

        self.assertIn("metadata.verify_github_release requires gate: Verify GitHub release assets", failures)

    def test_rejects_external_trial_metadata_without_validation_gate(self) -> None:
        payload = self.complete_production_claim_payload()
        payload["gates"] = [
            gate for gate in payload["gates"] if gate["name"] != "Validate external L4 workflow trial report"
        ]

        failures = verify_release_gate_report.validate_release_gate_report_payload(payload)

        self.assertIn(
            "metadata.external_trial_json requires gate: Validate external L4 workflow trial report",
            failures,
        )

    def test_rejects_external_package_metadata_without_validation_gate(self) -> None:
        payload = self.complete_production_claim_payload()
        payload["gates"] = [
            gate for gate in payload["gates"] if gate["name"] != "Validate external L4 evidence package"
        ]

        failures = verify_release_gate_report.validate_release_gate_report_payload(payload)

        self.assertIn(
            "metadata.external_evidence_package_dir requires gate: Validate external L4 evidence package",
            failures,
        )

    def test_rejects_clean_git_metadata_without_gate(self) -> None:
        payload = self.complete_production_claim_payload()
        payload["gates"] = [
            gate for gate in payload["gates"] if gate["name"] != "Require clean git worktree"
        ]

        failures = verify_release_gate_report.validate_release_gate_report_payload(payload)

        self.assertIn("metadata.require_clean_git=true requires gate: Require clean git worktree", failures)

    def test_rejects_l3_provenance_metadata_without_gate(self) -> None:
        payload = self.complete_production_claim_payload()
        payload["gates"] = [
            gate for gate in payload["gates"] if gate["name"] != "Validate CellBinDB L3 provenance"
        ]

        failures = verify_release_gate_report.validate_release_gate_report_payload(payload)

        self.assertIn(
            "metadata.require_l3_provenance=true requires gate: Validate CellBinDB L3 provenance",
            failures,
        )

    def test_rejects_live_github_release_gate_command_tampering(self) -> None:
        payload = self.complete_production_claim_payload()
        for gate in payload["gates"]:
            if gate["name"] == "Verify GitHub release assets":
                gate["command"] = [
                    "python3",
                    "benchmark/verify_github_release.py",
                    "v0.1.0",
                    "--json-out",
                    verify_release_gate_report.github_release_verification_report_path("v0.1.0"),
                ]

        failures = verify_release_gate_report.validate_release_gate_report_payload(payload)

        self.assertIn(
            "gate command for Verify GitHub release assets must match live release verifier command",
            failures,
        )

    def test_rejects_passing_production_claim_without_final_metadata_flags(self) -> None:
        payload = self.complete_production_claim_payload()
        payload["metadata"]["require_clean_git"] = False
        payload["metadata"]["require_l3_provenance"] = False
        payload["metadata"]["require_production_claim"] = False

        failures = verify_release_gate_report.validate_release_gate_report_payload(payload)

        self.assertIn("production PASS metadata.require_clean_git must be true", failures)
        self.assertIn("production PASS metadata.require_l3_provenance must be true", failures)
        self.assertIn("production PASS metadata.require_production_claim must be true", failures)

    def test_rejects_passing_production_claim_without_external_metadata_paths(self) -> None:
        payload = self.complete_production_claim_payload()
        payload["metadata"]["external_trial_json"] = None
        payload["metadata"]["external_trial_root"] = ""
        payload["metadata"]["external_evidence_package_dir"] = None

        failures = verify_release_gate_report.validate_release_gate_report_payload(payload)

        self.assertIn("production PASS metadata.external_trial_json must be a non-empty string", failures)
        self.assertIn("production PASS metadata.external_trial_root must be a non-empty string", failures)
        self.assertIn(
            "production PASS metadata.external_evidence_package_dir must be a non-empty string",
            failures,
        )

    def test_rejects_passing_production_claim_without_stable_release_metadata(self) -> None:
        payload = self.complete_production_claim_payload()
        payload["metadata"]["verify_github_release"] = "v0.1.0-rc.1"
        payload["metadata"]["github_release_kind"] = "prerelease"

        failures = verify_release_gate_report.validate_release_gate_report_payload(payload)

        self.assertIn(
            "production PASS metadata.verify_github_release must be a stable semver tag like v0.1.0",
            failures,
        )
        self.assertIn("production PASS metadata.github_release_kind must be stable: prerelease", failures)

    def test_rejects_stable_release_kind_without_stable_tag_even_before_production_pass(self) -> None:
        payload = self.valid_payload()
        payload["metadata"]["github_release_kind"] = "stable"
        payload["metadata"]["verify_github_release"] = None

        failures = verify_release_gate_report.validate_release_gate_report_payload(payload)

        self.assertIn(
            "metadata.github_release_kind=stable requires a stable metadata.verify_github_release tag",
            failures,
        )

    def test_rejects_stable_release_kind_with_prerelease_tag(self) -> None:
        payload = self.valid_payload()
        payload["metadata"]["github_release_kind"] = "stable"
        payload["metadata"]["verify_github_release"] = "v0.1.0-rc.1"
        payload["metadata"]["argv"] = [
            "benchmark/release_gate.py",
            "--verify-github-release",
            "v0.1.0-rc.1",
            "--github-release-kind",
            "stable",
        ]

        failures = verify_release_gate_report.validate_release_gate_report_payload(payload)

        self.assertIn(
            "metadata.github_release_kind=stable requires a stable metadata.verify_github_release tag",
            failures,
        )

    def test_rejects_metadata_argv_that_omits_recorded_flags_and_inputs(self) -> None:
        payload = self.complete_production_claim_payload()
        payload["metadata"]["argv"] = ["other.py", "--require-clean-git"]

        failures = verify_release_gate_report.validate_release_gate_report_payload(payload)

        self.assertIn("metadata.argv[0]=other.py", failures)
        self.assertIn("metadata.argv missing --require-l3-provenance for metadata.require_l3_provenance=true", failures)
        self.assertIn("metadata.argv missing --require-production-claim for metadata.require_production_claim=true", failures)
        self.assertIn(
            f"metadata.argv missing --external-trial-json {payload['metadata']['external_trial_json']}",
            failures,
        )
        self.assertIn(
            f"metadata.argv missing --external-trial-root {payload['metadata']['external_trial_root']}",
            failures,
        )
        self.assertIn(
            "metadata.argv missing --external-evidence-package-dir "
            f"{payload['metadata']['external_evidence_package_dir']}",
            failures,
        )
        self.assertIn("metadata.argv missing --verify-github-release v0.1.0", failures)
        self.assertIn("metadata.argv missing --github-release-kind stable", failures)

    def test_rejects_relative_release_gate_metadata_paths(self) -> None:
        payload = self.complete_production_claim_payload()
        payload["metadata"]["external_trial_json"] = "external/handoff_trial.json"
        payload["metadata"]["external_trial_root"] = "external"
        payload["metadata"]["external_evidence_package_dir"] = "evidence/external-l4-trial"

        failures = verify_release_gate_report.validate_release_gate_report_payload(payload)

        self.assertIn(
            "metadata.external_trial_json must be an absolute path: external/handoff_trial.json",
            failures,
        )
        self.assertIn("metadata.external_trial_root must be an absolute path: external", failures)
        self.assertIn(
            "metadata.external_evidence_package_dir must be an absolute path: evidence/external-l4-trial",
            failures,
        )

    def test_rejects_relative_release_gate_metadata_argv_paths(self) -> None:
        payload = self.complete_production_claim_payload()
        payload["metadata"]["external_trial_json"] = "external/handoff_trial.json"
        payload["metadata"]["argv"] = [
            "benchmark/release_gate.py",
            "--external-trial-json",
            "external/handoff_trial.json",
            "--out-json",
            "reports/final.json",
        ]

        failures = verify_release_gate_report.validate_release_gate_report_payload(payload)

        self.assertIn(
            "metadata.argv --external-trial-json must use an absolute path: external/handoff_trial.json",
            failures,
        )
        self.assertIn("metadata.argv --out-json must use an absolute path: reports/final.json", failures)

    def test_release_gate_canonicalizes_path_argv_values(self) -> None:
        canonical = release_gate.canonical_release_gate_argv(
            [
                "release_gate.py",
                "--external-trial-json",
                "external/handoff_trial.json",
                "--verify-github-release",
                "v0.1.0",
                "--out-json",
                "reports/final.json",
            ]
        )

        self.assertEqual("benchmark/release_gate.py", canonical[0])
        self.assertIn(str((ROOT / "external/handoff_trial.json").resolve(strict=False)), canonical)
        self.assertIn(str((ROOT / "reports/final.json").resolve(strict=False)), canonical)
        self.assertIn("v0.1.0", canonical)

    def test_accepts_metadata_argv_out_json_bound_to_verified_report(self) -> None:
        payload = self.valid_payload()
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "release-gate.json"
            payload["metadata"]["argv"] = [
                "benchmark/release_gate.py",
                "--out-json",
                str(report),
            ]

            self.assertEqual(
                [],
                verify_release_gate_report.validate_release_gate_report_payload(
                    payload,
                    report_path=report,
                ),
            )

    def test_rejects_metadata_argv_out_json_for_another_report(self) -> None:
        payload = self.valid_payload()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload["metadata"]["argv"] = [
                "benchmark/release_gate.py",
                "--out-json",
                str(root / "other-release-gate.json"),
            ]

            failures = verify_release_gate_report.validate_release_gate_report_payload(
                payload,
                report_path=root / "release-gate.json",
            )

        self.assertIn(
            f"metadata.argv --out-json must match verified report path: {root / 'other-release-gate.json'}",
            failures,
        )

    def test_accepts_saved_reviewer_gate_commands_bound_to_metadata(self) -> None:
        self.assertEqual(
            [],
            verify_release_gate_report.validate_release_gate_report_payload(
                self.payload_with_saved_reviewer_gate_commands()
            ),
        )

    def test_rejects_saved_reviewer_gate_command_tampering(self) -> None:
        payload = self.payload_with_saved_reviewer_gate_commands()
        for gate in payload["gates"]:
            if gate["name"] == "Verify saved stable GitHub release report":
                gate["command"] = [
                    "python3",
                    "benchmark/verify_github_release.py",
                    "--verify-report",
                    payload["metadata"]["github_release_verification_report"],
                    "--require-report-pass",
                ]

        failures = verify_release_gate_report.validate_release_gate_report_payload(payload)

        self.assertIn(
            "gate command for Verify saved stable GitHub release report must match saved verifier command",
            failures,
        )

    def test_rejects_saved_package_reviewer_gate_without_trial_json_requirement(self) -> None:
        payload = self.payload_with_saved_reviewer_gate_commands()
        for gate in payload["gates"]:
            if gate["name"] == "Verify saved external L4 evidence package report":
                gate["command"] = gate["command"][:-1]

        failures = verify_release_gate_report.validate_release_gate_report_payload(payload)

        self.assertIn(
            "gate command for Verify saved external L4 evidence package report must match saved verifier command",
            failures,
        )

    def test_rejects_saved_reviewer_metadata_without_matching_gate(self) -> None:
        payload = self.payload_with_saved_reviewer_gate_commands()
        payload["gates"] = [
            gate for gate in payload["gates"] if gate["name"] != "Verify saved external L4 trial report"
        ]

        failures = verify_release_gate_report.validate_release_gate_report_payload(payload)

        self.assertIn(
            "metadata.external_trial_verification_report requires gate: Verify saved external L4 trial report",
            failures,
        )

    def test_rejects_saved_github_reviewer_metadata_without_matching_gate(self) -> None:
        payload = self.payload_with_saved_reviewer_gate_commands()
        payload["gates"] = [
            gate for gate in payload["gates"] if gate["name"] != "Verify saved stable GitHub release report"
        ]

        failures = verify_release_gate_report.validate_release_gate_report_payload(payload)

        self.assertIn(
            "metadata.github_release_verification_report requires gate: Verify saved stable GitHub release report",
            failures,
        )

    def test_rejects_metadata_argv_values_not_reflected_in_metadata(self) -> None:
        payload = self.valid_payload()
        payload["metadata"]["argv"] = [
            "benchmark/release_gate.py",
            "--require-clean-git",
            "--external-trial-json",
            "external/handoff_trial.json",
            "--verify-github-release",
            "v0.1.0",
            "--github-release-kind",
            "stable",
        ]

        failures = verify_release_gate_report.validate_release_gate_report_payload(payload)

        self.assertIn(
            "metadata.require_clean_git must be true when metadata.argv includes --require-clean-git",
            failures,
        )
        self.assertIn(
            "metadata.external_trial_json must match metadata.argv --external-trial-json external/handoff_trial.json",
            failures,
        )
        self.assertIn(
            "metadata.verify_github_release must match metadata.argv --verify-github-release v0.1.0",
            failures,
        )
        self.assertIn(
            "metadata.github_release_kind must match metadata.argv --github-release-kind stable",
            failures,
        )

    def test_rejects_duplicate_or_missing_metadata_argv_values(self) -> None:
        payload = self.valid_payload()
        payload["metadata"]["argv"] = [
            "benchmark/release_gate.py",
            "--verify-github-release",
            "v0.1.0",
            "--verify-github-release",
            "v0.1.1",
            "--external-trial-json",
            "--github-release-kind",
        ]

        failures = verify_release_gate_report.validate_release_gate_report_payload(payload)

        self.assertIn("metadata.argv has duplicate --verify-github-release", failures)
        self.assertIn("metadata.argv --external-trial-json must include a value", failures)
        self.assertIn("metadata.argv --github-release-kind must include a value", failures)

    def test_rejects_bad_metadata_shape(self) -> None:
        payload = self.valid_payload()
        payload["metadata"]["git_commit"] = "abc123"
        payload["metadata"]["git_dirty"] = "false"

        failures = verify_release_gate_report.validate_release_gate_report_payload(payload)

        self.assertIn("metadata.git_commit is not a 40-character SHA: abc123", failures)
        self.assertIn("metadata.git_dirty must be a boolean", failures)

    def test_rejects_bad_gate_shape(self) -> None:
        payload = self.valid_payload()
        payload["gates"][0]["status"] = "SKIPPED"
        payload["gates"][0]["elapsed_seconds"] = -1

        failures = verify_release_gate_report.validate_release_gate_report_payload(payload)

        self.assertIn("gate status invalid for Rust formatting: SKIPPED", failures)
        self.assertIn("gate elapsed_seconds must be non-negative: Rust formatting", failures)


if __name__ == "__main__":
    unittest.main()
