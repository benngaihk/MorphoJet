#!/usr/bin/env python3
"""Unit tests for release gate helpers."""

from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmark"))

import release_gate  # noqa: E402


def valid_external_trial() -> dict:
    return {
        "trial_id": "external-lab-supported-columns-handoff",
        "status": "PASS",
        "external_evidence": {
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
        },
        "artifacts": ["external/handoff_contract.json"],
        "steps": [
            {"name": "Materialize Cells wide CSV", "status": "PASS"},
            {"name": "Validate downstream contract", "status": "PASS"},
        ],
    }


def add_artifact_provenance(trial: dict, root: Path) -> None:
    path = root / "external" / "handoff_contract.json"
    trial["artifact_provenance"] = [
        {
            "path": "external/handoff_contract.json",
            "size_bytes": path.stat().st_size,
            "sha256": release_gate.sha256_file(path),
        }
    ]


class ReleaseGateTest(unittest.TestCase):
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
            artifact = root / "external" / "handoff_contract.json"
            artifact.parent.mkdir()
            artifact.write_text("{}\n")
            trial = valid_external_trial()
            add_artifact_provenance(trial, root)

            self.assertEqual([], release_gate.external_trial_failures(trial, root))

    def test_external_trial_requires_artifacts_to_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            failures = release_gate.external_trial_failures(valid_external_trial(), Path(tmp))

        self.assertIn("trial artifact does not exist: external/handoff_contract.json", failures)

    def test_external_trial_rejects_empty_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "external" / "handoff_contract.json"
            artifact.parent.mkdir()
            artifact.write_text("")
            trial = valid_external_trial()
            trial["artifact_provenance"] = [
                {"path": "external/handoff_contract.json", "size_bytes": 1, "sha256": "0" * 64}
            ]

            failures = release_gate.external_trial_failures(trial, root)

        self.assertIn("trial artifact is empty: external/handoff_contract.json", failures)

    def test_external_trial_requires_artifact_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "external" / "handoff_contract.json"
            artifact.parent.mkdir()
            artifact.write_text("{}\n")

            failures = release_gate.external_trial_failures(valid_external_trial(), root)

        self.assertIn("trial artifact_provenance must be a non-empty list", failures)
        self.assertIn("trial artifact missing provenance: external/handoff_contract.json", failures)

    def test_external_trial_rejects_artifact_hash_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "external" / "handoff_contract.json"
            artifact.parent.mkdir()
            artifact.write_text("{}\n")
            trial = valid_external_trial()
            add_artifact_provenance(trial, root)
            trial["artifact_provenance"][0]["sha256"] = "0" * 64

            failures = release_gate.external_trial_failures(trial, root)

        self.assertIn("trial artifact sha256 mismatch: external/handoff_contract.json", failures)

    def test_external_trial_rejects_duplicate_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "external" / "handoff_contract.json"
            artifact.parent.mkdir()
            artifact.write_text("{}\n")
            trial = valid_external_trial()
            trial["artifacts"].append("external/handoff_contract.json")
            add_artifact_provenance(trial, root)

            failures = release_gate.external_trial_failures(trial, root)

        self.assertIn("trial artifact path is duplicated: external/handoff_contract.json", failures)

    def test_external_trial_rejects_duplicate_artifact_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "external" / "handoff_contract.json"
            artifact.parent.mkdir()
            artifact.write_text("{}\n")
            trial = valid_external_trial()
            add_artifact_provenance(trial, root)
            trial["artifact_provenance"].append(dict(trial["artifact_provenance"][0]))

            failures = release_gate.external_trial_failures(trial, root)

        self.assertIn(
            "trial artifact_provenance path is duplicated: external/handoff_contract.json",
            failures,
        )

    def test_external_trial_rejects_unlisted_artifact_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "external" / "handoff_contract.json"
            extra = root / "external" / "extra.json"
            artifact.parent.mkdir()
            artifact.write_text("{}\n")
            extra.write_text("{}\n")
            trial = valid_external_trial()
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
        trial = copy.deepcopy(valid_external_trial())
        trial["steps"][1]["status"] = "FAIL"

        self.assertIn(
            "failed trial steps=Validate downstream contract",
            release_gate.external_trial_failures(trial),
        )


if __name__ == "__main__":
    unittest.main()
