#!/usr/bin/env python3
"""Validate a saved MorphoJet release-gate JSON report."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
GITHUB_RELEASE_REPO = "benngaihk/MorphoJet"
FINAL_CLAIM_STATUS = "FINAL_PRODUCTION_CLAIM"
NON_FINAL_CLAIM_STATUS = "NOT_PRODUCTION_CLAIM"
FINAL_EVIDENCE_SCOPE = "FINAL_PRODUCTION_RELEASE_GATE"
NON_FINAL_EVIDENCE_SCOPE = "RELEASE_GATE_PRECHECK"

REQUIRED_AUDIT_CHECKS = [
    "clean_git_worktree",
    "standard_code_and_artifact_gates",
    "l3_provenance_hashes",
    "external_l4_workflow_trial",
    "external_l4_evidence_package",
    "external_l4_saved_reviewer_reports",
    "stable_github_release",
    "stable_github_release_saved_report",
]

PRODUCTION_CHECKLIST_GUIDANCE = {
    "clean_git_worktree": {
        "evidence": "Release-gate report generated with --require-clean-git and git_dirty=false.",
        "next_action": "Commit or remove local changes, then rerun the final gate with --require-clean-git.",
    },
    "standard_code_and_artifact_gates": {
        "evidence": "Rust, Python, manifest, L3 artifact, workflow bridge, and handoff gates are PASS.",
        "next_action": "Fix the failing standard gate detail, then regenerate the release-gate report.",
    },
    "l3_provenance_hashes": {
        "evidence": "CellBinDB L3 provenance exists, was not generated with --skip-cellprofiler, and hashes match.",
        "next_action": "Rerun with --require-l3-provenance after refreshing L3 artifacts when measurement code changed.",
    },
    "external_l4_workflow_trial": {
        "evidence": "A real external handoff_trial.json PASS report with no manual CSV edits and signed L4 evidence.",
        "next_action": (
            "Prepare the workspace, run readiness, then run benchmark/run_handoff_trial.py "
            "with --require-external-evidence and --readiness-report."
        ),
    },
    "external_l4_evidence_package": {
        "evidence": "A package_external_trial.py evidence package bound to the external trial report.",
        "next_action": "Package the accepted external trial and supply --external-evidence-package-dir.",
    },
    "external_l4_saved_reviewer_reports": {
        "evidence": "Saved external trial and evidence-package verifier reports rechecked with file hashing.",
        "next_action": (
            "Run verify_external_trial_report.py and verify_external_evidence_package.py, then recheck "
            "both saved reports with --verify-report-files --require-report-pass."
        ),
    },
    "stable_github_release": {
        "evidence": "A live non-prerelease GitHub release for the final tag verified from benngaihk/MorphoJet.",
        "next_action": "After L4 evidence is accepted, publish the stable tag and verify it with --github-release-kind stable.",
    },
    "stable_github_release_saved_report": {
        "evidence": "A saved stable GitHub release verifier report bound to the final tag, repo, commit, and assets.",
        "next_action": (
            "Save verify_github_release.py output outside the download dir, then recheck it with "
            "--verify-report-files --require-stable-report --verify-git-commit "
            "--expect-tag <final-tag> --expect-repo benngaihk/MorphoJet."
        ),
    },
}

NO_ACTION_NEEDED = "No action needed for this check."


def is_utc_datetime(value: datetime) -> bool:
    return value.utcoffset() == timezone.utc.utcoffset(value)


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
    "Validate CellBinDB direct-mask inspection",
    "Validate existing CellBinDB L3 artifacts",
    "Validate CellBinDB L3 provenance",
    "Validate CellBinDB workflow bridge artifacts",
    "Validate CellBinDB handoff trial artifacts",
    "Validate external L4 workflow trial report",
    "Validate external L4 evidence package",
    "Verify saved external L4 trial report",
    "Verify saved external L4 evidence package report",
    "Verify GitHub release assets",
    "Verify saved stable GitHub release report",
}

STABLE_TAG_PATTERN = re.compile(r"^v\d+\.\d+\.\d+(?:\+\S+)?$")

PRODUCTION_PATH_METADATA_KEYS = {
    "external_trial_json",
    "external_trial_root",
    "external_evidence_package_dir",
    "external_trial_verification_report",
    "external_evidence_package_verification_report",
    "github_release_verification_report",
}

PRODUCTION_PATH_ARGV_FLAGS = {
    "--external-trial-json",
    "--external-trial-root",
    "--external-evidence-package-dir",
    "--external-trial-verification-report",
    "--external-evidence-package-verification-report",
    "--github-release-verification-report",
    "--out-json",
    "--out-md",
}


def git_commit_is_reachable(commit: str) -> bool:
    completed = subprocess.run(
        ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    return completed.returncode == 0


def normalized_path(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def validate_metadata(metadata: Any, report_path: Path | None = None) -> list[str]:
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
            elif not is_utc_datetime(parsed_generated_at):
                failures.append("metadata.generated_at_utc must be UTC")
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
    elif github_release_kind == "stable":
        if not isinstance(verify_github_release, str) or not STABLE_TAG_PATTERN.fullmatch(verify_github_release):
            failures.append("metadata.github_release_kind=stable requires a stable metadata.verify_github_release tag")
    for key in sorted(PRODUCTION_PATH_METADATA_KEYS):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip() and not Path(value).is_absolute():
            failures.append(f"metadata.{key} must be an absolute path: {value}")
    failures.extend(validate_metadata_argv(metadata, report_path=report_path))
    return failures


def argv_has_flag(argv: list[str], flag: str) -> bool:
    return flag in argv


def argv_has_flag_value(argv: list[str], flag: str, expected: str) -> bool:
    for index, item in enumerate(argv[:-1]):
        if item == flag and argv[index + 1] == expected:
            return True
    return False


def argv_values(argv: list[str], flag: str) -> list[str | None]:
    values: list[str | None] = []
    for index, item in enumerate(argv):
        if item != flag:
            continue
        if index + 1 >= len(argv) or argv[index + 1].startswith("--"):
            values.append(None)
        else:
            values.append(argv[index + 1])
    return values


def validate_metadata_argv(metadata: Any, report_path: Path | None = None) -> list[str]:
    if not isinstance(metadata, dict):
        return []
    argv = metadata.get("argv")
    if not isinstance(argv, list) or not all(isinstance(item, str) for item in argv):
        return []
    failures = []
    if not argv:
        return failures
    if argv[0] != "benchmark/release_gate.py":
        failures.append(f"metadata.argv[0]={argv[0]}")
    required_bool_flags = {
        "require_clean_git": "--require-clean-git",
        "require_l3_provenance": "--require-l3-provenance",
        "require_production_claim": "--require-production-claim",
    }
    for metadata_key, flag in required_bool_flags.items():
        if metadata.get(metadata_key) is True and not argv_has_flag(argv, flag):
            failures.append(f"metadata.argv missing {flag} for metadata.{metadata_key}=true")
        if argv.count(flag) > 1:
            failures.append(f"metadata.argv has duplicate {flag}")
        if argv_has_flag(argv, flag) and metadata.get(metadata_key) is not True:
            failures.append(f"metadata.{metadata_key} must be true when metadata.argv includes {flag}")
    required_path_flags = {
        "external_trial_json": "--external-trial-json",
        "external_trial_root": "--external-trial-root",
        "external_evidence_package_dir": "--external-evidence-package-dir",
        "external_trial_verification_report": "--external-trial-verification-report",
        "external_evidence_package_verification_report": "--external-evidence-package-verification-report",
        "github_release_verification_report": "--github-release-verification-report",
        "verify_github_release": "--verify-github-release",
    }
    for metadata_key, flag in required_path_flags.items():
        value = metadata.get(metadata_key)
        if isinstance(value, str) and value.strip() and not argv_has_flag_value(argv, flag, value):
            failures.append(f"metadata.argv missing {flag} {value}")
        values = argv_values(argv, flag)
        if len(values) > 1:
            failures.append(f"metadata.argv has duplicate {flag}")
        for argv_value in values:
            if argv_value is None:
                failures.append(f"metadata.argv {flag} must include a value")
                continue
            if flag in PRODUCTION_PATH_ARGV_FLAGS and not Path(argv_value).is_absolute():
                failures.append(f"metadata.argv {flag} must use an absolute path: {argv_value}")
            if metadata.get(metadata_key) != argv_value:
                failures.append(f"metadata.{metadata_key} must match metadata.argv {flag} {argv_value}")
    for flag in sorted(PRODUCTION_PATH_ARGV_FLAGS - set(required_path_flags.values())):
        values = argv_values(argv, flag)
        if len(values) > 1:
            failures.append(f"metadata.argv has duplicate {flag}")
        for argv_value in values:
            if argv_value is None:
                failures.append(f"metadata.argv {flag} must include a value")
            elif not Path(argv_value).is_absolute():
                failures.append(f"metadata.argv {flag} must use an absolute path: {argv_value}")
            elif flag == "--out-json" and report_path is not None:
                if normalized_path(Path(argv_value)) != normalized_path(report_path):
                    failures.append(f"metadata.argv --out-json must match verified report path: {argv_value}")
    github_release_kind = metadata.get("github_release_kind")
    if (
        isinstance(github_release_kind, str)
        and github_release_kind != "prerelease"
        and not argv_has_flag_value(argv, "--github-release-kind", github_release_kind)
    ):
        failures.append(f"metadata.argv missing --github-release-kind {github_release_kind}")
    github_release_kind_values = argv_values(argv, "--github-release-kind")
    if len(github_release_kind_values) > 1:
        failures.append("metadata.argv has duplicate --github-release-kind")
    for argv_value in github_release_kind_values:
        if argv_value is None:
            failures.append("metadata.argv --github-release-kind must include a value")
        elif metadata.get("github_release_kind") != argv_value:
            failures.append(f"metadata.github_release_kind must match metadata.argv --github-release-kind {argv_value}")
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
    for key in [
        "external_trial_verification_report",
        "external_evidence_package_verification_report",
        "github_release_verification_report",
    ]:
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


def saved_github_release_report_command(report: str, expected_tag: str | None = None) -> list[str]:
    command = [
        "python3",
        "benchmark/verify_github_release.py",
        "--verify-report",
        report,
        "--verify-report-files",
        "--require-report-pass",
        "--require-stable-report",
        "--verify-git-commit",
        "--expect-repo",
        GITHUB_RELEASE_REPO,
    ]
    if expected_tag:
        command.extend(["--expect-tag", expected_tag])
    return command


def github_release_verification_report_path(tag: str) -> str:
    return str((ROOT / "benchmark" / "results" / "github-release-verification" / f"{tag}.json").resolve(strict=False))


def live_github_release_gate_command(tag: str, kind: str) -> list[str]:
    release_kind_flag = "--expect-stable" if kind == "stable" else "--expect-prerelease"
    return [
        "python3",
        "benchmark/verify_github_release.py",
        tag,
        "--repo",
        GITHUB_RELEASE_REPO,
        release_kind_flag,
        "--json-out",
        github_release_verification_report_path(tag),
    ]


def validate_live_github_release_gate_command(gate: dict, metadata: Any) -> list[str]:
    if gate.get("name") != "Verify GitHub release assets":
        return []
    if not isinstance(metadata, dict):
        return []
    command = gate.get("command")
    tag = metadata.get("verify_github_release")
    kind = metadata.get("github_release_kind")
    if not isinstance(tag, str) or not tag.strip():
        return ["gate command for Verify GitHub release assets requires metadata.verify_github_release"]
    if kind not in {"prerelease", "stable"}:
        return ["gate command for Verify GitHub release assets requires metadata.github_release_kind"]
    if not isinstance(command, list) or not all(isinstance(item, str) for item in command):
        return ["gate command for Verify GitHub release assets must be a string list"]
    if command != live_github_release_gate_command(tag, kind):
        return ["gate command for Verify GitHub release assets must match live release verifier command"]
    return []


def validate_saved_reviewer_gate_command(gate: dict, metadata: Any) -> list[str]:
    name = gate.get("name")
    command = gate.get("command")
    if not isinstance(name, str):
        return []
    if not isinstance(command, list) or not all(isinstance(item, str) for item in command):
        return []
    if not isinstance(metadata, dict):
        return []
    failures: list[str] = []
    expected: list[str] | None = None
    metadata_key: str | None = None
    if name == "Verify saved external L4 trial report":
        metadata_key = "external_trial_verification_report"
        report = metadata.get(metadata_key)
        if isinstance(report, str) and report.strip():
            expected = [
                "python3",
                "benchmark/verify_external_trial_report.py",
                "--verify-report",
                report,
                "--verify-report-files",
                "--require-report-pass",
            ]
    elif name == "Verify saved external L4 evidence package report":
        metadata_key = "external_evidence_package_verification_report"
        report = metadata.get(metadata_key)
        if isinstance(report, str) and report.strip():
            expected = [
                "python3",
                "benchmark/verify_external_evidence_package.py",
                "--verify-report",
                report,
                "--verify-report-files",
                "--require-report-pass",
                "--require-trial-json",
            ]
    elif name == "Verify saved stable GitHub release report":
        metadata_key = "github_release_verification_report"
        report = metadata.get(metadata_key)
        expected_tag = metadata.get("verify_github_release")
        if isinstance(report, str) and report.strip():
            expected = saved_github_release_report_command(
                report,
                expected_tag if isinstance(expected_tag, str) and expected_tag.strip() else None,
            )
    if metadata_key is not None and expected is None:
        failures.append(f"gate command for {name} requires metadata.{metadata_key}")
    elif expected is not None and command != expected:
        failures.append(f"gate command for {name} must match saved verifier command")
    return failures


SAVED_REVIEWER_METADATA_TO_GATE = {
    "external_trial_verification_report": "Verify saved external L4 trial report",
    "external_evidence_package_verification_report": "Verify saved external L4 evidence package report",
    "github_release_verification_report": "Verify saved stable GitHub release report",
}

EVIDENCE_METADATA_TO_GATE = {
    "external_trial_json": "Validate external L4 workflow trial report",
    "external_evidence_package_dir": "Validate external L4 evidence package",
    "verify_github_release": "Verify GitHub release assets",
}

FLAG_METADATA_TO_GATE = {
    "require_clean_git": "Require clean git worktree",
    "require_l3_provenance": "Validate CellBinDB L3 provenance",
    "run_l3": "Run CellBinDB L3 benchmark",
    "build_release_artifact": "Build local release archive",
}


def validate_metadata_gate_presence(metadata: Any, gate_names: set[str]) -> list[str]:
    if not isinstance(metadata, dict):
        return []
    failures: list[str] = []
    for metadata_key, gate_name in EVIDENCE_METADATA_TO_GATE.items():
        value = metadata.get(metadata_key)
        if isinstance(value, str) and value.strip() and gate_name not in gate_names:
            failures.append(f"metadata.{metadata_key} requires gate: {gate_name}")
    for metadata_key, gate_name in FLAG_METADATA_TO_GATE.items():
        if metadata.get(metadata_key) is True and gate_name not in gate_names:
            failures.append(f"metadata.{metadata_key}=true requires gate: {gate_name}")
    return failures


def validate_saved_reviewer_gate_presence(metadata: Any, gate_names: set[str]) -> list[str]:
    if not isinstance(metadata, dict):
        return []
    failures: list[str] = []
    for metadata_key, gate_name in SAVED_REVIEWER_METADATA_TO_GATE.items():
        value = metadata.get(metadata_key)
        if isinstance(value, str) and value.strip() and gate_name not in gate_names:
            failures.append(f"metadata.{metadata_key} requires gate: {gate_name}")
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


def expected_checklist_row(check: dict) -> dict[str, str] | None:
    name = check.get("name")
    status = check.get("status")
    if not isinstance(name, str) or name not in PRODUCTION_CHECKLIST_GUIDANCE or not isinstance(status, str):
        return None
    guidance = PRODUCTION_CHECKLIST_GUIDANCE[name]
    return {
        "check": name,
        "status": status,
        "evidence": guidance["evidence"],
        "next_action": NO_ACTION_NEEDED if status == "PASS" else guidance["next_action"],
    }


def validate_production_claim_checklist(payload: dict) -> list[str]:
    failures: list[str] = []
    audit = payload.get("production_claim_audit")
    checklist = payload.get("production_claim_checklist")
    if not isinstance(audit, dict):
        return []
    checks = audit.get("checks")
    if not isinstance(checks, list) or not checks:
        return []
    if not isinstance(checklist, list) or not checklist:
        return ["production_claim_checklist must be a non-empty list"]
    if len(checklist) != len(checks):
        failures.append("production_claim_checklist length does not match production_claim_audit.checks")
    expected_rows = [expected_checklist_row(check) for check in checks]
    for index, expected in enumerate(expected_rows):
        if expected is None:
            continue
        if index >= len(checklist):
            failures.append(f"production_claim_checklist missing row for {expected['check']}")
            continue
        row = checklist[index]
        if not isinstance(row, dict):
            failures.append("production_claim_checklist entries must be objects")
            continue
        for key in ["check", "status", "evidence", "next_action"]:
            if not isinstance(row.get(key), str) or not row.get(key):
                failures.append(f"production_claim_checklist.{expected['check']}.{key} must be a non-empty string")
        if row != expected:
            failures.append(f"production_claim_checklist row mismatch for {expected['check']}")
    return failures


def validate_report_claim_scope(payload: dict, metadata: Any, top_level_claim_status: Any) -> list[str]:
    failures: list[str] = []
    expected_final_signoff = bool(
        payload.get("status") == "PASS"
        and top_level_claim_status == "PASS"
        and isinstance(metadata, dict)
        and metadata.get("require_production_claim") is True
    )
    expected_claim_status = FINAL_CLAIM_STATUS if expected_final_signoff else NON_FINAL_CLAIM_STATUS
    expected_evidence_scope = FINAL_EVIDENCE_SCOPE if expected_final_signoff else NON_FINAL_EVIDENCE_SCOPE
    if payload.get("claim_status") != expected_claim_status:
        failures.append(f"claim_status={payload.get('claim_status')} expected {expected_claim_status}")
    if payload.get("evidence_scope") != expected_evidence_scope:
        failures.append(f"evidence_scope={payload.get('evidence_scope')} expected {expected_evidence_scope}")
    if payload.get("final_production_signoff") is not expected_final_signoff:
        failures.append(f"final_production_signoff={payload.get('final_production_signoff')} expected {expected_final_signoff}")
    return failures


def validate_release_gate_report_payload(
    payload: Any,
    require_report_pass: bool = False,
    require_production_claim_pass: bool = False,
    expected_missing_checks: list[str] | None = None,
    require_clean_git_metadata: bool = False,
    verify_git_commit: bool = False,
    report_path: Path | None = None,
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

    metadata = payload.get("metadata")
    failures.extend(validate_report_claim_scope(payload, metadata, top_level_claim_status))
    if isinstance(audit, dict):
        failures.extend(validate_audit_checks(audit, top_level_missing))
    failures.extend(validate_production_claim_checklist(payload))

    failures.extend(validate_metadata(metadata, report_path=report_path))
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
        failed_gate_names = []
        for gate in gates:
            failures.extend(validate_gate_entry(gate))
            if isinstance(gate, dict) and isinstance(gate.get("name"), str):
                failures.extend(validate_live_github_release_gate_command(gate, metadata))
                failures.extend(validate_saved_reviewer_gate_command(gate, metadata))
                if gate["name"] in gate_names:
                    failures.append(f"duplicate gate name: {gate['name']}")
                else:
                    gate_names.add(gate["name"])
                if gate.get("status") == "FAIL":
                    failed_gate_names.append(gate["name"])
        failures.extend(validate_metadata_gate_presence(metadata, gate_names))
        failures.extend(validate_saved_reviewer_gate_presence(metadata, gate_names))
        if payload.get("status") == "PASS" and failed_gate_names:
            failures.append("passing release-gate report has failed gates: " + ",".join(failed_gate_names))
        if (
            payload.get("status") in {"PASS", "FAIL"}
            and isinstance(metadata, dict)
            and top_level_claim_status in {"PASS", "INCOMPLETE"}
        ):
            expected_status = (
                "PASS"
                if not failed_gate_names
                and (top_level_claim_status == "PASS" or metadata.get("require_production_claim") is not True)
                else "FAIL"
            )
            if payload.get("status") != expected_status:
                failures.append(
                    "release-gate status does not match gate and production-claim statuses: "
                    f"{payload.get('status')} != {expected_status}"
                )
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
        report_path=path,
    )
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print(f"release-gate report ok: {path}")
    print(f"status={payload['status']}")
    print(f"claim_status={payload['claim_status']}")
    print(f"evidence_scope={payload['evidence_scope']}")
    print(f"final_production_signoff={payload['final_production_signoff']}")
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
