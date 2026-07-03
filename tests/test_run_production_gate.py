#!/usr/bin/env python3
"""Unit tests for the final production gate wrapper."""

from __future__ import annotations

import contextlib
import io
import sys
import tempfile
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

    def test_existing_input_validation_accepts_required_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_root = root / "external"
            package_dir = root / "evidence" / "external-l4-trial"
            trial_root.mkdir()
            package_dir.mkdir(parents=True)
            trial_json = trial_root / "handoff_trial.json"
            trial_json.write_text("{}\n", encoding="utf-8")
            args = self.parse(
                "--external-trial-json",
                str(trial_json),
                "--external-trial-root",
                str(trial_root),
                "--external-evidence-package-dir",
                str(package_dir),
            )

            run_production_gate.validate_existing_inputs(args)

    def test_existing_input_validation_rejects_missing_trial_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_root = root / "external"
            package_dir = root / "evidence" / "external-l4-trial"
            trial_root.mkdir()
            package_dir.mkdir(parents=True)
            args = self.parse(
                "--external-trial-json",
                str(trial_root / "missing.json"),
                "--external-trial-root",
                str(trial_root),
                "--external-evidence-package-dir",
                str(package_dir),
            )

            with self.assertRaisesRegex(run_production_gate.ProductionGateError, "--external-trial-json"):
                run_production_gate.validate_existing_inputs(args)

    def test_existing_input_validation_rejects_missing_trial_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package_dir = root / "evidence" / "external-l4-trial"
            package_dir.mkdir(parents=True)
            trial_json = root / "handoff_trial.json"
            trial_json.write_text("{}\n", encoding="utf-8")
            args = self.parse(
                "--external-trial-json",
                str(trial_json),
                "--external-trial-root",
                str(root / "missing-root"),
                "--external-evidence-package-dir",
                str(package_dir),
            )

            with self.assertRaisesRegex(run_production_gate.ProductionGateError, "--external-trial-root"):
                run_production_gate.validate_existing_inputs(args)

    def test_existing_input_validation_rejects_missing_package_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_root = root / "external"
            trial_root.mkdir()
            trial_json = trial_root / "handoff_trial.json"
            trial_json.write_text("{}\n", encoding="utf-8")
            args = self.parse(
                "--external-trial-json",
                str(trial_json),
                "--external-trial-root",
                str(trial_root),
                "--external-evidence-package-dir",
                str(root / "missing-package"),
            )

            with self.assertRaisesRegex(run_production_gate.ProductionGateError, "--external-evidence-package-dir"):
                run_production_gate.validate_existing_inputs(args)

    def test_dry_run_does_not_require_existing_paths(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            status = run_production_gate.main(
                [
                    "--external-trial-json",
                    "missing/handoff_trial.json",
                    "--external-trial-root",
                    "missing/root",
                    "--external-evidence-package-dir",
                    "missing/package",
                    "--github-release-tag",
                    "v0.1.0",
                    "--dry-run",
                ]
            )

        self.assertEqual(0, status)


if __name__ == "__main__":
    unittest.main()
