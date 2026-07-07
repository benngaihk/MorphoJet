#!/usr/bin/env python3
"""Unit tests for release gate helpers."""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmark"))

import release_gate  # noqa: E402


def valid_external_trial() -> dict:
    external_evidence = {
        "lab_or_org": "External Lab",
        "workflow_owner": "Assay Owner",
        "dataset_name": "Batch 42",
        "dataset_source": "LIMS export",
        "downstream_workflow": "Existing analysis notebook",
        "execution_environment": "Ubuntu 24.04, Python 3.12",
        "reviewer_name_or_role": "External QA Reviewer",
        "reviewed_at_utc": "2026-07-03T01:02:03+00:00",
        "signoff_statement": "Reviewed against the lab workflow acceptance criteria.",
        "manual_csv_editing": False,
        "acceptance_criteria": [
            "Existing downstream workflow consumes MorphoJet output without manual CSV edits."
        ],
    }
    manifest = {
        "trial_id": "external-lab-supported-columns-handoff",
        "morphojet_objects_csv": "external/morphojet/Objects.csv",
        "external_evidence": copy.deepcopy(external_evidence),
        "exports": [
            {
                "name": "Cells",
                "object_set": "Cells",
                "channels": ["DNA"],
                "out_csv": "external/morphojet/Cells.wide.csv",
                "expected_cellprofiler_csv": "external/cellprofiler/Cells.csv",
                "comparison_report": "external/workflow_bridge.md",
                "comparison_json": "external/workflow_bridge.json",
            }
        ],
        "downstream_checks": [
            {
                "name": "Validate downstream contract",
                "command": ["python3", "benchmark/check_cellprofiler_wide_contract.py"],
                "artifacts": ["external/handoff_contract.json"],
            }
        ],
    }
    return {
        "trial_id": "external-lab-supported-columns-handoff",
        "status": "PASS",
        "metadata": {
            "schema_version": 1,
            "generator": "benchmark/run_handoff_trial.py",
            "generated_at_utc": "2026-07-03T00:00:00+00:00",
            "git_commit": release_gate.git_commit(),
            "git_dirty": False,
            "git_status": [],
            "argv": [
                "benchmark/run_handoff_trial.py",
                "external_manifest.json",
                "--readiness-report",
                "external/readiness.json",
                "--out-json",
                "external/handoff_trial.json",
                "--out-md",
                "external/handoff_trial.md",
                "--require-external-evidence",
            ],
        },
        "manifest": "external_manifest.json",
        "rendered_manifest": manifest,
        "external_evidence": external_evidence,
        "readiness_report": {
            "path": "external/readiness.json",
            "size_bytes": 1,
            "sha256": "0" * 64,
            "status": "READY",
            "claim_status": "NOT_PRODUCTION_CLAIM",
            "generated_at_utc": "2026-07-02T23:59:59+00:00",
            "workspace": "/external",
            "manifest": "/external/external_manifest.json",
            "package_name": None,
        },
        "artifacts": release_gate.rendered_manifest_artifacts(manifest),
        "steps": [
            {
                "name": name,
                "command": command,
                "status": "PASS",
                "elapsed_seconds": 0.1,
                "detail": "ok",
            }
            for name, command in release_gate.rendered_manifest_step_commands(manifest)
        ],
    }


def write_trial_artifacts(trial: dict, root: Path, empty_paths: set[str] | None = None) -> None:
    empty_paths = empty_paths or set()
    readiness_summary = trial.get("readiness_report")
    if isinstance(readiness_summary, dict):
        readiness_path = root / "external" / "readiness.json"
        readiness_path.parent.mkdir(parents=True, exist_ok=True)
        readiness_payload = {
            "schema_version": 1,
            "checker": "benchmark/check_external_l4_readiness.py",
            "generated_at_utc": readiness_summary["generated_at_utc"],
            "argv": [
                "benchmark/check_external_l4_readiness.py",
                "--workspace",
                str((root / "external").resolve()),
                "--json-out",
                str(readiness_path.resolve()),
            ],
            "status": "READY",
            "claim_status": "NOT_PRODUCTION_CLAIM",
            "workspace": str((root / "external").resolve()),
            "manifest": str((root / "external" / "external_manifest.json").resolve()),
            "package_name": readiness_summary.get("package_name"),
            "variables": {"base_dir": str((root / "external").resolve())},
            "checks": [],
            "issues": [],
        }
        if readiness_summary.get("package_name") is not None:
            readiness_payload["argv"].extend(["--package-name", readiness_summary["package_name"]])
        readiness_path.write_text(json.dumps(readiness_payload, indent=2) + "\n", encoding="utf-8")
        readiness_summary.update(
            {
                "path": str(readiness_path.resolve()),
                "size_bytes": readiness_path.stat().st_size,
                "sha256": release_gate.sha256_file(readiness_path),
                "workspace": str((root / "external").resolve()),
                "manifest": str((root / "external" / "external_manifest.json").resolve()),
            }
        )
        argv = trial["metadata"]["argv"]
        argv[argv.index("--readiness-report") + 1] = str(readiness_path.resolve())
    for artifact in trial["artifacts"]:
        path = root / artifact
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("" if artifact in empty_paths else "{}\n")


def add_artifact_provenance(trial: dict, root: Path) -> None:
    trial["artifact_provenance"] = []
    for artifact in trial["artifacts"]:
        path = root / artifact
        trial["artifact_provenance"].append(
            {
                "path": artifact,
                "size_bytes": path.stat().st_size,
                "sha256": release_gate.sha256_file(path),
            }
        )


class ReleaseGateTest(unittest.TestCase):
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
            "git_commit": "abc123",
            "git_dirty": False,
            "git_status": [],
            "argv": ["benchmark/release_gate.py"],
        }

    def test_production_claim_audit_defaults_to_incomplete_without_l4_or_stable_release(self) -> None:
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

        audit = release_gate.build_production_claim_audit(
            self.production_args(),
            gates,
            {"git_commit": "abc123"},
        )

        self.assertEqual("INCOMPLETE", audit["status"])
        statuses = {check["name"]: check["status"] for check in audit["checks"]}
        self.assertEqual("MISSING", statuses["clean_git_worktree"])
        self.assertEqual("PASS", statuses["standard_code_and_artifact_gates"])
        self.assertEqual("MISSING", statuses["l3_provenance_hashes"])
        self.assertEqual("MISSING", statuses["external_l4_workflow_trial"])
        self.assertEqual("MISSING", statuses["external_l4_evidence_package"])
        self.assertEqual("MISSING", statuses["stable_github_release"])
        self.assertEqual(
            [
                "clean_git_worktree",
                "l3_provenance_hashes",
                "external_l4_workflow_trial",
                "external_l4_evidence_package",
                "stable_github_release",
            ],
            audit["missing_or_failed_checks"],
        )

    def test_production_claim_audit_passes_when_required_claim_gates_pass(self) -> None:
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
                "Verify GitHub release assets",
            ]
        )

        audit = release_gate.build_production_claim_audit(
            self.production_args(
                require_clean_git=True,
                require_l3_provenance=True,
                external_trial_json=Path("handoff_trial.json"),
                external_evidence_package_dir=Path("external-l4-package"),
                verify_github_release="v0.1.0",
                github_release_kind="stable",
            ),
            gates,
            {"git_commit": "abc123"},
        )

        self.assertEqual("PASS", audit["status"])
        self.assertEqual([], audit["missing_or_failed_checks"])

    def test_require_production_claim_fails_incomplete_audit(self) -> None:
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
            payload = release_gate.write_report(
                self.production_args(
                    require_production_claim=True,
                    out_json=root / "report.json",
                    out_md=root / "report.md",
                ),
                gates,
                self.production_metadata(),
            )
            written_payload = json.loads((root / "report.json").read_text(encoding="utf-8"))

        self.assertEqual("FAIL", payload["status"])
        self.assertEqual("INCOMPLETE", payload["production_claim_status"])
        self.assertEqual("INCOMPLETE", payload["production_claim_audit"]["status"])
        self.assertEqual(
            [
                "clean_git_worktree",
                "l3_provenance_hashes",
                "external_l4_workflow_trial",
                "external_l4_evidence_package",
                "stable_github_release",
            ],
            payload["production_claim_audit"]["missing_or_failed_checks"],
        )
        self.assertEqual(
            payload["production_claim_audit"]["missing_or_failed_checks"],
            payload["missing_or_failed_checks"],
        )
        self.assertEqual("INCOMPLETE", written_payload["production_claim_status"])
        self.assertEqual(payload["missing_or_failed_checks"], written_payload["missing_or_failed_checks"])

    def test_require_production_claim_passes_complete_audit(self) -> None:
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
                "Verify GitHub release assets",
            ]
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = release_gate.write_report(
                self.production_args(
                    require_clean_git=True,
                    require_l3_provenance=True,
                    require_production_claim=True,
                    external_trial_json=Path("handoff_trial.json"),
                    external_evidence_package_dir=Path("external-l4-package"),
                    verify_github_release="v0.1.0",
                    github_release_kind="stable",
                    out_json=root / "report.json",
                    out_md=root / "report.md",
                ),
                gates,
                self.production_metadata(),
            )

        self.assertEqual("PASS", payload["status"])
        self.assertEqual("PASS", payload["production_claim_status"])
        self.assertEqual([], payload["missing_or_failed_checks"])
        self.assertEqual("PASS", payload["production_claim_audit"]["status"])

    def test_doc_path_allowlist(self) -> None:
        self.assertTrue(release_gate.is_doc_path("README.md"))
        self.assertTrue(release_gate.is_doc_path("README.zh-CN.md"))
        self.assertTrue(release_gate.is_doc_path("docs/PRODUCTION_READINESS.md"))
        self.assertFalse(release_gate.is_doc_path("corpus/README.md"))
        self.assertFalse(release_gate.is_doc_path("benchmark/release_gate.py"))
        self.assertFalse(release_gate.is_doc_path("crates/morphojet/src/main.rs"))

    def test_l3_provenance_compatible_path_allowlist(self) -> None:
        self.assertTrue(release_gate.is_l3_provenance_compatible_path("README.md"))
        self.assertTrue(release_gate.is_l3_provenance_compatible_path("README.zh-CN.md"))
        self.assertTrue(release_gate.is_l3_provenance_compatible_path("docs/PRODUCTION_READINESS.md"))
        self.assertTrue(release_gate.is_l3_provenance_compatible_path("tests/test_release_gate.py"))
        self.assertTrue(release_gate.is_l3_provenance_compatible_path("benchmark/check_external_l4_readiness.py"))
        self.assertTrue(release_gate.is_l3_provenance_compatible_path("benchmark/release_gate.py"))
        self.assertTrue(release_gate.is_l3_provenance_compatible_path("benchmark/build_release_archive.py"))
        self.assertTrue(release_gate.is_l3_provenance_compatible_path("benchmark/handoff/external_lab_template.json"))
        self.assertTrue(release_gate.is_l3_provenance_compatible_path("benchmark/package_external_trial.py"))
        self.assertTrue(release_gate.is_l3_provenance_compatible_path("benchmark/prepare_external_l4_trial.py"))
        self.assertTrue(release_gate.is_l3_provenance_compatible_path("benchmark/run_handoff_trial.py"))
        self.assertTrue(release_gate.is_l3_provenance_compatible_path("benchmark/run_production_gate.py"))
        self.assertTrue(release_gate.is_l3_provenance_compatible_path("benchmark/validate_claim_language.py"))
        self.assertTrue(release_gate.is_l3_provenance_compatible_path("benchmark/validate_handoff_manifest.py"))
        self.assertTrue(release_gate.is_l3_provenance_compatible_path("benchmark/verify_github_release.py"))
        self.assertTrue(release_gate.is_l3_provenance_compatible_path("benchmark/verify_external_trial_report.py"))
        self.assertTrue(release_gate.is_l3_provenance_compatible_path("benchmark/verify_external_evidence_package.py"))
        self.assertTrue(release_gate.is_l3_provenance_compatible_path("benchmark/verify_release_gate_report.py"))
        self.assertTrue(release_gate.is_l3_provenance_compatible_path("benchmark/verify_release_archive.py"))
        self.assertFalse(release_gate.is_l3_provenance_compatible_path("benchmark/run_cellbindb_oracle.py"))
        self.assertFalse(release_gate.is_l3_provenance_compatible_path("crates/morphojet/src/main.rs"))

    def test_external_trial_report_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial = valid_external_trial()
            write_trial_artifacts(trial, root)
            add_artifact_provenance(trial, root)

            self.assertEqual([], release_gate.external_trial_failures(trial, root))

    def test_external_trial_gate_detail_includes_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial = valid_external_trial()
            write_trial_artifacts(trial, root)
            add_artifact_provenance(trial, root)
            report = root / "handoff_trial.json"
            trial["metadata"]["argv"][trial["metadata"]["argv"].index("--out-json") + 1] = str(report)
            report.write_text(json.dumps(trial) + "\n")

            gate = release_gate.validate_external_trial_report(report, root)

        self.assertEqual("PASS", gate.status)
        self.assertIn(f"trial_commit={trial['metadata']['git_commit'][:12]}", gate.detail)
        self.assertIn("generated_at_utc=2026-07-03T00:00:00+00:00", gate.detail)

    def test_external_trial_gate_rejects_out_json_metadata_for_different_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial = valid_external_trial()
            write_trial_artifacts(trial, root)
            add_artifact_provenance(trial, root)
            report = root / "handoff_trial.json"
            trial["metadata"]["argv"][trial["metadata"]["argv"].index("--out-json") + 1] = str(
                root / "other_handoff_trial.json"
            )
            report.write_text(json.dumps(trial) + "\n")

            gate = release_gate.validate_external_trial_report(report, root)

        self.assertEqual("FAIL", gate.status)
        self.assertIn("metadata.argv --out-json must match external trial report path", gate.detail)

    def test_external_trial_requires_artifacts_to_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            failures = release_gate.external_trial_failures(valid_external_trial(), Path(tmp))

        self.assertIn("trial artifact does not exist: external/handoff_contract.json", failures)

    def test_external_trial_rejects_empty_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial = valid_external_trial()
            write_trial_artifacts(trial, root, empty_paths={"external/handoff_contract.json"})
            add_artifact_provenance(trial, root)

            failures = release_gate.external_trial_failures(trial, root)

        self.assertIn("trial artifact is empty: external/handoff_contract.json", failures)

    def test_external_trial_requires_artifact_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial = valid_external_trial()
            write_trial_artifacts(trial, root)

            failures = release_gate.external_trial_failures(trial, root)

        self.assertIn("trial artifact_provenance must be a non-empty list", failures)
        self.assertIn("trial artifact missing provenance: external/handoff_contract.json", failures)

    def test_external_trial_requires_rendered_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial = valid_external_trial()
            write_trial_artifacts(trial, root)
            add_artifact_provenance(trial, root)
            del trial["rendered_manifest"]

            failures = release_gate.external_trial_failures(trial, root)

        self.assertIn("rendered_manifest must be present for external workflow trial reports", failures)

    def test_external_trial_requires_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial = valid_external_trial()
            write_trial_artifacts(trial, root)
            add_artifact_provenance(trial, root)
            del trial["metadata"]

            failures = release_gate.external_trial_failures(trial, root)

        self.assertIn("metadata must be present for external workflow trial reports", failures)

    def test_external_trial_rejects_dirty_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial = valid_external_trial()
            write_trial_artifacts(trial, root)
            add_artifact_provenance(trial, root)
            trial["metadata"]["git_dirty"] = True
            trial["metadata"]["git_status"] = [" M benchmark/run_handoff_trial.py"]

            failures = release_gate.external_trial_failures(trial, root)

        self.assertIn("metadata.git_dirty must be false", failures)
        self.assertIn("metadata.git_status must be empty for a clean external trial", failures)

    def test_external_trial_rejects_wrong_metadata_generator(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial = valid_external_trial()
            write_trial_artifacts(trial, root)
            add_artifact_provenance(trial, root)
            trial["metadata"]["generator"] = "manual_report.py"

            failures = release_gate.external_trial_failures(trial, root)

        self.assertIn("metadata.generator=manual_report.py", failures)

    def test_external_trial_rejects_non_utc_metadata_generation_time(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial = valid_external_trial()
            write_trial_artifacts(trial, root)
            add_artifact_provenance(trial, root)
            trial["metadata"]["generated_at_utc"] = "2026-07-03T08:00:00+08:00"

            failures = release_gate.external_trial_failures(trial, root)

        self.assertIn("metadata.generated_at_utc must be UTC", failures)

    def test_external_trial_requires_strict_runner_evidence_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial = valid_external_trial()
            write_trial_artifacts(trial, root)
            add_artifact_provenance(trial, root)
            trial["metadata"]["argv"] = [
                "benchmark/run_handoff_trial.py",
                "external_manifest.json",
                "--out-json",
                "external/handoff_trial.json",
                "--out-md",
                "external/handoff_trial.md",
            ]

            failures = release_gate.external_trial_failures(trial, root)

        self.assertIn(
            "metadata.argv must include exactly one --require-external-evidence "
            "for external workflow trial reports",
            failures,
        )

    def test_external_trial_rejects_metadata_argv_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial = valid_external_trial()
            write_trial_artifacts(trial, root)
            add_artifact_provenance(trial, root)
            trial["metadata"]["argv"] = [
                "benchmark/run_handoff_trial.py",
                "other_manifest.json",
                "--out-json",
                "--out-md",
                "external/handoff_trial.md",
                "--out-md",
                "external/other.md",
                "--require-external-evidence",
                "--require-external-evidence",
            ]

            failures = release_gate.external_trial_failures(trial, root)

        self.assertIn("metadata.argv must include trial manifest path exactly once: external_manifest.json", failures)
        self.assertIn("metadata.argv --out-json must include a value", failures)
        self.assertIn("metadata.argv has duplicate --out-md", failures)
        self.assertIn(
            "metadata.argv must include exactly one --require-external-evidence "
            "for external workflow trial reports",
            failures,
        )

    def test_external_trial_rejects_non_canonical_metadata_argv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial = valid_external_trial()
            write_trial_artifacts(trial, root)
            add_artifact_provenance(trial, root)
            trial["metadata"]["argv"].extend(["--dry-run", "unused-positional"])

            failures = release_gate.external_trial_failures(trial, root)

        self.assertIn("metadata.argv must match canonical external trial runner argv", failures)

    def test_external_trial_requires_manifest_source_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial = valid_external_trial()
            write_trial_artifacts(trial, root)
            add_artifact_provenance(trial, root)
            del trial["manifest"]

            failures = release_gate.external_trial_failures(trial, root)

        self.assertIn("trial manifest must be a non-empty string", failures)

    def test_external_trial_rejects_unreachable_metadata_commit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial = valid_external_trial()
            write_trial_artifacts(trial, root)
            add_artifact_provenance(trial, root)
            trial["metadata"]["git_commit"] = "b" * 40

            failures = release_gate.external_trial_failures(trial, root)

        self.assertIn("metadata.git_commit is not reachable: " + "b" * 40, failures)

    def test_external_trial_path_allowlist(self) -> None:
        self.assertTrue(release_gate.is_external_trial_compatible_path("README.md"))
        self.assertTrue(release_gate.is_external_trial_compatible_path("README.zh-CN.md"))
        self.assertTrue(release_gate.is_external_trial_compatible_path("docs/PRODUCTION_READINESS.md"))
        self.assertTrue(release_gate.is_external_trial_compatible_path("tests/test_release_gate.py"))
        self.assertTrue(release_gate.is_external_trial_compatible_path("benchmark/check_external_l4_readiness.py"))
        self.assertTrue(release_gate.is_external_trial_compatible_path("benchmark/release_gate.py"))
        self.assertTrue(release_gate.is_external_trial_compatible_path("benchmark/handoff/external_lab_template.json"))
        self.assertTrue(release_gate.is_external_trial_compatible_path("benchmark/package_external_trial.py"))
        self.assertTrue(release_gate.is_external_trial_compatible_path("benchmark/prepare_external_l4_trial.py"))
        self.assertTrue(release_gate.is_external_trial_compatible_path("benchmark/run_production_gate.py"))
        self.assertTrue(release_gate.is_external_trial_compatible_path("benchmark/validate_claim_language.py"))
        self.assertTrue(release_gate.is_external_trial_compatible_path("benchmark/validate_handoff_manifest.py"))
        self.assertTrue(release_gate.is_external_trial_compatible_path("benchmark/verify_github_release.py"))
        self.assertTrue(release_gate.is_external_trial_compatible_path("benchmark/verify_external_trial_report.py"))
        self.assertTrue(release_gate.is_external_trial_compatible_path("benchmark/verify_external_evidence_package.py"))
        self.assertTrue(release_gate.is_external_trial_compatible_path("benchmark/verify_release_gate_report.py"))
        self.assertTrue(release_gate.is_external_trial_compatible_path("benchmark/verify_release_archive.py"))
        self.assertFalse(release_gate.is_external_trial_compatible_path("benchmark/run_handoff_trial.py"))
        self.assertFalse(release_gate.is_external_trial_compatible_path("crates/morphojet/src/main.rs"))

    def test_github_release_verification_report_path_is_outside_download_dir(self) -> None:
        path = release_gate.github_release_verification_report_path("v0.1.0")

        self.assertEqual(Path("benchmark/results/github-release-verification/v0.1.0.json"), path)
        self.assertNotIn("benchmark/results/github-release/v0.1.0", str(path))

    def test_saved_github_release_report_command_verifies_git_commit_and_expected_tag(self) -> None:
        report = Path("github-release/verification.json")
        command = release_gate.saved_github_release_report_command(
            report,
            expected_tag="v0.1.0",
        )

        self.assertEqual(str(report.resolve(strict=False)), command[command.index("--verify-report") + 1])
        self.assertIn("--verify-report-files", command)
        self.assertIn("--require-report-pass", command)
        self.assertIn("--require-stable-report", command)
        self.assertIn("--verify-git-commit", command)
        self.assertEqual("v0.1.0", command[command.index("--expect-tag") + 1])

    def test_saved_github_release_report_command_verifies_git_commit_without_expected_tag(self) -> None:
        command = release_gate.saved_github_release_report_command(Path("github-release/verification.json"))

        self.assertIn("--verify-git-commit", command)
        self.assertNotIn("--expect-tag", command)

    def test_live_github_release_report_command_uses_absolute_report_path(self) -> None:
        command = release_gate.live_github_release_report_command("v0.1.0", "stable")

        self.assertEqual("--expect-stable", command[3])
        self.assertEqual(
            str(release_gate.github_release_verification_report_path("v0.1.0").resolve(strict=False)),
            command[command.index("--json-out") + 1],
        )

    def test_saved_external_trial_report_binding_failures_reject_mismatched_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "trial-verification.json"
            report.write_text(
                json.dumps(
                    {
                        "trial_json": str(root / "other" / "handoff_trial.json"),
                        "trial_root": str(root / "other"),
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            args = Namespace(
                external_trial_json=root / "external" / "handoff_trial.json",
                external_trial_root=root / "external",
            )

            failures = release_gate.saved_external_trial_report_binding_failures(report, args)

        self.assertIn("saved external trial report trial_json does not match --external-trial-json", failures)
        self.assertIn("saved external trial report trial_root does not match --external-trial-root", failures)

    def test_saved_external_package_report_binding_failures_reject_mismatched_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "package-verification.json"
            report.write_text(
                json.dumps(
                    {
                        "package_dir": str(root / "other-package"),
                        "trial_json": str(root / "other" / "handoff_trial.json"),
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            args = Namespace(
                external_trial_json=root / "external" / "handoff_trial.json",
                external_evidence_package_dir=root / "package",
            )

            failures = release_gate.saved_external_package_report_binding_failures(report, args)

        self.assertIn(
            "saved external evidence package report package_dir does not match --external-evidence-package-dir",
            failures,
        )
        self.assertIn(
            "saved external evidence package report trial_json does not match --external-trial-json",
            failures,
        )

    def test_report_outputs_must_not_overlap(self) -> None:
        args = self.production_args(out_json=Path("reports/gate.json"), out_md=Path("./reports/gate.json"))

        with self.assertRaisesRegex(SystemExit, "--out-md must not use the same path as --out-json"):
            release_gate.validate_report_output_paths(args)

    def test_report_output_must_not_overwrite_external_trial_json(self) -> None:
        args = self.production_args(
            external_trial_json=Path("external/handoff_trial.json"),
            out_json=Path("external/handoff_trial.json"),
        )

        with self.assertRaisesRegex(SystemExit, "--out-json must not overwrite --external-trial-json"):
            release_gate.validate_report_output_paths(args)

    def test_report_output_must_not_overwrite_external_trial_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial = valid_external_trial()
            write_trial_artifacts(trial, root)
            add_artifact_provenance(trial, root)
            trial_json = root / "external" / "handoff_trial.json"
            trial_json.write_text(json.dumps(trial, indent=2) + "\n", encoding="utf-8")
            args = self.production_args(
                external_trial_json=trial_json,
                external_trial_root=root,
                out_json=root / "external" / "handoff_contract.json",
            )

            with self.assertRaisesRegex(
                SystemExit,
                "--out-json must not overwrite external trial artifact: external/handoff_contract.json",
            ):
                release_gate.validate_report_output_paths(args)

    def test_report_output_must_not_overwrite_evidence_package_readiness_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package_dir = root / "package"
            package_dir.mkdir()
            readiness = package_dir / "readiness.json"
            readiness.write_text("{}\n", encoding="utf-8")
            args = self.production_args(
                external_evidence_package_dir=package_dir,
                out_json=readiness,
            )

            with self.assertRaisesRegex(
                SystemExit,
                "--out-json must not overwrite evidence package file: readiness.json",
            ):
                release_gate.validate_report_output_paths(args)

    def test_report_output_must_not_create_file_inside_external_trial_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial = valid_external_trial()
            write_trial_artifacts(trial, root)
            add_artifact_provenance(trial, root)
            trial_json = root / "external" / "handoff_trial.json"
            trial_json.write_text(json.dumps(trial, indent=2) + "\n", encoding="utf-8")
            args = self.production_args(
                external_trial_json=trial_json,
                external_trial_root=root,
                out_json=root / "external" / "handoff_contract.json" / "release-gate.json",
            )

            with self.assertRaisesRegex(
                SystemExit,
                "--out-json must not create a file inside external trial artifact: "
                "external/handoff_contract.json",
            ):
                release_gate.validate_report_output_paths(args)

    def test_report_output_must_not_overwrite_evidence_package_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package_dir = root / "package"
            artifact = package_dir / "artifacts" / "external" / "handoff_contract.json"
            artifact.parent.mkdir(parents=True)
            artifact.write_text("{}\n", encoding="utf-8")
            package_dir.mkdir(exist_ok=True)
            (package_dir / "artifact_manifest.json").write_text(
                json.dumps(
                    {
                        "artifacts": [
                            {
                                "package_path": "artifacts/external/handoff_contract.json",
                            }
                        ]
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            args = self.production_args(
                external_evidence_package_dir=package_dir,
                out_md=artifact,
            )

            with self.assertRaisesRegex(
                SystemExit,
                "--out-md must not overwrite evidence package artifact: artifacts/external/handoff_contract.json",
            ):
                release_gate.validate_report_output_paths(args)

    def test_report_output_must_not_create_file_inside_evidence_package_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package_dir = root / "package"
            artifact = package_dir / "artifacts" / "external" / "handoff_contract.json"
            artifact.parent.mkdir(parents=True)
            artifact.write_text("{}\n", encoding="utf-8")
            package_dir.mkdir(exist_ok=True)
            (package_dir / "artifact_manifest.json").write_text(
                json.dumps(
                    {
                        "artifacts": [
                            {
                                "package_path": "artifacts/external/handoff_contract.json",
                            }
                        ]
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            args = self.production_args(
                external_evidence_package_dir=package_dir,
                out_md=artifact / "release-gate.md",
            )

            with self.assertRaisesRegex(
                SystemExit,
                "--out-md must not create a file inside evidence package artifact: "
                "artifacts/external/handoff_contract.json",
            ):
                release_gate.validate_report_output_paths(args)

    def test_report_output_must_not_overwrite_github_release_verification_report(self) -> None:
        args = self.production_args(
            verify_github_release="v0.1.0",
            out_json=release_gate.github_release_verification_report_path("v0.1.0"),
        )

        with self.assertRaisesRegex(
            SystemExit,
            "--out-json must not overwrite GitHub release verification report",
        ):
            release_gate.validate_report_output_paths(args)

    def test_external_trial_rejects_rendered_manifest_evidence_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial = valid_external_trial()
            write_trial_artifacts(trial, root)
            add_artifact_provenance(trial, root)
            trial["rendered_manifest"]["external_evidence"]["dataset_name"] = "Different Batch"

            failures = release_gate.external_trial_failures(trial, root)

        self.assertIn("rendered_manifest.external_evidence must match external_evidence", failures)

    def test_external_trial_rejects_artifact_hash_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial = valid_external_trial()
            write_trial_artifacts(trial, root)
            add_artifact_provenance(trial, root)
            for entry in trial["artifact_provenance"]:
                if entry["path"] == "external/handoff_contract.json":
                    entry["sha256"] = "0" * 64

            failures = release_gate.external_trial_failures(trial, root)

        self.assertIn("trial artifact sha256 mismatch: external/handoff_contract.json", failures)

    def test_external_trial_requires_readiness_report_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial = valid_external_trial()
            write_trial_artifacts(trial, root)
            add_artifact_provenance(trial, root)
            del trial["readiness_report"]

            failures = release_gate.external_trial_failures(trial, root)

        self.assertIn("readiness_report must be present for external workflow trial reports", failures)

    def test_external_trial_rejects_readiness_report_hash_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial = valid_external_trial()
            write_trial_artifacts(trial, root)
            add_artifact_provenance(trial, root)
            readiness_path = Path(trial["readiness_report"]["path"])
            readiness_path.write_text("{}\n", encoding="utf-8")

            failures = release_gate.external_trial_failures(
                trial,
                root,
                readiness_report_file=readiness_path,
            )

        self.assertIn("readiness_report.sha256 must match readiness report file", failures)

    def test_external_trial_requires_readiness_report_package_name_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial = valid_external_trial()
            write_trial_artifacts(trial, root)
            add_artifact_provenance(trial, root)
            del trial["readiness_report"]["package_name"]

            failures = release_gate.external_trial_failures(trial, root)

        self.assertIn("readiness_report.package_name must be present", failures)

    def test_external_trial_rejects_readiness_report_package_name_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial = valid_external_trial()
            trial["readiness_report"]["package_name"] = "external-l4-demo"
            write_trial_artifacts(trial, root)
            add_artifact_provenance(trial, root)
            trial["readiness_report"]["package_name"] = "other-demo"
            readiness_path = Path(trial["readiness_report"]["path"])

            failures = release_gate.external_trial_failures(
                trial,
                root,
                readiness_report_file=readiness_path,
            )

        self.assertIn("readiness_report.package_name must match readiness report file", failures)

    def test_external_trial_rejects_duplicate_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial = valid_external_trial()
            trial["artifacts"].append("external/handoff_contract.json")
            write_trial_artifacts(trial, root)
            add_artifact_provenance(trial, root)

            failures = release_gate.external_trial_failures(trial, root)

        self.assertIn("trial artifact path is duplicated: external/handoff_contract.json", failures)

    def test_external_trial_rejects_duplicate_artifact_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial = valid_external_trial()
            write_trial_artifacts(trial, root)
            add_artifact_provenance(trial, root)
            handoff_entry = next(
                entry
                for entry in trial["artifact_provenance"]
                if entry["path"] == "external/handoff_contract.json"
            )
            trial["artifact_provenance"].append(dict(handoff_entry))

            failures = release_gate.external_trial_failures(trial, root)

        self.assertIn(
            "trial artifact_provenance path is duplicated: external/handoff_contract.json",
            failures,
        )

    def test_external_trial_rejects_unlisted_artifact_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            extra = root / "external" / "extra.json"
            extra.parent.mkdir(parents=True)
            extra.write_text("{}\n")
            trial = valid_external_trial()
            write_trial_artifacts(trial, root)
            add_artifact_provenance(trial, root)
            trial["artifact_provenance"].append(
                {
                    "path": "external/extra.json",
                    "size_bytes": extra.stat().st_size,
                    "sha256": release_gate.sha256_file(extra),
                }
            )

            failures = release_gate.external_trial_failures(trial, root)

        self.assertIn("trial artifact_provenance has unlisted artifact: external/extra.json", failures)

    def test_external_trial_requires_artifacts_from_rendered_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial = valid_external_trial()
            trial["artifacts"].remove("external/workflow_bridge.json")
            write_trial_artifacts(trial, root)
            add_artifact_provenance(trial, root)

            failures = release_gate.external_trial_failures(trial, root)

        self.assertIn(
            "trial artifact missing rendered_manifest output: external/workflow_bridge.json",
            failures,
        )

    def test_external_trial_rejects_artifacts_not_declared_by_rendered_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial = valid_external_trial()
            trial["artifacts"].append("external/extra.json")
            write_trial_artifacts(trial, root)
            add_artifact_provenance(trial, root)

            failures = release_gate.external_trial_failures(trial, root)

        self.assertIn("trial artifact not declared by rendered_manifest: external/extra.json", failures)

    def test_external_trial_requires_steps_from_rendered_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial = valid_external_trial()
            trial["steps"] = [
                step
                for step in trial["steps"]
                if step["name"] != "Compare Cells supported columns"
            ]
            write_trial_artifacts(trial, root)
            add_artifact_provenance(trial, root)

            failures = release_gate.external_trial_failures(trial, root)

        self.assertIn(
            "trial step missing rendered_manifest action: Compare Cells supported columns",
            failures,
        )

    def test_external_trial_rejects_steps_not_declared_by_rendered_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial = valid_external_trial()
            trial["steps"].append({"name": "Manual spreadsheet cleanup", "status": "PASS"})
            write_trial_artifacts(trial, root)
            add_artifact_provenance(trial, root)

            failures = release_gate.external_trial_failures(trial, root)

        self.assertIn(
            "trial step not declared by rendered_manifest: Manual spreadsheet cleanup",
            failures,
        )

    def test_external_trial_rejects_duplicate_step_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial = valid_external_trial()
            step = next(
                step
                for step in trial["steps"]
                if step["name"] == "Validate downstream contract"
            )
            trial["steps"].append(dict(step))
            write_trial_artifacts(trial, root)
            add_artifact_provenance(trial, root)

            failures = release_gate.external_trial_failures(trial, root)

        self.assertIn("trial step name is duplicated: Validate downstream contract", failures)

    def test_external_trial_requires_step_elapsed_seconds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial = valid_external_trial()
            for step in trial["steps"]:
                if step["name"] == "Compare Cells supported columns":
                    del step["elapsed_seconds"]
            write_trial_artifacts(trial, root)
            add_artifact_provenance(trial, root)

            failures = release_gate.external_trial_failures(trial, root)

        self.assertIn("trial step elapsed_seconds is invalid: Compare Cells supported columns", failures)

    def test_external_trial_rejects_negative_step_elapsed_seconds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial = valid_external_trial()
            for step in trial["steps"]:
                if step["name"] == "Validate downstream contract":
                    step["elapsed_seconds"] = -0.1
            write_trial_artifacts(trial, root)
            add_artifact_provenance(trial, root)

            failures = release_gate.external_trial_failures(trial, root)

        self.assertIn("trial step elapsed_seconds is invalid: Validate downstream contract", failures)

    def test_external_trial_requires_step_detail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial = valid_external_trial()
            for step in trial["steps"]:
                if step["name"] == "Materialize Cells wide CSV":
                    del step["detail"]
            write_trial_artifacts(trial, root)
            add_artifact_provenance(trial, root)

            failures = release_gate.external_trial_failures(trial, root)

        self.assertIn("trial step detail must be a string: Materialize Cells wide CSV", failures)

    def test_external_trial_requires_step_commands_from_rendered_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial = valid_external_trial()
            for step in trial["steps"]:
                if step["name"] == "Compare Cells supported columns":
                    del step["command"]
            write_trial_artifacts(trial, root)
            add_artifact_provenance(trial, root)

            failures = release_gate.external_trial_failures(trial, root)

        self.assertIn("trial step command mismatch: Compare Cells supported columns", failures)

    def test_external_trial_rejects_step_command_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial = valid_external_trial()
            for step in trial["steps"]:
                if step["name"] == "Materialize Cells wide CSV":
                    step["command"] = ["python3", "manual_edit.py"]
            write_trial_artifacts(trial, root)
            add_artifact_provenance(trial, root)

            failures = release_gate.external_trial_failures(trial, root)

        self.assertIn("trial step command mismatch: Materialize Cells wide CSV", failures)

    def test_external_trial_requires_evidence(self) -> None:
        trial = valid_external_trial()
        del trial["external_evidence"]

        self.assertIn("external_evidence must be present", release_gate.external_trial_failures(trial))

    def test_external_trial_rejects_placeholders(self) -> None:
        trial = copy.deepcopy(valid_external_trial())
        trial["external_evidence"]["dataset_source"] = "REPLACE_WITH_SOURCE"

        self.assertIn(
            "external_evidence.dataset_source must replace template placeholder text",
            release_gate.external_trial_failures(trial),
        )

    def test_external_trial_rejects_acceptance_criteria_placeholders(self) -> None:
        trial = copy.deepcopy(valid_external_trial())
        trial["external_evidence"]["acceptance_criteria"] = ["REPLACE_WITH_ACCEPTANCE_CRITERION"]

        self.assertIn(
            "external_evidence.acceptance_criteria[0] must replace template placeholder text",
            release_gate.external_trial_failures(trial),
        )

    def test_external_trial_requires_signoff_fields(self) -> None:
        trial = copy.deepcopy(valid_external_trial())
        del trial["external_evidence"]["reviewer_name_or_role"]
        trial["external_evidence"]["reviewed_at_utc"] = "2026-07-03T01:02:03"
        trial["external_evidence"]["signoff_statement"] = "REPLACE_WITH_SIGNOFF"

        failures = release_gate.external_trial_failures(trial)

        self.assertIn("external_evidence.reviewer_name_or_role must be a non-empty string", failures)
        self.assertIn("external_evidence.reviewed_at_utc must include timezone", failures)
        self.assertIn("external_evidence.signoff_statement must replace template placeholder text", failures)

    def test_external_trial_rejects_invalid_reviewed_at(self) -> None:
        trial = copy.deepcopy(valid_external_trial())
        trial["external_evidence"]["reviewed_at_utc"] = "not-a-date"

        self.assertIn(
            "external_evidence.reviewed_at_utc is invalid: not-a-date",
            release_gate.external_trial_failures(trial),
        )

    def test_external_trial_rejects_non_utc_reviewed_at(self) -> None:
        trial = copy.deepcopy(valid_external_trial())
        trial["external_evidence"]["reviewed_at_utc"] = "2026-07-03T09:02:03+08:00"

        self.assertIn(
            "external_evidence.reviewed_at_utc must be UTC",
            release_gate.external_trial_failures(trial),
        )

    def test_external_trial_rejects_review_before_trial_generation(self) -> None:
        trial = copy.deepcopy(valid_external_trial())
        trial["metadata"]["generated_at_utc"] = "2026-07-03T01:02:04+00:00"
        trial["external_evidence"]["reviewed_at_utc"] = "2026-07-03T01:02:03+00:00"

        self.assertIn(
            "external_evidence.reviewed_at_utc must be at or after metadata.generated_at_utc",
            release_gate.external_trial_failures(trial),
        )

    def test_external_trial_requires_no_manual_csv_editing(self) -> None:
        trial = copy.deepcopy(valid_external_trial())
        trial["external_evidence"]["manual_csv_editing"] = True

        self.assertIn(
            "external_evidence.manual_csv_editing must be false",
            release_gate.external_trial_failures(trial),
        )

    def test_external_trial_rejects_failed_steps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial = valid_external_trial()
            write_trial_artifacts(trial, root)
            add_artifact_provenance(trial, root)
            for step in trial["steps"]:
                if step["name"] == "Validate downstream contract":
                    step["status"] = "FAIL"

            failures = release_gate.external_trial_failures(trial, root)

        self.assertIn("failed trial steps=Validate downstream contract", failures)


if __name__ == "__main__":
    unittest.main()
