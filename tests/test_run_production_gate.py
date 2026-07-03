#!/usr/bin/env python3
"""Unit tests for the final production gate wrapper."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmark"))

import run_production_gate  # noqa: E402


class RunProductionGateTest(unittest.TestCase):
    def parse(self, *extra: str):
        return run_production_gate.parse_args(
            [
                "--external-trial-json",
                "external/handoff_trial.json",
                "--external-trial-root",
                "external",
                "--external-evidence-package-dir",
                "evidence/external-l4-trial",
                "--github-release-tag",
                "v0.1.0",
                *extra,
            ]
        )

    def test_builds_complete_required_production_claim_command(self) -> None:
        command = run_production_gate.build_release_gate_command(self.parse())

        self.assertEqual(sys.executable, command[0])
        self.assertIn("--require-clean-git", command)
        self.assertIn("--require-l3-provenance", command)
        self.assertIn("--require-production-claim", command)
        self.assertIn("--external-trial-json", command)
        self.assertIn("--external-trial-root", command)
        self.assertIn("--external-evidence-package-dir", command)
        self.assertIn("--verify-github-release", command)
        self.assertIn("v0.1.0", command)
        self.assertIn("--github-release-kind", command)
        self.assertEqual("stable", command[command.index("--github-release-kind") + 1])
        self.assertIn("benchmark/results/release-gate/production-claim.json", command)
        self.assertIn("benchmark/results/release-gate/production-claim.md", command)

    def test_rejects_release_candidate_tag(self) -> None:
        args = self.parse("--github-release-tag", "v0.1.0-rc.1")

        with self.assertRaisesRegex(run_production_gate.ProductionGateError, "not a stable release tag"):
            run_production_gate.build_release_gate_command(args)

    def test_adds_optional_l3_and_archive_preflight_flags(self) -> None:
        command = run_production_gate.build_release_gate_command(
            self.parse("--run-l3", "--build-release-artifact", "--release-version", "v0.1.0-preflight")
        )

        self.assertIn("--run-l3", command)
        self.assertIn("--build-release-artifact", command)
        self.assertEqual("v0.1.0-preflight", command[command.index("--release-version") + 1])


if __name__ == "__main__":
    unittest.main()
