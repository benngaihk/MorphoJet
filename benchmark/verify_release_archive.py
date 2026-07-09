#!/usr/bin/env python3
"""Verify a MorphoJet release archive and smoke-test the packaged binary."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = {"morphojet", "README.md", "README.zh-CN.md", "LICENSE"}
SOURCE_MATCH_FILES = ("README.md", "README.zh-CN.md", "LICENSE")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def expected_sha(path: Path) -> str:
    parts = path.read_text().split()
    if not parts:
        raise SystemExit(f"empty checksum file: {path}")
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


def safe_extract(archive: Path, destination: Path) -> None:
    with tarfile.open(archive, "r:gz") as handle:
        root = destination.resolve()
        for member in handle.getmembers():
            if member.issym() or member.islnk():
                raise SystemExit(f"unsafe archive link: {member.name}")
            if not (member.isdir() or member.isfile()):
                raise SystemExit(f"unsafe archive member type: {member.name}")
            target = (destination / member.name).resolve()
            try:
                target.relative_to(root)
            except ValueError:
                raise SystemExit(f"unsafe archive path: {member.name}")
        handle.extractall(destination)


def normalized_path_key(path: Path) -> str:
    return str(path.expanduser().resolve(strict=False))


def package_file_summaries(package_dir: Path, source_root: Path = ROOT) -> dict[str, dict[str, object]]:
    summaries = {}
    for filename in SOURCE_MATCH_FILES:
        package_path = package_dir / filename
        source_path = source_root / filename
        package_exists = package_path.is_file()
        source_exists = source_path.is_file()
        package_sha = sha256(package_path) if package_exists else None
        source_sha = sha256(source_path) if source_exists else None
        summaries[filename] = {
            "package_path": str(package_path),
            "source_path": str(source_path),
            "package_exists": package_exists,
            "source_exists": source_exists,
            "package_sha256": package_sha,
            "source_sha256": source_sha,
            "matches_source": package_exists and source_exists and package_sha == source_sha,
        }
    return summaries


def package_file_issues(summaries: dict[str, dict[str, object]]) -> list[str]:
    issues = []
    for filename in SOURCE_MATCH_FILES:
        summary = summaries.get(filename)
        if not isinstance(summary, dict):
            issues.append(f"missing package file summary for {filename}")
            continue
        if not summary.get("source_exists"):
            issues.append(f"repository source file missing for {filename}")
        if not summary.get("package_exists"):
            issues.append(f"package file missing for {filename}")
        elif summary.get("matches_source") is not True:
            issues.append(f"packaged {filename} does not match repository {filename}")
    return issues


def extracted_package_dir(extract_root: Path, issues: list[str]) -> Path:
    roots = [path for path in extract_root.iterdir() if path.is_dir()]
    if len(roots) != 1:
        issues.append(f"expected one top-level directory, found {len(roots)}")
        return roots[0] if roots else extract_root
    return roots[0]


def inspect_package_contents(archive: Path) -> dict[str, object]:
    issues: list[str] = []
    with tempfile.TemporaryDirectory(prefix="morphojet-release-") as tmp:
        tmp_path = Path(tmp)
        safe_extract(archive, tmp_path)
        package_dir = extracted_package_dir(tmp_path, issues)
        found = {path.name for path in package_dir.iterdir()} if package_dir.exists() else set()
        missing = sorted(REQUIRED_FILES - found)
        if missing:
            issues.append(f"missing files={','.join(missing)}")
        file_summaries = package_file_summaries(package_dir)
        issues.extend(package_file_issues(file_summaries))
    return {"issues": issues, "package_files": file_summaries}


def validate_json_out_path(json_out: Path | None, archive: Path, checksum: Path) -> None:
    if json_out is None:
        return
    protected = {
        normalized_path_key(archive): f"archive: {archive}",
        normalized_path_key(checksum): f"checksum: {checksum}",
    }
    protected_label = protected.get(normalized_path_key(json_out))
    if protected_label:
        raise SystemExit(f"--json-out must not overwrite {protected_label}")


def verify(archive: Path, checksum: Path, expect_commit: str | None) -> dict[str, object]:
    actual = sha256(archive)
    expected = expected_sha(checksum)
    issues = []
    issues.extend(checksum_issues(checksum, archive.name))
    if actual != expected:
        issues.append(f"sha256 mismatch expected={expected} actual={actual}")

    with tempfile.TemporaryDirectory(prefix="morphojet-release-") as tmp:
        tmp_path = Path(tmp)
        safe_extract(archive, tmp_path)
        package_dir = extracted_package_dir(tmp_path, issues)
        found = {path.name for path in package_dir.iterdir()} if package_dir.exists() else set()
        missing = sorted(REQUIRED_FILES - found)
        if missing:
            issues.append(f"missing files={','.join(missing)}")
        file_summaries = package_file_summaries(package_dir)
        issues.extend(package_file_issues(file_summaries))

        binary = package_dir / "morphojet"
        doctor_output = ""
        if binary.exists():
            if not binary.stat().st_mode & 0o111:
                issues.append("morphojet binary is not executable")
            completed = subprocess.run([str(binary), "doctor"], text=True, capture_output=True)
            doctor_output = completed.stdout
            if completed.returncode != 0:
                issues.append(f"morphojet doctor exited {completed.returncode}: {completed.stderr.strip()}")
            for required in ["morphojet.version=", "morphojet.commit=", "platform.os=", "platform.arch="]:
                if required not in doctor_output:
                    issues.append(f"doctor output missing {required}")
            if expect_commit and f"morphojet.commit={expect_commit}" not in doctor_output:
                issues.append(f"doctor output does not contain expected commit {expect_commit}")

    return {
        "status": "PASS" if not issues else "FAIL",
        "archive": str(archive),
        "checksum": str(checksum),
        "sha256": actual,
        "issues": issues,
        "expected_commit": expect_commit,
        "doctor_output": doctor_output,
        "package_files": file_summaries,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("--checksum", type=Path)
    parser.add_argument("--expect-commit")
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()

    checksum = args.checksum or args.archive.with_name(args.archive.name + ".sha256")
    if not args.archive.is_file():
        raise SystemExit(f"archive not found: {args.archive}")
    if not checksum.is_file():
        raise SystemExit(f"checksum not found: {checksum}")
    validate_json_out_path(args.json_out, args.archive, checksum)

    summary = verify(args.archive, checksum, args.expect_commit)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(summary, indent=2) + "\n")
    print(f"status={summary['status']}")
    print(f"archive={summary['archive']}")
    if summary["issues"]:
        for issue in summary["issues"]:
            print(f"ERROR: {issue}")
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
