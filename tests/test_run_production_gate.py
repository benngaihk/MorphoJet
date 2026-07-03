#!/usr/bin/env python3
"""Unit tests for the final production gate wrapper."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmark"))
sys.path.insert(0, str(ROOT / "tests"))

import package_external_trial  # noqa: E402
import run_production_gate  # noqa: E402
from test_release_gate import add_artifact_provenance, valid_external_trial, write_trial_artifacts  # noqa: E402


class RunProductionGateTest(unittest.TestCase):
    def write_valid_trial(self, root: Path) -> Path:
        trial = valid_external_trial()
        write_trial_artifacts(trial, root)
        add_artifact_provenance(trial, root)
        trial_json = root / "external" / "handoff_trial.json"
        trial_json.parent.mkdir(parents=True, exist_ok=True)
        trial_json.write_text(json.dumps(trial, indent=2) + "\n", encoding="utf-8")
        return trial_json

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

    def test_local_evidence_preflight_passes_valid_trial_package(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            package = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            args = self.parse(
                "--external-trial-json",
                str(trial_json),
                "--external-trial-root",
                str(root),
                "--external-evidence-package-dir",
                package["package_dir"],
                "--local-evidence-preflight-only",
                "--local-evidence-preflight-json",
                str(root / "preflight.json"),
                "--local-evidence-preflight-md",
                str(root / "preflight.md"),
            )

            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                status = run_production_gate.run_local_evidence_preflight(args)

        self.assertEqual(0, status)
        self.assertIn("Validate external L4 workflow trial report: PASS", stdout.getvalue())
        self.assertIn("Validate external L4 evidence package: PASS", stdout.getvalue())

    def test_local_evidence_preflight_writes_json_and_markdown_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            package = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            out_json = root / "reports" / "preflight.json"
            out_md = root / "reports" / "preflight.md"
            args = self.parse(
                "--external-trial-json",
                str(trial_json),
                "--external-trial-root",
                str(root),
                "--external-evidence-package-dir",
                package["package_dir"],
                "--local-evidence-preflight-json",
                str(out_json),
                "--local-evidence-preflight-md",
                str(out_md),
                "--local-evidence-preflight-only",
            )

            with contextlib.redirect_stdout(io.StringIO()):
                status = run_production_gate.run_local_evidence_preflight(args)

            payload = json.loads(out_json.read_text(encoding="utf-8"))
            markdown = out_md.read_text(encoding="utf-8")

        self.assertEqual(0, status)
        self.assertEqual(1, payload["schema_version"])
        self.assertEqual("PASS", payload["status"])
        self.assertEqual("NOT_PRODUCTION_CLAIM", payload["claim_status"])
        self.assertEqual("LOCAL_EXTERNAL_L4_PREFLIGHT", payload["evidence_scope"])
        self.assertIs(False, payload["final_evidence_acceptable"])
        self.assertEqual(
            ["external_l4_workflow_trial", "external_l4_evidence_package"],
            payload["validated_checks"],
        )
        self.assertIn("stable_github_release", payload["skipped_final_checks"])
        self.assertIn("production_claim_enforcement", payload["skipped_final_checks"])
        artifact_by_name = {artifact["name"]: artifact for artifact in payload["input_artifacts"]}
        self.assertEqual(
            {
                "external_trial_json",
                "package_handoff_trial_json",
                "package_zip",
                "package_zip_sha256",
            },
            set(artifact_by_name),
        )
        self.assertTrue(artifact_by_name["external_trial_json"]["exists"])
        self.assertEqual(64, len(artifact_by_name["external_trial_json"]["sha256"]))
        self.assertTrue(artifact_by_name["package_zip"]["exists"])
        self.assertEqual(64, len(artifact_by_name["package_zip"]["sha256"]))
        self.assertEqual(2, len(payload["gates"]))
        self.assertIn("Local External L4 Evidence Preflight", markdown)
        self.assertIn("claim_status: `NOT_PRODUCTION_CLAIM`", markdown)
        self.assertIn("evidence_scope: `LOCAL_EXTERNAL_L4_PREFLIGHT`", markdown)
        self.assertIn("final_evidence_acceptable: `False`", markdown)
        self.assertIn("## Input Artifacts", markdown)
        self.assertIn("package_zip", markdown)
        self.assertIn("Validate external L4 evidence package", markdown)
        self.assertIn("does not satisfy the stable GitHub release", markdown)

    def test_verify_local_evidence_preflight_report_passes_without_evidence_args(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            package = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            out_json = root / "reports" / "preflight.json"
            args = self.parse(
                "--external-trial-json",
                str(trial_json),
                "--external-trial-root",
                str(root),
                "--external-evidence-package-dir",
                package["package_dir"],
                "--local-evidence-preflight-json",
                str(out_json),
                "--local-evidence-preflight-md",
                str(root / "reports" / "preflight.md"),
                "--local-evidence-preflight-only",
            )
            with contextlib.redirect_stdout(io.StringIO()):
                run_production_gate.run_local_evidence_preflight(args)

            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                status = run_production_gate.main(
                    [
                        "--verify-local-evidence-preflight-report",
                        str(out_json),
                    ]
                )

        self.assertEqual(0, status)
        self.assertIn("local evidence preflight report ok", stdout.getvalue())

    def test_verify_local_evidence_preflight_report_recomputes_input_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            package = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            out_json = root / "reports" / "preflight.json"
            args = self.parse(
                "--external-trial-json",
                str(trial_json),
                "--external-trial-root",
                str(root),
                "--external-evidence-package-dir",
                package["package_dir"],
                "--local-evidence-preflight-json",
                str(out_json),
                "--local-evidence-preflight-md",
                str(root / "reports" / "preflight.md"),
                "--local-evidence-preflight-only",
            )
            with contextlib.redirect_stdout(io.StringIO()):
                run_production_gate.run_local_evidence_preflight(args)

            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                status = run_production_gate.main(
                    [
                        "--verify-local-evidence-preflight-report",
                        str(out_json),
                        "--verify-local-evidence-preflight-files",
                    ]
                )

        self.assertEqual(0, status)
        self.assertIn("verified_files=True", stdout.getvalue())

    def test_verify_local_evidence_preflight_report_rejects_hash_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            package = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            out_json = root / "reports" / "preflight.json"
            args = self.parse(
                "--external-trial-json",
                str(trial_json),
                "--external-trial-root",
                str(root),
                "--external-evidence-package-dir",
                package["package_dir"],
                "--local-evidence-preflight-json",
                str(out_json),
                "--local-evidence-preflight-md",
                str(root / "reports" / "preflight.md"),
                "--local-evidence-preflight-only",
            )
            with contextlib.redirect_stdout(io.StringIO()):
                run_production_gate.run_local_evidence_preflight(args)
            Path(package["zip"]).write_bytes(b"tampered\n")

            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                status = run_production_gate.main(
                    [
                        "--verify-local-evidence-preflight-report",
                        str(out_json),
                        "--verify-local-evidence-preflight-files",
                    ]
                )

        self.assertEqual(1, status)
        self.assertIn("input artifact", stderr.getvalue())

    def test_verify_local_evidence_preflight_report_rejects_claim_status_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "preflight.json"
            report.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "status": "PASS",
                        "claim_status": "PASS",
                        "evidence_scope": "LOCAL_EXTERNAL_L4_PREFLIGHT",
                        "final_evidence_acceptable": False,
                        "validated_checks": run_production_gate.LOCAL_PREFLIGHT_VALIDATED_CHECKS,
                        "skipped_final_checks": run_production_gate.LOCAL_PREFLIGHT_SKIPPED_FINAL_CHECKS,
                        "metadata": {},
                        "input_artifacts": [],
                        "gates": [],
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                status = run_production_gate.main(
                    [
                        "--verify-local-evidence-preflight-report",
                        str(report),
                    ]
                )

        self.assertEqual(1, status)
        self.assertIn("claim_status=PASS", stderr.getvalue())

    def test_verify_local_evidence_preflight_report_rejects_final_evidence_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            package = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            out_json = root / "reports" / "preflight.json"
            args = self.parse(
                "--external-trial-json",
                str(trial_json),
                "--external-trial-root",
                str(root),
                "--external-evidence-package-dir",
                package["package_dir"],
                "--local-evidence-preflight-json",
                str(out_json),
                "--local-evidence-preflight-md",
                str(root / "reports" / "preflight.md"),
                "--local-evidence-preflight-only",
            )
            with contextlib.redirect_stdout(io.StringIO()):
                run_production_gate.run_local_evidence_preflight(args)
            payload = json.loads(out_json.read_text(encoding="utf-8"))
            payload["evidence_scope"] = "FINAL_PRODUCTION_CLAIM"
            payload["final_evidence_acceptable"] = True
            out_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                status = run_production_gate.main(
                    [
                        "--verify-local-evidence-preflight-report",
                        str(out_json),
                    ]
                )

        self.assertEqual(1, status)
        self.assertIn("evidence_scope=FINAL_PRODUCTION_CLAIM", stderr.getvalue())
        self.assertIn("final_evidence_acceptable=True", stderr.getvalue())

    def test_verify_local_evidence_preflight_report_rejects_bad_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            package = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            out_json = root / "reports" / "preflight.json"
            args = self.parse(
                "--external-trial-json",
                str(trial_json),
                "--external-trial-root",
                str(root),
                "--external-evidence-package-dir",
                package["package_dir"],
                "--local-evidence-preflight-json",
                str(out_json),
                "--local-evidence-preflight-md",
                str(root / "reports" / "preflight.md"),
                "--local-evidence-preflight-only",
            )
            with contextlib.redirect_stdout(io.StringIO()):
                run_production_gate.run_local_evidence_preflight(args)
            payload = json.loads(out_json.read_text(encoding="utf-8"))
            payload["metadata"]["git_commit"] = "abc123"
            payload["metadata"]["git_dirty"] = "false"
            payload["metadata"]["local_evidence_preflight_only"] = False
            out_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                status = run_production_gate.main(
                    [
                        "--verify-local-evidence-preflight-report",
                        str(out_json),
                    ]
                )

        self.assertEqual(1, status)
        self.assertIn("metadata.git_commit is not a 40-character SHA", stderr.getvalue())
        self.assertIn("metadata.git_dirty must be a boolean", stderr.getvalue())
        self.assertIn("metadata.local_evidence_preflight_only must be true", stderr.getvalue())

    def test_verify_local_evidence_preflight_report_can_require_pass_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            package = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            out_json = root / "reports" / "preflight.json"
            args = self.parse(
                "--external-trial-json",
                str(trial_json),
                "--external-trial-root",
                str(root),
                "--external-evidence-package-dir",
                package["package_dir"],
                "--local-evidence-preflight-json",
                str(out_json),
                "--local-evidence-preflight-md",
                str(root / "reports" / "preflight.md"),
                "--local-evidence-preflight-only",
            )
            with contextlib.redirect_stdout(io.StringIO()):
                run_production_gate.run_local_evidence_preflight(args)
            payload = json.loads(out_json.read_text(encoding="utf-8"))
            payload["status"] = "FAIL"
            payload["gates"][0]["status"] = "FAIL"
            out_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with contextlib.redirect_stdout(io.StringIO()):
                default_status = run_production_gate.main(
                    [
                        "--verify-local-evidence-preflight-report",
                        str(out_json),
                    ]
                )
            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                required_status = run_production_gate.main(
                    [
                        "--verify-local-evidence-preflight-report",
                        str(out_json),
                        "--require-local-evidence-preflight-pass",
                    ]
                )

        self.assertEqual(0, default_status)
        self.assertEqual(1, required_status)
        self.assertIn("local evidence preflight status is not PASS", stderr.getvalue())

    def test_main_preflight_only_does_not_print_final_release_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            package = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )

            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                status = run_production_gate.main(
                    [
                        "--external-trial-json",
                        str(trial_json),
                        "--external-trial-root",
                        str(root),
                        "--external-evidence-package-dir",
                        package["package_dir"],
                        "--github-release-tag",
                        "v0.1.0",
                        "--local-evidence-preflight-json",
                        str(root / "main-preflight.json"),
                        "--local-evidence-preflight-md",
                        str(root / "main-preflight.md"),
                        "--local-evidence-preflight-only",
                    ]
                )

        self.assertEqual(0, status)
        self.assertNotIn("benchmark/release_gate.py", stdout.getvalue())
        self.assertIn("Validate external L4 evidence package: PASS", stdout.getvalue())

    def test_local_evidence_preflight_fails_package_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            package = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            other_trial_json = root / "other_trial.json"
            other_trial_json.write_text("{}\n", encoding="utf-8")
            args = self.parse(
                "--external-trial-json",
                str(other_trial_json),
                "--external-trial-root",
                str(root),
                "--external-evidence-package-dir",
                package["package_dir"],
                "--local-evidence-preflight-json",
                str(root / "failed-preflight.json"),
                "--local-evidence-preflight-md",
                str(root / "failed-preflight.md"),
                "--local-evidence-preflight-only",
            )

            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                status = run_production_gate.run_local_evidence_preflight(args)
            payload = json.loads((root / "failed-preflight.json").read_text(encoding="utf-8"))

        self.assertEqual(1, status)
        self.assertEqual("FAIL", payload["status"])
        self.assertEqual("NOT_PRODUCTION_CLAIM", payload["claim_status"])
        self.assertIn("Validate external L4 workflow trial report: FAIL", stdout.getvalue())
        self.assertIn("Validate external L4 evidence package: FAIL", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
