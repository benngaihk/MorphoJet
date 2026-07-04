#!/usr/bin/env python3
"""Validate a saved MorphoJet release-gate JSON report."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_AUDIT_CHECKS = [
    "clean_git_worktree",
    "standard_code_and_artifact_gates",
    "l3_provenance_hashes",
    "external_l4_workflow_trial",
    "external_l4_evidence_package",
    "stable_github_release",
]

REQUIRED_PRODUCTION_GATE_NAMES = {
    "Require clean git worktree",
    "Rust formatting",
    "Rust tests",
    "Rust clippy",
    "Python helper compilation",
    "Python helper tests",
    "Validate claim language",
    "Validate handoff manifests",
    "Validate external lab handoff template",
    "Validate existing CellBinDB L3 artifacts",
    "Validate CellBinDB L3 provenance",
    "Validate CellBinDB workflow bridge artifacts",
    "Validate CellBinDB handoff trial artifacts",
    "Validate external L4 workflow trial report",
    "Validate external L4 evidence package",
    "Verify GitHub release assets",
}

STABLE_TAG_PATTERN = re.compile(r"^v\d+\.\d+\.\d+(?:\+\S+)?$")


def git_commit_is_reachable(commit: str) -> bool:
    completed = subprocess.run(
        ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    return completed.returncode == 0


def validate_metadata(metadata: Any) -> list[str]:
    failures: list[str] = []
    if not isinstance(metadata, dict):
        return ["metadata must be an object"]
    required_keys = [
        "generated_at_utc",
        "git_commit",
        "git_dirty",
        "git_status",
        "argv",
        "require_clean_git",
        "require_l3_provenance",
        "require_production_claim",
        "verify_github_release",
        "github_release_kind",
    ]
    for key in required_keys:
        if key not in metadata:
            failures.append(f"metadata missing {key}")
    generated_at = metadata.get("generated_at_utc")
    if isinstance(generated_at, str):
        try:
            parsed_generated_at = datetime.fromisoformat(generated_at)
            if parsed_generated_at.tzinfo is None:
                failures.append("metadata.generated_at_utc must include timezone")
        except ValueError:
            failures.append(f"metadata.generated_at_utc is invalid: {generated_at}")
    elif "generated_at_utc" in metadata:
        failures.append("metadata.generated_at_utc must be a string")
    git_commit = metadata.get("git_commit")
    if isinstance(git_commit, str):
        if not re.fullmatch(r"[0-9a-f]{40}", git_commit):
            failures.append(f"metadata.git_commit is not a 40-character SHA: {git_commit}")
    elif "git_commit" in metadata:
        failures.append("metadata.git_commit must be a string")
    for bool_key in ["git_dirty", "require_clean_git", "require_l3_provenance", "require_production_claim"]:
        if bool_key in metadata and not isinstance(metadata.get(bool_key), bool):
            failures.append(f"metadata.{bool_key} must be a boolean")
    for list_key in ["git_status", "argv"]:
        value = metadata.get(list_key)
        if list_key in metadata and (
            not isinstance(value, list) or not all(isinstance(item, str) for item in value)
        ):
            failures.append(f"metadata.{list_key} must be a string list")
    verify_github_release = metadata.get("verify_github_release")
    if verify_github_release is not None and not isinstance(verify_github_release, str):
        failures.append("metadata.verify_github_release must be null or a string")
    github_release_kind = metadata.get("github_release_kind")
    if github_release_kind not in {"prerelease", "stable", None}:
        failures.append(f"metadata.github_release_kind={github_release_kind}")
    return failures


def validate_production_claim_metadata(metadata: Any) -> list[str]:
    failures: list[str] = []
    if not isinstance(metadata, dict):
        return failures
    for key in ["require_clean_git", "require_l3_provenance", "require_production_claim"]:
        if metadata.get(key) is not True:
            failures.append(f"production PASS metadata.{key} must be true")
    for key in ["external_trial_json", "external_trial_root", "external_evidence_package_dir"]:
        value = metadata.get(key)
        if not isinstance(value, str) or not value.strip():
            failures.append(f"production PASS metadata.{key} must be a non-empty string")
    tag = metadata.get("verify_github_release")
    if not isinstance(tag, str) or not STABLE_TAG_PATTERN.fullmatch(tag):
        failures.append("production PASS metadata.verify_github_release must be a stable semver tag like v0.1.0")
    if metadata.get("github_release_kind") != "stable":
        failures.append(f"production PASS metadata.github_release_kind must be stable: {metadata.get('github_release_kind')}")
    return failures


def validate_gate_entry(gate: Any) -> list[str]:
    failures: list[str] = []
    if not isinstance(gate, dict):
        return ["gate entries must be objects"]
    name = gate.get("name")
    if not isinstance(name, str) or not name:
        failures.append("gate name must be a non-empty string")
    command = gate.get("command")
    if command is not None and (
        not isinstance(command, list) or not all(isinstance(item, str) for item in command)
    ):
        failures.append(f"gate command must be null or a string list: {name}")
    if gate.get("status") not in {"PASS", "FAIL"}:
        failures.append(f"gate status invalid for {name}: {gate.get('status')}")
    elapsed = gate.get("elapsed_seconds")
    if not isinstance(elapsed, (int, float)) or elapsed < 0:
        failures.append(f"gate elapsed_seconds must be non-negative: {name}")
    if not isinstance(gate.get("detail"), str):
        failures.append(f"gate detail must be a string: {name}")
    return failures


def validate_audit_checks(audit: dict, top_level_missing: Any) -> list[str]:
    failures: list[str] = []
    checks = audit.get("checks")
    if not isinstance(checks, list) or not checks:
        return ["production_claim_audit.checks must be a non-empty list"]
    check_names = []
    failed_check_names = []
    for check in checks:
        if not isinstance(check, dict):
            failures.append("production_claim_audit.check entries must be objects")
            continue
        name = check.get("name")
        status = check.get("status")
        if not isinstance(name, str) or not name:
            failures.append("production_claim_audit.check name must be a non-empty string")
            continue
        check_names.append(name)
        if status not in {"PASS", "FAIL", "MISSING"}:
            failures.append(f"production_claim_audit.check status invalid for {name}: {status}")
        if not isinstance(check.get("detail"), str):
            failures.append(f"production_claim_audit.check detail must be a string: {name}")
        if status != "PASS":
            failed_check_names.append(name)
    if check_names != REQUIRED_AUDIT_CHECKS:
        failures.append(f"production_claim_audit.check names={check_names}")
    if isinstance(top_level_missing, list) and failed_check_names != top_level_missing:
        failures.append("missing_or_failed_checks does not match audit check statuses")
    return failures


def validate_release_gate_report_payload(
    payload: Any,
    require_report_pass: bool = False,
    require_production_claim_pass: bool = False,
    expected_missing_checks: list[str] | None = None,
    require_clean_git_metadata: bool = False,
    verify_git_commit: bool = False,
) -> list[str]:
    failures: list[str] = []
    if not isinstance(payload, dict):
        return ["release-gate report must be a JSON object"]

    if payload.get("status") not in {"PASS", "FAIL"}:
        failures.append(f"status={payload.get('status')}")
    if require_report_pass and payload.get("status") != "PASS":
        failures.append(f"release-gate report status is not PASS: {payload.get('status')}")

    audit = payload.get("production_claim_audit")
    if not isinstance(audit, dict):
        failures.append("production_claim_audit must be an object")
        audit = {}
    audit_status = audit.get("status")
    if audit_status not in {"PASS", "INCOMPLETE"}:
        failures.append(f"production_claim_audit.status={audit_status}")
    top_level_claim_status = payload.get("production_claim_status")
    if top_level_claim_status != audit_status:
        failures.append(
            "production_claim_status does not match production_claim_audit.status: "
            f"{top_level_claim_status} != {audit_status}"
        )
    if require_production_claim_pass and top_level_claim_status != "PASS":
        failures.append(f"production_claim_status is not PASS: {top_level_claim_status}")

    audit_missing = audit.get("missing_or_failed_checks")
    top_level_missing = payload.get("missing_or_failed_checks")
    if not isinstance(audit_missing, list) or not all(isinstance(item, str) for item in audit_missing):
        failures.append("production_claim_audit.missing_or_failed_checks must be a string list")
    if top_level_missing != audit_missing:
        failures.append("missing_or_failed_checks does not match production_claim_audit")
    if top_level_claim_status == "PASS" and top_level_missing != []:
        failures.append("passing production claim must have no missing_or_failed_checks")
    if expected_missing_checks is not None:
        if not isinstance(top_level_missing, list):
            failures.append("missing_or_failed_checks must be a list before comparing expected checks")
        elif top_level_missing != expected_missing_checks:
            failures.append(
                "missing_or_failed_checks does not match expected checks: "
                f"{top_level_missing} != {expected_missing_checks}"
            )

    if isinstance(audit, dict):
        failures.extend(validate_audit_checks(audit, top_level_missing))

    metadata = payload.get("metadata")
    failures.extend(validate_metadata(metadata))
    if isinstance(metadata, dict):
        if require_clean_git_metadata:
            if metadata.get("git_dirty") is not False:
                failures.append("metadata.git_dirty is not false")
            if metadata.get("git_status") != []:
                failures.append("metadata.git_status is not empty")
        git_commit = metadata.get("git_commit")
        if verify_git_commit and isinstance(git_commit, str) and re.fullmatch(r"[0-9a-f]{40}", git_commit):
            if not git_commit_is_reachable(git_commit):
                failures.append(f"metadata.git_commit is not reachable: {git_commit}")
    if top_level_claim_status == "PASS":
        failures.extend(validate_production_claim_metadata(metadata))

    gates = payload.get("gates")
    if not isinstance(gates, list) or not gates:
        failures.append("gates must be a non-empty list")
        gate_names = set()
    else:
        gate_names = set()
        for gate in gates:
            failures.extend(validate_gate_entry(gate))
            if isinstance(gate, dict) and isinstance(gate.get("name"), str):
                gate_names.add(gate["name"])
        if top_level_claim_status == "PASS":
            missing_required_gates = sorted(REQUIRED_PRODUCTION_GATE_NAMES - gate_names)
            if missing_required_gates:
                failures.append("passing production claim missing gates: " + ",".join(missing_required_gates))
    return failures


def verify_release_gate_report(
    path: Path,
    require_report_pass: bool = False,
    require_production_claim_pass: bool = False,
    expected_missing_checks: list[str] | None = None,
    require_clean_git_metadata: bool = False,
    verify_git_commit: bool = False,
) -> int:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - exact report verification failure.
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    failures = validate_release_gate_report_payload(
        payload,
        require_report_pass=require_report_pass,
        require_production_claim_pass=require_production_claim_pass,
        expected_missing_checks=expected_missing_checks,
        require_clean_git_metadata=require_clean_git_metadata,
        verify_git_commit=verify_git_commit,
    )
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print(f"release-gate report ok: {path}")
    print(f"status={payload['status']}")
    print(f"production_claim_status={payload['production_claim_status']}")
    print(f"missing_or_failed_checks={','.join(payload['missing_or_failed_checks']) or 'none'}")
    if expected_missing_checks is not None:
        print(f"expected_missing_checks={','.join(expected_missing_checks) or 'none'}")
    print(f"verified_git_commit={verify_git_commit}")
    print(f"required_clean_git_metadata={require_clean_git_metadata}")
    return 0


def parse_expected_missing_checks(value: str) -> list[str]:
    if value == "none":
        return []
    checks = [item.strip() for item in value.split(",") if item.strip()]
    if not checks:
        raise argparse.ArgumentTypeError("expected checks must be comma-separated names or 'none'")
    unknown = sorted(set(checks) - set(REQUIRED_AUDIT_CHECKS))
    if unknown:
        raise argparse.ArgumentTypeError("unknown expected check(s): " + ",".join(unknown))
    return checks


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path, help="Release-gate JSON report to validate")
    parser.add_argument("--require-report-pass", action="store_true")
    parser.add_argument("--require-production-claim-pass", action="store_true")
    parser.add_argument(
        "--require-clean-git-metadata",
        action="store_true",
        help="Require metadata.git_dirty=false and metadata.git_status=[] in the saved report",
    )
    parser.add_argument(
        "--verify-git-commit",
        action="store_true",
        help="Require metadata.git_commit to be reachable in the current checkout",
    )
    parser.add_argument(
        "--expect-missing-checks",
        type=parse_expected_missing_checks,
        help="Comma-separated production-claim blockers expected in missing_or_failed_checks, or 'none'",
    )
    args = parser.parse_args()
    return verify_release_gate_report(
        args.report,
        require_report_pass=args.require_report_pass,
        require_production_claim_pass=args.require_production_claim_pass,
        expected_missing_checks=args.expect_missing_checks,
        require_clean_git_metadata=args.require_clean_git_metadata,
        verify_git_commit=args.verify_git_commit,
    )


if __name__ == "__main__":
    raise SystemExit(main())
