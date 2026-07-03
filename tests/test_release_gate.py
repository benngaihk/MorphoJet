#!/usr/bin/env python3
"""Unit tests for release gate helpers."""

from __future__ import annotations

import copy
import sys
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
        self.assertEqual([], release_gate.external_trial_failures(valid_external_trial()))

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
