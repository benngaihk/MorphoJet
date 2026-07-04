#!/usr/bin/env python3
"""Unit tests for GitHub release verification helpers."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmark"))

import verify_github_release  # noqa: E402


class VerifyGithubReleaseTest(unittest.TestCase):
    FULL_COMMIT = "a" * 40
    DOCTOR_COMMIT = "a" * 12

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
        self.assertEqual(
            [],
            verify_github_release.release_type_issues(
                "v0.1.0+build.7", {"isPrerelease": False}, expect_prerelease=False, expect_stable=True
            ),
        )
        issues = verify_github_release.release_type_issues(
            "v0.1.0-rc.1", {"isPrerelease": True}, expect_prerelease=False, expect_stable=True
        )
        self.assertIn("stable release is marked prerelease", issues)
        self.assertIn("stable release tag must be a non-prerelease semver tag like v0.1.0", issues)

    def test_stable_expectation_rejects_non_rc_prerelease_tags(self) -> None:
        for tag in ["v0.1.0-beta.1", "v0.1", "release-0.1.0"]:
            with self.subTest(tag=tag):
                self.assertIn(
                    "stable release tag must be a non-prerelease semver tag like v0.1.0",
                    verify_github_release.release_type_issues(
                        tag,
                        {"isPrerelease": False},
                        expect_prerelease=False,
                        expect_stable=True,
                    ),
                )

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

    def test_release_asset_metadata_keeps_auditable_fields_sorted_by_name(self) -> None:
        self.assertEqual(
            [
                {
                    "name": "a.tar.gz",
                    "url": "https://example.test/a",
                    "size": 12,
                    "content_type": "application/gzip",
                },
                {
                    "name": "b.tar.gz",
                    "url": "https://example.test/b",
                    "size": 34,
                    "content_type": "application/gzip",
                },
            ],
            verify_github_release.release_asset_metadata(
                {
                    "assets": [
                        {
                            "name": "b.tar.gz",
                            "url": "https://example.test/b",
                            "size": 34,
                            "contentType": "application/gzip",
                        },
                        {
                            "name": "a.tar.gz",
                            "url": "https://example.test/a",
                            "size": 12,
                            "contentType": "application/gzip",
                        },
                    ]
                }
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

    def valid_report(self, root: Path) -> Path:
        out_dir = root / "release"
        out_dir.mkdir()
        expected_assets = sorted(verify_github_release.expected_asset_names("v0.1.0"))
        archive_summaries = []
        for archive_name in [name for name in expected_assets if name.endswith(".tar.gz")]:
            archive = out_dir / archive_name
            archive.write_text(f"{archive_name}\n", encoding="utf-8")
            digest = verify_github_release.sha256(archive)
            (out_dir / f"{archive_name}.sha256").write_text(f"{digest}  {archive_name}\n", encoding="utf-8")
            archive_summaries.append(
                {
                    "archive": archive.name,
                    "sha256": digest,
                    "checksum_match": True,
                    "doctor": {"status": "PASS", "issues": [], "expected_commit": self.DOCTOR_COMMIT}
                    if "linux-x86_64" in archive.name
                    else None,
                }
            )
        report = {
            "schema_version": 1,
            "verifier": "benchmark/verify_github_release.py",
            "generated_at_utc": "2026-07-03T00:00:00+00:00",
            "status": "PASS",
            "tag": "v0.1.0",
            "repo": "benngaihk/MorphoJet",
            "url": "https://github.com/benngaihk/MorphoJet/releases/tag/v0.1.0",
            "out_dir": str(out_dir),
            "is_prerelease": False,
            "expected_release_kind": "stable",
            "expected_commit": self.FULL_COMMIT,
            "expected_doctor_commit": self.DOCTOR_COMMIT,
            "asset_count": len(expected_assets),
            "assets": {
                "expected": expected_assets,
                "release_metadata": expected_assets,
                "downloaded": expected_assets,
                "expected_count": len(expected_assets),
                "release_metadata_count": len(expected_assets),
                "downloaded_count": len(expected_assets),
            },
            "asset_metadata": [
                {
                    "name": name,
                    "url": f"https://github.com/benngaihk/MorphoJet/releases/download/v0.1.0/{name}",
                    "size": 100 + index,
                    "content_type": "application/gzip" if name.endswith(".tar.gz") else "text/plain",
                }
                for index, name in enumerate(expected_assets)
            ],
            "archives": archive_summaries,
            "issues": [],
        }
        path = root / "github-release-verification.json"
        path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        return path

    def test_saved_release_report_passes_with_file_recheck(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = self.valid_report(Path(tmp))

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                status = verify_github_release.verify_saved_github_release_report(
                    report,
                    require_report_pass=True,
                    require_stable_report=True,
                    verify_files=True,
                )

        self.assertEqual(0, status)

    def test_saved_release_report_rejects_non_stable_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = self.valid_report(Path(tmp))
            payload = json.loads(report.read_text(encoding="utf-8"))
            payload["expected_release_kind"] = "prerelease"
            report.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                status = verify_github_release.verify_saved_github_release_report(
                    report,
                    require_stable_report=True,
                )

        self.assertEqual(1, status)

    def test_saved_release_report_rejects_bad_report_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = self.valid_report(Path(tmp))
            payload = json.loads(report.read_text(encoding="utf-8"))
            payload["schema_version"] = 2
            payload["verifier"] = "other.py"
            payload["generated_at_utc"] = "not-a-date"

            failures = verify_github_release.validate_verification_report_payload(payload)

        self.assertIn("schema_version=2", failures)
        self.assertIn("verifier=other.py", failures)
        self.assertIn("generated_at_utc is invalid: not-a-date", failures)

    def test_saved_release_report_rejects_unbound_commit_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = self.valid_report(Path(tmp))
            payload = json.loads(report.read_text(encoding="utf-8"))
            payload["expected_doctor_commit"] = "b" * 12
            payload["archives"][0]["doctor"]["expected_commit"] = "c" * 12

            failures = verify_github_release.validate_verification_report_payload(payload)

        self.assertIn("expected_doctor_commit must match the first 12 characters of expected_commit", failures)
        self.assertIn(
            "archive doctor expected_commit does not match expected_doctor_commit: "
            "morphojet-v0.1.0-linux-x86_64.tar.gz",
            failures,
        )

    def test_saved_release_report_rejects_short_expected_commit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = self.valid_report(Path(tmp))
            payload = json.loads(report.read_text(encoding="utf-8"))
            payload["expected_commit"] = "abc123"

            failures = verify_github_release.validate_verification_report_payload(payload)

        self.assertIn("expected_commit must be a full 40-character lowercase git commit", failures)

    def test_saved_release_report_rejects_failed_doctor_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = self.valid_report(Path(tmp))
            payload = json.loads(report.read_text(encoding="utf-8"))
            payload["archives"][0]["doctor"]["status"] = "FAIL"
            payload["archives"][0]["doctor"]["issues"] = ["doctor output missing morphojet.commit="]

            failures = verify_github_release.validate_verification_report_payload(payload)

        self.assertIn(
            "archive doctor status is not PASS: morphojet-v0.1.0-linux-x86_64.tar.gz status=FAIL",
            failures,
        )
        self.assertIn("archive doctor has issues: morphojet-v0.1.0-linux-x86_64.tar.gz", failures)

    def test_saved_release_report_rejects_incomplete_pass_asset_sets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = self.valid_report(Path(tmp))
            payload = json.loads(report.read_text(encoding="utf-8"))
            payload["assets"]["downloaded"] = payload["assets"]["downloaded"][:-1]
            payload["assets"]["downloaded_count"] = len(payload["assets"]["downloaded"])
            payload["asset_count"] = len(payload["assets"]["downloaded"])
            payload["archives"] = payload["archives"][:-1]

            failures = verify_github_release.validate_verification_report_payload(payload)

        self.assertIn("passing github release verification report assets.downloaded must match assets.expected", failures)
        self.assertIn("archives must match downloaded .tar.gz assets", failures)

    def test_saved_release_report_can_require_expected_tag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = self.valid_report(Path(tmp))

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                matching_status = verify_github_release.verify_saved_github_release_report(
                    report,
                    expect_tag="v0.1.0",
                )
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                mismatched_status = verify_github_release.verify_saved_github_release_report(
                    report,
                    expect_tag="v0.2.0",
                )

        self.assertEqual(0, matching_status)
        self.assertEqual(1, mismatched_status)

    def test_saved_release_report_can_verify_git_commit_and_tag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = self.valid_report(Path(tmp))

            with patch.object(verify_github_release, "git_commit", return_value=self.FULL_COMMIT):
                with redirect_stdout(StringIO()) as stdout, redirect_stderr(StringIO()):
                    status = verify_github_release.verify_saved_github_release_report(
                        report,
                        expect_tag="v0.1.0",
                        verify_git_commit=True,
                    )

        self.assertEqual(0, status)
        self.assertIn("verified_git_commit=True", stdout.getvalue())

    def test_saved_release_report_rejects_tag_commit_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = self.valid_report(Path(tmp))

            with patch.object(verify_github_release, "git_commit", side_effect=[self.FULL_COMMIT, "b" * 40]):
                with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                    status = verify_github_release.verify_saved_github_release_report(
                        report,
                        expect_tag="v0.1.0",
                        verify_git_commit=True,
                    )

        self.assertEqual(1, status)

    def test_saved_release_report_can_require_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = self.valid_report(Path(tmp))
            payload = json.loads(report.read_text(encoding="utf-8"))
            payload["status"] = "FAIL"
            payload["issues"] = ["release is draft"]
            report.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                status = verify_github_release.verify_saved_github_release_report(
                    report,
                    require_report_pass=True,
                )

        self.assertEqual(1, status)

    def test_saved_release_report_rejects_bad_asset_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = self.valid_report(Path(tmp))
            payload = json.loads(report.read_text(encoding="utf-8"))
            first = payload["asset_metadata"][0]
            first["url"] = ""
            first["size"] = 0
            first["content_type"] = None
            payload["asset_metadata"].append(dict(payload["asset_metadata"][0]))
            report.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            failures = verify_github_release.validate_verification_report_payload(payload)

        self.assertIn(f"asset_metadata.url must be a non-empty string: {first['name']}", failures)
        self.assertIn(f"asset_metadata.size must be a positive integer: {first['name']}", failures)
        self.assertIn(f"asset_metadata.content_type must be a non-empty string: {first['name']}", failures)
        self.assertIn(f"asset_metadata name is duplicated: {first['name']}", failures)

    def test_saved_release_report_recomputes_asset_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = self.valid_report(root)
            (root / "release" / "extra.txt").write_text("extra\n", encoding="utf-8")

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                status = verify_github_release.verify_saved_github_release_report(report, verify_files=True)

        self.assertEqual(1, status)

    def test_saved_release_report_recomputes_archive_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = self.valid_report(root)
            payload = json.loads(report.read_text(encoding="utf-8"))
            archive = root / "release" / payload["archives"][0]["archive"]
            archive.write_bytes(b"tampered\n")

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                status = verify_github_release.verify_saved_github_release_report(report, verify_files=True)

        self.assertEqual(1, status)


if __name__ == "__main__":
    unittest.main()
