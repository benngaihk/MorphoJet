#!/usr/bin/env python3
"""Validate a packaged external L4 trial evidence bundle."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import release_gate

SCHEMA_VERSION = 1
VERIFIER = "benchmark/verify_external_evidence_package.py"
SHA256_RE = re.compile(r"[0-9a-f]{64}")
PACKAGE_REVIEW_FILES = {
    "package_handoff_trial": "handoff_trial.json",
    "package_rendered_manifest": "rendered_manifest.json",
    "package_external_evidence": "external_evidence.json",
    "package_artifact_manifest": "artifact_manifest.json",
    "package_readme": "README.md",
}


def file_summary(path: Path) -> dict[str, Any]:
    summary: dict[str, Any] = {"path": str(path), "exists": path.is_file()}
    if path.is_file():
        summary["size_bytes"] = path.stat().st_size
        summary["sha256"] = release_gate.sha256_file(path)
    else:
        summary["size_bytes"] = None
        summary["sha256"] = None
    return summary


def package_input_files(package_dir: Path, trial_json: Path | None = None) -> dict[str, dict[str, Any]]:
    files = {key: file_summary(package_dir / filename) for key, filename in PACKAGE_REVIEW_FILES.items()}
    files["package_zip"] = file_summary(package_dir.parent / f"{package_dir.name}.zip")
    files["package_zip_sha256"] = file_summary(package_dir.parent / f"{package_dir.name}.zip.sha256")
    if trial_json is not None:
        files["source_trial_json"] = file_summary(trial_json)
    return files


def input_file_summary_issues(name: str, summary: Any, require_exists: bool) -> list[str]:
    failures = []
    if not isinstance(summary, dict):
        return [f"input_files.{name} must be an object"]
    path = summary.get("path")
    if not isinstance(path, str) or not path.strip():
        failures.append(f"input_files.{name}.path must be a non-empty string")
    exists = summary.get("exists")
    if not isinstance(exists, bool):
        failures.append(f"input_files.{name}.exists must be a boolean")
    elif require_exists and not exists:
        failures.append(f"input_files.{name}.exists must be true")
    size = summary.get("size_bytes")
    digest = summary.get("sha256")
    if exists is True:
        if not isinstance(size, int) or size <= 0:
            failures.append(f"input_files.{name}.size_bytes must be a positive integer")
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            failures.append(f"input_files.{name}.sha256 must be a SHA-256 digest")
    else:
        if size is not None:
            failures.append(f"input_files.{name}.size_bytes must be null when missing")
        if digest is not None:
            failures.append(f"input_files.{name}.sha256 must be null when missing")
    return failures


def input_files_issues(input_files: Any, status: Any, require_trial_json: bool) -> list[str]:
    failures = []
    if not isinstance(input_files, dict):
        return ["input_files must be an object"]
    required_keys = set(PACKAGE_REVIEW_FILES) | {"package_zip", "package_zip_sha256"}
    if require_trial_json:
        required_keys.add("source_trial_json")
    for missing in sorted(required_keys - set(input_files)):
        failures.append(f"input_files missing required entry: {missing}")
    for name, summary in input_files.items():
        if not isinstance(name, str) or not name.strip():
            failures.append("input_files keys must be non-empty strings")
            continue
        require_exists = status == "PASS" and (name in required_keys or name == "source_trial_json")
        failures.extend(input_file_summary_issues(name, summary, require_exists=require_exists))
    return failures


def recomputed_input_file_issues(recorded: dict[str, Any], package_dir: Path, trial_json: Path | None) -> list[str]:
    failures = []
    current = package_input_files(package_dir, trial_json)
    for name, current_summary in current.items():
        recorded_summary = recorded.get(name)
        if not isinstance(recorded_summary, dict):
            failures.append(f"input_files.{name} missing from saved report")
            continue
        for field in ["path", "exists", "size_bytes", "sha256"]:
            if recorded_summary.get(field) != current_summary.get(field):
                failures.append(f"input_files.{name}.{field} changed after recomputing evidence package validation")
    for name in sorted(set(recorded) - set(current)):
        failures.append(f"input_files has unexpected saved entry: {name}")
    return failures


def normalized_path_key(path: Path) -> str:
    return str(path.expanduser().resolve(strict=False))


def package_artifact_paths(package_dir: Path) -> dict[str, Path]:
    manifest_path = package_dir / "artifact_manifest.json"
    if not manifest_path.is_file():
        return {}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(manifest, dict):
        return {}
    paths = {}
    for entry in manifest.get("artifacts", []):
        if isinstance(entry, dict) and isinstance(entry.get("package_path"), str) and entry["package_path"]:
            paths[f"package artifact: {entry['package_path']}"] = package_dir / entry["package_path"]
    return paths


def validate_json_out_path(json_out: Path | None, package_dir: Path, trial_json: Path | None) -> None:
    if json_out is None:
        return
    protected = {
        normalized_path_key(package_dir / filename): f"package review file: {filename}"
        for filename in PACKAGE_REVIEW_FILES.values()
    }
    protected[normalized_path_key(package_dir.parent / f"{package_dir.name}.zip")] = (
        f"package zip: {package_dir.name}.zip"
    )
    protected[normalized_path_key(package_dir.parent / f"{package_dir.name}.zip.sha256")] = (
        f"package checksum: {package_dir.name}.zip.sha256"
    )
    if trial_json is not None:
        protected[normalized_path_key(trial_json)] = f"source trial JSON: {trial_json}"
    for label, path in package_artifact_paths(package_dir).items():
        protected[normalized_path_key(path)] = label
    protected_label = protected.get(normalized_path_key(json_out))
    if protected_label:
        raise SystemExit(f"--json-out must not overwrite {protected_label}")


def verify_external_evidence_package(
    package_dir: Path,
    trial_json: Path | None = None,
    json_out: Path | None = None,
    require_pass: bool = True,
) -> int:
    validate_json_out_path(json_out, package_dir, trial_json)
    gate = release_gate.validate_external_evidence_package(package_dir, trial_json)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "verifier": VERIFIER,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": gate.status,
        "package_dir": str(package_dir),
        "trial_json": str(trial_json) if trial_json else None,
        "input_files": package_input_files(package_dir, trial_json),
        "gate": asdict(gate),
    }
    if json_out:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if gate.status == "PASS":
        print(gate.detail)
        if json_out:
            print(f"wrote {json_out}")
        return 0
    print(f"FAIL: {gate.detail}", file=sys.stderr)
    if json_out:
        print(f"wrote {json_out}", file=sys.stderr)
    return 1 if require_pass else 0


def validate_verification_report_payload(
    payload: Any,
    require_report_pass: bool = False,
    require_trial_json: bool = False,
) -> list[str]:
    failures: list[str] = []
    if not isinstance(payload, dict):
        return ["external evidence package verification report must be a JSON object"]
    status = payload.get("status")
    if status not in {"PASS", "FAIL"}:
        failures.append(f"status={status}")
    if require_report_pass and status != "PASS":
        failures.append(f"external evidence package verification report status is not PASS: {status}")
    if payload.get("schema_version") != SCHEMA_VERSION:
        failures.append(f"schema_version={payload.get('schema_version')}")
    if payload.get("verifier") != VERIFIER:
        failures.append(f"verifier={payload.get('verifier')}")
    generated_at = payload.get("generated_at_utc")
    if isinstance(generated_at, str):
        try:
            parsed_generated_at = datetime.fromisoformat(generated_at)
            if parsed_generated_at.tzinfo is None:
                failures.append("generated_at_utc must include timezone")
        except ValueError:
            failures.append(f"generated_at_utc is invalid: {generated_at}")
    else:
        failures.append("generated_at_utc must be a string")
    package_dir = payload.get("package_dir")
    if not isinstance(package_dir, str) or not package_dir.strip():
        failures.append("package_dir must be a non-empty string")
    trial_json = payload.get("trial_json")
    if trial_json is not None and (not isinstance(trial_json, str) or not trial_json.strip()):
        failures.append("trial_json must be null or a non-empty string")
    if require_trial_json and (not isinstance(trial_json, str) or not trial_json.strip()):
        failures.append("trial_json is required for production package reviewer reports")
    input_files = payload.get("input_files")
    failures.extend(input_files_issues(input_files, status, require_trial_json))
    gate = payload.get("gate")
    if not isinstance(gate, dict):
        failures.append("gate must be an object")
        return failures
    if gate.get("name") != "Validate external L4 evidence package":
        failures.append(f"gate.name={gate.get('name')}")
    gate_status = gate.get("status")
    if gate_status not in {"PASS", "FAIL"}:
        failures.append(f"gate.status={gate_status}")
    if status != gate_status:
        failures.append(f"status does not match gate.status: {status} != {gate_status}")
    if not isinstance(gate.get("detail"), str) or not gate["detail"].strip():
        failures.append("gate.detail must be a non-empty string")
    if gate.get("command") is not None:
        failures.append("gate.command must be null")
    elapsed = gate.get("elapsed_seconds")
    if not isinstance(elapsed, (int, float)) or elapsed < 0:
        failures.append(f"gate.elapsed_seconds={elapsed}")
    return failures


def verify_saved_external_evidence_package_report(
    report: Path,
    require_report_pass: bool = False,
    verify_files: bool = False,
    require_trial_json: bool = False,
) -> int:
    try:
        payload = json.loads(report.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - exact report verification failure.
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    failures = validate_verification_report_payload(
        payload,
        require_report_pass=require_report_pass,
        require_trial_json=require_trial_json,
    )
    if not failures and verify_files:
        package_dir = Path(payload["package_dir"])
        trial_json = Path(payload["trial_json"]) if payload.get("trial_json") is not None else None
        gate = release_gate.validate_external_evidence_package(package_dir, trial_json)
        recorded_gate = payload["gate"]
        if recorded_gate.get("name") != gate.name:
            failures.append(f"gate.name changed: {recorded_gate.get('name')} != {gate.name}")
        if recorded_gate.get("status") != gate.status:
            failures.append(f"gate.status changed: {recorded_gate.get('status')} != {gate.status}")
        if recorded_gate.get("detail") != gate.detail:
            failures.append("gate.detail changed after recomputing evidence package validation")
        if payload.get("status") != gate.status:
            failures.append(
                "status changed after recomputing evidence package validation: "
                f"{payload.get('status')} != {gate.status}"
            )
        failures.extend(recomputed_input_file_issues(payload["input_files"], package_dir, trial_json))
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print(f"external evidence package verification report ok: {report}")
    print(f"status={payload['status']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("package_dir", nargs="?", type=Path, help="External L4 evidence package directory")
    parser.add_argument(
        "--trial-json",
        type=Path,
        help="Optional source handoff_trial.json to bind the package to a specific trial report",
    )
    parser.add_argument("--json-out", type=Path, help="Optional machine-readable verifier report")
    parser.add_argument("--verify-report", type=Path, help="Validate a saved verifier JSON report")
    parser.add_argument("--verify-report-files", action="store_true", help="Recompute package validation from report paths")
    parser.add_argument("--require-report-pass", action="store_true", help="Reject saved verifier reports that are not PASS")
    parser.add_argument(
        "--require-trial-json",
        action="store_true",
        help="With --verify-report, require the saved package reviewer report to be bound to a source trial JSON",
    )
    parser.add_argument(
        "--allow-fail-report",
        action="store_true",
        help="Write/print a FAIL report but exit 0; intended only for diagnostics",
    )
    args = parser.parse_args()
    if args.verify_report:
        return verify_saved_external_evidence_package_report(
            args.verify_report,
            require_report_pass=args.require_report_pass,
            verify_files=args.verify_report_files,
            require_trial_json=args.require_trial_json,
        )
    if args.package_dir is None:
        parser.error("package_dir is required unless --verify-report is used")
    return verify_external_evidence_package(
        args.package_dir,
        trial_json=args.trial_json,
        json_out=args.json_out,
        require_pass=not args.allow_fail_report,
    )


if __name__ == "__main__":
    raise SystemExit(main())
