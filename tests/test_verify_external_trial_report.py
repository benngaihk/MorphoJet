#!/usr/bin/env python3
"""Unit tests for the standalone external trial report verifier."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmark"))
sys.path.insert(0, str(ROOT / "tests"))

import verify_external_trial_report  # noqa: E402
from test_release_gate import add_artifact_provenance, valid_external_trial, write_trial_artifacts  # noqa: E402


class VerifyExternalTrialReportTest(unittest.TestCase):
    def write_valid_trial(self, root: Path) -> Path:
        trial = valid_external_trial()
        write_trial_artifacts(trial, root)
        add_artifact_provenance(trial, root)
        trial_json = root / "external" / "handoff_trial.json"
        trial_json.parent.mkdir(parents=True, exist_ok=True)
        trial_json.write_text(json.dumps(trial, indent=2) + "\n", encoding="utf-8")
        return trial_json

    def test_verifier_accepts_valid_trial_and_writes_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            json_out = root / "review" / "external-trial-verification.json"

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                code = verify_external_trial_report.verify_external_trial_report(
                    trial_json,
                    root,
                    json_out=json_out,
                )
            payload = json.loads(json_out.read_text(encoding="utf-8"))

        self.assertEqual(0, code)
        self.assertEqual("PASS", payload["status"])
        self.assertEqual("Validate external L4 workflow trial report", payload["gate"]["name"])
        self.assertIn("External workflow trial PASS", payload["gate"]["detail"])

    def test_verifier_rejects_invalid_trial(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            trial = json.loads(trial_json.read_text(encoding="utf-8"))
            trial["external_evidence"]["manual_csv_editing"] = True
            trial_json.write_text(json.dumps(trial, indent=2) + "\n", encoding="utf-8")

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                code = verify_external_trial_report.verify_external_trial_report(trial_json, root)

        self.assertEqual(1, code)

    def test_verifier_can_write_failed_diagnostic_report_without_failing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            trial = json.loads(trial_json.read_text(encoding="utf-8"))
            trial["external_evidence"]["manual_csv_editing"] = True
            trial_json.write_text(json.dumps(trial, indent=2) + "\n", encoding="utf-8")
            json_out = root / "failed-external-trial-verification.json"

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                code = verify_external_trial_report.verify_external_trial_report(
                    trial_json,
                    root,
                    json_out=json_out,
                    require_pass=False,
                )
            payload = json.loads(json_out.read_text(encoding="utf-8"))

        self.assertEqual(0, code)
        self.assertEqual("FAIL", payload["status"])
        self.assertIn("manual_csv_editing", payload["gate"]["detail"])


if __name__ == "__main__":
    unittest.main()
