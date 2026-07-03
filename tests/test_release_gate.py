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
            "argv": ["benchmark/run_handoff_trial.py", "external_manifest.json"],
        },
        "rendered_manifest": manifest,
        "external_evidence": external_evidence,
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

    def test_production_claim_audit_defaults_to_incomplete_without_l4_or_stable_release(self) -> None:
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
        self.assertEqual("MISSING", statuses["stable_github_release"])
        self.assertEqual(
            [
                "clean_git_worktree",
                "l3_provenance_hashes",
                "external_l4_workflow_trial",
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
                "Validate handoff manifests",
                "Validate external lab handoff template",
                "Validate existing CellBinDB L3 artifacts",
                "Validate CellBinDB L3 provenance",
                "Validate CellBinDB workflow bridge artifacts",
                "Validate CellBinDB handoff trial artifacts",
                "Validate external L4 workflow trial report",
                "Verify GitHub release assets",
            ]
        )

        audit = release_gate.build_production_claim_audit(
            self.production_args(
                require_clean_git=True,
                require_l3_provenance=True,
                external_trial_json=Path("handoff_trial.json"),
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

        self.assertEqual("FAIL", payload["status"])
        self.assertEqual("INCOMPLETE", payload["production_claim_audit"]["status"])
        self.assertEqual(
            [
                "clean_git_worktree",
                "l3_provenance_hashes",
                "external_l4_workflow_trial",
                "stable_github_release",
            ],
            payload["production_claim_audit"]["missing_or_failed_checks"],
        )

    def test_require_production_claim_passes_complete_audit(self) -> None:
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
                    verify_github_release="v0.1.0",
                    github_release_kind="stable",
                    out_json=root / "report.json",
                    out_md=root / "report.md",
                ),
                gates,
                self.production_metadata(),
            )

        self.assertEqual("PASS", payload["status"])
        self.assertEqual("PASS", payload["production_claim_audit"]["status"])

    def test_doc_path_allowlist(self) -> None:
        self.assertTrue(release_gate.is_doc_path("README.md"))
        self.assertTrue(release_gate.is_doc_path("docs/PRODUCTION_READINESS.md"))
        self.assertFalse(release_gate.is_doc_path("benchmark/release_gate.py"))
        self.assertFalse(release_gate.is_doc_path("crates/morphojet/src/main.rs"))

    def test_l3_provenance_compatible_path_allowlist(self) -> None:
        self.assertTrue(release_gate.is_l3_provenance_compatible_path("README.md"))
        self.assertTrue(release_gate.is_l3_provenance_compatible_path("docs/PRODUCTION_READINESS.md"))
        self.assertTrue(release_gate.is_l3_provenance_compatible_path("tests/test_release_gate.py"))
        self.assertTrue(release_gate.is_l3_provenance_compatible_path("benchmark/release_gate.py"))
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
            report.write_text(json.dumps(trial) + "\n")

            gate = release_gate.validate_external_trial_report(report, root)

        self.assertEqual("PASS", gate.status)
        self.assertIn(f"trial_commit={trial['metadata']['git_commit'][:12]}", gate.detail)
        self.assertIn("generated_at_utc=2026-07-03T00:00:00+00:00", gate.detail)

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
        self.assertTrue(release_gate.is_external_trial_compatible_path("docs/PRODUCTION_READINESS.md"))
        self.assertTrue(release_gate.is_external_trial_compatible_path("tests/test_release_gate.py"))
        self.assertTrue(release_gate.is_external_trial_compatible_path("benchmark/release_gate.py"))
        self.assertFalse(release_gate.is_external_trial_compatible_path("benchmark/run_handoff_trial.py"))
        self.assertFalse(release_gate.is_external_trial_compatible_path("crates/morphojet/src/main.rs"))

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
