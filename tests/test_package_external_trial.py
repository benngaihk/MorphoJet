#!/usr/bin/env python3
"""Unit tests for external trial evidence packaging."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
import warnings
import zipfile
from contextlib import contextmanager
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmark"))
sys.path.insert(0, str(ROOT / "tests"))

import package_external_trial  # noqa: E402
import release_gate  # noqa: E402
import verify_external_evidence_package  # noqa: E402
from test_release_gate import add_artifact_provenance, valid_external_trial, write_trial_artifacts  # noqa: E402


@contextmanager
def temporary_cwd(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


class PackageExternalTrialTest(unittest.TestCase):
    def write_valid_trial(self, root: Path) -> Path:
        trial = valid_external_trial()
        write_trial_artifacts(trial, root)
        add_artifact_provenance(trial, root)
        trial_json = root / "external" / "handoff_trial.json"
        trial["metadata"]["argv"][trial["metadata"]["argv"].index("--out-json") + 1] = str(trial_json)
        trial_json.parent.mkdir(parents=True, exist_ok=True)
        trial_json.write_text(json.dumps(trial, indent=2) + "\n", encoding="utf-8")
        return trial_json

    def test_package_valid_external_trial(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            out_dir = root / "package-out"

            result = package_external_trial.create_package(
                trial_json,
                root,
                out_dir,
                package_name="external-l4-demo",
            )

            package_dir = Path(result["package_dir"])
            zip_path = Path(result["zip"])
            sha_path = Path(result["sha256"])
            manifest = json.loads((package_dir / "artifact_manifest.json").read_text())

            self.assertTrue((package_dir / "handoff_trial.json").is_file())
            self.assertTrue((package_dir / "readiness.json").is_file())
            self.assertTrue((package_dir / "rendered_manifest.json").is_file())
            self.assertTrue((package_dir / "external_evidence.json").is_file())
            self.assertTrue((package_dir / "README.md").is_file())
            self.assertTrue((package_dir / "artifacts/external/handoff_contract.json").is_file())
            self.assertEqual(4, result["artifact_count"])
            self.assertEqual(4, len(manifest["artifacts"]))
            self.assertEqual(
                json.loads(trial_json.read_text(encoding="utf-8"))["readiness_report"],
                manifest["readiness_report"],
            )
            self.assertEqual(trial_json.stat().st_size, manifest["trial_json_size_bytes"])
            self.assertEqual(release_gate.sha256_file(trial_json), manifest["trial_json_sha256"])
            self.assertEqual(
                [
                    "benchmark/package_external_trial.py",
                    "--trial-json",
                    str(trial_json.resolve()),
                    "--trial-root",
                    str(root.resolve()),
                    "--out-dir",
                    str(out_dir.resolve()),
                    "--package-name",
                    "external-l4-demo",
                ],
                manifest["argv"],
            )
            self.assertEqual(
                ["README.md", "external_evidence.json", "handoff_trial.json", "readiness.json", "rendered_manifest.json"],
                sorted(entry["path"] for entry in manifest["review_files"]),
            )
            self.assertEqual(release_gate.sha256_file(zip_path), sha_path.read_text().split()[0])
            with zipfile.ZipFile(zip_path) as archive:
                self.assertIn("external-l4-demo/README.md", archive.namelist())
                self.assertIn("external-l4-demo/artifacts/external/handoff_contract.json", archive.namelist())

    def test_package_rejects_output_directory_covering_source_trial_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)

            with self.assertRaisesRegex(
                package_external_trial.PackageError,
                "package directory must not contain source trial JSON",
            ):
                package_external_trial.create_package(
                    trial_json,
                    root,
                    root,
                    package_name="external",
                    overwrite=True,
                )

            self.assertTrue(trial_json.is_file())
            self.assertTrue((root / "external" / "handoff_contract.json").is_file())

    def test_package_rejects_output_directory_equal_to_source_trial_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)

            with self.assertRaisesRegex(
                package_external_trial.PackageError,
                "package directory must not contain source trial JSON",
            ):
                package_external_trial.create_package(
                    trial_json,
                    root,
                    trial_json.parent,
                    package_name=trial_json.name,
                    overwrite=True,
                )

            self.assertTrue(trial_json.is_file())

    def test_release_gate_accepts_valid_package(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            result = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )

            gate = release_gate.validate_external_evidence_package(Path(result["package_dir"]), trial_json)

        self.assertEqual("PASS", gate.status)
        self.assertIn("External L4 evidence package PASS", gate.detail)

    def test_standalone_verifier_accepts_valid_package_and_writes_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            result = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            json_out = root / "review" / "external-package-verification.json"

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                code = verify_external_evidence_package.verify_external_evidence_package(
                    Path(result["package_dir"]),
                    trial_json=trial_json,
                    json_out=json_out,
                )
            payload = json.loads(json_out.read_text(encoding="utf-8"))
            expected_trial_sha = release_gate.sha256_file(trial_json)
            expected_zip_sha = release_gate.sha256_file(Path(result["zip"]))
            expected_manifest_sha = release_gate.sha256_file(Path(result["package_dir"]) / "artifact_manifest.json")
            expected_readiness_sha = release_gate.sha256_file(Path(result["package_dir"]) / "readiness.json")

        self.assertEqual(0, code)
        self.assertEqual(1, payload["schema_version"])
        self.assertEqual("benchmark/verify_external_evidence_package.py", payload["verifier"])
        generated_at = datetime.fromisoformat(payload["generated_at_utc"])
        self.assertEqual(timezone.utc.utcoffset(generated_at), generated_at.utcoffset())
        self.assertEqual("PASS", payload["status"])
        self.assertEqual("Validate external L4 evidence package", payload["gate"]["name"])
        self.assertIn("External L4 evidence package PASS", payload["gate"]["detail"])
        self.assertEqual(expected_trial_sha, payload["input_files"]["source_trial_json"]["sha256"])
        self.assertEqual(expected_zip_sha, payload["input_files"]["package_zip"]["sha256"])
        self.assertEqual(expected_manifest_sha, payload["input_files"]["package_artifact_manifest"]["sha256"])
        self.assertEqual(expected_readiness_sha, payload["input_files"]["package_readiness"]["sha256"])

    def test_standalone_verifier_records_absolute_paths_for_relative_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            result = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            package_dir = Path(result["package_dir"])
            json_out = root / "review" / "external-package-verification.json"

            with temporary_cwd(root), redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                code = verify_external_evidence_package.verify_external_evidence_package(
                    Path("package-out/external-l4-demo"),
                    trial_json=Path("external/handoff_trial.json"),
                    json_out=Path("review/external-package-verification.json"),
                )
            payload = json.loads(json_out.read_text(encoding="utf-8"))

        self.assertEqual(0, code)
        self.assertEqual(str(package_dir.resolve()), payload["package_dir"])
        self.assertEqual(str(trial_json.resolve()), payload["trial_json"])
        self.assertEqual(
            str((package_dir / "artifact_manifest.json").resolve()),
            payload["input_files"]["package_artifact_manifest"]["path"],
        )
        self.assertEqual(
            str((package_dir / "readiness.json").resolve()),
            payload["input_files"]["package_readiness"]["path"],
        )
        self.assertEqual(str(trial_json.resolve()), payload["input_files"]["source_trial_json"]["path"])
        self.assertIn(str(package_dir.resolve()), payload["argv"])
        self.assertIn(str(trial_json.resolve()), payload["argv"])
        self.assertIn(str(json_out.resolve()), payload["argv"])

    def test_package_verifier_json_out_must_not_overwrite_source_trial_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            result = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )

            with self.assertRaises(SystemExit) as context:
                verify_external_evidence_package.verify_external_evidence_package(
                    Path(result["package_dir"]),
                    trial_json=trial_json,
                    json_out=trial_json,
                )

        self.assertIn("--json-out must not overwrite source trial JSON", str(context.exception))

    def test_package_verifier_json_out_must_not_overwrite_package_review_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            result = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            package_dir = Path(result["package_dir"])

            with self.assertRaises(SystemExit) as context:
                verify_external_evidence_package.verify_external_evidence_package(
                    package_dir,
                    trial_json=trial_json,
                    json_out=package_dir / "artifact_manifest.json",
                )

        self.assertIn("--json-out must not overwrite package review file: artifact_manifest.json", str(context.exception))

    def test_package_verifier_json_out_must_not_overwrite_package_readiness_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            result = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            package_dir = Path(result["package_dir"])

            with self.assertRaises(SystemExit) as context:
                verify_external_evidence_package.verify_external_evidence_package(
                    package_dir,
                    trial_json=trial_json,
                    json_out=package_dir / "readiness.json",
                )

        self.assertIn("--json-out must not overwrite package review file: readiness.json", str(context.exception))

    def test_package_verifier_json_out_must_not_overwrite_package_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            result = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            package_dir = Path(result["package_dir"])

            with self.assertRaises(SystemExit) as context:
                verify_external_evidence_package.verify_external_evidence_package(
                    package_dir,
                    trial_json=trial_json,
                    json_out=package_dir / "artifacts" / "external" / "handoff_contract.json",
                )

        self.assertIn(
            "--json-out must not overwrite package artifact: artifacts/external/handoff_contract.json",
            str(context.exception),
        )

    def test_package_verifier_json_out_must_not_create_file_inside_package_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            result = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            package_dir = Path(result["package_dir"])

            with self.assertRaises(SystemExit) as context:
                verify_external_evidence_package.verify_external_evidence_package(
                    package_dir,
                    trial_json=trial_json,
                    json_out=package_dir / "artifacts" / "external" / "handoff_contract.json" / "review.json",
                )

        self.assertIn(
            "--json-out must not create a file inside package artifact: artifacts/external/handoff_contract.json",
            str(context.exception),
        )

    def test_standalone_verifier_rejects_invalid_package(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            result = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            Path(result["sha256"]).write_text("0" * 64 + "  external-l4-demo.zip\n", encoding="utf-8")

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                code = verify_external_evidence_package.verify_external_evidence_package(
                    Path(result["package_dir"]),
                    trial_json=trial_json,
                )

        self.assertEqual(1, code)

    def test_standalone_verifier_can_write_failed_diagnostic_report_without_failing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            result = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            Path(result["sha256"]).write_text("0" * 64 + "  external-l4-demo.zip\n", encoding="utf-8")
            json_out = root / "failed-package-verification.json"

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                code = verify_external_evidence_package.verify_external_evidence_package(
                    Path(result["package_dir"]),
                    trial_json=trial_json,
                    json_out=json_out,
                    require_pass=False,
                )
            payload = json.loads(json_out.read_text(encoding="utf-8"))

        self.assertEqual(0, code)
        self.assertEqual("FAIL", payload["status"])
        self.assertIn("package zip sha256 mismatch", payload["gate"]["detail"])

    def test_saved_package_verification_report_passes_with_file_recheck(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            result = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            json_out = root / "external-package-verification.json"
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                verify_external_evidence_package.verify_external_evidence_package(
                    Path(result["package_dir"]),
                    trial_json=trial_json,
                    json_out=json_out,
                )

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                code = verify_external_evidence_package.verify_saved_external_evidence_package_report(
                    json_out,
                    require_report_pass=True,
                    verify_files=True,
                )

        self.assertEqual(0, code)

    def test_saved_package_verification_report_rejects_status_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            result = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            json_out = root / "external-package-verification.json"
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                verify_external_evidence_package.verify_external_evidence_package(
                    Path(result["package_dir"]),
                    trial_json=trial_json,
                    json_out=json_out,
                )
            payload = json.loads(json_out.read_text(encoding="utf-8"))
            payload["status"] = "FAIL"
            json_out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                code = verify_external_evidence_package.verify_saved_external_evidence_package_report(json_out)

        self.assertEqual(1, code)

    def test_saved_package_verification_report_rejects_metadata_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            result = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            json_out = root / "external-package-verification.json"
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                verify_external_evidence_package.verify_external_evidence_package(
                    Path(result["package_dir"]),
                    trial_json=trial_json,
                    json_out=json_out,
                )
            payload = json.loads(json_out.read_text(encoding="utf-8"))
            payload["schema_version"] = 2
            payload["verifier"] = "other.py"
            payload["generated_at_utc"] = "not-a-date"
            json_out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                code = verify_external_evidence_package.verify_saved_external_evidence_package_report(json_out)

        self.assertEqual(1, code)

    def test_saved_package_verification_report_rejects_non_utc_generated_at(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            result = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            json_out = root / "external-package-verification.json"
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                verify_external_evidence_package.verify_external_evidence_package(
                    Path(result["package_dir"]),
                    trial_json=trial_json,
                    json_out=json_out,
                )
            payload = json.loads(json_out.read_text(encoding="utf-8"))
            payload["generated_at_utc"] = "2026-07-07T12:00:00+08:00"
            json_out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            stderr = StringIO()
            with redirect_stdout(StringIO()), redirect_stderr(stderr):
                code = verify_external_evidence_package.verify_saved_external_evidence_package_report(json_out)

        self.assertEqual(1, code)
        self.assertIn("generated_at_utc must be UTC", stderr.getvalue())

    def test_saved_package_verification_report_rejects_relative_top_level_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            result = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            json_out = root / "external-package-verification.json"
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                verify_external_evidence_package.verify_external_evidence_package(
                    Path(result["package_dir"]),
                    trial_json=trial_json,
                    json_out=json_out,
                )
            payload = json.loads(json_out.read_text(encoding="utf-8"))
            payload["package_dir"] = "package-out/external-l4-demo"
            payload["trial_json"] = "external/handoff_trial.json"
            json_out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            stderr = StringIO()
            with redirect_stdout(StringIO()), redirect_stderr(stderr):
                code = verify_external_evidence_package.verify_saved_external_evidence_package_report(json_out)

        self.assertEqual(1, code)
        self.assertIn("package_dir must be an absolute path", stderr.getvalue())
        self.assertIn("trial_json must be an absolute path", stderr.getvalue())

    def test_saved_package_verification_report_rejects_relative_package_dir_argv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            result = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            json_out = root / "external-package-verification.json"
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                verify_external_evidence_package.verify_external_evidence_package(
                    Path(result["package_dir"]),
                    trial_json=trial_json,
                    json_out=json_out,
                )
            payload = json.loads(json_out.read_text(encoding="utf-8"))
            payload["argv"][1] = "package-out/external-l4-demo"
            json_out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
                code = verify_external_evidence_package.verify_saved_external_evidence_package_report(json_out)

        self.assertEqual(1, code)
        self.assertIn("argv package_dir must be an absolute path", stderr.getvalue())

    def test_saved_package_verification_report_rejects_relative_trial_json_argv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            result = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            json_out = root / "external-package-verification.json"
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                verify_external_evidence_package.verify_external_evidence_package(
                    Path(result["package_dir"]),
                    trial_json=trial_json,
                    json_out=json_out,
                )
            payload = json.loads(json_out.read_text(encoding="utf-8"))
            payload["argv"][payload["argv"].index("--trial-json") + 1] = "external/handoff_trial.json"
            json_out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
                code = verify_external_evidence_package.verify_saved_external_evidence_package_report(json_out)

        self.assertEqual(1, code)
        self.assertIn("argv --trial-json must be an absolute path", stderr.getvalue())

    def test_saved_package_verification_report_rejects_argv_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            result = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            json_out = root / "external-package-verification.json"
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                verify_external_evidence_package.verify_external_evidence_package(
                    Path(result["package_dir"]),
                    trial_json=trial_json,
                    json_out=json_out,
                )
            payload = json.loads(json_out.read_text(encoding="utf-8"))
            payload["argv"] = [
                "benchmark/verify_external_evidence_package.py",
                str(root / "other-package"),
                "--trial-json",
                "--json-out",
                str(json_out),
                "--verify-report",
                str(json_out),
            ]
            json_out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
                code = verify_external_evidence_package.verify_saved_external_evidence_package_report(json_out)

        self.assertEqual(1, code)
        self.assertIn("argv must include package_dir exactly once", stderr.getvalue())
        self.assertIn("argv --trial-json must include a value", stderr.getvalue())
        self.assertIn("argv must not include --verify-report", stderr.getvalue())

    def test_saved_package_verification_report_rejects_json_out_path_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            result = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            json_out = root / "external-package-verification.json"
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                verify_external_evidence_package.verify_external_evidence_package(
                    Path(result["package_dir"]),
                    trial_json=trial_json,
                    json_out=json_out,
                )
            payload = json.loads(json_out.read_text(encoding="utf-8"))
            payload["argv"][payload["argv"].index("--json-out") + 1] = str(root / "other-package-verification.json")
            json_out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
                code = verify_external_evidence_package.verify_saved_external_evidence_package_report(json_out)

        self.assertEqual(1, code)
        self.assertIn("argv --json-out must match saved verifier report path", stderr.getvalue())

    def test_saved_package_verification_report_rejects_relative_json_out_argv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            result = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            json_out = root / "external-package-verification.json"
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                verify_external_evidence_package.verify_external_evidence_package(
                    Path(result["package_dir"]),
                    trial_json=trial_json,
                    json_out=json_out,
                )
            payload = json.loads(json_out.read_text(encoding="utf-8"))
            payload["argv"][payload["argv"].index("--json-out") + 1] = json_out.name
            json_out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with temporary_cwd(root), redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
                code = verify_external_evidence_package.verify_saved_external_evidence_package_report(json_out)

        self.assertEqual(1, code)
        self.assertIn("argv --json-out must be an absolute path", stderr.getvalue())

    def test_saved_package_verification_report_requires_json_out_path_binding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            result = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            json_out = root / "external-package-verification.json"
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                verify_external_evidence_package.verify_external_evidence_package(
                    Path(result["package_dir"]),
                    trial_json=trial_json,
                    json_out=json_out,
                )
            payload = json.loads(json_out.read_text(encoding="utf-8"))
            json_out_index = payload["argv"].index("--json-out")
            del payload["argv"][json_out_index:json_out_index + 2]
            json_out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
                code = verify_external_evidence_package.verify_saved_external_evidence_package_report(json_out)

        self.assertEqual(1, code)
        self.assertIn("argv missing --json-out for saved verifier report", stderr.getvalue())

    def test_saved_package_verification_report_recomputes_package_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            result = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            json_out = root / "external-package-verification.json"
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                verify_external_evidence_package.verify_external_evidence_package(
                    Path(result["package_dir"]),
                    trial_json=trial_json,
                    json_out=json_out,
                )
            payload = json.loads(json_out.read_text(encoding="utf-8"))
            payload["gate"]["detail"] = "External L4 evidence package PASS: stale detail"
            json_out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                code = verify_external_evidence_package.verify_saved_external_evidence_package_report(
                    json_out,
                    verify_files=True,
                )

        self.assertEqual(1, code)

    def test_saved_package_verification_report_recomputes_input_file_summaries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            result = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            json_out = root / "external-package-verification.json"
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                verify_external_evidence_package.verify_external_evidence_package(
                    Path(result["package_dir"]),
                    trial_json=trial_json,
                    json_out=json_out,
                )
            payload = json.loads(json_out.read_text(encoding="utf-8"))
            payload["input_files"]["package_readiness"]["sha256"] = "0" * 64
            json_out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
                code = verify_external_evidence_package.verify_saved_external_evidence_package_report(
                    json_out,
                    verify_files=True,
                )

        self.assertEqual(1, code)
        self.assertIn(
            "input_files.package_readiness.sha256 changed after recomputing evidence package validation",
            stderr.getvalue(),
        )

    def test_saved_package_verification_report_rejects_unbound_package_summary_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            result = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            json_out = root / "external-package-verification.json"
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                verify_external_evidence_package.verify_external_evidence_package(
                    Path(result["package_dir"]),
                    trial_json=trial_json,
                    json_out=json_out,
                )
            payload = json.loads(json_out.read_text(encoding="utf-8"))
            payload["input_files"]["package_readme"]["path"] = str(root / "other" / "README.md")
            json_out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
                code = verify_external_evidence_package.verify_saved_external_evidence_package_report(json_out)

        self.assertEqual(1, code)
        self.assertIn("input_files.package_readme.path must match report inputs", stderr.getvalue())

    def test_saved_package_verification_report_rejects_unbound_readiness_summary_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            result = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            json_out = root / "external-package-verification.json"
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                verify_external_evidence_package.verify_external_evidence_package(
                    Path(result["package_dir"]),
                    trial_json=trial_json,
                    json_out=json_out,
                )
            payload = json.loads(json_out.read_text(encoding="utf-8"))
            payload["input_files"]["package_readiness"]["path"] = str(root / "other" / "readiness.json")
            json_out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
                code = verify_external_evidence_package.verify_saved_external_evidence_package_report(json_out)

        self.assertEqual(1, code)
        self.assertIn("input_files.package_readiness.path must match report inputs", stderr.getvalue())

    def test_saved_package_verification_report_rejects_unbound_source_trial_summary_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            result = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            json_out = root / "external-package-verification.json"
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                verify_external_evidence_package.verify_external_evidence_package(
                    Path(result["package_dir"]),
                    trial_json=trial_json,
                    json_out=json_out,
                )
            payload = json.loads(json_out.read_text(encoding="utf-8"))
            payload["input_files"]["source_trial_json"]["path"] = str(root / "other-trial.json")
            json_out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
                code = verify_external_evidence_package.verify_saved_external_evidence_package_report(json_out)

        self.assertEqual(1, code)
        self.assertIn("input_files.source_trial_json.path must match report inputs", stderr.getvalue())

    def test_saved_package_verification_report_rejects_unexpected_input_file_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            result = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            json_out = root / "external-package-verification.json"
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                verify_external_evidence_package.verify_external_evidence_package(
                    Path(result["package_dir"]),
                    trial_json=trial_json,
                    json_out=json_out,
                )
            payload = json.loads(json_out.read_text(encoding="utf-8"))
            payload["input_files"]["unrelated_file"] = {
                "path": str(root / "unrelated.txt"),
                "exists": False,
                "size_bytes": None,
                "sha256": None,
            }
            json_out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
                code = verify_external_evidence_package.verify_saved_external_evidence_package_report(json_out)

        self.assertEqual(1, code)
        self.assertIn("input_files has unexpected entry: unrelated_file", stderr.getvalue())

    def test_saved_package_verification_report_can_require_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            result = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            Path(result["sha256"]).write_text("0" * 64 + "  external-l4-demo.zip\n", encoding="utf-8")
            json_out = root / "failed-package-verification.json"
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                verify_external_evidence_package.verify_external_evidence_package(
                    Path(result["package_dir"]),
                    trial_json=trial_json,
                    json_out=json_out,
                    require_pass=False,
                )

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                code = verify_external_evidence_package.verify_saved_external_evidence_package_report(
                    json_out,
                    require_report_pass=True,
                )

        self.assertEqual(1, code)

    def test_saved_package_verification_report_can_require_trial_json_binding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            result = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            json_out = root / "external-package-verification.json"
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                verify_external_evidence_package.verify_external_evidence_package(
                    Path(result["package_dir"]),
                    json_out=json_out,
                )

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                default_code = verify_external_evidence_package.verify_saved_external_evidence_package_report(
                    json_out,
                    require_report_pass=True,
                    verify_files=True,
                )
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                required_code = verify_external_evidence_package.verify_saved_external_evidence_package_report(
                    json_out,
                    require_report_pass=True,
                    verify_files=True,
                    require_trial_json=True,
                )

        self.assertEqual(0, default_code)
        self.assertEqual(1, required_code)

    def test_release_gate_rejects_package_for_different_trial_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            result = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            other_trial = json.loads(trial_json.read_text())
            other_trial["external_evidence"]["dataset_name"] = "Different Batch"
            other_trial_json = root / "other_trial.json"
            other_trial_json.write_text(json.dumps(other_trial, indent=2) + "\n", encoding="utf-8")

            gate = release_gate.validate_external_evidence_package(Path(result["package_dir"]), other_trial_json)

        self.assertEqual("FAIL", gate.status)
        self.assertIn("does not match --external-trial-json", gate.detail)

    def test_release_gate_rejects_package_zip_hash_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            result = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            Path(result["sha256"]).write_text("0" * 64 + "  external-l4-demo.zip\n", encoding="utf-8")

            gate = release_gate.validate_external_evidence_package(Path(result["package_dir"]), trial_json)

        self.assertEqual("FAIL", gate.status)
        self.assertIn("package zip sha256 mismatch", gate.detail)

    def test_release_gate_rejects_package_zip_sha_target_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            result = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            zip_path = Path(result["zip"])
            Path(result["sha256"]).write_text(
                f"{release_gate.sha256_file(zip_path)}  other-package.zip\n",
                encoding="utf-8",
            )

            gate = release_gate.validate_external_evidence_package(Path(result["package_dir"]), trial_json)

        self.assertEqual("FAIL", gate.status)
        self.assertIn("package zip sha256 target mismatch for external-l4-demo.zip", gate.detail)

    def test_release_gate_rejects_package_zip_sha_invalid_digest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            result = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            Path(result["sha256"]).write_text("not-a-sha  external-l4-demo.zip\n", encoding="utf-8")

            gate = release_gate.validate_external_evidence_package(Path(result["package_dir"]), trial_json)

        self.assertEqual("FAIL", gate.status)
        self.assertIn("package zip sha256 digest is invalid", gate.detail)

    def test_release_gate_rejects_package_zip_missing_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            result = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            zip_path = Path(result["zip"])
            omitted = "external-l4-demo/artifacts/external/handoff_contract.json"
            with tempfile.TemporaryDirectory() as rewrite_tmp:
                rewritten = Path(rewrite_tmp) / "external-l4-demo.zip"
                with zipfile.ZipFile(zip_path) as original, zipfile.ZipFile(
                    rewritten, "w", compression=zipfile.ZIP_DEFLATED
                ) as replacement:
                    for name in original.namelist():
                        if name != omitted:
                            replacement.writestr(name, original.read(name))
                rewritten.replace(zip_path)

            gate = release_gate.validate_external_evidence_package(Path(result["package_dir"]), trial_json)

        self.assertEqual("FAIL", gate.status)
        self.assertIn("package zip missing entry: " + omitted, gate.detail)

    def test_release_gate_rejects_package_zip_extra_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            result = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            zip_path = Path(result["zip"])
            with zipfile.ZipFile(zip_path, "a", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("external-l4-demo/extra-notes.txt", "undeclared\n")
            Path(result["sha256"]).write_text(
                f"{release_gate.sha256_file(zip_path)}  external-l4-demo.zip\n",
                encoding="utf-8",
            )

            gate = release_gate.validate_external_evidence_package(Path(result["package_dir"]), trial_json)

        self.assertEqual("FAIL", gate.status)
        self.assertIn("package zip has unexpected entry: external-l4-demo/extra-notes.txt", gate.detail)

    def test_release_gate_rejects_package_zip_duplicate_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            result = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            zip_path = Path(result["zip"])
            duplicated = "external-l4-demo/README.md"
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                with zipfile.ZipFile(zip_path, "a", compression=zipfile.ZIP_DEFLATED) as archive:
                    archive.writestr(duplicated, "duplicate\n")
            Path(result["sha256"]).write_text(
                f"{release_gate.sha256_file(zip_path)}  external-l4-demo.zip\n",
                encoding="utf-8",
            )

            gate = release_gate.validate_external_evidence_package(Path(result["package_dir"]), trial_json)

        self.assertEqual("FAIL", gate.status)
        self.assertIn("package zip entry is duplicated: " + duplicated, gate.detail)

    def test_release_gate_rejects_package_zip_entry_content_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            result = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            zip_path = Path(result["zip"])
            changed = "external-l4-demo/README.md"
            with tempfile.TemporaryDirectory() as rewrite_tmp:
                rewritten = Path(rewrite_tmp) / "external-l4-demo.zip"
                with zipfile.ZipFile(zip_path) as original, zipfile.ZipFile(
                    rewritten, "w", compression=zipfile.ZIP_DEFLATED
                ) as replacement:
                    for name in original.namelist():
                        replacement.writestr(name, "tampered\n" if name == changed else original.read(name))
                rewritten.replace(zip_path)
            Path(result["sha256"]).write_text(
                f"{release_gate.sha256_file(zip_path)}  external-l4-demo.zip\n",
                encoding="utf-8",
            )

            gate = release_gate.validate_external_evidence_package(Path(result["package_dir"]), trial_json)

        self.assertEqual("FAIL", gate.status)
        self.assertIn("package zip entry content mismatch: " + changed, gate.detail)

    def test_release_gate_rejects_duplicate_artifact_package_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            result = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            package_dir = Path(result["package_dir"])
            manifest_path = package_dir / "artifact_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["artifacts"][1]["package_path"] = manifest["artifacts"][0]["package_path"]
            manifest["artifacts"][1]["size_bytes"] = manifest["artifacts"][0]["size_bytes"]
            manifest["artifacts"][1]["sha256"] = manifest["artifacts"][0]["sha256"]
            manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

            gate = release_gate.validate_external_evidence_package(package_dir, trial_json)

        self.assertEqual("FAIL", gate.status)
        self.assertIn("package artifact package_path is duplicated", gate.detail)

    def test_release_gate_rejects_package_readme_missing_signoff_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            result = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            package_dir = Path(result["package_dir"])
            readme_path = package_dir / "README.md"
            readme_path.write_text("# External L4 Trial Evidence Package\n\nplaceholder\n", encoding="utf-8")
            zip_path = Path(result["zip"])
            package_external_trial.zip_directory(package_dir, zip_path)
            Path(result["sha256"]).write_text(
                f"{release_gate.sha256_file(zip_path)}  external-l4-demo.zip\n",
                encoding="utf-8",
            )

            gate = release_gate.validate_external_evidence_package(package_dir, trial_json)

        self.assertEqual("FAIL", gate.status)
        self.assertIn("package README missing signoff field: trial_id", gate.detail)
        self.assertIn("package README missing signoff field: validation_detail", gate.detail)

    def test_release_gate_rejects_tampered_review_file_digest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            result = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            package_dir = Path(result["package_dir"])
            readme_path = package_dir / "README.md"
            readme_path.write_text(readme_path.read_text(encoding="utf-8") + "\nTampered.\n", encoding="utf-8")
            zip_path = Path(result["zip"])
            package_external_trial.zip_directory(package_dir, zip_path)
            Path(result["sha256"]).write_text(
                f"{release_gate.sha256_file(zip_path)}  external-l4-demo.zip\n",
                encoding="utf-8",
            )

            gate = release_gate.validate_external_evidence_package(package_dir, trial_json)

        self.assertEqual("FAIL", gate.status)
        self.assertIn("package review_file size mismatch: README.md", gate.detail)
        self.assertIn("package review_file sha256 mismatch: README.md", gate.detail)

    def test_release_gate_rejects_package_readme_missing_external_evidence_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            result = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            package_dir = Path(result["package_dir"])
            readme_path = package_dir / "README.md"
            readme = readme_path.read_text(encoding="utf-8")
            readme_path.write_text(
                readme.replace("- dataset_source: `LIMS export`\n", "").replace(
                    "- execution_environment: `Ubuntu 24.04, Python 3.12`\n",
                    "",
                ).replace(
                    "- reviewer_name_or_role: `External QA Reviewer`\n",
                    "",
                ).replace(
                    "- reviewed_at_utc: `2026-07-03T01:02:03+00:00`\n",
                    "",
                ).replace(
                    "- signoff_statement: `Reviewed against the lab workflow acceptance criteria.`\n",
                    "",
                ),
                encoding="utf-8",
            )
            zip_path = Path(result["zip"])
            package_external_trial.zip_directory(package_dir, zip_path)
            Path(result["sha256"]).write_text(
                f"{release_gate.sha256_file(zip_path)}  external-l4-demo.zip\n",
                encoding="utf-8",
            )

            gate = release_gate.validate_external_evidence_package(package_dir, trial_json)

        self.assertEqual("FAIL", gate.status)
        self.assertIn("package README missing signoff field: dataset_source", gate.detail)
        self.assertIn("package README missing signoff field: execution_environment", gate.detail)
        self.assertIn("package README missing signoff field: reviewer_name_or_role", gate.detail)
        self.assertIn("package README missing signoff field: reviewed_at_utc", gate.detail)
        self.assertIn("package README missing signoff field: signoff_statement", gate.detail)

    def test_release_gate_rejects_package_readme_missing_acceptance_criterion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            result = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            package_dir = Path(result["package_dir"])
            readme_path = package_dir / "README.md"
            readme = readme_path.read_text(encoding="utf-8")
            readme_path.write_text(
                readme.replace(
                    "- Existing downstream workflow consumes MorphoJet output without manual CSV edits.\n",
                    "",
                ),
                encoding="utf-8",
            )
            zip_path = Path(result["zip"])
            package_external_trial.zip_directory(package_dir, zip_path)
            Path(result["sha256"]).write_text(
                f"{release_gate.sha256_file(zip_path)}  external-l4-demo.zip\n",
                encoding="utf-8",
            )

            gate = release_gate.validate_external_evidence_package(package_dir, trial_json)

        self.assertEqual("FAIL", gate.status)
        self.assertIn("package README missing acceptance criterion: 0", gate.detail)

    def test_release_gate_rejects_package_readme_missing_validation_detail_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            result = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            package_dir = Path(result["package_dir"])
            manifest = json.loads((package_dir / "artifact_manifest.json").read_text(encoding="utf-8"))
            readme_path = package_dir / "README.md"
            readme_path.write_text(
                readme_path.read_text(encoding="utf-8").replace(
                    manifest["validation_detail"],
                    "External workflow trial PASS: redacted detail",
                ),
                encoding="utf-8",
            )
            zip_path = Path(result["zip"])
            package_external_trial.zip_directory(package_dir, zip_path)
            Path(result["sha256"]).write_text(
                f"{release_gate.sha256_file(zip_path)}  external-l4-demo.zip\n",
                encoding="utf-8",
            )

            gate = release_gate.validate_external_evidence_package(package_dir, trial_json)

        self.assertEqual("FAIL", gate.status)
        self.assertIn("package README missing signoff field: validation_detail_text", gate.detail)

    def test_release_gate_rejects_artifact_manifest_validation_detail_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            result = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            package_dir = Path(result["package_dir"])
            manifest_path = package_dir / "artifact_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["validation_detail"] = "External workflow trial PASS: stale copied detail"
            manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            zip_path = Path(result["zip"])
            package_external_trial.zip_directory(package_dir, zip_path)
            Path(result["sha256"]).write_text(
                f"{release_gate.sha256_file(zip_path)}  external-l4-demo.zip\n",
                encoding="utf-8",
            )

            gate = release_gate.validate_external_evidence_package(package_dir, trial_json)

        self.assertEqual("FAIL", gate.status)
        self.assertIn("package artifact_manifest.validation_detail must match external trial PASS detail", gate.detail)

    def test_release_gate_rejects_artifact_manifest_trial_json_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            result = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            package_dir = Path(result["package_dir"])
            manifest_path = package_dir / "artifact_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["trial_json"] = str(root / "other" / "handoff_trial.json")
            manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            zip_path = Path(result["zip"])
            package_external_trial.zip_directory(package_dir, zip_path)
            Path(result["sha256"]).write_text(
                f"{release_gate.sha256_file(zip_path)}  external-l4-demo.zip\n",
                encoding="utf-8",
            )

            gate = release_gate.validate_external_evidence_package(package_dir, trial_json)

        self.assertEqual("FAIL", gate.status)
        self.assertIn("package artifact_manifest.trial_json must match --external-trial-json", gate.detail)

    def test_release_gate_rejects_non_utc_artifact_manifest_packaged_at(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            result = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            package_dir = Path(result["package_dir"])
            manifest_path = package_dir / "artifact_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["packaged_at_utc"] = "2026-07-03T08:00:00+08:00"
            manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            zip_path = Path(result["zip"])
            package_external_trial.zip_directory(package_dir, zip_path)
            Path(result["sha256"]).write_text(
                f"{release_gate.sha256_file(zip_path)}  external-l4-demo.zip\n",
                encoding="utf-8",
            )

            gate = release_gate.validate_external_evidence_package(package_dir, trial_json)

        self.assertEqual("FAIL", gate.status)
        self.assertIn("package artifact_manifest.packaged_at_utc must be UTC", gate.detail)

    def test_release_gate_rejects_artifact_manifest_argv_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            result = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            package_dir = Path(result["package_dir"])
            manifest_path = package_dir / "artifact_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["argv"][manifest["argv"].index("--out-dir") + 1] = str(root / "other-package-out")
            manifest["argv"][manifest["argv"].index("--package-name") + 1] = "other-package"
            manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            zip_path = Path(result["zip"])
            package_external_trial.zip_directory(package_dir, zip_path)
            Path(result["sha256"]).write_text(
                f"{release_gate.sha256_file(zip_path)}  external-l4-demo.zip\n",
                encoding="utf-8",
            )

            gate = release_gate.validate_external_evidence_package(package_dir, trial_json)

        self.assertEqual("FAIL", gate.status)
        self.assertIn("package artifact_manifest.argv --out-dir must match artifact_manifest", gate.detail)
        self.assertIn("package artifact_manifest.argv --package-name must match package name", gate.detail)

    def test_release_gate_rejects_artifact_manifest_argv_with_extra_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            result = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            package_dir = Path(result["package_dir"])
            manifest_path = package_dir / "artifact_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["argv"].extend(["--dry-run", "unused-positional"])
            manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            zip_path = Path(result["zip"])
            package_external_trial.zip_directory(package_dir, zip_path)
            Path(result["sha256"]).write_text(
                f"{release_gate.sha256_file(zip_path)}  external-l4-demo.zip\n",
                encoding="utf-8",
            )

            gate = release_gate.validate_external_evidence_package(package_dir, trial_json)

        self.assertEqual("FAIL", gate.status)
        self.assertIn("package artifact_manifest.argv must match canonical packager argv", gate.detail)

    def test_release_gate_requires_artifact_manifest_argv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            result = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            package_dir = Path(result["package_dir"])
            manifest_path = package_dir / "artifact_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            del manifest["argv"]
            manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            zip_path = Path(result["zip"])
            package_external_trial.zip_directory(package_dir, zip_path)
            Path(result["sha256"]).write_text(
                f"{release_gate.sha256_file(zip_path)}  external-l4-demo.zip\n",
                encoding="utf-8",
            )

            gate = release_gate.validate_external_evidence_package(package_dir, trial_json)

        self.assertEqual("FAIL", gate.status)
        self.assertIn("package artifact_manifest.argv must be a non-empty string list", gate.detail)

    def test_release_gate_rejects_artifact_manifest_trial_json_digest_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            result = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            package_dir = Path(result["package_dir"])
            manifest_path = package_dir / "artifact_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["trial_json_size_bytes"] += 1
            manifest["trial_json_sha256"] = "0" * 64
            manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            zip_path = Path(result["zip"])
            package_external_trial.zip_directory(package_dir, zip_path)
            Path(result["sha256"]).write_text(
                f"{release_gate.sha256_file(zip_path)}  external-l4-demo.zip\n",
                encoding="utf-8",
            )

            gate = release_gate.validate_external_evidence_package(package_dir, trial_json)

        self.assertEqual("FAIL", gate.status)
        self.assertIn(
            "package artifact_manifest.trial_json_size_bytes must match packaged handoff_trial.json",
            gate.detail,
        )
        self.assertIn(
            "package artifact_manifest.trial_json_sha256 must match packaged handoff_trial.json",
            gate.detail,
        )

    def test_release_gate_rejects_packaged_readiness_json_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            result = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            package_dir = Path(result["package_dir"])
            (package_dir / "readiness.json").write_text('{"status":"STALE"}\n', encoding="utf-8")
            zip_path = Path(result["zip"])
            package_external_trial.zip_directory(package_dir, zip_path)
            Path(result["sha256"]).write_text(
                f"{release_gate.sha256_file(zip_path)}  external-l4-demo.zip\n",
                encoding="utf-8",
            )

            gate = release_gate.validate_external_evidence_package(package_dir, trial_json)

        self.assertEqual("FAIL", gate.status)
        self.assertIn("package review_file sha256 mismatch: readiness.json", gate.detail)
        self.assertIn("readiness_report.sha256 must match readiness report file", gate.detail)

    def test_release_gate_rejects_artifact_manifest_trial_root_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            result = package_external_trial.create_package(
                trial_json,
                root,
                root / "package-out",
                package_name="external-l4-demo",
            )
            package_dir = Path(result["package_dir"])
            manifest_path = package_dir / "artifact_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["trial_root"] = str(root / "other-root")
            manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            zip_path = Path(result["zip"])
            package_external_trial.zip_directory(package_dir, zip_path)
            Path(result["sha256"]).write_text(
                f"{release_gate.sha256_file(zip_path)}  external-l4-demo.zip\n",
                encoding="utf-8",
            )

            gate = release_gate.validate_external_evidence_package(package_dir, trial_json)

        self.assertEqual("FAIL", gate.status)
        self.assertIn("package artifact_manifest.trial_root does not resolve trial artifacts", gate.detail)

    def test_package_rejects_invalid_external_trial(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial_json = self.write_valid_trial(root)
            trial = json.loads(trial_json.read_text())
            trial["external_evidence"]["manual_csv_editing"] = True
            trial_json.write_text(json.dumps(trial, indent=2) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(package_external_trial.PackageError, "manual_csv_editing"):
                package_external_trial.create_package(trial_json, root, root / "package-out")

    def test_package_rejects_relative_path_traversal(self) -> None:
        with self.assertRaisesRegex(package_external_trial.PackageError, "unsafe artifact path"):
            package_external_trial.packaged_artifact_path("../outside.csv")


if __name__ == "__main__":
    unittest.main()
