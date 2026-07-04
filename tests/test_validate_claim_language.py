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


if __name__ == "__main__":
    unittest.main()
