#!/usr/bin/env python3
"""Unit tests for production-claim language guard."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmark"))

import validate_claim_language  # noqa: E402


class ValidateClaimLanguageTest(unittest.TestCase):
    def test_default_paths_include_chinese_readme(self) -> None:
        default_paths = {path.relative_to(ROOT).as_posix() for path in validate_claim_language.DEFAULT_PATHS}

        self.assertIn("README.md", default_paths)
        self.assertIn("README.zh-CN.md", default_paths)
        self.assertIn("MORPHOJET-FEASIBILITY.md", default_paths)
        self.assertIn("corpus/README.md", default_paths)
        self.assertIn("docs/PRODUCTION_READINESS.md", default_paths)

    def test_accepts_guarded_claim_language(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "README.md"
            path.write_text(
                "MorphoJet is not production-ready yet.\n"
                "Do not claim broad CellProfiler replacement before L4.\n"
                "Not allowed before L4:\n"
                "> MorphoJet replaces CellProfiler.\n",
                encoding="utf-8",
            )

            failures = validate_claim_language.validate_paths([path])

        self.assertEqual([], failures)

    def test_rejects_unguarded_production_ready_claim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "README.md"
            path.write_text("MorphoJet is production-ready for labs.\n", encoding="utf-8")

            failures = validate_claim_language.validate_paths([path])

        self.assertEqual(1, len(failures))
        self.assertIn("unsupported production/replacement claim", failures[0])

    def test_rejects_unguarded_cellprofiler_replacement_claim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "README.md"
            path.write_text("MorphoJet replaces CellProfiler.\n", encoding="utf-8")

            failures = validate_claim_language.validate_paths([path])

        self.assertEqual(1, len(failures))
        self.assertIn("MorphoJet replaces CellProfiler", failures[0])

    def test_accepts_guarded_chinese_claim_language(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "README.zh-CN.md"
            path.write_text(
                "MorphoJet 目前不是 CellProfiler 的替代品。\n"
                "在外部 L4 和稳定 release 通过之前，不能宣称生产级。\n",
                encoding="utf-8",
            )

            failures = validate_claim_language.validate_paths([path])

        self.assertEqual([], failures)

    def test_accepts_guarded_chinese_substitution_heading(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "MORPHOJET-FEASIBILITY.md"
            path.write_text("## 为什么不替代 CellProfiler：尊重 oracle\n", encoding="utf-8")

            failures = validate_claim_language.validate_paths([path])

        self.assertEqual([], failures)

    def test_rejects_unguarded_chinese_production_claim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "README.zh-CN.md"
            path.write_text("MorphoJet 已达到生产级，可直接用于实验室。\n", encoding="utf-8")

            failures = validate_claim_language.validate_paths([path])

        self.assertEqual(1, len(failures))
        self.assertIn("unsupported production/replacement claim", failures[0])

    def test_rejects_unguarded_chinese_cellprofiler_replacement_claim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "README.zh-CN.md"
            path.write_text("MorphoJet 可以替代 CellProfiler。\n", encoding="utf-8")

            failures = validate_claim_language.validate_paths([path])

        self.assertEqual(1, len(failures))
        self.assertIn("MorphoJet 可以替代 CellProfiler", failures[0])

    def test_directory_scan_is_recursive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nested = root / "nested" / "README.md"
            nested.parent.mkdir(parents=True)
            nested.write_text("MorphoJet is production-ready for labs.\n", encoding="utf-8")

            failures = validate_claim_language.validate_paths([root])

        self.assertEqual(1, len(failures))
        self.assertIn("nested/README.md", failures[0])


if __name__ == "__main__":
    unittest.main()
