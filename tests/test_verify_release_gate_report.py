#!/usr/bin/env python3
"""Unit tests for saved release-gate report verification."""

from __future__ import annotations

import copy
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
            "git_commit": "abc123",
            "git_dirty": False,
            "git_status": [],
            "argv": ["benchmark/release_gate.py"],
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
        payload = copy.deepcopy(self.valid_payload())
        payload["status"] = "PASS"
        payload["production_claim_status"] = "PASS"
        payload["missing_or_failed_checks"] = []
        payload["production_claim_audit"]["status"] = "PASS"
        payload["production_claim_audit"]["missing_or_failed_checks"] = []
        for check in payload["production_claim_audit"]["checks"]:
            check["status"] = "PASS"

        self.assertEqual(
            [],
            verify_release_gate_report.validate_release_gate_report_payload(
                payload,
                require_report_pass=True,
                require_production_claim_pass=True,
            ),
        )


if __name__ == "__main__":
    unittest.main()
