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
                "Validate handoff manifests",
                "Validate external lab handoff template",
                "Validate existing CellBinDB L3 artifacts",
                "Validate CellBinDB L3 provenance",
                "Validate CellBinDB workflow bridge artifacts",
                "Validate CellBinDB handoff trial artifacts",
                "Validate external L4 workflow trial report",
                "Validate external L4 evidence package",
                "Verify GitHub release assets",
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            return release_gate.write_report(
                self.production_args(
                    require_clean_git=True,
                    require_l3_provenance=True,
                    require_production_claim=True,
                    external_trial_json=Path("external/handoff_trial.json"),
                    external_trial_root=Path("external"),
                    external_evidence_package_dir=Path("evidence/external-l4-trial"),
                    verify_github_release="v0.1.0",
                    github_release_kind="stable",
                    out_json=root / "report.json",
                    out_md=root / "report.md",
                ),
                gates,
                {
                    **self.production_metadata(),
                    "verify_github_release": "v0.1.0",
                    "github_release_kind": "stable",
                    "require_clean_git": True,
                    "require_l3_provenance": True,
                    "require_production_claim": True,
                    "external_trial_json": "external/handoff_trial.json",
                    "external_trial_root": "external",
                    "external_evidence_package_dir": "evidence/external-l4-trial",
                },
            )

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

    def test_can_require_production_claim_pass(self) -> None:
        self.assertIn(
            "production_claim_status is not PASS: INCOMPLETE",
            verify_release_gate_report.validate_release_gate_report_payload(
                self.valid_payload(),
                require_production_claim_pass=True,
            ),
        )

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
