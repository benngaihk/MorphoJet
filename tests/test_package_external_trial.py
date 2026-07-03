#!/usr/bin/env python3
"""Unit tests for external trial evidence packaging."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmark"))
sys.path.insert(0, str(ROOT / "tests"))

import package_external_trial  # noqa: E402
import release_gate  # noqa: E402
from test_release_gate import add_artifact_provenance, valid_external_trial, write_trial_artifacts  # noqa: E402


class PackageExternalTrialTest(unittest.TestCase):
    def write_valid_trial(self, root: Path) -> Path:
        trial = valid_external_trial()
        write_trial_artifacts(trial, root)
        add_artifact_provenance(trial, root)
        trial_json = root / "external" / "handoff_trial.json"
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
            self.assertTrue((package_dir / "rendered_manifest.json").is_file())
            self.assertTrue((package_dir / "external_evidence.json").is_file())
            self.assertTrue((package_dir / "README.md").is_file())
            self.assertTrue((package_dir / "artifacts/external/handoff_contract.json").is_file())
            self.assertEqual(4, result["artifact_count"])
            self.assertEqual(4, len(manifest["artifacts"]))
            self.assertEqual(release_gate.sha256_file(zip_path), sha_path.read_text().split()[0])
            with zipfile.ZipFile(zip_path) as archive:
                self.assertIn("external-l4-demo/README.md", archive.namelist())
                self.assertIn("external-l4-demo/artifacts/external/handoff_contract.json", archive.namelist())

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
