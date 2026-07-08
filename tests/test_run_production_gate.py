#!/usr/bin/env python3
"""Unit tests for the final production gate wrapper."""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmark"))
sys.path.insert(0, str(ROOT / "tests"))

import package_external_trial  # noqa: E402
import release_gate  # noqa: E402
import run_production_gate  # noqa: E402
import verify_external_evidence_package  # noqa: E402
import verify_external_trial_report  # noqa: E402
import verify_github_release  # noqa: E402
from test_release_gate import add_artifact_provenance, valid_external_trial, write_trial_artifacts  # noqa: E402


class RunProductionGateTest(unittest.TestCase):
    FULL_COMMIT = "a" * 40
    DOCTOR_COMMIT = "a" * 12

    def test_github_release_repo_reuses_release_gate_contract(self) -> None:
        self.assertIs(release_gate.GITHUB_RELEASE_REPO, run_production_gate.GITHUB_RELEASE_REPO)

    def write_valid_trial(self, root: Path, package_name: str | None = None) -> Path:
        trial = valid_external_trial()
        trial["readiness_report"]["package_name"] = package_name
        write_trial_artifacts(trial, root)
        add_artifact_provenance(trial, root)
        trial_json = root / "external" / "handoff_trial.json"
        trial["metadata"]["argv"][trial["metadata"]["argv"].index("--out-json") + 1] = str(trial_json)
        trial_json.parent.mkdir(parents=True, exist_ok=True)
        trial_json.write_text(json.dumps(trial, indent=2) + "\n", encoding="utf-8")
        return trial_json

    def write_valid_github_release_report(self, root: Path) -> Path:
        out_dir = root / "github-release"
        out_dir.mkdir()
        expected_assets = sorted(verify_github_release.expected_asset_names("v0.1.0"))
        archive_summaries = []
        for archive_name in [name for name in expected_assets if name.endswith(".tar.gz")]:
            archive = out_dir / archive_name
            archive.write_text(f"{archive_name}\n", encoding="utf-8")
            digest = verify_github_release.sha256(archive)
            (out_dir / f"{archive_name}.sha256").write_text(f"{digest}  {archive_name}\n", encoding="utf-8")
            archive_summaries.append(
                {
                    "archive": archive.name,
                    "sha256": digest,
                    "checksum_match": True,
                    "doctor": {"status": "PASS", "issues": [], "expected_commit": self.DOCTOR_COMMIT}
                    if "linux-x86_64" in archive.name
                    else None,
                }
            )
        report = root / "github-release-verification.json"
        report.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "verifier": "benchmark/verify_github_release.py",
                    "generated_at_utc": "2026-07-03T00:00:00+00:00",
                    "claim_status": "NOT_PRODUCTION_CLAIM",
                    "evidence_scope": "GITHUB_STABLE_RELEASE_VERIFICATION",
                    "final_production_signoff": False,
                    "status": "PASS",
                    "argv": [
                        "benchmark/verify_github_release.py",
                        "v0.1.0",
                        "--repo",
                        "benngaihk/MorphoJet",
                        "--out-dir",
                        str(out_dir),
                        "--expect-stable",
                        "--json-out",
                        str(root / "github-release-verification.json"),
                    ],
                    "tag": "v0.1.0",
                    "repo": "benngaihk/MorphoJet",
                    "url": "https://github.com/benngaihk/MorphoJet/releases/tag/v0.1.0",
                    "release_id": "RE_release",
                    "release_database_id": 123,
                    "release_api_url": "https://api.github.com/repos/benngaihk/MorphoJet/releases/123",
                    "release_created_at": "2026-07-03T00:00:00Z",
                    "release_published_at": "2026-07-03T00:00:01Z",
                    "release_author_login": "github-actions[bot]",
                    "out_dir": str(out_dir),
                    "is_draft": False,
                    "is_immutable": False,
                    "is_prerelease": False,
                    "target_commitish": "main",
                    "expected_release_kind": "stable",
                    "expected_commit": self.FULL_COMMIT,
                    "expected_doctor_commit": self.DOCTOR_COMMIT,
                    "asset_count": len(expected_assets),
                    "assets": {
                        "expected": expected_assets,
                        "release_metadata": expected_assets,
                        "downloaded": expected_assets,
                        "expected_count": len(expected_assets),
                        "release_metadata_count": len(expected_assets),
                        "downloaded_count": len(expected_assets),
                    },
                    "asset_metadata": [
                        {
                            "name": name,
                            "github_id": f"asset-{index}",
                            "api_url": f"https://api.github.com/repos/benngaihk/MorphoJet/releases/assets/{index}",
                            "url": f"https://github.com/benngaihk/MorphoJet/releases/download/v0.1.0/{name}",
                            "size": (out_dir / name).stat().st_size,
                            "content_type": "application/gzip" if name.endswith(".tar.gz") else "text/plain",
                            "digest": f"sha256:{verify_github_release.sha256(out_dir / name)}",
                            "state": "uploaded",
                            "created_at": "2026-07-03T00:00:00Z",
                            "updated_at": "2026-07-03T00:00:01Z",
                        }
                        for index, name in enumerate(expected_assets, start=1)
                    ],
                    "archives": archive_summaries,
                    "issues": [],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return report

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

    def write_local_preflight(
        self,
        root: Path,
        package_name: str = "external-l4-demo",
    ) -> tuple[int, Path, Path, Path]:
        trial_json = self.write_valid_trial(root, package_name=package_name)
        package = package_external_trial.create_package(
            trial_json,
            root,
            root / "package-out",
            package_name=package_name,
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
            status = run_production_gate.run_local_evidence_preflight(args)
        return status, out_json, trial_json, Path(package["package_dir"])

    def test_builds_complete_required_production_claim_command(self) -> None:
        command = run_production_gate.build_release_gate_command(
            self.parse(
                "--external-trial-verification-report",
                "external/trial-verification.json",
                "--external-evidence-package-verification-report",
                "evidence/package-verification.json",
                "--github-release-verification-report",
                "github/verification.json",
            )
        )

        self.assertEqual(sys.executable, command[0])
        self.assertIn("--require-clean-git", command)
        self.assertIn("--require-l3-provenance", command)
        self.assertIn("--require-production-claim", command)
        self.assertIn("--external-trial-json", command)
        self.assertIn("--external-trial-root", command)
        self.assertIn("--external-evidence-package-dir", command)
        self.assertIn("--external-trial-verification-report", command)
        self.assertEqual(
            "external/trial-verification.json",
            command[command.index("--external-trial-verification-report") + 1],
        )
        self.assertIn("--external-evidence-package-verification-report", command)
        self.assertEqual(
            "evidence/package-verification.json",
            command[command.index("--external-evidence-package-verification-report") + 1],
        )
        self.assertIn("--github-release-verification-report", command)
        self.assertEqual(
            "github/verification.json",
            command[command.index("--github-release-verification-report") + 1],
        )
        self.assertIn("--verify-github-release", command)
        self.assertIn("v0.1.0", command)
        self.assertIn("--github-release-kind", command)
        self.assertEqual("stable", command[command.index("--github-release-kind") + 1])
        self.assertIn("benchmark/results/release-gate/production-claim.json", command)
        self.assertIn("benchmark/results/release-gate/production-claim.md", command)

    def test_builds_final_report_verification_command(self) -> None:
        args = self.parse("--out-json", "reports/final-production.json")

        command = run_production_gate.build_final_report_verification_command(args)

        self.assertEqual(sys.executable, command[0])
        self.assertEqual("benchmark/verify_release_gate_report.py", command[1])
        self.assertEqual("reports/final-production.json", command[2])
        self.assertIn("--require-report-pass", command)
        self.assertIn("--require-clean-git-metadata", command)
        self.assertIn("--verify-git-commit", command)
        self.assertIn("--require-production-claim-pass", command)
        self.assertEqual("none", command[command.index("--expect-missing-checks") + 1])

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

    def test_existing_input_validation_rejects_missing_reviewer_reports(self) -> None:
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
                "--external-trial-verification-report",
                str(root / "missing-trial-verification.json"),
            )

            with self.assertRaisesRegex(run_production_gate.ProductionGateError, "--external-trial-verification-report"):
                run_production_gate.validate_existing_inputs(args)

    def test_existing_input_validation_rejects_missing_github_release_report(self) -> None:
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
                "--github-release-verification-report",
                str(root / "missing-github-release-verification.json"),
            )

            with self.assertRaisesRegex(run_production_gate.ProductionGateError, "--github-release-verification-report"):
                run_production_gate.validate_existing_inputs(args)

    def test_dry_run_does_not_require_existing_paths(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()) as stdout:
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
        self.assertIn("benchmark/release_gate.py", stdout.getvalue())
        self.assertIn("benchmark/verify_release_gate_report.py", stdout.getvalue())

    def test_final_run_requires_saved_verifier_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_root = root / "external"
            package_dir = root / "evidence" / "external-l4-trial"
            trial_root.mkdir()
            package_dir.mkdir(parents=True)
            trial_json = trial_root / "handoff_trial.json"
            trial_json.write_text("{}\n", encoding="utf-8")

            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                status = run_production_gate.main(
                    [
                        "--external-trial-json",
                        str(trial_json),
                        "--external-trial-root",
                        str(trial_root),
                        "--external-evidence-package-dir",
                        str(package_dir),
                        "--github-release-tag",
                        "v0.1.0",
                    ]
                )

        self.assertEqual(2, status)
        self.assertIn("--external-trial-verification-report", stderr.getvalue())
        self.assertIn("--external-evidence-package-verification-report", stderr.getvalue())
        self.assertIn("--github-release-verification-report", stderr.getvalue())

    def test_local_preflight_does_not_require_saved_verifier_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            status, _out_json, _trial_json, _package_dir = self.write_local_preflight(root)

        self.assertEqual(0, status)

    def test_main_verifies_final_report_after_successful_release_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_root = root / "external"
            package_dir = root / "evidence" / "external-l4-trial"
            trial_root.mkdir()
            package_dir.mkdir(parents=True)
            trial_json = trial_root / "handoff_trial.json"
            trial_json.write_text("{}\n", encoding="utf-8")
            trial_report = root / "trial-verification.json"
            package_report = root / "package-verification.json"
            github_report = root / "github-verification.json"
            for report in [trial_report, package_report, github_report]:
                report.write_text("{}\n", encoding="utf-8")
            out_json = root / "reports" / "production-claim.json"
            out_md = root / "reports" / "production-claim.md"
            with (
                patch.object(run_production_gate, "saved_reviewer_report_gates", return_value=[]) as reviewer_mock,
                patch.object(
                    run_production_gate.subprocess,
                    "run",
                    return_value=run_production_gate.subprocess.CompletedProcess(["release-gate"], 0),
                ) as run_mock,
                patch.object(
                    run_production_gate.verify_release_gate_report,
                    "verify_release_gate_report",
                    return_value=0,
                ) as verify_mock,
                contextlib.redirect_stdout(io.StringIO()) as stdout,
            ):
                status = run_production_gate.main(
                    [
                        "--external-trial-json",
                        str(trial_json),
                        "--external-trial-root",
                        str(trial_root),
                        "--external-evidence-package-dir",
                        str(package_dir),
                        "--github-release-tag",
                        "v0.1.0",
                        "--external-trial-verification-report",
                        str(trial_report),
                        "--external-evidence-package-verification-report",
                        str(package_report),
                        "--github-release-verification-report",
                        str(github_report),
                        "--out-json",
                        str(out_json),
                        "--out-md",
                        str(out_md),
                    ]
                )

        self.assertEqual(0, status)
        reviewer_mock.assert_called_once()
        run_mock.assert_called_once()
        verify_mock.assert_called_once_with(
            out_json,
            require_report_pass=True,
            require_production_claim_pass=True,
            expected_missing_checks=[],
            require_clean_git_metadata=True,
            verify_git_commit=True,
        )
        self.assertIn("benchmark/verify_release_gate_report.py", stdout.getvalue())

    def test_main_fails_when_final_report_verification_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_root = root / "external"
            package_dir = root / "evidence" / "external-l4-trial"
            trial_root.mkdir()
            package_dir.mkdir(parents=True)
            trial_json = trial_root / "handoff_trial.json"
            trial_json.write_text("{}\n", encoding="utf-8")
            trial_report = root / "trial-verification.json"
            package_report = root / "package-verification.json"
            github_report = root / "github-verification.json"
            for report in [trial_report, package_report, github_report]:
                report.write_text("{}\n", encoding="utf-8")
            with (
                patch.object(run_production_gate, "saved_reviewer_report_gates", return_value=[]),
                patch.object(
                    run_production_gate.subprocess,
                    "run",
                    return_value=run_production_gate.subprocess.CompletedProcess(["release-gate"], 0),
                ),
                patch.object(
                    run_production_gate.verify_release_gate_report,
                    "verify_release_gate_report",
                    return_value=1,
                ) as verify_mock,
                contextlib.redirect_stdout(io.StringIO()),
            ):
                status = run_production_gate.main(
                    [
                        "--external-trial-json",
                        str(trial_json),
                        "--external-trial-root",
                        str(trial_root),
                        "--external-evidence-package-dir",
                        str(package_dir),
                        "--github-release-tag",
                        "v0.1.0",
                        "--external-trial-verification-report",
                        str(trial_report),
                        "--external-evidence-package-verification-report",
                        str(package_report),
                        "--github-release-verification-report",
                        str(github_report),
                    ]
                )

        self.assertEqual(1, status)
        verify_mock.assert_called_once()

    def test_main_does_not_verify_final_report_when_release_gate_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_root = root / "external"
            package_dir = root / "evidence" / "external-l4-trial"
            trial_root.mkdir()
            package_dir.mkdir(parents=True)
            trial_json = trial_root / "handoff_trial.json"
            trial_json.write_text("{}\n", encoding="utf-8")
            trial_report = root / "trial-verification.json"
            package_report = root / "package-verification.json"
            github_report = root / "github-verification.json"
            for report in [trial_report, package_report, github_report]:
                report.write_text("{}\n", encoding="utf-8")
            with (
                patch.object(run_production_gate, "saved_reviewer_report_gates", return_value=[]),
                patch.object(
                    run_production_gate.subprocess,
                    "run",
                    return_value=run_production_gate.subprocess.CompletedProcess(["release-gate"], 7),
                ),
                patch.object(
                    run_production_gate.verify_release_gate_report,
                    "verify_release_gate_report",
                    return_value=0,
                ) as verify_mock,
                contextlib.redirect_stdout(io.StringIO()),
            ):
                status = run_production_gate.main(
                    [
                        "--external-trial-json",
                        str(trial_json),
                        "--external-trial-root",
                        str(trial_root),
                        "--external-evidence-package-dir",
                        str(package_dir),
                        "--github-release-tag",
                        "v0.1.0",
                        "--external-trial-verification-report",
                        str(trial_report),
                        "--external-evidence-package-verification-report",
                        str(package_report),
                        "--github-release-verification-report",
                        str(github_report),
                    ]
                )

        self.assertEqual(7, status)
        verify_mock.assert_not_called()

    def test_final_report_outputs_must_not_overlap(self) -> None:
        args = self.parse("--out-json", "reports/production.json", "--out-md", "./reports/production.json")

        with self.assertRaisesRegex(run_production_gate.ProductionGateError, "--out-md must not use the same path"):
            run_production_gate.validate_report_output_paths(
                args,
                [
                    ("--out-json", args.out_json),
                    ("--out-md", args.out_md),
                ],
            )

    def test_final_report_output_must_not_overwrite_external_trial_json(self) -> None:
        args = self.parse("--out-json", "external/handoff_trial.json")

        with self.assertRaisesRegex(run_production_gate.ProductionGateError, "--out-json must not overwrite"):
            run_production_gate.validate_report_output_paths(
                args,
                [
                    ("--out-json", args.out_json),
                    ("--out-md", args.out_md),
                ],
            )

    def test_final_report_output_must_not_overwrite_package_readiness_json(self) -> None:
        args = self.parse("--out-json", "evidence/external-l4-trial/readiness.json")

        with self.assertRaisesRegex(
            run_production_gate.ProductionGateError,
            "--out-json must not overwrite packaged readiness.json",
        ):
            run_production_gate.validate_report_output_paths(
                args,
                [
                    ("--out-json", args.out_json),
                    ("--out-md", args.out_md),
                ],
            )

    def test_final_report_output_must_not_overwrite_package_chinese_readme(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            package = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            package_dir = Path(package["package_dir"])
            args = self.parse(
                "--external-trial-json",
                str(trial_json),
                "--external-trial-root",
                str(root),
                "--external-evidence-package-dir",
                str(package_dir),
                "--out-json",
                str(package_dir / "README.zh-CN.md"),
            )

            with self.assertRaisesRegex(
                run_production_gate.ProductionGateError,
                "--out-json must not overwrite evidence package review file: README.zh-CN.md",
            ):
                run_production_gate.validate_report_output_paths(
                    args,
                    [
                        ("--out-json", args.out_json),
                        ("--out-md", args.out_md),
                    ],
                )

    def test_final_report_output_must_not_create_file_inside_declared_trial_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            args = self.parse(
                "--external-trial-json",
                str(trial_json),
                "--external-trial-root",
                str(root),
                "--out-json",
                str(root / "external" / "handoff_contract.json" / "production-claim.json"),
            )

            with self.assertRaisesRegex(
                run_production_gate.ProductionGateError,
                "--out-json must not create a file inside external trial artifact: external/handoff_contract.json",
            ):
                run_production_gate.validate_report_output_paths(
                    args,
                    [
                        ("--out-json", args.out_json),
                        ("--out-md", args.out_md),
                    ],
                )

    def test_local_preflight_output_must_not_overwrite_package_checksum(self) -> None:
        args = self.parse(
            "--local-evidence-preflight-json",
            "evidence/external-l4-trial.zip.sha256",
            "--local-evidence-preflight-only",
        )

        with self.assertRaisesRegex(
            run_production_gate.ProductionGateError,
            "--local-evidence-preflight-json must not overwrite evidence package checksum",
        ):
            run_production_gate.validate_report_output_paths(
                args,
                [
                    ("--local-evidence-preflight-json", args.local_evidence_preflight_json),
                    ("--local-evidence-preflight-md", args.local_evidence_preflight_md),
                ],
            )

    def test_local_preflight_output_must_not_create_file_inside_package_dir(self) -> None:
        args = self.parse(
            "--local-evidence-preflight-json",
            "evidence/external-l4-trial/review/local-preflight.json",
            "--local-evidence-preflight-only",
        )

        with self.assertRaisesRegex(
            run_production_gate.ProductionGateError,
            "--local-evidence-preflight-json must not create a file inside --external-evidence-package-dir",
        ):
            run_production_gate.validate_report_output_paths(
                args,
                [
                    ("--local-evidence-preflight-json", args.local_evidence_preflight_json),
                    ("--local-evidence-preflight-md", args.local_evidence_preflight_md),
                ],
            )

    def test_dry_run_rejects_report_output_over_external_input(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()) as stderr:
            status = run_production_gate.main(
                [
                    "--external-trial-json",
                    "external/handoff_trial.json",
                    "--external-trial-root",
                    "external",
                    "--external-evidence-package-dir",
                    "evidence/external-l4-trial",
                    "--github-release-tag",
                    "v0.1.0",
                    "--out-json",
                    "external/handoff_trial.json",
                    "--dry-run",
                ]
            )

        self.assertEqual(2, status)
        self.assertIn("--out-json must not overwrite --external-trial-json", stderr.getvalue())

    def test_final_report_output_must_not_overwrite_declared_trial_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            args = self.parse(
                "--external-trial-json",
                str(trial_json),
                "--external-trial-root",
                str(root),
                "--out-json",
                str(root / "external" / "handoff_contract.json"),
            )

            with self.assertRaisesRegex(
                run_production_gate.ProductionGateError,
                "--out-json must not overwrite external trial artifact: external/handoff_contract.json",
            ):
                run_production_gate.validate_report_output_paths(
                    args,
                    [
                        ("--out-json", args.out_json),
                        ("--out-md", args.out_md),
                    ],
                )

    def test_local_preflight_output_must_not_overwrite_packaged_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            package = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            package_dir = Path(package["package_dir"])
            args = self.parse(
                "--external-trial-json",
                str(trial_json),
                "--external-trial-root",
                str(root),
                "--external-evidence-package-dir",
                str(package_dir),
                "--local-evidence-preflight-json",
                str(package_dir / "artifacts" / "external" / "handoff_contract.json"),
                "--local-evidence-preflight-only",
            )

            with self.assertRaisesRegex(
                run_production_gate.ProductionGateError,
                "--local-evidence-preflight-json must not overwrite evidence package artifact: "
                "artifacts/external/handoff_contract.json",
            ):
                run_production_gate.validate_report_output_paths(
                    args,
                    [
                        ("--local-evidence-preflight-json", args.local_evidence_preflight_json),
                        ("--local-evidence-preflight-md", args.local_evidence_preflight_md),
                    ],
                )

    def test_local_preflight_output_must_not_overwrite_package_chinese_readme(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            package = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            package_dir = Path(package["package_dir"])
            args = self.parse(
                "--external-trial-json",
                str(trial_json),
                "--external-trial-root",
                str(root),
                "--external-evidence-package-dir",
                str(package_dir),
                "--local-evidence-preflight-json",
                str(package_dir / "README.zh-CN.md"),
                "--local-evidence-preflight-only",
            )

            with self.assertRaisesRegex(
                run_production_gate.ProductionGateError,
                "--local-evidence-preflight-json must not overwrite evidence package review file: README.zh-CN.md",
            ):
                run_production_gate.validate_report_output_paths(
                    args,
                    [
                        ("--local-evidence-preflight-json", args.local_evidence_preflight_json),
                        ("--local-evidence-preflight-md", args.local_evidence_preflight_md),
                    ],
                )

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

    def test_local_evidence_preflight_binds_saved_reviewer_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            package = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            trial_report = root / "external-trial-verification.json"
            package_report = root / "external-package-verification.json"
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                verify_external_trial_report.verify_external_trial_report(
                    trial_json,
                    root,
                    json_out=trial_report,
                )
                verify_external_evidence_package.verify_external_evidence_package(
                    Path(package["package_dir"]),
                    trial_json=trial_json,
                    json_out=package_report,
                )
            out_json = root / "reports" / "preflight.json"
            args = self.parse(
                "--external-trial-json",
                str(trial_json),
                "--external-trial-root",
                str(root),
                "--external-evidence-package-dir",
                package["package_dir"],
                "--external-trial-verification-report",
                str(trial_report),
                "--external-evidence-package-verification-report",
                str(package_report),
                "--local-evidence-preflight-json",
                str(out_json),
                "--local-evidence-preflight-md",
                str(root / "reports" / "preflight.md"),
                "--local-evidence-preflight-only",
            )

            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                status = run_production_gate.run_local_evidence_preflight(args)
            payload = json.loads(out_json.read_text(encoding="utf-8"))

        self.assertEqual(0, status)
        self.assertIn("Verify saved external L4 trial report: PASS", stdout.getvalue())
        self.assertIn("Verify saved external L4 evidence package report: PASS", stdout.getvalue())
        artifact_names = {artifact["name"] for artifact in payload["input_artifacts"]}
        self.assertIn("external_trial_verification_report", artifact_names)
        self.assertIn("external_evidence_package_verification_report", artifact_names)
        gate_names = {gate["name"] for gate in payload["gates"]}
        self.assertIn("Verify saved external L4 trial report", gate_names)
        self.assertIn("Verify saved external L4 evidence package report", gate_names)
        self.assertIn("external_l4_saved_reviewer_reports", payload["validated_checks"])
        self.assertNotIn("external_l4_saved_reviewer_reports", payload["skipped_final_checks"])

    def test_verify_local_evidence_preflight_requires_saved_reviewer_gates_when_bound(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            package = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            trial_report = root / "external-trial-verification.json"
            package_report = root / "external-package-verification.json"
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                verify_external_trial_report.verify_external_trial_report(
                    trial_json,
                    root,
                    json_out=trial_report,
                )
                verify_external_evidence_package.verify_external_evidence_package(
                    Path(package["package_dir"]),
                    trial_json=trial_json,
                    json_out=package_report,
                )
            out_json = root / "reports" / "preflight.json"
            args = self.parse(
                "--external-trial-json",
                str(trial_json),
                "--external-trial-root",
                str(root),
                "--external-evidence-package-dir",
                package["package_dir"],
                "--external-trial-verification-report",
                str(trial_report),
                "--external-evidence-package-verification-report",
                str(package_report),
                "--local-evidence-preflight-json",
                str(out_json),
                "--local-evidence-preflight-md",
                str(root / "reports" / "preflight.md"),
                "--local-evidence-preflight-only",
            )
            with contextlib.redirect_stdout(io.StringIO()):
                run_production_gate.run_local_evidence_preflight(args)
            payload = json.loads(out_json.read_text(encoding="utf-8"))
            payload["gates"] = [
                gate
                for gate in payload["gates"]
                if gate["name"] != "Verify saved external L4 evidence package report"
            ]
            out_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                status = run_production_gate.main(
                    [
                        "--verify-local-evidence-preflight-report",
                        str(out_json),
                    ]
                )

        self.assertEqual(1, status)
        self.assertIn("missing_required=['Verify saved external L4 evidence package report']", stderr.getvalue())

    def test_verify_local_evidence_preflight_rejects_missing_required_input_hash(self) -> None:
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
            artifact = next(item for item in payload["input_artifacts"] if item["name"] == "package_zip")
            artifact["exists"] = False
            artifact["size_bytes"] = None
            artifact["sha256"] = None
            out_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                status = run_production_gate.main(
                    [
                        "--verify-local-evidence-preflight-report",
                        str(out_json),
                    ]
                )

        self.assertEqual(1, status)
        self.assertIn("input_artifacts.package_zip.exists must be true", stderr.getvalue())

    def test_verify_local_evidence_preflight_rejects_missing_bound_reviewer_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            package = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            trial_report = root / "external-trial-verification.json"
            package_report = root / "external-package-verification.json"
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                verify_external_trial_report.verify_external_trial_report(
                    trial_json,
                    root,
                    json_out=trial_report,
                )
                verify_external_evidence_package.verify_external_evidence_package(
                    Path(package["package_dir"]),
                    trial_json=trial_json,
                    json_out=package_report,
                )
            out_json = root / "reports" / "preflight.json"
            args = self.parse(
                "--external-trial-json",
                str(trial_json),
                "--external-trial-root",
                str(root),
                "--external-evidence-package-dir",
                package["package_dir"],
                "--external-trial-verification-report",
                str(trial_report),
                "--external-evidence-package-verification-report",
                str(package_report),
                "--local-evidence-preflight-json",
                str(out_json),
                "--local-evidence-preflight-md",
                str(root / "reports" / "preflight.md"),
                "--local-evidence-preflight-only",
            )
            with contextlib.redirect_stdout(io.StringIO()):
                run_production_gate.run_local_evidence_preflight(args)
            payload = json.loads(out_json.read_text(encoding="utf-8"))
            artifact = next(
                item for item in payload["input_artifacts"] if item["name"] == "external_trial_verification_report"
            )
            artifact["exists"] = False
            artifact["size_bytes"] = None
            artifact["sha256"] = None
            out_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                status = run_production_gate.main(
                    [
                        "--verify-local-evidence-preflight-report",
                        str(out_json),
                    ]
                )

        self.assertEqual(1, status)
        self.assertIn("input_artifacts.external_trial_verification_report.exists must be true", stderr.getvalue())

    def test_final_wrapper_reuses_release_gate_saved_external_reviewer_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            package = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            trial_report = root / "external-trial-verification.json"
            package_report = root / "external-package-verification.json"
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                verify_external_trial_report.verify_external_trial_report(
                    trial_json,
                    root,
                    json_out=trial_report,
                )
                verify_external_evidence_package.verify_external_evidence_package(
                    Path(package["package_dir"]),
                    trial_json=trial_json,
                    json_out=package_report,
                )
            args = self.parse(
                "--external-trial-json",
                str(trial_json),
                "--external-trial-root",
                str(root),
                "--external-evidence-package-dir",
                package["package_dir"],
                "--external-trial-verification-report",
                str(trial_report),
                "--external-evidence-package-verification-report",
                str(package_report),
            )

            gates = run_production_gate.saved_reviewer_report_gates(args)

        gate_by_name = {gate.name: gate for gate in gates}
        self.assertEqual("PASS", gate_by_name["Verify saved external L4 trial report"].status)
        self.assertEqual(
            release_gate.saved_external_trial_report_command(trial_report),
            gate_by_name["Verify saved external L4 trial report"].command,
        )
        self.assertEqual("PASS", gate_by_name["Verify saved external L4 evidence package report"].status)
        self.assertEqual(
            release_gate.saved_external_package_report_command(package_report),
            gate_by_name["Verify saved external L4 evidence package report"].command,
        )

    def test_saved_trial_report_must_match_current_trial_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            other_root = root / "other"
            other_trial_json = self.write_valid_trial(other_root)
            trial_report = root / "other-trial-verification.json"
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                verify_external_trial_report.verify_external_trial_report(
                    other_trial_json,
                    other_root,
                    json_out=trial_report,
                )
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
                "--external-trial-verification-report",
                str(trial_report),
            )

            gates = run_production_gate.saved_reviewer_report_gates(args)

        self.assertEqual(1, len(gates))
        self.assertEqual("FAIL", gates[0].status)
        self.assertIn("saved external trial report trial_json does not match --external-trial-json", gates[0].detail)
        self.assertIn("saved external trial report trial_root does not match --external-trial-root", gates[0].detail)

    def test_malformed_saved_trial_report_returns_failed_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            package = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            trial_report = root / "bad-trial-verification.json"
            trial_report.write_text("{not-json\n", encoding="utf-8")
            args = self.parse(
                "--external-trial-json",
                str(trial_json),
                "--external-trial-root",
                str(root),
                "--external-evidence-package-dir",
                package["package_dir"],
                "--external-trial-verification-report",
                str(trial_report),
            )

            gates = run_production_gate.saved_reviewer_report_gates(args)

        self.assertEqual(1, len(gates))
        self.assertEqual("FAIL", gates[0].status)
        self.assertIn("ERROR: JSONDecodeError", gates[0].detail)

    def test_saved_package_report_must_match_current_package_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            package = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            other_root = root / "other"
            other_trial_json = self.write_valid_trial(other_root)
            other_package = package_external_trial.create_package(
                other_trial_json,
                other_root,
                root / "other-package-out",
                package_name="external-l4-other",
            )
            package_report = root / "other-package-verification.json"
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                verify_external_evidence_package.verify_external_evidence_package(
                    Path(other_package["package_dir"]),
                    trial_json=other_trial_json,
                    json_out=package_report,
                )
            args = self.parse(
                "--external-trial-json",
                str(trial_json),
                "--external-trial-root",
                str(root),
                "--external-evidence-package-dir",
                package["package_dir"],
                "--external-evidence-package-verification-report",
                str(package_report),
            )

            gates = run_production_gate.saved_reviewer_report_gates(args)

        self.assertEqual(1, len(gates))
        self.assertEqual("FAIL", gates[0].status)
        self.assertIn(
            "saved external evidence package report package_dir does not match --external-evidence-package-dir",
            gates[0].detail,
        )
        self.assertIn(
            "saved external evidence package report trial_json does not match --external-trial-json",
            gates[0].detail,
        )

    def test_final_wrapper_binds_saved_github_release_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            github_report = self.write_valid_github_release_report(root)
            args = self.parse("--github-release-verification-report", str(github_report))

            with patch.object(verify_github_release, "git_commit", return_value=self.FULL_COMMIT):
                gates = run_production_gate.saved_reviewer_report_gates(args, include_github_release=True)

        self.assertEqual(1, len(gates))
        self.assertEqual("Verify saved stable GitHub release report", gates[0].name)
        self.assertEqual("PASS", gates[0].status)
        self.assertEqual(
            release_gate.saved_github_release_report_command(github_report, expected_tag="v0.1.0"),
            gates[0].command,
        )
        self.assertIn("--require-stable-report", gates[0].command)
        self.assertIn("--verify-git-commit", gates[0].command)
        self.assertIn("--expect-tag", gates[0].command)
        self.assertEqual("v0.1.0", gates[0].command[gates[0].command.index("--expect-tag") + 1])
        self.assertIn("--expect-repo", gates[0].command)
        self.assertEqual("benngaihk/MorphoJet", gates[0].command[gates[0].command.index("--expect-repo") + 1])

    def test_final_wrapper_rejects_non_stable_saved_github_release_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            github_report = self.write_valid_github_release_report(root)
            payload = json.loads(github_report.read_text(encoding="utf-8"))
            payload["expected_release_kind"] = "prerelease"
            github_report.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            args = self.parse("--github-release-verification-report", str(github_report))

            with patch.object(verify_github_release, "git_commit", return_value=self.FULL_COMMIT):
                gates = run_production_gate.saved_reviewer_report_gates(args, include_github_release=True)

        self.assertEqual(1, len(gates))
        self.assertEqual("FAIL", gates[0].status)
        self.assertIn("expected_release_kind is not stable", gates[0].detail)

    def test_final_wrapper_rejects_saved_github_release_report_for_different_tag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            github_report = self.write_valid_github_release_report(root)
            args = self.parse(
                "--github-release-tag",
                "v0.2.0",
                "--github-release-verification-report",
                str(github_report),
            )

            with patch.object(verify_github_release, "git_commit", return_value=self.FULL_COMMIT):
                gates = run_production_gate.saved_reviewer_report_gates(args, include_github_release=True)

        self.assertEqual(1, len(gates))
        self.assertEqual("FAIL", gates[0].status)
        self.assertIn("tag does not match expected tag", gates[0].detail)

    def test_final_wrapper_rejects_saved_github_release_report_for_different_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            github_report = self.write_valid_github_release_report(root)
            payload = json.loads(github_report.read_text(encoding="utf-8"))
            payload["repo"] = "other/repo"
            payload["argv"][payload["argv"].index("--repo") + 1] = "other/repo"
            payload["url"] = "https://github.com/other/repo/releases/tag/v0.1.0"
            payload["release_api_url"] = "https://api.github.com/repos/other/repo/releases/123"
            for record in payload["asset_metadata"]:
                record["url"] = f"https://github.com/other/repo/releases/download/v0.1.0/{record['name']}"
                record["api_url"] = record["api_url"].replace(
                    "https://api.github.com/repos/benngaihk/MorphoJet/",
                    "https://api.github.com/repos/other/repo/",
                )
            github_report.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            args = self.parse("--github-release-verification-report", str(github_report))

            with patch.object(verify_github_release, "git_commit", return_value=self.FULL_COMMIT):
                gates = run_production_gate.saved_reviewer_report_gates(args, include_github_release=True)

        self.assertEqual(1, len(gates))
        self.assertEqual("FAIL", gates[0].status)
        self.assertIn(
            "github release verification report repo does not match expected repo: other/repo != benngaihk/MorphoJet",
            gates[0].detail,
        )

    def test_local_evidence_preflight_fails_tampered_saved_package_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            package = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            package_report = root / "external-package-verification.json"
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                verify_external_evidence_package.verify_external_evidence_package(
                    Path(package["package_dir"]),
                    trial_json=trial_json,
                    json_out=package_report,
                )
            payload = json.loads(package_report.read_text(encoding="utf-8"))
            payload["gate"]["detail"] = "External L4 evidence package PASS: stale detail"
            package_report.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            args = self.parse(
                "--external-trial-json",
                str(trial_json),
                "--external-trial-root",
                str(root),
                "--external-evidence-package-dir",
                package["package_dir"],
                "--external-evidence-package-verification-report",
                str(package_report),
                "--local-evidence-preflight-json",
                str(root / "failed-preflight.json"),
                "--local-evidence-preflight-md",
                str(root / "failed-preflight.md"),
                "--local-evidence-preflight-only",
            )

            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                status = run_production_gate.run_local_evidence_preflight(args)

        self.assertEqual(1, status)
        self.assertIn("Verify saved external L4 evidence package report: FAIL", stdout.getvalue())

    def test_local_evidence_preflight_does_not_validate_failed_saved_reviewer_pair(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            package = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            trial_report = root / "external-trial-verification.json"
            package_report = root / "external-package-verification.json"
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                verify_external_trial_report.verify_external_trial_report(
                    trial_json,
                    root,
                    json_out=trial_report,
                )
                verify_external_evidence_package.verify_external_evidence_package(
                    Path(package["package_dir"]),
                    trial_json=trial_json,
                    json_out=package_report,
                )
            payload = json.loads(package_report.read_text(encoding="utf-8"))
            payload["gate"]["detail"] = "External L4 evidence package PASS: stale detail"
            package_report.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            out_json = root / "reports" / "failed-preflight.json"
            args = self.parse(
                "--external-trial-json",
                str(trial_json),
                "--external-trial-root",
                str(root),
                "--external-evidence-package-dir",
                package["package_dir"],
                "--external-trial-verification-report",
                str(trial_report),
                "--external-evidence-package-verification-report",
                str(package_report),
                "--local-evidence-preflight-json",
                str(out_json),
                "--local-evidence-preflight-md",
                str(root / "reports" / "failed-preflight.md"),
                "--local-evidence-preflight-only",
            )

            with contextlib.redirect_stdout(io.StringIO()):
                status = run_production_gate.run_local_evidence_preflight(args)
            preflight = json.loads(out_json.read_text(encoding="utf-8"))
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as stderr:
                verify_status = run_production_gate.main(
                    [
                        "--verify-local-evidence-preflight-report",
                        str(out_json),
                    ]
                )

        self.assertEqual(1, status)
        self.assertEqual(0, verify_status, stderr.getvalue())
        self.assertNotIn("external_l4_saved_reviewer_reports", preflight["validated_checks"])
        self.assertIn("external_l4_saved_reviewer_reports", preflight["skipped_final_checks"])

    def test_local_evidence_preflight_fails_unbound_saved_package_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            package = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            package_report = root / "external-package-verification.json"
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                verify_external_evidence_package.verify_external_evidence_package(
                    Path(package["package_dir"]),
                    json_out=package_report,
                )
            args = self.parse(
                "--external-trial-json",
                str(trial_json),
                "--external-trial-root",
                str(root),
                "--external-evidence-package-dir",
                package["package_dir"],
                "--external-evidence-package-verification-report",
                str(package_report),
                "--local-evidence-preflight-json",
                str(root / "failed-preflight.json"),
                "--local-evidence-preflight-md",
                str(root / "failed-preflight.md"),
                "--local-evidence-preflight-only",
            )

            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                status = run_production_gate.run_local_evidence_preflight(args)

        self.assertEqual(1, status)
        self.assertIn("trial_json is required for production package reviewer reports", stdout.getvalue())

    def test_local_evidence_preflight_writes_json_and_markdown_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root, package_name="external-l4-demo")
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
            package_readiness_payload = json.loads(
                (Path(package["package_dir"]) / "readiness.json").read_text(encoding="utf-8")
            )
            package_dir = Path(package["package_dir"])
            expected_handoff_contract = verify_external_evidence_package.rendered_manifest_contract_summary(
                package_dir / "rendered_manifest.json"
            )

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
        self.assertIn("stable_github_release_saved_report", payload["skipped_final_checks"])
        self.assertIn("external_l4_saved_reviewer_reports", payload["skipped_final_checks"])
        self.assertIn("production_claim_enforcement", payload["skipped_final_checks"])
        self.assertEqual(
            [
                check
                for check in release_gate.PRODUCTION_AUDIT_CHECK_NAMES
                if check not in run_production_gate.LOCAL_PREFLIGHT_VALIDATED_CHECKS
            ]
            + ["production_claim_enforcement"],
            run_production_gate.LOCAL_PREFLIGHT_SKIPPED_FINAL_CHECKS,
        )
        checklist_by_check = {row["check"]: row for row in payload["skipped_final_checklist"]}
        self.assertEqual("SKIPPED", checklist_by_check["external_l4_saved_reviewer_reports"]["status"])
        self.assertEqual(
            release_gate.PRODUCTION_CHECKLIST_GUIDANCE["external_l4_saved_reviewer_reports"]["evidence"],
            checklist_by_check["external_l4_saved_reviewer_reports"]["evidence"],
        )
        self.assertEqual(
            release_gate.PRODUCTION_CHECKLIST_GUIDANCE["external_l4_saved_reviewer_reports"]["next_action"],
            checklist_by_check["external_l4_saved_reviewer_reports"]["next_action"],
        )
        self.assertEqual("SKIPPED", checklist_by_check["stable_github_release"]["status"])
        self.assertEqual(
            release_gate.PRODUCTION_CHECKLIST_GUIDANCE["stable_github_release"]["next_action"],
            checklist_by_check["stable_github_release"]["next_action"],
        )
        self.assertEqual("SKIPPED", checklist_by_check["stable_github_release_saved_report"]["status"])
        self.assertEqual(
            release_gate.PRODUCTION_CHECKLIST_GUIDANCE["stable_github_release_saved_report"]["next_action"],
            checklist_by_check["stable_github_release_saved_report"]["next_action"],
        )
        self.assertIn(
            "without --local-evidence-preflight-only",
            checklist_by_check["production_claim_enforcement"]["next_action"],
        )
        artifact_by_name = {artifact["name"]: artifact for artifact in payload["input_artifacts"]}
        self.assertEqual(
            {
                "external_trial_json",
                "package_handoff_trial_json",
                "package_artifact_manifest_json",
                "package_readiness_json",
                "package_readme",
                "package_readme_zh",
                "package_zip",
                "package_zip_sha256",
            },
            set(artifact_by_name),
        )
        self.assertTrue(artifact_by_name["external_trial_json"]["exists"])
        self.assertEqual(64, len(artifact_by_name["external_trial_json"]["sha256"]))
        self.assertEqual("NOT_PRODUCTION_CLAIM", artifact_by_name["external_trial_json"]["claim_status"])
        self.assertEqual("EXTERNAL_L4_WORKFLOW_TRIAL", artifact_by_name["external_trial_json"]["evidence_scope"])
        self.assertIs(False, artifact_by_name["external_trial_json"]["final_production_signoff"])
        self.assertEqual("NOT_PRODUCTION_CLAIM", artifact_by_name["package_handoff_trial_json"]["claim_status"])
        self.assertEqual(
            "EXTERNAL_L4_WORKFLOW_TRIAL",
            artifact_by_name["package_handoff_trial_json"]["evidence_scope"],
        )
        self.assertIs(False, artifact_by_name["package_handoff_trial_json"]["final_production_signoff"])
        self.assertEqual("NOT_PRODUCTION_CLAIM", artifact_by_name["package_artifact_manifest_json"]["claim_status"])
        self.assertEqual(
            "EXTERNAL_L4_EVIDENCE_PACKAGE",
            artifact_by_name["package_artifact_manifest_json"]["evidence_scope"],
        )
        self.assertIs(False, artifact_by_name["package_artifact_manifest_json"]["final_production_signoff"])
        self.assertEqual(
            "NOT_PRODUCTION_CLAIM",
            artifact_by_name["package_artifact_manifest_json"]["trial_claim_status"],
        )
        self.assertEqual(
            "EXTERNAL_L4_WORKFLOW_TRIAL",
            artifact_by_name["package_artifact_manifest_json"]["trial_evidence_scope"],
        )
        self.assertIs(False, artifact_by_name["package_artifact_manifest_json"]["trial_final_production_signoff"])
        self.assertTrue(artifact_by_name["package_zip"]["exists"])
        self.assertEqual(64, len(artifact_by_name["package_zip"]["sha256"]))
        self.assertEqual("external-l4-demo", artifact_by_name["package_readiness_json"]["package_name"])
        self.assertEqual("READY", artifact_by_name["package_readiness_json"]["status"])
        self.assertEqual("NOT_PRODUCTION_CLAIM", artifact_by_name["package_readiness_json"]["claim_status"])
        self.assertEqual(
            "EXTERNAL_L4_READINESS_PRECHECK",
            artifact_by_name["package_readiness_json"]["evidence_scope"],
        )
        self.assertIs(False, artifact_by_name["package_readiness_json"]["final_production_signoff"])
        self.assertEqual(
            package_readiness_payload["generated_at_utc"],
            artifact_by_name["package_readiness_json"]["generated_at_utc"],
        )
        self.assertEqual(package_readiness_payload["workspace"], artifact_by_name["package_readiness_json"]["workspace"])
        self.assertEqual(package_readiness_payload["manifest"], artifact_by_name["package_readiness_json"]["manifest"])
        for readme_name in ["package_readme", "package_readme_zh"]:
            self.assertTrue(artifact_by_name[readme_name]["exists"])
            self.assertEqual("NOT_PRODUCTION_CLAIM", artifact_by_name[readme_name]["claim_status"])
            self.assertEqual("EXTERNAL_L4_EVIDENCE_PACKAGE", artifact_by_name[readme_name]["evidence_scope"])
            self.assertIs(False, artifact_by_name[readme_name]["final_production_signoff"])
            self.assertIs(True, artifact_by_name[readme_name]["review_entrypoint_present"])
            self.assertEqual(expected_handoff_contract, artifact_by_name[readme_name]["handoff_contract"])
            self.assertEqual("READY", artifact_by_name[readme_name]["readiness_status"])
            self.assertEqual("NOT_PRODUCTION_CLAIM", artifact_by_name[readme_name]["readiness_claim_status"])
            self.assertEqual(
                "EXTERNAL_L4_READINESS_PRECHECK",
                artifact_by_name[readme_name]["readiness_evidence_scope"],
            )
            self.assertIs(False, artifact_by_name[readme_name]["readiness_final_production_signoff"])
            self.assertEqual(
                package_readiness_payload["generated_at_utc"],
                artifact_by_name[readme_name]["readiness_generated_at_utc"],
            )
            self.assertEqual("external-l4-demo", artifact_by_name[readme_name]["readiness_package_name"])
            self.assertEqual(
                package_readiness_payload["workspace"],
                artifact_by_name[readme_name]["readiness_workspace"],
            )
            self.assertEqual(
                package_readiness_payload["manifest"],
                artifact_by_name[readme_name]["readiness_manifest"],
            )
        self.assertEqual(2, len(payload["gates"]))
        self.assertIn("Local External L4 Evidence Preflight", markdown)
        self.assertIn("claim_status: `NOT_PRODUCTION_CLAIM`", markdown)
        self.assertIn("evidence_scope: `LOCAL_EXTERNAL_L4_PREFLIGHT`", markdown)
        self.assertIn("final_evidence_acceptable: `False`", markdown)
        self.assertIn("## Input Artifacts", markdown)
        input_header = next(line for line in markdown.splitlines() if line.startswith("| Name |"))
        input_header_cells = [cell.strip() for cell in input_header.strip("|").split("|")]
        review_entrypoint_index = input_header_cells.index("Review Entrypoint")
        for readme_name in ["package_readme", "package_readme_zh"]:
            readme_line = next(
                line for line in markdown.splitlines() if line.startswith(f"| {readme_name} |")
            )
            readme_cells = [cell.strip() for cell in readme_line.strip("|").split("|")]
            self.assertEqual("True", readme_cells[review_entrypoint_index])
        self.assertIn("## Package README Handoff Contracts", markdown)
        self.assertIn("package_readme_zh", markdown)
        self.assertIn("morphojet_objects_csv", markdown)
        self.assertIn("## Skipped Final Checks", markdown)
        self.assertIn("stable_github_release", markdown)
        self.assertIn("Trial Claim Status", markdown)
        self.assertIn("Readiness Generated At", markdown)
        self.assertIn("Readiness Workspace", markdown)
        self.assertIn("Readiness Manifest", markdown)
        self.assertIn("EXTERNAL_L4_READINESS_PRECHECK", markdown)
        self.assertIn(package_readiness_payload["generated_at_utc"], markdown)
        self.assertIn("package_artifact_manifest_json", markdown)
        self.assertIn(package_readiness_payload["workspace"], markdown)
        self.assertIn(package_readiness_payload["manifest"], markdown)
        self.assertIn("package_readme", markdown)
        self.assertIn("package_readme_zh", markdown)
        self.assertIn("package_zip", markdown)
        self.assertIn("Validate external L4 evidence package", markdown)
        self.assertIn("does not satisfy the stable GitHub release", markdown)

    def test_local_evidence_preflight_records_absolute_paths_for_relative_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            package = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            resolved_root = root.resolve()
            package_dir = Path(package["package_dir"]).resolve()
            out_json = root / "reports" / "preflight.json"
            old_cwd = Path.cwd()
            try:
                os.chdir(root)
                args = self.parse(
                    "--external-trial-json",
                    str(trial_json.resolve().relative_to(resolved_root)),
                    "--external-trial-root",
                    ".",
                    "--external-evidence-package-dir",
                    str(package_dir.relative_to(resolved_root)),
                    "--local-evidence-preflight-json",
                    "reports/preflight.json",
                    "--local-evidence-preflight-md",
                    "reports/preflight.md",
                    "--local-evidence-preflight-only",
                )
                with contextlib.redirect_stdout(io.StringIO()):
                    status = run_production_gate.run_local_evidence_preflight(args)
            finally:
                os.chdir(old_cwd)

            payload = json.loads(out_json.read_text(encoding="utf-8"))

        self.assertEqual(0, status)
        metadata = payload["metadata"]
        for key in [
            "external_trial_json",
            "external_trial_root",
            "external_evidence_package_dir",
        ]:
            self.assertTrue(Path(metadata[key]).is_absolute(), key)
        for artifact in payload["input_artifacts"]:
            self.assertTrue(Path(artifact["path"]).is_absolute(), artifact["name"])
        for flag in [
            "--external-trial-json",
            "--external-trial-root",
            "--external-evidence-package-dir",
            "--local-evidence-preflight-json",
            "--local-evidence-preflight-md",
        ]:
            values = run_production_gate.argv_values(metadata["argv"], flag)
            self.assertEqual(1, len(values), flag)
            self.assertIsNotNone(values[0], flag)
            self.assertTrue(Path(values[0]).is_absolute(), flag)

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

    def test_verify_local_evidence_preflight_report_rejects_trial_scope_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            status, out_json, _trial_json, _package_dir = self.write_local_preflight(root)
            payload = json.loads(out_json.read_text(encoding="utf-8"))
            artifact_by_name = {artifact["name"]: artifact for artifact in payload["input_artifacts"]}
            artifact_by_name["external_trial_json"]["claim_status"] = "FINAL_PRODUCTION_CLAIM"
            out_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                verify_status = run_production_gate.main(
                    [
                        "--verify-local-evidence-preflight-report",
                        str(out_json),
                    ]
                )

        self.assertEqual(0, status)
        self.assertEqual(1, verify_status)
        self.assertIn(
            "input_artifacts.external_trial_json.claim_status=FINAL_PRODUCTION_CLAIM",
            stderr.getvalue(),
        )

    def test_verify_local_evidence_preflight_report_rejects_packaged_trial_scope_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            status, out_json, _trial_json, _package_dir = self.write_local_preflight(root)
            payload = json.loads(out_json.read_text(encoding="utf-8"))
            artifact_by_name = {artifact["name"]: artifact for artifact in payload["input_artifacts"]}
            artifact_by_name["package_handoff_trial_json"]["final_production_signoff"] = True
            out_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                verify_status = run_production_gate.main(
                    [
                        "--verify-local-evidence-preflight-report",
                        str(out_json),
                    ]
                )

        self.assertEqual(0, status)
        self.assertEqual(1, verify_status)
        self.assertIn(
            "input_artifacts.package_handoff_trial_json.final_production_signoff must be false",
            stderr.getvalue(),
        )

    def test_verify_local_evidence_preflight_report_rejects_package_manifest_scope_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            status, out_json, _trial_json, _package_dir = self.write_local_preflight(root)
            payload = json.loads(out_json.read_text(encoding="utf-8"))
            artifact_by_name = {artifact["name"]: artifact for artifact in payload["input_artifacts"]}
            artifact_by_name["package_artifact_manifest_json"]["trial_evidence_scope"] = (
                "FINAL_PRODUCTION_RELEASE_GATE"
            )
            out_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                verify_status = run_production_gate.main(
                    [
                        "--verify-local-evidence-preflight-report",
                        str(out_json),
                    ]
                )

        self.assertEqual(0, status)
        self.assertEqual(1, verify_status)
        self.assertIn(
            "input_artifacts.package_artifact_manifest_json.trial_evidence_scope=FINAL_PRODUCTION_RELEASE_GATE",
            stderr.getvalue(),
        )

    def test_verify_local_evidence_preflight_files_recomputes_trial_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            status, out_json, trial_json, _package_dir = self.write_local_preflight(root)
            trial = json.loads(trial_json.read_text(encoding="utf-8"))
            trial["claim_status"] = "FINAL_PRODUCTION_CLAIM"
            trial_json.write_text(json.dumps(trial, indent=2) + "\n", encoding="utf-8")
            payload = json.loads(out_json.read_text(encoding="utf-8"))
            artifact_by_name = {artifact["name"]: artifact for artifact in payload["input_artifacts"]}
            artifact_by_name["external_trial_json"]["size_bytes"] = trial_json.stat().st_size
            artifact_by_name["external_trial_json"]["sha256"] = run_production_gate.release_gate.sha256_file(
                trial_json
            )
            out_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                verify_status = run_production_gate.main(
                    [
                        "--verify-local-evidence-preflight-report",
                        str(out_json),
                        "--verify-local-evidence-preflight-files",
                    ]
                )

        self.assertEqual(0, status)
        self.assertEqual(1, verify_status)
        self.assertIn("input artifact claim_status mismatch: external_trial_json", stderr.getvalue())

    def test_verify_local_evidence_preflight_files_recomputes_manifest_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            status, out_json, _trial_json, package_dir = self.write_local_preflight(root)
            manifest_path = package_dir / "artifact_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["trial_final_production_signoff"] = True
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            payload = json.loads(out_json.read_text(encoding="utf-8"))
            artifact_by_name = {artifact["name"]: artifact for artifact in payload["input_artifacts"]}
            artifact_by_name["package_artifact_manifest_json"]["size_bytes"] = manifest_path.stat().st_size
            artifact_by_name["package_artifact_manifest_json"]["sha256"] = (
                run_production_gate.release_gate.sha256_file(manifest_path)
            )
            out_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                verify_status = run_production_gate.main(
                    [
                        "--verify-local-evidence-preflight-report",
                        str(out_json),
                        "--verify-local-evidence-preflight-files",
                    ]
                )

        self.assertEqual(0, status)
        self.assertEqual(1, verify_status)
        self.assertIn(
            "input artifact trial_final_production_signoff mismatch: package_artifact_manifest_json",
            stderr.getvalue(),
        )

    def test_verify_local_evidence_preflight_files_recomputes_package_readiness_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            status, out_json, _trial_json, package_dir = self.write_local_preflight(
                root,
                package_name="external-l4-demo",
            )
            readiness_path = package_dir / "readiness.json"
            readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
            readiness["claim_status"] = "FINAL_PRODUCTION_CLAIM"
            readiness["evidence_scope"] = "FINAL_PRODUCTION_RELEASE_GATE"
            readiness["final_production_signoff"] = True
            readiness_path.write_text(json.dumps(readiness, indent=2) + "\n", encoding="utf-8")
            payload = json.loads(out_json.read_text(encoding="utf-8"))
            artifact_by_name = {artifact["name"]: artifact for artifact in payload["input_artifacts"]}
            artifact_by_name["package_readiness_json"]["size_bytes"] = readiness_path.stat().st_size
            artifact_by_name["package_readiness_json"]["sha256"] = run_production_gate.release_gate.sha256_file(
                readiness_path
            )
            out_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                verify_status = run_production_gate.main(
                    [
                        "--verify-local-evidence-preflight-report",
                        str(out_json),
                        "--verify-local-evidence-preflight-files",
                    ]
                )

        self.assertEqual(0, status)
        self.assertEqual(1, verify_status)
        self.assertIn(
            "input_artifacts.package_readiness_json.claim_status must match package readiness report",
            stderr.getvalue(),
        )
        self.assertIn(
            "input_artifacts.package_readiness_json.evidence_scope must match package readiness report",
            stderr.getvalue(),
        )
        self.assertIn(
            "input_artifacts.package_readiness_json.final_production_signoff must match package readiness report",
            stderr.getvalue(),
        )

    def test_verify_local_evidence_preflight_report_rejects_artifact_path_tampering(self) -> None:
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
            for artifact in payload["input_artifacts"]:
                if artifact["name"] == "external_trial_json":
                    artifact["path"] = str(root / "other_trial.json")
            out_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                status = run_production_gate.main(
                    [
                        "--verify-local-evidence-preflight-report",
                        str(out_json),
                    ]
                )

        self.assertEqual(1, status)
        self.assertIn(
            "input_artifacts.external_trial_json.path does not match metadata.external_trial_json",
            stderr.getvalue(),
        )

    def test_verify_local_evidence_preflight_report_rejects_metadata_package_path_tampering(self) -> None:
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
            payload["metadata"]["external_evidence_package_dir"] = str(root / "other-package")
            out_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                status = run_production_gate.main(
                    [
                        "--verify-local-evidence-preflight-report",
                        str(out_json),
                    ]
                )

        self.assertEqual(1, status)
        self.assertIn(
            "input_artifacts.package_handoff_trial_json.path does not match "
            "metadata.external_evidence_package_dir",
            stderr.getvalue(),
        )

    def test_verify_local_evidence_preflight_report_rejects_package_readiness_path_tampering(self) -> None:
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
            for artifact in payload["input_artifacts"]:
                if artifact["name"] == "package_readiness_json":
                    artifact["path"] = str(root / "other-readiness.json")
            out_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                status = run_production_gate.main(
                    [
                        "--verify-local-evidence-preflight-report",
                        str(out_json),
                    ]
                )

        self.assertEqual(1, status)
        self.assertIn(
            "input_artifacts.package_readiness_json.path does not match "
            "metadata.external_evidence_package_dir",
            stderr.getvalue(),
        )

    def test_verify_local_evidence_preflight_report_rejects_package_readiness_name_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root, package_name="external-l4-demo")
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
            for artifact in payload["input_artifacts"]:
                if artifact["name"] == "package_readiness_json":
                    artifact["package_name"] = "other-demo"
            out_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                status = run_production_gate.main(
                    [
                        "--verify-local-evidence-preflight-report",
                        str(out_json),
                    ]
                )

        self.assertEqual(1, status)
        self.assertIn(
            "input_artifacts.package_readiness_json.package_name must match package readiness report",
            stderr.getvalue(),
        )

    def test_verify_local_evidence_preflight_report_rejects_package_readiness_scope_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            status, out_json, _trial_json, _package_dir = self.write_local_preflight(
                root,
                package_name="external-l4-demo",
            )
            payload = json.loads(out_json.read_text(encoding="utf-8"))
            artifact_by_name = {artifact["name"]: artifact for artifact in payload["input_artifacts"]}
            artifact_by_name["package_readiness_json"]["status"] = "PASS"
            artifact_by_name["package_readiness_json"]["claim_status"] = "FINAL_PRODUCTION_CLAIM"
            artifact_by_name["package_readiness_json"]["evidence_scope"] = "FINAL_PRODUCTION_RELEASE_GATE"
            artifact_by_name["package_readiness_json"]["final_production_signoff"] = True
            artifact_by_name["package_readiness_json"]["generated_at_utc"] = "2026-07-03T00:00:00+00:00"
            out_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                verify_status = run_production_gate.main(
                    [
                        "--verify-local-evidence-preflight-report",
                        str(out_json),
                    ]
                )

        self.assertEqual(0, status)
        self.assertEqual(1, verify_status)
        self.assertIn("input_artifacts.package_readiness_json.status=PASS", stderr.getvalue())
        self.assertIn(
            "input_artifacts.package_readiness_json.claim_status=FINAL_PRODUCTION_CLAIM",
            stderr.getvalue(),
        )
        self.assertIn(
            "input_artifacts.package_readiness_json.evidence_scope=FINAL_PRODUCTION_RELEASE_GATE",
            stderr.getvalue(),
        )
        self.assertIn(
            "input_artifacts.package_readiness_json.final_production_signoff must be false",
            stderr.getvalue(),
        )
        self.assertIn(
            "input_artifacts.package_readiness_json.generated_at_utc must match package readiness report",
            stderr.getvalue(),
        )

    def test_verify_local_evidence_preflight_report_rejects_package_readme_scope_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            status, out_json, _trial_json, _package_dir = self.write_local_preflight(
                root,
                package_name="external-l4-demo",
            )
            payload = json.loads(out_json.read_text(encoding="utf-8"))
            artifact_by_name = {artifact["name"]: artifact for artifact in payload["input_artifacts"]}
            artifact_by_name["package_readme_zh"]["readiness_claim_status"] = "FINAL_PRODUCTION_CLAIM"
            artifact_by_name["package_readme_zh"]["readiness_evidence_scope"] = "FINAL_PRODUCTION_RELEASE_GATE"
            artifact_by_name["package_readme_zh"]["readiness_final_production_signoff"] = True
            out_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                verify_status = run_production_gate.main(
                    [
                        "--verify-local-evidence-preflight-report",
                        str(out_json),
                    ]
                )

        self.assertEqual(0, status)
        self.assertEqual(1, verify_status)
        self.assertIn(
            "input_artifacts.package_readme_zh.readiness_claim_status=FINAL_PRODUCTION_CLAIM",
            stderr.getvalue(),
        )
        self.assertIn(
            "input_artifacts.package_readme_zh.readiness_evidence_scope=FINAL_PRODUCTION_RELEASE_GATE",
            stderr.getvalue(),
        )
        self.assertIn(
            "input_artifacts.package_readme_zh.readiness_final_production_signoff must be false",
            stderr.getvalue(),
        )

    def test_verify_local_evidence_preflight_report_rejects_package_readme_handoff_contract_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            status, out_json, _trial_json, _package_dir = self.write_local_preflight(
                root,
                package_name="external-l4-demo",
            )
            payload = json.loads(out_json.read_text(encoding="utf-8"))
            artifact_by_name = {artifact["name"]: artifact for artifact in payload["input_artifacts"]}
            artifact_by_name["package_readme"]["handoff_contract"] = {
                "morphojet_objects_csv": "external/morphojet/Other.csv"
            }
            out_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                verify_status = run_production_gate.main(
                    [
                        "--verify-local-evidence-preflight-report",
                        str(out_json),
                    ]
                )

        self.assertEqual(0, status)
        self.assertEqual(1, verify_status)
        self.assertIn(
            "input_artifacts.package_readme.handoff_contract must match package README",
            stderr.getvalue(),
        )
        self.assertIn(
            "input_artifacts.package_readme.handoff_contract must match rendered manifest",
            stderr.getvalue(),
        )

    def test_verify_local_evidence_preflight_report_rejects_package_readme_reviewer_entrypoint_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            status, out_json, _trial_json, _package_dir = self.write_local_preflight(
                root,
                package_name="external-l4-demo",
            )
            payload = json.loads(out_json.read_text(encoding="utf-8"))
            artifact_by_name = {artifact["name"]: artifact for artifact in payload["input_artifacts"]}
            artifact_by_name["package_readme_zh"]["review_entrypoint_present"] = False
            out_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                verify_status = run_production_gate.main(
                    [
                        "--verify-local-evidence-preflight-report",
                        str(out_json),
                    ]
                )

        self.assertEqual(0, status)
        self.assertEqual(1, verify_status)
        self.assertIn(
            "input_artifacts.package_readme_zh.review_entrypoint_present must be true",
            stderr.getvalue(),
        )

    def test_verify_local_evidence_preflight_files_recomputes_package_readme_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            status, out_json, _trial_json, package_dir = self.write_local_preflight(
                root,
                package_name="external-l4-demo",
            )
            readme_path = package_dir / "README.md"
            readme_path.write_text(
                readme_path.read_text(encoding="utf-8").replace(
                    "- readiness_claim_status: `NOT_PRODUCTION_CLAIM`",
                    "- readiness_claim_status: `FINAL_PRODUCTION_CLAIM`",
                ),
                encoding="utf-8",
            )
            payload = json.loads(out_json.read_text(encoding="utf-8"))
            artifact_by_name = {artifact["name"]: artifact for artifact in payload["input_artifacts"]}
            artifact_by_name["package_readme"]["size_bytes"] = readme_path.stat().st_size
            artifact_by_name["package_readme"]["sha256"] = run_production_gate.release_gate.sha256_file(readme_path)
            out_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                verify_status = run_production_gate.main(
                    [
                        "--verify-local-evidence-preflight-report",
                        str(out_json),
                        "--verify-local-evidence-preflight-files",
                    ]
                )

        self.assertEqual(0, status)
        self.assertEqual(1, verify_status)
        self.assertIn("input artifact readiness_claim_status mismatch: package_readme", stderr.getvalue())

    def test_verify_local_evidence_preflight_files_recomputes_package_readme_handoff_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            status, out_json, _trial_json, package_dir = self.write_local_preflight(
                root,
                package_name="external-l4-demo",
            )
            readme_path = package_dir / "README.zh-CN.md"
            readme_path.write_text(
                readme_path.read_text(encoding="utf-8").replace(
                    "- morphojet_objects_csv: `external/morphojet/Objects.csv`",
                    "- morphojet_objects_csv: `external/morphojet/Other.csv`",
                ),
                encoding="utf-8",
            )
            payload = json.loads(out_json.read_text(encoding="utf-8"))
            artifact_by_name = {artifact["name"]: artifact for artifact in payload["input_artifacts"]}
            artifact_by_name["package_readme_zh"]["size_bytes"] = readme_path.stat().st_size
            artifact_by_name["package_readme_zh"]["sha256"] = run_production_gate.release_gate.sha256_file(
                readme_path
            )
            file_failures = run_production_gate.validate_local_evidence_preflight_files(payload)
            out_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                verify_status = run_production_gate.main(
                    [
                        "--verify-local-evidence-preflight-report",
                        str(out_json),
                        "--verify-local-evidence-preflight-files",
                    ]
                )

        self.assertEqual(0, status)
        self.assertIn("input artifact handoff_contract mismatch: package_readme_zh", file_failures)
        self.assertEqual(1, verify_status)
        self.assertIn(
            "input_artifacts.package_readme_zh.handoff_contract must match package README",
            stderr.getvalue(),
        )

    def test_verify_local_evidence_preflight_files_recomputes_package_readme_reviewer_entrypoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            status, out_json, _trial_json, package_dir = self.write_local_preflight(
                root,
                package_name="external-l4-demo",
            )
            readme_path = package_dir / "README.zh-CN.md"
            readme_path.write_text(
                readme_path.read_text(encoding="utf-8").replace("## 中文 reviewer 入口", "## 复核说明"),
                encoding="utf-8",
            )
            payload = json.loads(out_json.read_text(encoding="utf-8"))
            artifact_by_name = {artifact["name"]: artifact for artifact in payload["input_artifacts"]}
            artifact_by_name["package_readme_zh"]["size_bytes"] = readme_path.stat().st_size
            artifact_by_name["package_readme_zh"]["sha256"] = run_production_gate.release_gate.sha256_file(
                readme_path
            )
            file_failures = run_production_gate.validate_local_evidence_preflight_files(payload)
            out_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                verify_status = run_production_gate.main(
                    [
                        "--verify-local-evidence-preflight-report",
                        str(out_json),
                        "--verify-local-evidence-preflight-files",
                    ]
                )

        self.assertEqual(0, status)
        self.assertIn("input artifact review_entrypoint_present mismatch: package_readme_zh", file_failures)
        self.assertEqual(1, verify_status)
        self.assertIn(
            "input_artifacts.package_readme_zh.review_entrypoint_present must match package README",
            stderr.getvalue(),
        )

    def test_verify_local_evidence_preflight_report_rejects_package_readiness_manifest_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root, package_name="external-l4-demo")
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
            for artifact in payload["input_artifacts"]:
                if artifact["name"] == "package_readiness_json":
                    artifact["manifest"] = str(root / "external" / "other.json")
            out_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                status = run_production_gate.main(
                    [
                        "--verify-local-evidence-preflight-report",
                        str(out_json),
                    ]
                )

        self.assertEqual(1, status)
        self.assertIn(
            "input_artifacts.package_readiness_json.manifest must match package readiness report",
            stderr.getvalue(),
        )

    def test_verify_local_evidence_preflight_report_rejects_package_readiness_workspace_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root, package_name="external-l4-demo")
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
            for artifact in payload["input_artifacts"]:
                if artifact["name"] == "package_readiness_json":
                    artifact["workspace"] = str(root / "other-workspace")
            out_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                status = run_production_gate.main(
                    [
                        "--verify-local-evidence-preflight-report",
                        str(out_json),
                    ]
                )

        self.assertEqual(1, status)
        self.assertIn(
            "input_artifacts.package_readiness_json.workspace must match package readiness report",
            stderr.getvalue(),
        )

    def test_verify_local_evidence_preflight_report_recomputes_gates(self) -> None:
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
                        "--verify-local-evidence-preflight-gates",
                    ]
                )

        self.assertEqual(0, status)
        self.assertIn("verified_gates=True", stdout.getvalue())

    def test_verify_local_evidence_preflight_report_rejects_gate_detail_tampering(self) -> None:
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
            payload["gates"][0]["detail"] = "External workflow trial PASS: stale detail"
            out_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                status = run_production_gate.main(
                    [
                        "--verify-local-evidence-preflight-report",
                        str(out_json),
                        "--verify-local-evidence-preflight-gates",
                    ]
                )

        self.assertEqual(1, status)
        self.assertIn("gate.detail changed", stderr.getvalue())

    def test_verify_local_evidence_preflight_report_rejects_status_gate_mismatch(self) -> None:
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
            payload["gates"][0]["status"] = "FAIL"
            out_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                status = run_production_gate.main(
                    [
                        "--verify-local-evidence-preflight-report",
                        str(out_json),
                    ]
                )

        self.assertEqual(1, status)
        self.assertIn(
            "local evidence preflight status does not match gate statuses: PASS != FAIL",
            stderr.getvalue(),
        )

    def test_verify_local_evidence_preflight_report_rejects_duplicate_gate_names(self) -> None:
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
            payload["gates"][1]["name"] = payload["gates"][0]["name"]
            out_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                status = run_production_gate.main(
                    [
                        "--verify-local-evidence-preflight-report",
                        str(out_json),
                    ]
                )

        self.assertEqual(1, status)
        self.assertIn("duplicate gate name: Validate external L4 workflow trial report", stderr.getvalue())

    def test_verify_local_evidence_preflight_report_rejects_bad_gate_shape(self) -> None:
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
            payload["gates"][0]["command"] = "not-a-list"
            payload["gates"][0]["elapsed_seconds"] = -1
            out_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                status = run_production_gate.main(
                    [
                        "--verify-local-evidence-preflight-report",
                        str(out_json),
                    ]
                )

        self.assertEqual(1, status)
        self.assertIn(
            "gate command must be null or a string list: Validate external L4 workflow trial report",
            stderr.getvalue(),
        )
        self.assertIn(
            "gate elapsed_seconds must be non-negative: Validate external L4 workflow trial report",
            stderr.getvalue(),
        )

    def test_verify_local_evidence_preflight_report_rejects_changed_trial_gate(self) -> None:
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
            trial = json.loads(trial_json.read_text(encoding="utf-8"))
            trial["external_evidence"]["manual_csv_editing"] = True
            trial_json.write_text(json.dumps(trial, indent=2) + "\n", encoding="utf-8")

            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                status = run_production_gate.main(
                    [
                        "--verify-local-evidence-preflight-report",
                        str(out_json),
                        "--verify-local-evidence-preflight-gates",
                    ]
                )

        self.assertEqual(1, status)
        self.assertIn("gate.status changed", stderr.getvalue())

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

    def test_verify_local_evidence_preflight_report_rejects_skipped_checklist_tampering(self) -> None:
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
            stable_index = next(
                index
                for index, row in enumerate(payload["skipped_final_checklist"])
                if row["check"] == "stable_github_release"
            )
            payload["skipped_final_checklist"][stable_index]["status"] = "PASS"
            payload["skipped_final_checklist"][stable_index]["next_action"] = "No action needed."
            out_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                status = run_production_gate.main(
                    [
                        "--verify-local-evidence-preflight-report",
                        str(out_json),
                    ]
                )

        self.assertEqual(1, status)
        self.assertIn("skipped_final_checklist row mismatch for stable_github_release", stderr.getvalue())

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

    def test_verify_local_evidence_preflight_report_rejects_non_utc_metadata_timestamp(self) -> None:
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
            payload["metadata"]["generated_at_utc"] = "2026-07-07T12:00:00+08:00"
            out_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                status = run_production_gate.main(
                    [
                        "--verify-local-evidence-preflight-report",
                        str(out_json),
                    ]
                )

        self.assertEqual(1, status)
        self.assertIn("metadata.generated_at_utc must be UTC", stderr.getvalue())

    def test_verify_local_evidence_preflight_report_rejects_argv_tampering(self) -> None:
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
            payload["metadata"]["argv"] = [
                "benchmark/run_production_gate.py",
                "--external-trial-json",
                str(trial_json),
                "--external-trial-root",
                str(root),
                "--external-evidence-package-dir",
                str(root / "other-package"),
                "--github-release-tag",
                "v0.1.0",
            ]
            out_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                status = run_production_gate.main(
                    [
                        "--verify-local-evidence-preflight-report",
                        str(out_json),
                    ]
                )

        self.assertEqual(1, status)
        self.assertIn(
            "metadata.argv must include exactly one --local-evidence-preflight-only",
            stderr.getvalue(),
        )
        self.assertIn(
            "metadata.external_evidence_package_dir must match metadata.argv "
            "--external-evidence-package-dir",
            stderr.getvalue(),
        )

    def test_verify_local_evidence_preflight_report_rejects_bad_metadata_paths(self) -> None:
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
            payload["metadata"]["external_trial_json"] = ""
            payload["metadata"]["external_trial_root"] = None
            payload["metadata"]["external_evidence_package_dir"] = 123
            payload["metadata"]["external_trial_verification_report"] = ""
            out_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                status = run_production_gate.main(
                    [
                        "--verify-local-evidence-preflight-report",
                        str(out_json),
                    ]
                )

        self.assertEqual(1, status)
        self.assertIn("metadata.external_trial_json must be a non-empty string", stderr.getvalue())
        self.assertIn("metadata.external_trial_root must be a non-empty string", stderr.getvalue())
        self.assertIn("metadata.external_evidence_package_dir must be a non-empty string", stderr.getvalue())
        self.assertIn(
            "metadata.external_trial_verification_report must be null or a non-empty string",
            stderr.getvalue(),
        )

    def test_verify_local_evidence_preflight_report_rejects_relative_metadata_path(self) -> None:
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
            payload["metadata"]["external_trial_json"] = "external/handoff_trial.json"
            out_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                status = run_production_gate.main(
                    [
                        "--verify-local-evidence-preflight-report",
                        str(out_json),
                    ]
                )

        self.assertEqual(1, status)
        self.assertIn("metadata.external_trial_json must be an absolute path", stderr.getvalue())

    def test_verify_local_evidence_preflight_report_rejects_relative_input_artifact_path(self) -> None:
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
            for artifact in payload["input_artifacts"]:
                if artifact["name"] == "external_trial_json":
                    artifact["path"] = "external/handoff_trial.json"
            out_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                status = run_production_gate.main(
                    [
                        "--verify-local-evidence-preflight-report",
                        str(out_json),
                    ]
                )

        self.assertEqual(1, status)
        self.assertIn("input artifact path must be absolute: external_trial_json", stderr.getvalue())

    def test_verify_local_evidence_preflight_report_rejects_relative_argv_path(self) -> None:
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
            argv = payload["metadata"]["argv"]
            argv[argv.index("--external-trial-json") + 1] = "external/handoff_trial.json"
            out_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                status = run_production_gate.main(
                    [
                        "--verify-local-evidence-preflight-report",
                        str(out_json),
                    ]
                )

        self.assertEqual(1, status)
        self.assertIn(
            "metadata.argv --external-trial-json must use an absolute path",
            stderr.getvalue(),
        )

    def test_verify_local_evidence_preflight_report_rejects_duplicate_input_paths(self) -> None:
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
            package_trial_path = str(Path(package["package_dir"]) / "handoff_trial.json")
            payload["metadata"]["external_trial_json"] = package_trial_path
            for artifact in payload["input_artifacts"]:
                if artifact["name"] == "external_trial_json":
                    artifact["path"] = package_trial_path
            out_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                status = run_production_gate.main(
                    [
                        "--verify-local-evidence-preflight-report",
                        str(out_json),
                    ]
                )

        self.assertEqual(1, status)
        self.assertIn(
            "duplicate input artifact path: external_trial_json and package_handoff_trial_json",
            stderr.getvalue(),
        )

    def test_verify_local_evidence_preflight_report_rejects_unreachable_commit(self) -> None:
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
            payload["metadata"]["git_commit"] = "f" * 40
            out_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                status = run_production_gate.main(
                    [
                        "--verify-local-evidence-preflight-report",
                        str(out_json),
                    ]
                )

        self.assertEqual(1, status)
        self.assertIn("metadata.git_commit is not reachable", stderr.getvalue())

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

    def test_local_evidence_preflight_rejects_github_release_verification_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            package = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            github_report = root / "github-release-verification.json"
            github_report.write_text("{}\n", encoding="utf-8")

            with contextlib.redirect_stderr(io.StringIO()) as stderr:
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
                        "--github-release-verification-report",
                        str(github_report),
                        "--local-evidence-preflight-json",
                        str(root / "main-preflight.json"),
                        "--local-evidence-preflight-md",
                        str(root / "main-preflight.md"),
                        "--local-evidence-preflight-only",
                    ]
                )

        self.assertEqual(2, status)
        self.assertIn(
            "--github-release-verification-report is not used with --local-evidence-preflight-only",
            stderr.getvalue(),
        )

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
