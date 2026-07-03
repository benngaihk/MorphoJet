#!/usr/bin/env python3
"""Unit tests for release gate helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmark"))

import release_gate  # noqa: E402


class ReleaseGateTest(unittest.TestCase):
    def test_doc_path_allowlist(self) -> None:
        self.assertTrue(release_gate.is_doc_path("README.md"))
        self.assertTrue(release_gate.is_doc_path("docs/PRODUCTION_READINESS.md"))
        self.assertFalse(release_gate.is_doc_path("benchmark/release_gate.py"))
        self.assertFalse(release_gate.is_doc_path("crates/morphojet/src/main.rs"))


if __name__ == "__main__":
    unittest.main()
