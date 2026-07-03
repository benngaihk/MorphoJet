#!/usr/bin/env python3
"""Unit tests for GitHub release verification helpers."""

from __future__ import annotations

import sys
import tempfile
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

    def test_release_identity_accepts_matching_tag_and_url(self) -> None:
        self.assertEqual(
            [],
            verify_github_release.release_identity_issues(
                "v0.1.0", {"tagName": "v0.1.0", "url": "https://github.com/benngaihk/MorphoJet/releases/v0.1.0"}
            ),
        )

    def test_release_identity_rejects_mismatched_tag_and_missing_url(self) -> None:
        issues = verify_github_release.release_identity_issues("v0.1.0", {"tagName": "v0.1.1", "url": ""})

        self.assertIn("release tagName mismatch: v0.1.1", issues)
        self.assertIn("release url must be a non-empty string", issues)

    def test_checksum_issues_accepts_matching_archive_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            checksum = Path(tmp) / "archive.tar.gz.sha256"
            checksum.write_text("a" * 64 + "  archive.tar.gz\n")

            self.assertEqual([], verify_github_release.checksum_issues(checksum, "archive.tar.gz"))

    def test_checksum_issues_rejects_invalid_digest_and_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            checksum = Path(tmp) / "archive.tar.gz.sha256"
            checksum.write_text("not-a-sha  other.tar.gz\n")

            issues = verify_github_release.checksum_issues(checksum, "archive.tar.gz")

        self.assertIn("invalid checksum digest for archive.tar.gz", issues)
        self.assertIn("checksum file target mismatch for archive.tar.gz: other.tar.gz", issues)

    def test_asset_issues_accepts_exact_expected_assets(self) -> None:
        expected = verify_github_release.expected_asset_names("v0.1.0")

        self.assertEqual([], verify_github_release.asset_issues(expected, expected, expected))

    def test_asset_issues_rejects_missing_and_extra_assets(self) -> None:
        expected = verify_github_release.expected_asset_names("v0.1.0")
        missing = next(iter(expected))
        release_assets = (expected - {missing}) | {"morphojet-v0.1.0-extra.tar.gz"}
        downloaded_assets = expected | {"notes.txt"}

        issues = verify_github_release.asset_issues(expected, release_assets, downloaded_assets)

        self.assertIn("release metadata missing assets: " + missing, issues)
        self.assertIn("release metadata has unexpected assets: morphojet-v0.1.0-extra.tar.gz", issues)
        self.assertIn("unexpected downloaded assets: notes.txt", issues)
        self.assertTrue(
            any(issue.startswith("release metadata/download asset mismatch:") for issue in issues),
            issues,
        )

    def test_release_asset_names_ignores_malformed_assets(self) -> None:
        self.assertEqual(
            {"asset.tar.gz"},
            verify_github_release.release_asset_names(
                {"assets": [{"name": "asset.tar.gz"}, {"name": None}, "not-an-object"]}
            ),
        )

    def test_asset_summary_sorts_assets_and_counts_each_source(self) -> None:
        summary = verify_github_release.asset_summary(
            {"b.tar.gz", "a.tar.gz"},
            {"b.tar.gz"},
            {"a.tar.gz", "c.tar.gz"},
        )

        self.assertEqual(["a.tar.gz", "b.tar.gz"], summary["expected"])
        self.assertEqual(["b.tar.gz"], summary["release_metadata"])
        self.assertEqual(["a.tar.gz", "c.tar.gz"], summary["downloaded"])
        self.assertEqual(2, summary["expected_count"])
        self.assertEqual(1, summary["release_metadata_count"])
        self.assertEqual(2, summary["downloaded_count"])

    def test_doctor_run_issues_accepts_verified_archive(self) -> None:
        self.assertEqual([], verify_github_release.doctor_run_issues([{"doctor": {"issues": []}}]))

    def test_doctor_run_issues_requires_verified_archive(self) -> None:
        self.assertEqual(
            ["no compatible release archive was doctor-verified on this machine"],
            verify_github_release.doctor_run_issues([{"doctor": None}]),
        )


if __name__ == "__main__":
    unittest.main()
