#!/usr/bin/env python3
"""Unit tests for release archive verification helpers."""

from __future__ import annotations

import io
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmark"))

import verify_release_archive  # noqa: E402


def write_tar(path: Path, members: list[tuple[str, bytes, str]]) -> None:
    with tarfile.open(path, "w:gz") as archive:
        for name, content, kind in members:
            info = tarfile.TarInfo(name)
            if kind == "symlink":
                info.type = tarfile.SYMTYPE
                info.linkname = "../outside"
                archive.addfile(info)
            elif kind == "dir":
                info.type = tarfile.DIRTYPE
                archive.addfile(info)
            elif kind == "fifo":
                info.type = tarfile.FIFOTYPE
                archive.addfile(info)
            else:
                info.size = len(content)
                archive.addfile(info, io.BytesIO(content))


class VerifyReleaseArchiveTest(unittest.TestCase):
    def test_required_files_include_chinese_readme(self) -> None:
        self.assertIn("README.zh-CN.md", verify_release_archive.REQUIRED_FILES)

    def test_checksum_issues_accepts_matching_archive_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            checksum = Path(tmp) / "archive.tar.gz.sha256"
            checksum.write_text("a" * 64 + "  archive.tar.gz\n")

            self.assertEqual([], verify_release_archive.checksum_issues(checksum, "archive.tar.gz"))

    def test_checksum_issues_rejects_invalid_digest_and_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            checksum = Path(tmp) / "archive.tar.gz.sha256"
            checksum.write_text("not-a-sha  other.tar.gz\n")

            issues = verify_release_archive.checksum_issues(checksum, "archive.tar.gz")

        self.assertIn("invalid checksum digest for archive.tar.gz", issues)
        self.assertIn("checksum file target mismatch for archive.tar.gz: other.tar.gz", issues)

    def test_safe_extract_accepts_normal_archive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "archive.tar.gz"
            out = root / "out"
            out.mkdir()
            write_tar(archive, [("package/README.md", b"ok\n", "file")])

            verify_release_archive.safe_extract(archive, out)

            self.assertEqual("ok\n", (out / "package" / "README.md").read_text())

    def test_json_out_must_not_overwrite_archive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "archive.tar.gz"
            checksum = root / "archive.tar.gz.sha256"

            with self.assertRaisesRegex(SystemExit, "--json-out must not overwrite archive"):
                verify_release_archive.validate_json_out_path(archive, archive, checksum)

    def test_json_out_must_not_overwrite_checksum(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "archive.tar.gz"
            checksum = root / "archive.tar.gz.sha256"

            with self.assertRaisesRegex(SystemExit, "--json-out must not overwrite checksum"):
                verify_release_archive.validate_json_out_path(checksum, archive, checksum)

    def test_safe_extract_accepts_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "archive.tar.gz"
            out = root / "out"
            out.mkdir()
            write_tar(archive, [("package", b"", "dir"), ("package/README.md", b"ok\n", "file")])

            verify_release_archive.safe_extract(archive, out)

            self.assertTrue((out / "package").is_dir())

    def test_safe_extract_rejects_parent_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "archive.tar.gz"
            out = root / "out"
            out.mkdir()
            write_tar(archive, [("../evil.txt", b"bad\n", "file")])

            with self.assertRaisesRegex(SystemExit, "unsafe archive path"):
                verify_release_archive.safe_extract(archive, out)

    def test_safe_extract_rejects_links(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "archive.tar.gz"
            out = root / "out"
            out.mkdir()
            write_tar(archive, [("package/link", b"", "symlink")])

            with self.assertRaisesRegex(SystemExit, "unsafe archive link"):
                verify_release_archive.safe_extract(archive, out)

    def test_safe_extract_rejects_special_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "archive.tar.gz"
            out = root / "out"
            out.mkdir()
            write_tar(archive, [("package/fifo", b"", "fifo")])

            with self.assertRaisesRegex(SystemExit, "unsafe archive member type"):
                verify_release_archive.safe_extract(archive, out)


if __name__ == "__main__":
    unittest.main()
