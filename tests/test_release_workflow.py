#!/usr/bin/env python3
"""Unit tests for the GitHub release workflow."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/release.yml"


class ReleaseWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow_text = WORKFLOW.read_text(encoding="utf-8")

    def test_release_uses_node24_actions_and_cli_publishing(self) -> None:
        self.assertIn("actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0", self.workflow_text)
        self.assertNotIn("softprops/action-gh-release", self.workflow_text)
        self.assertIn("GH_TOKEN: ${{ github.token }}", self.workflow_text)
        self.assertIn(
            'gh release view "${tag}" --repo "${GITHUB_REPOSITORY}"',
            self.workflow_text,
        )
        self.assertIn(
            'gh release upload "${tag}" "${files[@]}" --clobber --repo "${GITHUB_REPOSITORY}"',
            self.workflow_text,
        )
        self.assertIn(
            'gh release create "${tag}" "${files[@]}" --verify-tag --generate-notes --repo "${GITHUB_REPOSITORY}"',
            self.workflow_text,
        )

    def test_release_runs_locked_rust_audit(self) -> None:
        self.assertIn("cargo install cargo-audit --version 0.22.2 --locked", self.workflow_text)
        self.assertIn("cargo audit --file Cargo.lock", self.workflow_text)


if __name__ == "__main__":
    unittest.main()
