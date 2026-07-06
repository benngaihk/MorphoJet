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
                    "github_id": "asset-a",
                    "api_url": "https://api.github.com/repos/benngaihk/MorphoJet/releases/assets/1",
                    "url": "https://example.test/a",
                    "size": 12,
                    "content_type": "application/gzip",
                    "digest": "sha256:" + "a" * 64,
                    "state": "uploaded",
                    "created_at": "2026-07-03T00:00:00Z",
                    "updated_at": "2026-07-03T00:00:01Z",
                },
                {
                    "name": "b.tar.gz",
                    "github_id": "asset-b",
                    "api_url": "https://api.github.com/repos/benngaihk/MorphoJet/releases/assets/2",
                    "url": "https://example.test/b",
                    "size": 34,
                    "content_type": "application/gzip",
                    "digest": "sha256:" + "b" * 64,
                    "state": "uploaded",
                    "created_at": "2026-07-03T00:00:00Z",
                    "updated_at": "2026-07-03T00:00:01Z",
                },
            ],
            verify_github_release.release_asset_metadata(
                {
                    "assets": [
                        {
                            "name": "b.tar.gz",
                            "id": "asset-b",
                            "apiUrl": "https://api.github.com/repos/benngaihk/MorphoJet/releases/assets/2",
                            "url": "https://example.test/b",
                            "size": 34,
                            "contentType": "application/gzip",
                            "digest": "sha256:" + "b" * 64,
                            "state": "uploaded",
                            "createdAt": "2026-07-03T00:00:00Z",
                            "updatedAt": "2026-07-03T00:00:01Z",
                        },
                        {
                            "name": "a.tar.gz",
                            "id": "asset-a",
                            "apiUrl": "https://api.github.com/repos/benngaihk/MorphoJet/releases/assets/1",
                            "url": "https://example.test/a",
                            "size": 12,
                            "contentType": "application/gzip",
                            "digest": "sha256:" + "a" * 64,
                            "state": "uploaded",
                            "createdAt": "2026-07-03T00:00:00Z",
                            "updatedAt": "2026-07-03T00:00:01Z",
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

    def test_release_output_safety_accepts_existing_expected_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            for name in verify_github_release.expected_asset_names("v0.1.0"):
                (out_dir / name).write_text("asset\n", encoding="utf-8")

            self.assertEqual([], verify_github_release.release_output_safety_issues("v0.1.0", out_dir))

    def test_release_output_safety_rejects_mixed_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            (out_dir / "notes.txt").write_text("not release asset\n", encoding="utf-8")
            (out_dir / "nested").mkdir()

            issues = verify_github_release.release_output_safety_issues("v0.1.0", out_dir)

        self.assertIn("--out-dir contains files not owned by this release download: nested,notes.txt", issues)

    def test_release_output_safety_rejects_json_out_inside_download_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)

            issues = verify_github_release.release_output_safety_issues(
                "v0.1.0",
                out_dir,
                json_out=out_dir / "verification.json",
            )

        self.assertIn("--json-out must not be inside --out-dir", issues)

    def test_release_output_safety_rejects_json_out_over_release_asset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            asset_name = "morphojet-v0.1.0-linux-x86_64.tar.gz"

            issues = verify_github_release.release_output_safety_issues(
                "v0.1.0",
                out_dir,
                json_out=out_dir / asset_name,
            )

        self.assertIn(f"--json-out must not overwrite release asset: {asset_name}", issues)
        self.assertIn("--json-out must not be inside --out-dir", issues)

    def test_validate_release_output_paths_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            (out_dir / "notes.txt").write_text("not release asset\n", encoding="utf-8")

            with self.assertRaises(SystemExit) as context:
                verify_github_release.validate_release_output_paths("v0.1.0", out_dir)

        self.assertIn("--out-dir contains files not owned by this release download", str(context.exception))

    def test_asset_file_metadata_issues_accepts_matching_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            asset = out_dir / "asset.tar.gz"
            asset.write_text("asset\n", encoding="utf-8")
            records = [
                {
                    "name": asset.name,
                    "size": asset.stat().st_size,
                    "digest": f"sha256:{verify_github_release.sha256(asset)}",
                }
            ]

            self.assertEqual([], verify_github_release.asset_file_metadata_issues(records, out_dir, [asset.name]))

    def test_asset_file_metadata_issues_rejects_mismatched_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            asset = out_dir / "asset.tar.gz"
            asset.write_text("asset\n", encoding="utf-8")
            records = [{"name": asset.name, "size": asset.stat().st_size + 1, "digest": "sha256:" + "0" * 64}]

            issues = verify_github_release.asset_file_metadata_issues(records, out_dir, [asset.name])

        self.assertIn("asset metadata size changed: asset.tar.gz", issues)
        self.assertIn("asset metadata digest changed: asset.tar.gz", issues)

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
            "argv": [
                "benchmark/verify_github_release.py",
                "v0.1.0",
                "--repo",
                "benngaihk/MorphoJet",
                "--out-dir",
                str(out_dir),
                "--expect-stable",
                "--json-out",
                str(root / "github-release-verification.json"),
            ],
            "tag": "v0.1.0",
            "repo": "benngaihk/MorphoJet",
            "url": "https://github.com/benngaihk/MorphoJet/releases/tag/v0.1.0",
            "release_id": "RE_release",
            "release_database_id": 123,
            "release_api_url": "https://api.github.com/repos/benngaihk/MorphoJet/releases/123",
            "release_created_at": "2026-07-03T00:00:00Z",
            "release_published_at": "2026-07-03T00:00:01Z",
            "release_author_login": "github-actions[bot]",
            "out_dir": str(out_dir),
            "is_draft": False,
            "is_immutable": False,
            "is_prerelease": False,
            "target_commitish": "main",
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
                    "github_id": f"asset-{index}",
                    "api_url": f"https://api.github.com/repos/benngaihk/MorphoJet/releases/assets/{index}",
                    "url": f"https://github.com/benngaihk/MorphoJet/releases/download/v0.1.0/{name}",
                    "size": (out_dir / name).stat().st_size,
                    "content_type": "application/gzip" if name.endswith(".tar.gz") else "text/plain",
                    "digest": f"sha256:{verify_github_release.sha256(out_dir / name)}",
                    "state": "uploaded",
                    "created_at": "2026-07-03T00:00:00Z",
                    "updated_at": "2026-07-03T00:00:01Z",
                }
                for index, name in enumerate(expected_assets, start=1)
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
            payload["is_draft"] = "no"
            payload["argv"] = "not-a-list"

            failures = verify_github_release.validate_verification_report_payload(payload)

        self.assertIn("schema_version=2", failures)
        self.assertIn("verifier=other.py", failures)
        self.assertIn("generated_at_utc is invalid: not-a-date", failures)
        self.assertIn("is_draft must be a boolean", failures)
        self.assertIn("argv must be a non-empty string list", failures)

    def test_saved_release_report_rejects_argv_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = self.valid_report(Path(tmp))
            payload = json.loads(report.read_text(encoding="utf-8"))
            payload["argv"] = [
                "benchmark/verify_github_release.py",
                "v0.2.0",
                "--repo",
                "other/repo",
                "--out-dir",
                "--expect-prerelease",
                "--expect-stable",
                "--expect-stable",
                "--json-out",
                str(report),
                "--verify-report",
                str(report),
            ]

            failures = verify_github_release.validate_verification_report_payload(payload)

        self.assertIn("argv must include tag exactly once: v0.1.0", failures)
        self.assertIn("repo must match argv --repo other/repo", failures)
        self.assertIn("argv --out-dir must include a value", failures)
        self.assertIn("argv has duplicate --expect-stable", failures)
        self.assertIn("argv must not include --expect-prerelease unless expected_release_kind is prerelease", failures)
        self.assertIn("argv must not include --verify-report for a generated verifier report", failures)

    def test_saved_release_report_rejects_json_out_path_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = self.valid_report(Path(tmp))
            payload = json.loads(report.read_text(encoding="utf-8"))
            payload["argv"][payload["argv"].index("--json-out") + 1] = str(Path(tmp) / "other-release-verification.json")
            report.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
                status = verify_github_release.verify_saved_github_release_report(report)

        self.assertEqual(1, status)
        self.assertIn("argv --json-out must match saved verifier report path", stderr.getvalue())

    def test_saved_release_report_rejects_bad_release_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = self.valid_report(Path(tmp))
            payload = json.loads(report.read_text(encoding="utf-8"))
            payload["release_id"] = ""
            payload["release_database_id"] = 0
            payload["release_api_url"] = "https://api.github.com/repos/other/repo/releases/123"
            payload["release_created_at"] = "2026-07-03T00:00:02Z"
            payload["release_published_at"] = "2026-07-03T00:00:01Z"
            payload["release_author_login"] = ""
            payload["is_immutable"] = "false"
            payload["target_commitish"] = ""

            failures = verify_github_release.validate_verification_report_payload(payload)

        self.assertIn("release_id must be a non-empty string", failures)
        self.assertIn("release_database_id must be a positive integer", failures)
        self.assertIn(
            "release_api_url does not match repo: https://api.github.com/repos/other/repo/releases/123",
            failures,
        )
        self.assertIn("release_published_at must not be earlier than release_created_at", failures)
        self.assertIn("release_author_login must be a non-empty string", failures)
        self.assertIn("is_immutable must be a boolean", failures)
        self.assertIn("target_commitish must be a non-empty string", failures)

    def test_live_release_metadata_issues_match_saved_report_identity_checks(self) -> None:
        issues = verify_github_release.live_release_metadata_issues(
            "benngaihk/MorphoJet",
            "v0.1.0",
            {
                "tagName": "v0.1.0",
                "url": "https://github.com/other/repo/releases/tag/v0.1.0",
                "id": "",
                "databaseId": 0,
                "apiUrl": "https://api.github.com/repos/other/repo/releases/123",
                "createdAt": "2026-07-03T00:00:02Z",
                "publishedAt": "2026-07-03T00:00:01Z",
                "author": {},
                "isImmutable": "false",
                "targetCommitish": "",
            },
        )

        self.assertIn(
            "url does not match repo/tag: "
            "https://github.com/other/repo/releases/tag/v0.1.0 != "
            "https://github.com/benngaihk/MorphoJet/releases/tag/v0.1.0",
            issues,
        )
        self.assertIn("release_id must be a non-empty string", issues)
        self.assertIn("release_database_id must be a positive integer", issues)
        self.assertIn(
            "release_api_url does not match repo: https://api.github.com/repos/other/repo/releases/123",
            issues,
        )
        self.assertIn("release_published_at must not be earlier than release_created_at", issues)
        self.assertIn("release_author_login must be a non-empty string", issues)
        self.assertIn("is_immutable must be a boolean", issues)
        self.assertIn("target_commitish must be a non-empty string", issues)

    def test_saved_release_report_rejects_passing_draft_release(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = self.valid_report(Path(tmp))
            payload = json.loads(report.read_text(encoding="utf-8"))
            payload["is_draft"] = True

            failures = verify_github_release.validate_verification_report_payload(payload)

        self.assertIn("passing github release verification report must have is_draft=false", failures)

    def test_saved_release_report_rejects_url_not_bound_to_repo_and_tag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = self.valid_report(Path(tmp))
            payload = json.loads(report.read_text(encoding="utf-8"))
            payload["url"] = "https://github.com/other/repo/releases/tag/v0.1.0"

            failures = verify_github_release.validate_verification_report_payload(payload)

        self.assertIn(
            "url does not match repo/tag: "
            "https://github.com/other/repo/releases/tag/v0.1.0 != "
            "https://github.com/benngaihk/MorphoJet/releases/tag/v0.1.0",
            failures,
        )

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

    def test_saved_release_report_rejects_expected_assets_not_bound_to_tag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = self.valid_report(Path(tmp))
            payload = json.loads(report.read_text(encoding="utf-8"))
            omitted = "morphojet-v0.1.0-linux-x86_64.tar.gz.sha256"
            payload["assets"]["expected"].remove(omitted)
            payload["assets"]["release_metadata"].remove(omitted)
            payload["assets"]["downloaded"].remove(omitted)
            payload["assets"]["expected_count"] -= 1
            payload["assets"]["release_metadata_count"] -= 1
            payload["assets"]["downloaded_count"] -= 1
            payload["asset_count"] -= 1
            payload["asset_metadata"] = [
                record for record in payload["asset_metadata"] if record["name"] != omitted
            ]

            failures = verify_github_release.validate_verification_report_payload(payload)

        self.assertIn("assets.expected does not match required release assets for tag", failures)

    def test_saved_release_report_rejects_archive_digest_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = self.valid_report(Path(tmp))
            payload = json.loads(report.read_text(encoding="utf-8"))
            archive = payload["archives"][0]
            metadata = next(record for record in payload["asset_metadata"] if record["name"] == archive["archive"])
            metadata["digest"] = "sha256:" + "0" * 64

            failures = verify_github_release.validate_verification_report_payload(payload)

        self.assertIn(f"archive sha256 does not match asset metadata digest: {archive['archive']}", failures)

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
            first["github_id"] = ""
            first["api_url"] = "https://api.github.com/repos/other/repo/releases/assets/1"
            first["url"] = ""
            first["size"] = 0
            first["content_type"] = None
            first["digest"] = "sha256:not-a-digest"
            first["state"] = "starter"
            first["created_at"] = "not-a-date"
            first["updated_at"] = "2026-07-02T00:00:00"
            payload["asset_metadata"].append(dict(payload["asset_metadata"][0]))
            report.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            failures = verify_github_release.validate_verification_report_payload(payload)

        self.assertIn(f"asset_metadata.github_id must be a non-empty string: {first['name']}", failures)
        self.assertIn(f"asset_metadata.api_url does not match repo for {first['name']}: {first['api_url']}", failures)
        self.assertIn(f"asset_metadata.url must be a non-empty string: {first['name']}", failures)
        self.assertIn(f"asset_metadata.size must be a positive integer: {first['name']}", failures)
        self.assertIn(f"asset_metadata.content_type must be a non-empty string: {first['name']}", failures)
        self.assertIn(f"asset_metadata.digest must be sha256:<64 lowercase hex>: {first['name']}", failures)
        self.assertIn(f"asset_metadata.state must be uploaded: {first['name']}", failures)
        self.assertIn(f"asset_metadata.created_at is invalid: {first['name']}", failures)
        self.assertIn(f"asset_metadata.updated_at must include timezone: {first['name']}", failures)
        self.assertIn(f"asset_metadata name is duplicated: {first['name']}", failures)

    def test_saved_release_report_rejects_duplicate_asset_identity_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = self.valid_report(Path(tmp))
            payload = json.loads(report.read_text(encoding="utf-8"))
            first = payload["asset_metadata"][0]
            second = payload["asset_metadata"][1]
            second["github_id"] = first["github_id"]
            second["api_url"] = first["api_url"]

            failures = verify_github_release.validate_verification_report_payload(payload)

        self.assertIn(f"asset_metadata github_id is duplicated: {first['github_id']}", failures)
        self.assertIn(f"asset_metadata api_url is duplicated: {first['api_url']}", failures)

    def test_saved_release_report_rejects_asset_url_not_bound_to_repo_tag_and_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = self.valid_report(Path(tmp))
            payload = json.loads(report.read_text(encoding="utf-8"))
            first = payload["asset_metadata"][0]
            first["url"] = "https://github.com/benngaihk/MorphoJet/releases/download/v0.2.0/other.tar.gz"

            failures = verify_github_release.validate_verification_report_payload(payload)

        self.assertIn(
            f"asset_metadata.url does not match repo/tag/name for {first['name']}: {first['url']}",
            failures,
        )

    def test_saved_release_report_rejects_asset_timestamp_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = self.valid_report(Path(tmp))
            payload = json.loads(report.read_text(encoding="utf-8"))
            first = payload["asset_metadata"][0]
            first["created_at"] = "2026-07-03T00:00:02Z"
            first["updated_at"] = "2026-07-03T00:00:01Z"

            failures = verify_github_release.validate_verification_report_payload(payload)

        self.assertIn(f"asset_metadata.updated_at must not be earlier than created_at: {first['name']}", failures)

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

    def test_saved_release_report_recomputes_asset_metadata_digest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = self.valid_report(root)
            payload = json.loads(report.read_text(encoding="utf-8"))
            checksum_name = next(name for name in payload["assets"]["downloaded"] if name.endswith(".sha256"))
            checksum = root / "release" / checksum_name
            checksum.write_text(checksum.read_text(encoding="utf-8").rstrip() + "  \n", encoding="utf-8")

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
                status = verify_github_release.verify_saved_github_release_report(report, verify_files=True)

        self.assertEqual(1, status)
        self.assertIn(f"asset metadata digest changed: {checksum_name}", stderr.getvalue())

    def test_saved_release_report_recomputes_asset_metadata_size(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = self.valid_report(root)
            payload = json.loads(report.read_text(encoding="utf-8"))
            first = payload["asset_metadata"][0]
            first["size"] += 1
            report.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
                status = verify_github_release.verify_saved_github_release_report(report, verify_files=True)

        self.assertEqual(1, status)
        self.assertIn(f"asset metadata size changed: {first['name']}", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
