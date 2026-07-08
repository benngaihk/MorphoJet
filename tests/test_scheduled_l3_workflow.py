#!/usr/bin/env python3
"""Unit tests for the scheduled CellBinDB L3 GitHub workflow."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/cellbindb-l3.yml"


class ScheduledL3WorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow_text = WORKFLOW.read_text(encoding="utf-8")

    def test_workflow_has_manual_and_scheduled_entrypoints(self) -> None:
        self.assertIn("name: CellBinDB L3 Validation", self.workflow_text)
        self.assertIn("workflow_dispatch:", self.workflow_text)
        self.assertIn("schedule:", self.workflow_text)
        self.assertIn('cron: "17 6 * * 1"', self.workflow_text)

    def test_workflow_runs_the_scheduler_ready_l3_script(self) -> None:
        self.assertIn("runs-on: ubuntu-latest", self.workflow_text)
        self.assertIn("timeout-minutes: 360", self.workflow_text)
        self.assertIn("permissions:\n  contents: read", self.workflow_text)
        self.assertIn("dtolnay/rust-toolchain@stable", self.workflow_text)
        self.assertIn("benchmark/run_cellbindb_l3_validation.sh", self.workflow_text)

    def test_workflow_uploads_auditable_l3_evidence(self) -> None:
        required_artifacts = [
            "benchmark/results/release-gate/l3-cellbindb.json",
            "benchmark/results/release-gate/l3-cellbindb.md",
            "benchmark/results/cellbindb/oracle-full/parity.json",
            "benchmark/results/cellbindb/oracle-full/impact.json",
            "benchmark/results/cellbindb/oracle-full/provenance.json",
            "benchmark/results/cellbindb/oracle-full/workflow_bridge.json",
            "benchmark/results/cellbindb/oracle-full/handoff_trial.json",
        ]

        self.assertIn("actions/upload-artifact@v4", self.workflow_text)
        self.assertIn("if-no-files-found: error", self.workflow_text)
        for artifact in required_artifacts:
            self.assertIn(artifact, self.workflow_text)


if __name__ == "__main__":
    unittest.main()
