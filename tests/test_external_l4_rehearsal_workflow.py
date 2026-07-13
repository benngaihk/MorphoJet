#!/usr/bin/env python3
"""Unit tests for the external L4 internal rehearsal GitHub workflow."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/external-l4-rehearsal.yml"


class ExternalL4RehearsalWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow_text = WORKFLOW.read_text(encoding="utf-8")

    def test_workflow_has_push_manual_and_scheduled_entrypoints(self) -> None:
        self.assertIn("name: External L4 Internal Rehearsal", self.workflow_text)
        self.assertIn("workflow_dispatch:", self.workflow_text)
        self.assertIn("branches: [main]", self.workflow_text)
        self.assertIn("schedule:", self.workflow_text)
        self.assertIn('cron: "43 7 * * 2"', self.workflow_text)

    def test_workflow_runs_internal_rehearsal_outside_repo(self) -> None:
        self.assertIn("runs-on: ubuntu-latest", self.workflow_text)
        self.assertIn("timeout-minutes: 60", self.workflow_text)
        self.assertIn("permissions:\n  contents: read", self.workflow_text)
        self.assertIn('workspace="${RUNNER_TEMP}/morphojet-external-l4-rehearsal"', self.workflow_text)
        self.assertIn('fixture="${RUNNER_TEMP}/morphojet-external-l4-fixture"', self.workflow_text)
        self.assertIn("minimal-template.json", self.workflow_text)
        self.assertIn("python3 benchmark/run_external_l4_rehearsal.py", self.workflow_text)
        self.assertIn("--morphojet-objects", self.workflow_text)
        self.assertIn("--cellprofiler-cells", self.workflow_text)
        self.assertIn("--package-name ci-external-l4-rehearsal", self.workflow_text)
        self.assertIn("--overwrite", self.workflow_text)
        self.assertIn('--verify-report "${workspace}/external-l4-rehearsal-summary.json"', self.workflow_text)
        self.assertIn("--verify-report-files", self.workflow_text)
        self.assertIn("--require-report-pass", self.workflow_text)

    def test_workflow_uploads_auditable_rehearsal_evidence(self) -> None:
        required_artifacts = [
            "external-l4-rehearsal-summary.json",
            "external-l4-rehearsal-summary.md",
            "trial_plan.json",
            "README.zh-CN.md",
            "readiness.json",
            "handoff_trial.json",
            "handoff_trial-verification.json",
            "evidence-package-verification.json",
            "local-evidence-preflight.json",
            "local-evidence-preflight.md",
            "evidence-package/**",
        ]

        self.assertIn("actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02", self.workflow_text)
        self.assertIn("if-no-files-found: error", self.workflow_text)
        self.assertIn("retention-days: 30", self.workflow_text)
        for artifact in required_artifacts:
            self.assertIn(artifact, self.workflow_text)


if __name__ == "__main__":
    unittest.main()
