#!/usr/bin/env python3
"""Download and verify GitHub release assets for a MorphoJet tag."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import shutil
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from verify_release_archive import verify


VERIFIER = "benchmark/verify_github_release.py"
REQUIRED_PACKAGE_FILES = {"morphojet", "README.md", "LICENSE"}
STABLE_TAG_PATTERN = re.compile(r"^v\d+\.\d+\.\d+(?:\+\S+)?$")
FULL_COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")
SHORT_COMMIT_PATTERN = re.compile(r"[0-9a-f]{12}")
ASSET_DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")


def run(command: list[str]) -> str:
    completed = subprocess.run(command, text=True, capture_output=True, check=True)
    return completed.stdout


def git_tag_commit(tag: str) -> str:
    return run(["git", "rev-list", "-n", "1", tag]).strip()


def git_commit(rev: str) -> str:
    return run(["git", "rev-parse", f"{rev}^{{commit}}"]).strip()


def doctor_commit_for(full_commit: str) -> str:
    return full_commit[:12]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def checksum_value(path: Path) -> str:
    parts = path.read_text().split()
    if not parts:
        raise ValueError(f"empty checksum file: {path}")
    return parts[0]


def checksum_issues(path: Path, archive_name: str) -> list[str]:
    parts = path.read_text().split()
    if not parts:
        return [f"empty checksum file: {path.name}"]
    issues = []
    digest = parts[0]
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        issues.append(f"invalid checksum digest for {archive_name}")
    if len(parts) < 2:
        issues.append(f"checksum file missing archive name for {archive_name}")
    elif Path(parts[1]).name != archive_name:
        issues.append(f"checksum file target mismatch for {archive_name}: {parts[1]}")
    return issues


def archive_members(path: Path) -> set[str]:
    with tarfile.open(path, "r:gz") as handle:
        return {Path(name).name for name in handle.getnames()}


def release_json(repo: str, tag: str) -> dict:
    return json.loads(run(["gh", "release", "view", tag, "--repo", repo, "--json", "tagName,name,url,isDraft,isPrerelease,assets"]))


def download_release(repo: str, tag: str, out_dir: Path) -> None:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    run(["gh", "release", "download", tag, "--repo", repo, "--dir", str(out_dir)])


def verify_archive_shape(archive: Path) -> list[str]:
    members = archive_members(archive)
    missing = sorted(REQUIRED_PACKAGE_FILES - members)
    return [f"{archive.name} missing package files: {','.join(missing)}"] if missing else []


def compatible_archive(archive: Path) -> bool:
    system = platform.system().lower()
    machine = platform.machine()
    if system == "darwin":
        return f"macos-{machine}" in archive.name
    if system == "linux":
        return f"linux-{machine}" in archive.name
    return False


def release_type_issues(tag: str, release: dict, expect_prerelease: bool, expect_stable: bool) -> list[str]:
    issues = []
    if expect_prerelease and not release.get("isPrerelease"):
        issues.append("release is not marked prerelease")
    if expect_stable:
        if release.get("isPrerelease"):
            issues.append("stable release is marked prerelease")
        if not STABLE_TAG_PATTERN.fullmatch(tag):
            issues.append("stable release tag must be a non-prerelease semver tag like v0.1.0")
    return issues


def release_identity_issues(tag: str, release: dict) -> list[str]:
    issues = []
    if release.get("tagName") != tag:
        issues.append(f"release tagName mismatch: {release.get('tagName')}")
    if not isinstance(release.get("url"), str) or not release.get("url", "").strip():
        issues.append("release url must be a non-empty string")
    return issues


def expected_release_url(repo: str, tag: str) -> str:
    return f"https://github.com/{repo}/releases/tag/{tag}"


def expected_asset_url(repo: str, tag: str, name: str) -> str:
    return f"https://github.com/{repo}/releases/download/{tag}/{name}"


def expected_asset_api_url_prefix(repo: str) -> str:
    return f"https://api.github.com/repos/{repo}/releases/assets/"


def expected_asset_names(tag: str) -> set[str]:
    return {
        f"morphojet-{tag}-linux-x86_64.tar.gz",
        f"morphojet-{tag}-linux-x86_64.tar.gz.sha256",
        f"morphojet-{tag}-macos-arm64.tar.gz",
        f"morphojet-{tag}-macos-arm64.tar.gz.sha256",
    }


def release_asset_names(release: dict) -> set[str]:
    names = set()
    for asset in release.get("assets") or []:
        if isinstance(asset, dict) and isinstance(asset.get("name"), str):
            names.add(asset["name"])
    return names


def release_asset_metadata(release: dict) -> list[dict[str, Any]]:
    records = []
    for asset in release.get("assets") or []:
        if not isinstance(asset, dict) or not isinstance(asset.get("name"), str):
            continue
        records.append(
            {
                "name": asset["name"],
                "github_id": asset.get("id"),
                "api_url": asset.get("apiUrl"),
                "url": asset.get("url"),
                "size": asset.get("size"),
                "content_type": asset.get("contentType"),
                "digest": asset.get("digest"),
                "state": asset.get("state"),
                "created_at": asset.get("createdAt"),
                "updated_at": asset.get("updatedAt"),
            }
        )
    return sorted(records, key=lambda record: record["name"])


def asset_issues(expected_assets: set[str], release_assets: set[str], downloaded_assets: set[str]) -> list[str]:
    issues = []
    missing_release_assets = sorted(expected_assets - release_assets)
    if missing_release_assets:
        issues.append(f"release metadata missing assets: {','.join(missing_release_assets)}")
    unexpected_release_assets = sorted(release_assets - expected_assets)
    if unexpected_release_assets:
        issues.append(f"release metadata has unexpected assets: {','.join(unexpected_release_assets)}")
    missing_downloaded_assets = sorted(expected_assets - downloaded_assets)
    if missing_downloaded_assets:
        issues.append(f"missing assets: {','.join(missing_downloaded_assets)}")
    unexpected_downloaded_assets = sorted(downloaded_assets - expected_assets)
    if unexpected_downloaded_assets:
        issues.append(f"unexpected downloaded assets: {','.join(unexpected_downloaded_assets)}")
    metadata_download_delta = sorted(release_assets ^ downloaded_assets)
    if metadata_download_delta:
        issues.append(f"release metadata/download asset mismatch: {','.join(metadata_download_delta)}")
    return issues


def asset_summary(expected_assets: set[str], release_assets: set[str], downloaded_assets: set[str]) -> dict:
    return {
        "expected": sorted(expected_assets),
        "release_metadata": sorted(release_assets),
        "downloaded": sorted(downloaded_assets),
        "expected_count": len(expected_assets),
        "release_metadata_count": len(release_assets),
        "downloaded_count": len(downloaded_assets),
    }


def asset_metadata_issues(records: Any, release_asset_names_payload: Any, repo: Any = None, tag: Any = None) -> list[str]:
    failures = []
    if not isinstance(records, list) or not records:
        return ["asset_metadata must be a non-empty list"]
    if not isinstance(release_asset_names_payload, list) or not all(
        isinstance(item, str) for item in release_asset_names_payload
    ):
        release_asset_names_payload = []
    observed_names = []
    observed_github_ids = []
    observed_api_urls = []
    for record in records:
        if not isinstance(record, dict):
            failures.append("asset_metadata entries must be objects")
            continue
        name = record.get("name")
        if not isinstance(name, str) or not name.strip():
            failures.append("asset_metadata.name must be a non-empty string")
            continue
        observed_names.append(name)
        github_id = record.get("github_id")
        if not isinstance(github_id, str) or not github_id.strip():
            failures.append(f"asset_metadata.github_id must be a non-empty string: {name}")
        else:
            observed_github_ids.append(github_id)
        api_url = record.get("api_url")
        if not isinstance(api_url, str) or not api_url.strip():
            failures.append(f"asset_metadata.api_url must be a non-empty string: {name}")
        else:
            observed_api_urls.append(api_url)
            if isinstance(repo, str) and repo.strip():
                expected_prefix = expected_asset_api_url_prefix(repo)
                if not api_url.startswith(expected_prefix):
                    failures.append(f"asset_metadata.api_url does not match repo for {name}: {api_url}")
        url = record.get("url")
        if not isinstance(url, str) or not url.strip():
            failures.append(f"asset_metadata.url must be a non-empty string: {name}")
        elif isinstance(repo, str) and repo.strip() and isinstance(tag, str) and tag.strip():
            expected_url = expected_asset_url(repo, tag, name)
            if url != expected_url:
                failures.append(f"asset_metadata.url does not match repo/tag/name for {name}: {url}")
        size = record.get("size")
        if not isinstance(size, int) or size <= 0:
            failures.append(f"asset_metadata.size must be a positive integer: {name}")
        content_type = record.get("content_type")
        if not isinstance(content_type, str) or not content_type.strip():
            failures.append(f"asset_metadata.content_type must be a non-empty string: {name}")
        digest = record.get("digest")
        if not isinstance(digest, str) or not ASSET_DIGEST_PATTERN.fullmatch(digest):
            failures.append(f"asset_metadata.digest must be sha256:<64 lowercase hex>: {name}")
        if record.get("state") != "uploaded":
            failures.append(f"asset_metadata.state must be uploaded: {name}")
        created_at = record.get("created_at")
        updated_at = record.get("updated_at")
        parsed_created_at = parse_asset_timestamp(created_at, f"asset_metadata.created_at", name, failures)
        parsed_updated_at = parse_asset_timestamp(updated_at, f"asset_metadata.updated_at", name, failures)
        if parsed_created_at is not None and parsed_updated_at is not None and parsed_updated_at < parsed_created_at:
            failures.append(f"asset_metadata.updated_at must not be earlier than created_at: {name}")
    if observed_names != sorted(observed_names):
        failures.append("asset_metadata entries must be sorted by name")
    duplicated_names = sorted(name for name in set(observed_names) if observed_names.count(name) > 1)
    for name in duplicated_names:
        failures.append(f"asset_metadata name is duplicated: {name}")
    duplicated_github_ids = sorted(
        github_id for github_id in set(observed_github_ids) if observed_github_ids.count(github_id) > 1
    )
    for github_id in duplicated_github_ids:
        failures.append(f"asset_metadata github_id is duplicated: {github_id}")
    duplicated_api_urls = sorted(api_url for api_url in set(observed_api_urls) if observed_api_urls.count(api_url) > 1)
    for api_url in duplicated_api_urls:
        failures.append(f"asset_metadata api_url is duplicated: {api_url}")
    if sorted(observed_names) != release_asset_names_payload:
        failures.append("asset_metadata names do not match assets.release_metadata")
    return failures


def parse_asset_timestamp(value: Any, field: str, asset_name: str, failures: list[str]) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        failures.append(f"{field} must be a non-empty ISO timestamp: {asset_name}")
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        failures.append(f"{field} is invalid: {asset_name}")
        return None
    if parsed.tzinfo is None:
        failures.append(f"{field} must include timezone: {asset_name}")
        return None
    return parsed


def asset_file_metadata_issues(records: list[dict[str, Any]], out_dir: Path, asset_names: list[str]) -> list[str]:
    failures = []
    metadata_by_name = {record["name"]: record for record in records if isinstance(record.get("name"), str)}
    for asset_name in asset_names:
        metadata = metadata_by_name.get(asset_name)
        if metadata is None:
            failures.append(f"asset metadata missing for downloaded asset: {asset_name}")
            continue
        digest = metadata.get("digest")
        if not isinstance(digest, str) or not ASSET_DIGEST_PATTERN.fullmatch(digest):
            failures.append(f"asset_metadata.digest must be sha256:<64 lowercase hex>: {asset_name}")
            continue
        asset = out_dir / asset_name
        if not asset.is_file():
            failures.append(f"asset file missing for metadata digest: {asset_name}")
            continue
        size = metadata.get("size")
        if isinstance(size, int) and size > 0 and size != asset.stat().st_size:
            failures.append(f"asset metadata size changed: {asset_name}")
        if digest != f"sha256:{sha256(asset)}":
            failures.append(f"asset metadata digest changed: {asset_name}")
    return failures


def archive_metadata_digest_issues(records: list[dict[str, Any]], archive_summaries: list[dict[str, Any]]) -> list[str]:
    failures = []
    metadata_by_name = {record["name"]: record for record in records if isinstance(record.get("name"), str)}
    for archive in archive_summaries:
        archive_name = archive.get("archive")
        if not isinstance(archive_name, str):
            continue
        metadata = metadata_by_name.get(archive_name)
        if metadata is None:
            failures.append(f"asset metadata missing for archive: {archive_name}")
            continue
        digest = metadata.get("digest")
        sha = archive.get("sha256")
        if isinstance(digest, str) and ASSET_DIGEST_PATTERN.fullmatch(digest) and isinstance(sha, str):
            if digest != f"sha256:{sha}":
                failures.append(f"archive sha256 does not match asset metadata digest: {archive_name}")
    return failures


def release_report_url_issues(repo: Any, tag: Any, url: Any) -> list[str]:
    if not isinstance(repo, str) or not repo.strip() or not isinstance(tag, str) or not tag.strip():
        return []
    if not isinstance(url, str) or not url.strip():
        return []
    expected_url = expected_release_url(repo, tag)
    if url != expected_url:
        return [f"url does not match repo/tag: {url} != {expected_url}"]
    return []


def doctor_run_issues(archive_summaries: list[dict]) -> list[str]:
    if any(summary.get("doctor") is not None for summary in archive_summaries):
        return []
    return ["no compatible release archive was doctor-verified on this machine"]


def expected_commit_issues(expected_commit: Any, expected_doctor_commit: Any) -> list[str]:
    failures = []
    if not isinstance(expected_commit, str) or not expected_commit.strip():
        failures.append("expected_commit must be a non-empty string")
    elif not FULL_COMMIT_PATTERN.fullmatch(expected_commit):
        failures.append("expected_commit must be a full 40-character lowercase git commit")
    if not isinstance(expected_doctor_commit, str) or not expected_doctor_commit.strip():
        failures.append("expected_doctor_commit must be a non-empty string")
    elif not SHORT_COMMIT_PATTERN.fullmatch(expected_doctor_commit):
        failures.append("expected_doctor_commit must be a 12-character lowercase git commit prefix")
    if (
        isinstance(expected_commit, str)
        and FULL_COMMIT_PATTERN.fullmatch(expected_commit)
        and isinstance(expected_doctor_commit, str)
        and SHORT_COMMIT_PATTERN.fullmatch(expected_doctor_commit)
        and expected_doctor_commit != doctor_commit_for(expected_commit)
    ):
        failures.append("expected_doctor_commit must match the first 12 characters of expected_commit")
    return failures


def git_commit_verification_issues(expected_commit: Any, expect_tag: str | None) -> list[str]:
    failures = []
    if not isinstance(expected_commit, str) or not FULL_COMMIT_PATTERN.fullmatch(expected_commit):
        return failures
    try:
        resolved_commit = git_commit(expected_commit)
    except subprocess.CalledProcessError as exc:
        return [f"expected_commit is not reachable in this git checkout: {expected_commit} ({exc})"]
    if resolved_commit != expected_commit:
        failures.append(f"expected_commit resolves to a different commit: {resolved_commit}")
    if expect_tag is not None:
        try:
            tag_commit = git_commit(expect_tag)
        except subprocess.CalledProcessError as exc:
            failures.append(f"expected tag is not reachable in this git checkout: {expect_tag} ({exc})")
        else:
            if tag_commit != expected_commit:
                failures.append(f"expected tag commit does not match expected_commit: {expect_tag}={tag_commit}")
    return failures


def validate_verification_report_payload(
    payload: Any,
    require_report_pass: bool = False,
    require_stable_report: bool = False,
    expect_tag: str | None = None,
) -> list[str]:
    failures: list[str] = []
    if not isinstance(payload, dict):
        return ["github release verification report must be a JSON object"]
    if payload.get("schema_version") != 1:
        failures.append(f"schema_version={payload.get('schema_version')}")
    if payload.get("verifier") != VERIFIER:
        failures.append(f"verifier={payload.get('verifier')}")
    generated_at = payload.get("generated_at_utc")
    if not isinstance(generated_at, str) or not generated_at.strip():
        failures.append("generated_at_utc must be a non-empty string")
    else:
        try:
            parsed_generated_at = datetime.fromisoformat(generated_at)
            if parsed_generated_at.tzinfo is None:
                failures.append("generated_at_utc must include timezone")
        except ValueError:
            failures.append(f"generated_at_utc is invalid: {generated_at}")
    status = payload.get("status")
    if status not in {"PASS", "FAIL"}:
        failures.append(f"status={status}")
    if require_report_pass and status != "PASS":
        failures.append(f"github release verification report status is not PASS: {status}")
    tag = payload.get("tag")
    if not isinstance(tag, str) or not tag.strip():
        failures.append("tag must be a non-empty string")
    elif expect_tag is not None and tag != expect_tag:
        failures.append(f"github release verification report tag does not match expected tag: {tag} != {expect_tag}")
    repo = payload.get("repo")
    if not isinstance(repo, str) or not repo.strip():
        failures.append("repo must be a non-empty string")
    url = payload.get("url")
    if not isinstance(url, str) or not url.strip():
        failures.append("url must be a non-empty string")
    else:
        failures.extend(release_report_url_issues(repo, tag, url))
    if not isinstance(payload.get("is_prerelease"), bool):
        failures.append("is_prerelease must be a boolean")
    expected_kind = payload.get("expected_release_kind")
    if expected_kind not in {"stable", "prerelease", None}:
        failures.append(f"expected_release_kind={expected_kind}")
    if require_stable_report:
        if expected_kind != "stable":
            failures.append(f"expected_release_kind is not stable: {expected_kind}")
        if payload.get("is_prerelease") is not False:
            failures.append("stable report must have is_prerelease=false")
        if isinstance(tag, str) and not STABLE_TAG_PATTERN.fullmatch(tag):
            failures.append("stable report tag must be a non-prerelease semver tag like v0.1.0")
    expected_commit = payload.get("expected_commit")
    expected_doctor_commit = payload.get("expected_doctor_commit")
    failures.extend(expected_commit_issues(expected_commit, expected_doctor_commit))
    out_dir = payload.get("out_dir")
    if out_dir is not None and (not isinstance(out_dir, str) or not out_dir.strip()):
        failures.append("out_dir must be null or a non-empty string")
    asset_count = payload.get("asset_count")
    if not isinstance(asset_count, int) or asset_count < 0:
        failures.append(f"asset_count={asset_count}")

    assets = payload.get("assets")
    expected_assets_payload: Any = []
    release_metadata_assets: Any = []
    downloaded_assets_payload: Any = []
    if not isinstance(assets, dict):
        failures.append("assets must be an object")
    else:
        for key in ["expected", "release_metadata", "downloaded"]:
            value = assets.get(key)
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                failures.append(f"assets.{key} must be a string list")
            elif value != sorted(value):
                failures.append(f"assets.{key} must be sorted")
        expected_assets_payload = assets.get("expected")
        release_metadata_assets = assets.get("release_metadata")
        downloaded_assets_payload = assets.get("downloaded")
        for key, list_key in [
            ("expected_count", "expected"),
            ("release_metadata_count", "release_metadata"),
            ("downloaded_count", "downloaded"),
        ]:
            count = assets.get(key)
            values = assets.get(list_key)
            if not isinstance(count, int) or count < 0:
                failures.append(f"assets.{key}={count}")
            elif isinstance(values, list) and count != len(values):
                failures.append(f"assets.{key} does not match assets.{list_key}")
        if (
            status == "PASS"
            and isinstance(expected_assets_payload, list)
            and isinstance(release_metadata_assets, list)
            and expected_assets_payload != release_metadata_assets
        ):
            failures.append("passing github release verification report assets.release_metadata must match assets.expected")
        if (
            status == "PASS"
            and isinstance(expected_assets_payload, list)
            and isinstance(downloaded_assets_payload, list)
            and expected_assets_payload != downloaded_assets_payload
        ):
            failures.append("passing github release verification report assets.downloaded must match assets.expected")
        if (
            isinstance(asset_count, int)
            and isinstance(downloaded_assets_payload, list)
            and asset_count != len(downloaded_assets_payload)
        ):
            failures.append("asset_count does not match assets.downloaded")
    asset_metadata = payload.get("asset_metadata")
    failures.extend(asset_metadata_issues(asset_metadata, release_metadata_assets, repo=repo, tag=tag))

    archives = payload.get("archives")
    if not isinstance(archives, list):
        failures.append("archives must be a list")
    else:
        archive_names = []
        for archive in archives:
            if not isinstance(archive, dict):
                failures.append("archive entries must be objects")
                continue
            if not isinstance(archive.get("archive"), str) or not archive["archive"].endswith(".tar.gz"):
                failures.append(f"archive name invalid: {archive.get('archive')}")
            else:
                archive_names.append(archive["archive"])
            digest = archive.get("sha256")
            if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                failures.append(f"archive sha256 invalid: {archive.get('archive')}")
            if not isinstance(archive.get("checksum_match"), bool):
                failures.append(f"archive checksum_match must be boolean: {archive.get('archive')}")
            doctor = archive.get("doctor")
            if doctor is not None:
                if not isinstance(doctor, dict):
                    failures.append(f"archive doctor must be an object or null: {archive.get('archive')}")
                    continue
                doctor_status = doctor.get("status")
                if doctor_status != "PASS":
                    failures.append(f"archive doctor status is not PASS: {archive.get('archive')} status={doctor_status}")
                doctor_issues = doctor.get("issues")
                if not isinstance(doctor_issues, list) or not all(isinstance(issue, str) for issue in doctor_issues):
                    failures.append(f"archive doctor issues must be a string list: {archive.get('archive')}")
                elif doctor_issues:
                    failures.append(f"archive doctor has issues: {archive.get('archive')}")
                if doctor.get("expected_commit") != expected_doctor_commit:
                    failures.append(f"archive doctor expected_commit does not match expected_doctor_commit: {archive.get('archive')}")
        downloaded_archive_names = (
            sorted(name for name in downloaded_assets_payload if name.endswith(".tar.gz"))
            if isinstance(downloaded_assets_payload, list)
            and all(isinstance(name, str) for name in downloaded_assets_payload)
            else []
        )
        if sorted(archive_names) != downloaded_archive_names:
            failures.append("archives must match downloaded .tar.gz assets")
        if isinstance(asset_metadata, list):
            failures.extend(
                archive_metadata_digest_issues(
                    [record for record in asset_metadata if isinstance(record, dict)],
                    [archive for archive in archives if isinstance(archive, dict)],
                )
            )
    issues = payload.get("issues")
    if not isinstance(issues, list) or not all(isinstance(issue, str) for issue in issues):
        failures.append("issues must be a string list")
    elif status == "PASS" and issues:
        failures.append("passing github release verification report must have no issues")
    if status == "PASS" and isinstance(archives, list):
        failures.extend(doctor_run_issues([archive for archive in archives if isinstance(archive, dict)]))
    return failures


def verify_saved_github_release_report(
    report: Path,
    require_report_pass: bool = False,
    require_stable_report: bool = False,
    verify_files: bool = False,
    expect_tag: str | None = None,
    verify_git_commit: bool = False,
) -> int:
    try:
        payload = json.loads(report.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - exact report verification failure.
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    failures = validate_verification_report_payload(
        payload,
        require_report_pass=require_report_pass,
        require_stable_report=require_stable_report,
        expect_tag=expect_tag,
    )
    if verify_git_commit:
        failures.extend(git_commit_verification_issues(payload.get("expected_commit"), expect_tag))
    if not failures and verify_files:
        out_dir_value = payload.get("out_dir")
        if not isinstance(out_dir_value, str) or not out_dir_value.strip():
            failures.append("out_dir is required for --verify-report-files")
        else:
            out_dir = Path(out_dir_value)
            if not out_dir.is_dir():
                failures.append(f"out_dir is not a directory: {out_dir}")
            else:
                downloaded = sorted(path.name for path in out_dir.iterdir() if path.is_file())
                recorded_downloaded = payload["assets"]["downloaded"]
                if downloaded != recorded_downloaded:
                    failures.append("downloaded asset list changed after report was written")
                failures.extend(asset_file_metadata_issues(payload["asset_metadata"], out_dir, recorded_downloaded))
                for archive_summary in payload["archives"]:
                    archive = out_dir / archive_summary["archive"]
                    if not archive.is_file():
                        failures.append(f"archive file missing: {archive.name}")
                        continue
                    if sha256(archive) != archive_summary["sha256"]:
                        failures.append(f"archive sha256 changed: {archive.name}")
                    checksum = archive.with_name(archive.name + ".sha256")
                    if not checksum.is_file():
                        failures.append(f"checksum file missing: {checksum.name}")
                    else:
                        failures.extend(checksum_issues(checksum, archive.name))
                        try:
                            if checksum_value(checksum) != sha256(archive):
                                failures.append(f"checksum mismatch for {archive.name}")
                        except ValueError as exc:
                            failures.append(str(exc))
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print(f"github release verification report ok: {report}")
    print(f"status={payload['status']}")
    print(f"tag={payload['tag']}")
    if verify_git_commit:
        print("verified_git_commit=True")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("tag", nargs="?")
    parser.add_argument("--repo", default="benngaihk/MorphoJet")
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--expect-commit")
    parser.add_argument("--expect-prerelease", action="store_true")
    parser.add_argument("--expect-stable", action="store_true")
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--verify-report", type=Path, help="Validate a saved GitHub release verification JSON report")
    parser.add_argument("--verify-report-files", action="store_true", help="Recompute downloaded asset file checks")
    parser.add_argument("--verify-git-commit", action="store_true", help="Require the saved expected commit and expected tag to resolve in this checkout")
    parser.add_argument("--require-report-pass", action="store_true", help="Reject saved verifier reports that are not PASS")
    parser.add_argument("--require-stable-report", action="store_true", help="Reject saved verifier reports that are not stable-release reports")
    parser.add_argument("--expect-tag", help="With --verify-report, reject saved verifier reports for a different tag")
    args = parser.parse_args()
    if args.verify_report:
        return verify_saved_github_release_report(
            args.verify_report,
            require_report_pass=args.require_report_pass,
            require_stable_report=args.require_stable_report,
            verify_files=args.verify_report_files,
            expect_tag=args.expect_tag,
            verify_git_commit=args.verify_git_commit,
        )
    if args.tag is None:
        parser.error("tag is required unless --verify-report is used")

    out_dir = args.out_dir or Path("benchmark/results/github-release") / args.tag
    expected_commit = git_commit(args.expect_commit) if args.expect_commit else git_tag_commit(args.tag)
    expected_doctor_commit = doctor_commit_for(expected_commit)
    release = release_json(args.repo, args.tag)
    download_release(args.repo, args.tag, out_dir)

    issues: list[str] = []
    if release.get("isDraft"):
        issues.append("release is draft")
    if args.expect_prerelease and args.expect_stable:
        issues.append("--expect-prerelease and --expect-stable are mutually exclusive")
    issues.extend(release_identity_issues(args.tag, release))
    issues.extend(release_type_issues(args.tag, release, args.expect_prerelease, args.expect_stable))

    expected_assets = expected_asset_names(args.tag)
    release_assets = release_asset_names(release)
    actual_assets = {path.name for path in out_dir.iterdir() if path.is_file()}
    asset_metadata = release_asset_metadata(release)
    issues.extend(asset_issues(expected_assets, release_assets, actual_assets))
    issues.extend(asset_metadata_issues(asset_metadata, sorted(release_assets), repo=args.repo, tag=args.tag))
    issues.extend(asset_file_metadata_issues(asset_metadata, out_dir, sorted(actual_assets)))

    archive_summaries = []
    for archive in sorted(out_dir.glob("*.tar.gz")):
        checksum = archive.with_name(archive.name + ".sha256")
        if not checksum.exists():
            issues.append(f"missing checksum for {archive.name}")
            continue
        actual = sha256(archive)
        expected = checksum_value(checksum)
        issues.extend(checksum_issues(checksum, archive.name))
        if actual != expected:
            issues.append(f"checksum mismatch for {archive.name}")
        issues.extend(verify_archive_shape(archive))

        doctor_summary = None
        if compatible_archive(archive):
            doctor_summary = verify(archive, checksum, expected_doctor_commit)
            issues.extend(doctor_summary["issues"])
        archive_summaries.append(
            {
                "archive": archive.name,
                "sha256": actual,
                "checksum_match": actual == expected,
                "doctor": doctor_summary,
            }
        )
    issues.extend(doctor_run_issues(archive_summaries))

    summary = {
        "schema_version": 1,
        "verifier": VERIFIER,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if not issues else "FAIL",
        "tag": args.tag,
        "repo": args.repo,
        "url": release.get("url"),
        "out_dir": str(out_dir),
        "is_prerelease": release.get("isPrerelease"),
        "expected_release_kind": "stable" if args.expect_stable else "prerelease" if args.expect_prerelease else None,
        "expected_commit": expected_commit,
        "expected_doctor_commit": expected_doctor_commit,
        "asset_count": len(actual_assets),
        "assets": asset_summary(expected_assets, release_assets, actual_assets),
        "asset_metadata": asset_metadata,
        "archives": archive_summaries,
        "issues": issues,
    }
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(summary, indent=2) + "\n")
    print(f"status={summary['status']}")
    print(f"url={summary['url']}")
    print(f"asset_count={summary['asset_count']}")
    for issue in issues:
        print(f"ERROR: {issue}")
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
