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
            else:
                info.size = len(content)
                archive.addfile(info, io.BytesIO(content))


class VerifyReleaseArchiveTest(unittest.TestCase):
    def test_safe_extract_accepts_normal_archive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "archive.tar.gz"
            out = root / "out"
            out.mkdir()
            write_tar(archive, [("package/README.md", b"ok\n", "file")])

            verify_release_archive.safe_extract(archive, out)

            self.assertEqual("ok\n", (out / "package" / "README.md").read_text())

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


if __name__ == "__main__":
    unittest.main()
