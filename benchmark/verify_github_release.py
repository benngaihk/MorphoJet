#!/usr/bin/env python3
"""Download and verify GitHub release assets for a MorphoJet tag."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import tarfile
from pathlib import Path

from verify_release_archive import verify


REQUIRED_PACKAGE_FILES = {"morphojet", "README.md", "LICENSE"}


def run(command: list[str]) -> str:
    completed = subprocess.run(command, text=True, capture_output=True, check=True)
    return completed.stdout


def git_tag_commit(tag: str) -> str:
    return run(["git", "rev-list", "-n", "1", "--abbrev-commit", "--abbrev=12", tag]).strip()


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
        if "-rc" in tag:
            issues.append("stable release tag must not contain -rc")
    return issues


def release_identity_issues(tag: str, release: dict) -> list[str]:
    issues = []
    if release.get("tagName") != tag:
        issues.append(f"release tagName mismatch: {release.get('tagName')}")
    if not isinstance(release.get("url"), str) or not release.get("url", "").strip():
        issues.append("release url must be a non-empty string")
    return issues


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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("tag")
    parser.add_argument("--repo", default="benngaihk/MorphoJet")
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--expect-commit")
    parser.add_argument("--expect-prerelease", action="store_true")
    parser.add_argument("--expect-stable", action="store_true")
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()

    out_dir = args.out_dir or Path("benchmark/results/github-release") / args.tag
    expected_commit = args.expect_commit or git_tag_commit(args.tag)
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
    issues.extend(asset_issues(expected_assets, release_assets, actual_assets))

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
            doctor_summary = verify(archive, checksum, expected_commit)
            issues.extend(doctor_summary["issues"])
        archive_summaries.append(
            {
                "archive": archive.name,
                "sha256": actual,
                "checksum_match": actual == expected,
                "doctor": doctor_summary,
            }
        )

    summary = {
        "status": "PASS" if not issues else "FAIL",
        "tag": args.tag,
        "repo": args.repo,
        "url": release.get("url"),
        "is_prerelease": release.get("isPrerelease"),
        "expected_release_kind": "stable" if args.expect_stable else "prerelease" if args.expect_prerelease else None,
        "expected_commit": expected_commit,
        "asset_count": len(actual_assets),
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
