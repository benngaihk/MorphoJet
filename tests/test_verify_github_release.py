#!/usr/bin/env python3
"""Unit tests for GitHub release verification helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmark"))

import verify_github_release  # noqa: E402


class VerifyGithubReleaseTest(unittest.TestCase):
    def test_prerelease_expectation(self) -> None:
        self.assertEqual(
            [],
            verify_github_release.release_type_issues(
                "v0.1.0-rc.1", {"isPrerelease": True}, expect_prerelease=True, expect_stable=False
            ),
        )
        self.assertIn(
            "release is not marked prerelease",
            verify_github_release.release_type_issues(
                "v0.1.0-rc.1", {"isPrerelease": False}, expect_prerelease=True, expect_stable=False
            ),
        )

    def test_stable_expectation(self) -> None:
        self.assertEqual(
            [],
            verify_github_release.release_type_issues(
                "v0.1.0", {"isPrerelease": False}, expect_prerelease=False, expect_stable=True
            ),
        )
        issues = verify_github_release.release_type_issues(
            "v0.1.0-rc.1", {"isPrerelease": True}, expect_prerelease=False, expect_stable=True
        )
        self.assertIn("stable release is marked prerelease", issues)
        self.assertIn("stable release tag must not contain -rc", issues)


if __name__ == "__main__":
    unittest.main()
