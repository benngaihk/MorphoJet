#!/usr/bin/env python3
"""Unit tests for local release archive build safety helpers."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmark"))

import build_release_archive  # noqa: E402


class BuildReleaseArchiveTest(unittest.TestCase):
    def test_version_rejects_path_separators(self) -> None:
        for version in ["../escape", "v0.1.0/evil", "v0.1.0 beta"]:
            with self.subTest(version=version):
                with self.assertRaisesRegex(SystemExit, "--version must contain only"):
                    build_release_archive.validate_version(version)

    def test_package_name_accepts_release_like_versions(self) -> None:
        name = build_release_archive.package_name("v0.1.0+build.7")

        self.assertTrue(name.startswith("morphojet-v0.1.0+build.7-"))

    def test_existing_release_package_dir_is_replaceable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            package_dir = Path(tmp) / "morphojet-local-macos-arm64"
            package_dir.mkdir()
            for name in ["morphojet", "README.md", "LICENSE"]:
                (package_dir / name).write_text("ok\n", encoding="utf-8")

            self.assertTrue(build_release_archive.package_dir_is_replaceable(package_dir))

    def test_existing_package_dir_with_extra_file_is_not_replaceable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            package_dir = Path(tmp) / "morphojet-local-macos-arm64"
            package_dir.mkdir()
            (package_dir / "notes.txt").write_text("not release output\n", encoding="utf-8")

            self.assertFalse(build_release_archive.package_dir_is_replaceable(package_dir))

    def test_validate_outputs_rejects_non_release_package_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            package_dir = out_dir / "morphojet-local-macos-arm64"
            package_dir.mkdir()
            (package_dir / "notes.txt").write_text("not release output\n", encoding="utf-8")

            with self.assertRaisesRegex(SystemExit, "refusing to replace non-release package directory"):
                build_release_archive.validate_outputs(
                    out_dir,
                    package_dir,
                    out_dir / "morphojet-local-macos-arm64.tar.gz",
                    out_dir / "morphojet-local-macos-arm64.tar.gz.sha256",
                )

    def test_validate_outputs_rejects_archive_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            archive = out_dir / "morphojet-local-macos-arm64.tar.gz"
            archive.mkdir()

            with self.assertRaisesRegex(SystemExit, "refusing to replace non-file archive"):
                build_release_archive.validate_outputs(
                    out_dir,
                    out_dir / "morphojet-local-macos-arm64",
                    archive,
                    out_dir / "morphojet-local-macos-arm64.tar.gz.sha256",
                )

    def test_validate_outputs_rejects_paths_outside_out_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "out"
            out_dir.mkdir()

            with self.assertRaisesRegex(SystemExit, "archive must stay inside --out-dir"):
                build_release_archive.validate_outputs(
                    out_dir,
                    out_dir / "morphojet-local-macos-arm64",
                    Path(tmp) / "morphojet-local-macos-arm64.tar.gz",
                    out_dir / "morphojet-local-macos-arm64.tar.gz.sha256",
                )


if __name__ == "__main__":
    unittest.main()
