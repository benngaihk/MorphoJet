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
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmark"))
sys.path.insert(0, str(ROOT / "tests"))

import package_external_trial  # noqa: E402
import run_production_gate  # noqa: E402
import verify_external_evidence_package  # noqa: E402
import verify_external_trial_report  # noqa: E402
import verify_github_release  # noqa: E402
from test_release_gate import add_artifact_provenance, valid_external_trial, write_trial_artifacts  # noqa: E402


class RunProductionGateTest(unittest.TestCase):
    FULL_COMMIT = "a" * 40
    DOCTOR_COMMIT = "a" * 12

    def write_valid_trial(self, root: Path) -> Path:
        trial = valid_external_trial()
        write_trial_artifacts(trial, root)
        add_artifact_provenance(trial, root)
        trial_json = root / "external" / "handoff_trial.json"
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
                    "status": "PASS",
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
        self.assertIn("--require-stable-report", gates[0].command)
        self.assertIn("--verify-git-commit", gates[0].command)
        self.assertIn("--expect-tag", gates[0].command)
        self.assertEqual("v0.1.0", gates[0].command[gates[0].command.index("--expect-tag") + 1])

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
            "saved GitHub release report repo does not match production repo: other/repo != benngaihk/MorphoJet",
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
