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
import release_gate  # noqa: E402
from test_release_gate import add_artifact_provenance, valid_external_trial, write_trial_artifacts  # noqa: E402


class VerifyExternalTrialReportTest(unittest.TestCase):
    def write_valid_trial(self, root: Path) -> Path:
        trial = valid_external_trial()
        write_trial_artifacts(trial, root)
        add_artifact_provenance(trial, root)
        trial_json = root / "external" / "handoff_trial.json"
        trial["metadata"]["argv"][trial["metadata"]["argv"].index("--out-json") + 1] = str(trial_json)
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
            expected_trial_sha = release_gate.sha256_file(trial_json)
            expected_artifact_files = verify_external_trial_report.trial_input_files(trial_json, root)["artifact_files"]

        self.assertEqual(0, code)
        self.assertEqual(1, payload["schema_version"])
        self.assertEqual("benchmark/verify_external_trial_report.py", payload["verifier"])
        self.assertIn("+00:00", payload["generated_at_utc"])
        self.assertEqual("PASS", payload["status"])
        self.assertEqual("Validate external L4 workflow trial report", payload["gate"]["name"])
        self.assertIn("External workflow trial PASS", payload["gate"]["detail"])
        self.assertEqual(expected_trial_sha, payload["input_files"]["trial_json"]["sha256"])
        self.assertEqual(expected_artifact_files, payload["input_files"]["artifact_files"])

    def test_verifier_json_out_must_not_overwrite_trial_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)

            with self.assertRaises(SystemExit) as context:
                verify_external_trial_report.verify_external_trial_report(
                    trial_json,
                    root,
                    json_out=trial_json,
                )

        self.assertIn("--json-out must not overwrite trial JSON", str(context.exception))

    def test_verifier_json_out_must_not_overwrite_trial_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)

            with self.assertRaises(SystemExit) as context:
                verify_external_trial_report.verify_external_trial_report(
                    trial_json,
                    root,
                    json_out=root / "external" / "handoff_contract.json",
                )

        self.assertIn("--json-out must not overwrite trial artifact: external/handoff_contract.json", str(context.exception))

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

    def test_saved_verification_report_passes_with_file_recheck(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            json_out = root / "external-trial-verification.json"
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                verify_external_trial_report.verify_external_trial_report(
                    trial_json,
                    root,
                    json_out=json_out,
                )

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                code = verify_external_trial_report.verify_saved_external_trial_report(
                    json_out,
                    require_report_pass=True,
                    verify_files=True,
                )

        self.assertEqual(0, code)

    def test_saved_verification_report_rejects_status_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            json_out = root / "external-trial-verification.json"
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                verify_external_trial_report.verify_external_trial_report(
                    trial_json,
                    root,
                    json_out=json_out,
                )
            payload = json.loads(json_out.read_text(encoding="utf-8"))
            payload["status"] = "FAIL"
            json_out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                code = verify_external_trial_report.verify_saved_external_trial_report(json_out)

        self.assertEqual(1, code)

    def test_saved_verification_report_rejects_metadata_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            json_out = root / "external-trial-verification.json"
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                verify_external_trial_report.verify_external_trial_report(
                    trial_json,
                    root,
                    json_out=json_out,
                )
            payload = json.loads(json_out.read_text(encoding="utf-8"))
            payload["schema_version"] = 2
            payload["verifier"] = "other.py"
            payload["generated_at_utc"] = "not-a-date"
            json_out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                code = verify_external_trial_report.verify_saved_external_trial_report(json_out)

        self.assertEqual(1, code)

    def test_saved_verification_report_rejects_argv_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            json_out = root / "external-trial-verification.json"
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                verify_external_trial_report.verify_external_trial_report(
                    trial_json,
                    root,
                    json_out=json_out,
                )
            payload = json.loads(json_out.read_text(encoding="utf-8"))
            payload["argv"] = [
                "benchmark/verify_external_trial_report.py",
                str(root / "other_trial.json"),
                "--trial-root",
                "--json-out",
                str(json_out),
                "--verify-report",
                str(json_out),
            ]
            json_out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
                code = verify_external_trial_report.verify_saved_external_trial_report(json_out)

        self.assertEqual(1, code)
        self.assertIn("argv must include trial_json exactly once", stderr.getvalue())
        self.assertIn("argv --trial-root must include a value", stderr.getvalue())
        self.assertIn("argv must not include --verify-report", stderr.getvalue())

    def test_saved_verification_report_rejects_json_out_path_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            json_out = root / "external-trial-verification.json"
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                verify_external_trial_report.verify_external_trial_report(
                    trial_json,
                    root,
                    json_out=json_out,
                )
            payload = json.loads(json_out.read_text(encoding="utf-8"))
            payload["argv"][payload["argv"].index("--json-out") + 1] = str(root / "other-verification.json")
            json_out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
                code = verify_external_trial_report.verify_saved_external_trial_report(json_out)

        self.assertEqual(1, code)
        self.assertIn("argv --json-out must match saved verifier report path", stderr.getvalue())

    def test_saved_verification_report_requires_json_out_path_binding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            json_out = root / "external-trial-verification.json"
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                verify_external_trial_report.verify_external_trial_report(
                    trial_json,
                    root,
                    json_out=json_out,
                )
            payload = json.loads(json_out.read_text(encoding="utf-8"))
            json_out_index = payload["argv"].index("--json-out")
            del payload["argv"][json_out_index:json_out_index + 2]
            json_out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
                code = verify_external_trial_report.verify_saved_external_trial_report(json_out)

        self.assertEqual(1, code)
        self.assertIn("argv missing --json-out for saved verifier report", stderr.getvalue())

    def test_saved_verification_report_recomputes_trial_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            json_out = root / "external-trial-verification.json"
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                verify_external_trial_report.verify_external_trial_report(
                    trial_json,
                    root,
                    json_out=json_out,
                )
            payload = json.loads(json_out.read_text(encoding="utf-8"))
            payload["gate"]["detail"] = "External workflow trial PASS: stale detail"
            json_out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                code = verify_external_trial_report.verify_saved_external_trial_report(
                    json_out,
                    verify_files=True,
                )

        self.assertEqual(1, code)

    def test_saved_verification_report_recomputes_input_file_summaries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            json_out = root / "external-trial-verification.json"
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                verify_external_trial_report.verify_external_trial_report(
                    trial_json,
                    root,
                    json_out=json_out,
                )
            payload = json.loads(json_out.read_text(encoding="utf-8"))
            payload["input_files"]["trial_json"]["sha256"] = "0" * 64
            json_out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
                code = verify_external_trial_report.verify_saved_external_trial_report(
                    json_out,
                    verify_files=True,
                )

        self.assertEqual(1, code)
        self.assertIn("input_files.trial_json.sha256 changed after recomputing trial validation", stderr.getvalue())

    def test_saved_verification_report_rejects_unbound_trial_json_summary_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            json_out = root / "external-trial-verification.json"
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                verify_external_trial_report.verify_external_trial_report(
                    trial_json,
                    root,
                    json_out=json_out,
                )
            payload = json.loads(json_out.read_text(encoding="utf-8"))
            payload["input_files"]["trial_json"]["path"] = str(root / "other" / "handoff_trial.json")
            json_out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
                code = verify_external_trial_report.verify_saved_external_trial_report(json_out)

        self.assertEqual(1, code)
        self.assertIn("input_files.trial_json.path must match trial_json", stderr.getvalue())

    def test_saved_verification_report_rejects_unbound_artifact_summary_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            json_out = root / "external-trial-verification.json"
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                verify_external_trial_report.verify_external_trial_report(
                    trial_json,
                    root,
                    json_out=json_out,
                )
            payload = json.loads(json_out.read_text(encoding="utf-8"))
            payload["input_files"]["artifact_files"][0]["path"] = str(root / "other-artifact.json")
            json_out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
                code = verify_external_trial_report.verify_saved_external_trial_report(json_out)

        self.assertEqual(1, code)
        self.assertIn(
            "input_files.artifact_files[0].path must match resolved source_path",
            stderr.getvalue(),
        )

    def test_saved_verification_report_can_require_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            trial = json.loads(trial_json.read_text(encoding="utf-8"))
            trial["external_evidence"]["manual_csv_editing"] = True
            trial_json.write_text(json.dumps(trial, indent=2) + "\n", encoding="utf-8")
            json_out = root / "failed-external-trial-verification.json"
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                verify_external_trial_report.verify_external_trial_report(
                    trial_json,
                    root,
                    json_out=json_out,
                    require_pass=False,
                )

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                code = verify_external_trial_report.verify_saved_external_trial_report(
                    json_out,
                    require_report_pass=True,
                )

        self.assertEqual(1, code)


if __name__ == "__main__":
    unittest.main()
