#!/usr/bin/env python3
"""Audit final production evidence inputs before running the release gate."""

from __future__ import annotations

import argparse
import json
import shlex
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import release_gate
import run_production_gate
import verify_github_release
import verify_github_workflows


AUDITOR = "benchmark/audit_production_evidence.py"
EVIDENCE_SCOPE = "PRODUCTION_EVIDENCE_READINESS_AUDIT"
DEFAULT_OUT_JSON = Path("benchmark/results/release-gate/production-evidence-audit.json")
DEFAULT_OUT_MD = Path("benchmark/results/release-gate/production-evidence-audit.md")
AUDITED_CHECK_NAMES = release_gate.PRODUCTION_FINAL_BLOCKER_NAMES
READY_STATUS = release_gate.PRODUCTION_AUDIT_PASS_STATUS
INCOMPLETE_STATUS = release_gate.PRODUCTION_AUDIT_INCOMPLETE_STATUS


def is_utc_datetime(value: datetime) -> bool:
    return value.utcoffset() == timezone.utc.utcoffset(value)


def gate(name: str, status: str, detail: str, command: list[str] | None = None) -> release_gate.Gate:
    return release_gate.Gate(name=name, command=command, status=status, elapsed_seconds=0.0, detail=detail)


def missing_gate(name: str, detail: str) -> release_gate.Gate:
    return gate(name, release_gate.PRODUCTION_AUDIT_MISSING_STATUS, detail)


def timed_call(name: str, command: list[str], fn, *args, **kwargs) -> release_gate.Gate:
    started = time.perf_counter()
    try:
        status_code = fn(*args, **kwargs)
        status = "PASS" if status_code == 0 else "FAIL"
        detail = "saved verifier report passed" if status_code == 0 else "saved verifier report failed"
    except Exception as exc:  # noqa: BLE001 - audit reports exact verifier failure.
        status = "FAIL"
        detail = f"{type(exc).__name__}: {exc}"
    return release_gate.Gate(
        name=name,
        command=command,
        status=status,
        elapsed_seconds=time.perf_counter() - started,
        detail=detail,
    )


def verify_saved_github_workflow_gate(report: Path) -> release_gate.Gate:
    return timed_call(
        "Verify saved GitHub Actions workflow report",
        release_gate.saved_github_workflow_report_command(report, expected_commit=release_gate.git_commit()),
        verify_github_workflows.verify_saved_report,
        report,
        require_report_pass=True,
        expect_repo=release_gate.GITHUB_RELEASE_REPO,
        expect_branch=release_gate.GITHUB_ACTIONS_WORKFLOW_BRANCH,
        expect_commit=release_gate.git_commit(),
        expect_workflows=release_gate.GITHUB_ACTIONS_REQUIRED_WORKFLOWS,
    )


def verify_saved_github_release_gate(report: Path, tag: str) -> release_gate.Gate:
    return timed_call(
        "Verify saved stable GitHub release report",
        release_gate.saved_github_release_report_command(report, expected_tag=tag),
        verify_github_release.verify_saved_github_release_report,
        report,
        require_report_pass=True,
        require_stable_report=True,
        verify_files=True,
        expect_tag=tag,
        expect_repo=release_gate.GITHUB_RELEASE_REPO,
        verify_git_commit=True,
    )


def live_github_release_gate(tag: str, enabled: bool) -> release_gate.Gate:
    if not enabled:
        return missing_gate(
            "Verify GitHub release assets",
            "Live stable release verification was not requested; final gate must still run "
            "--verify-github-release with --github-release-kind stable.",
        )
    return release_gate.run_command(
        "Verify GitHub release assets",
        release_gate.live_github_release_report_command(tag, "stable"),
    )


def external_saved_reviewer_gates(args: argparse.Namespace) -> list[release_gate.Gate]:
    if not args.external_trial_verification_report and not args.external_evidence_package_verification_report:
        return [
            missing_gate(
                "Verify saved external L4 reviewer reports",
                "Both saved external trial and evidence-package reviewer reports are missing.",
            )
        ]
    if not args.external_trial_verification_report or not args.external_evidence_package_verification_report:
        return [
            missing_gate(
                "Verify saved external L4 reviewer reports",
                "Saved external trial and evidence-package reviewer reports must be supplied as a pair.",
            )
        ]
    if not args.external_trial_json or not args.external_trial_root or not args.external_evidence_package_dir:
        return [
            missing_gate(
                "Verify saved external L4 reviewer reports",
                "Saved reviewer reports require --external-trial-json, --external-trial-root, "
                "and --external-evidence-package-dir for binding checks.",
            )
        ]
    return run_production_gate.saved_reviewer_report_gates(args)


def combine_gates(name: str, gates: list[release_gate.Gate], missing_detail: str) -> release_gate.Gate:
    if not gates:
        return missing_gate(name, missing_detail)
    statuses = [item.status for item in gates]
    if all(status == "PASS" for status in statuses):
        return gate(name, "PASS", "; ".join(item.detail for item in gates if item.detail))
    if any(status == "FAIL" for status in statuses):
        return gate(name, "FAIL", "; ".join(item.detail for item in gates if item.detail))
    return missing_gate(name, "; ".join(item.detail for item in gates if item.detail) or missing_detail)


def build_gate_map(args: argparse.Namespace) -> tuple[dict[str, release_gate.Gate], list[release_gate.Gate]]:
    gates: list[release_gate.Gate] = []
    gate_map: dict[str, release_gate.Gate] = {}

    clean_gate = release_gate.validate_clean_git_worktree(release_gate.git_status_porcelain())
    gate_map["clean_git_worktree"] = clean_gate
    gates.append(clean_gate)

    l3_gate = release_gate.validate_l3_provenance_artifact()
    gate_map["l3_provenance_hashes"] = l3_gate
    gates.append(l3_gate)

    if args.github_workflow_verification_report:
        workflow_gate = verify_saved_github_workflow_gate(args.github_workflow_verification_report)
    else:
        workflow_gate = missing_gate(
            "Verify saved GitHub Actions workflow report",
            "Supply --github-workflow-verification-report for the final commit on main.",
        )
    gate_map["github_actions_workflow_verification"] = workflow_gate
    gates.append(workflow_gate)

    if args.external_trial_json and args.external_trial_root:
        trial_gate = release_gate.validate_external_trial_report(args.external_trial_json, args.external_trial_root)
    else:
        trial_gate = missing_gate(
            "Validate external L4 workflow trial report",
            "Supply --external-trial-json and --external-trial-root from a real external L4 trial.",
        )
    gate_map["external_l4_workflow_trial"] = trial_gate
    gates.append(trial_gate)

    if args.external_evidence_package_dir and args.external_trial_json:
        package_gate = release_gate.validate_external_evidence_package(
            args.external_evidence_package_dir,
            args.external_trial_json,
        )
    else:
        package_gate = missing_gate(
            "Validate external L4 evidence package",
            "Supply --external-evidence-package-dir together with --external-trial-json.",
        )
    gate_map["external_l4_evidence_package"] = package_gate
    gates.append(package_gate)

    reviewer_gates = external_saved_reviewer_gates(args)
    gate_map["external_l4_saved_reviewer_reports"] = combine_gates(
        "Verify saved external L4 reviewer reports",
        reviewer_gates,
        "Supply both saved external reviewer reports.",
    )
    gates.extend(reviewer_gates)

    live_release_gate = live_github_release_gate(args.github_release_tag, args.verify_live_github_release)
    gate_map["stable_github_release"] = live_release_gate
    gates.append(live_release_gate)

    if args.github_release_verification_report:
        release_report_gate = verify_saved_github_release_gate(
            args.github_release_verification_report,
            args.github_release_tag,
        )
    else:
        release_report_gate = missing_gate(
            "Verify saved stable GitHub release report",
            "Supply --github-release-verification-report produced for the final stable tag.",
        )
    gate_map["stable_github_release_saved_report"] = release_report_gate
    gates.append(release_report_gate)

    return gate_map, gates


def check_rows(gate_map: dict[str, release_gate.Gate]) -> list[dict[str, str]]:
    rows = []
    for name in AUDITED_CHECK_NAMES:
        gate_item = gate_map[name]
        guidance = release_gate.PRODUCTION_CHECKLIST_GUIDANCE[name]
        rows.append(
            {
                "name": name,
                "status": gate_item.status,
                "detail": gate_item.detail,
                "required_evidence": guidance["evidence"],
                "next_action": "No action needed for this check."
                if gate_item.status == "PASS"
                else guidance["next_action"],
            }
        )
    return rows


def input_paths(args: argparse.Namespace) -> dict[str, str | None]:
    return {
        "external_trial_json": absolute_path_text(args.external_trial_json) if args.external_trial_json else None,
        "external_trial_root": absolute_path_text(args.external_trial_root) if args.external_trial_root else None,
        "external_evidence_package_dir": absolute_path_text(args.external_evidence_package_dir)
        if args.external_evidence_package_dir
        else None,
        "external_trial_verification_report": absolute_path_text(args.external_trial_verification_report)
        if args.external_trial_verification_report
        else None,
        "external_evidence_package_verification_report": absolute_path_text(args.external_evidence_package_verification_report)
        if args.external_evidence_package_verification_report
        else None,
        "github_release_verification_report": absolute_path_text(args.github_release_verification_report)
        if args.github_release_verification_report
        else None,
        "github_workflow_verification_report": absolute_path_text(args.github_workflow_verification_report)
        if args.github_workflow_verification_report
        else None,
    }


def absolute_path_text(path: Path) -> str:
    return str(path.expanduser().resolve(strict=False))


def final_wrapper_command(args: argparse.Namespace) -> list[str] | None:
    required = [
        args.external_trial_json,
        args.external_trial_root,
        args.external_evidence_package_dir,
        args.external_trial_verification_report,
        args.external_evidence_package_verification_report,
        args.github_release_verification_report,
        args.github_workflow_verification_report,
    ]
    if any(value is None for value in required):
        return None
    return [
        sys.executable,
        AUDITOR.replace("audit_production_evidence.py", "run_production_gate.py"),
        "--external-trial-json",
        absolute_path_text(args.external_trial_json),
        "--external-trial-root",
        absolute_path_text(args.external_trial_root),
        "--external-evidence-package-dir",
        absolute_path_text(args.external_evidence_package_dir),
        "--external-trial-verification-report",
        absolute_path_text(args.external_trial_verification_report),
        "--external-evidence-package-verification-report",
        absolute_path_text(args.external_evidence_package_verification_report),
        "--github-release-verification-report",
        absolute_path_text(args.github_release_verification_report),
        "--github-workflow-verification-report",
        absolute_path_text(args.github_workflow_verification_report),
        "--github-release-tag",
        args.github_release_tag,
    ]


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    gate_map, gates = build_gate_map(args)
    checks = check_rows(gate_map)
    missing_or_failed = [row["name"] for row in checks if row["status"] != "PASS"]
    failed = [row["name"] for row in checks if row["status"] == "FAIL"]
    production_status = READY_STATUS if not missing_or_failed else INCOMPLETE_STATUS
    return {
        "schema_version": 1,
        "auditor": AUDITOR,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "claim_status": release_gate.NON_FINAL_CLAIM_STATUS,
        "evidence_scope": EVIDENCE_SCOPE,
        "final_production_signoff": release_gate.NON_FINAL_PRODUCTION_SIGNOFF,
        "status": "FAIL" if failed else "PASS",
        "production_claim_status": production_status,
        "missing_or_failed_checks": missing_or_failed,
        "failed_checks": failed,
        "checks": checks,
        "gates": [asdict(item) for item in gates],
        "metadata": {
            "git_commit": release_gate.git_commit(),
            "git_dirty": bool(release_gate.git_status_porcelain()),
            "git_status": release_gate.git_status_porcelain(),
            "argv": canonical_argv(args),
            "github_release_tag": args.github_release_tag,
            "verify_live_github_release": args.verify_live_github_release,
            "inputs": input_paths(args),
            "final_wrapper_command": final_wrapper_command(args),
        },
    }


def markdown_cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_markdown(payload: dict[str, Any], out_json: Path) -> str:
    metadata = payload["metadata"]
    lines = [
        "# Production Evidence Readiness Audit",
        "",
        f"- status: `{payload['status']}`",
        f"- production_claim_status: `{payload['production_claim_status']}`",
        f"- claim_status: `{payload['claim_status']}`",
        f"- evidence_scope: `{payload['evidence_scope']}`",
        f"- final_production_signoff: `{payload['final_production_signoff']}`",
        f"- json: `{out_json}`",
        f"- generated_at_utc: `{payload['generated_at_utc']}`",
        f"- git_commit: `{metadata['git_commit']}`",
        f"- git_dirty: `{metadata['git_dirty']}`",
        f"- github_release_tag: `{metadata['github_release_tag']}`",
        "",
        "This audit is not a production signoff. It only checks whether the final release-gate inputs "
        "are present and currently reusable.",
        "",
        "## Checks",
        "",
        "| Check | Status | Detail | Required Evidence | Next Action |",
        "|---|---:|---|---|---|",
    ]
    for row in payload["checks"]:
        lines.append(
            "| "
            f"{markdown_cell(row['name'])} | "
            f"{markdown_cell(row['status'])} | "
            f"{markdown_cell(row['detail'])} | "
            f"{markdown_cell(row['required_evidence'])} | "
            f"{markdown_cell(row['next_action'])} |"
        )
    lines.extend(["", "## Inputs", "", "| Name | Path |", "|---|---|"])
    for name, path in metadata["inputs"].items():
        lines.append(f"| {markdown_cell(name)} | {markdown_cell(path or '')} |")
    command = metadata.get("final_wrapper_command")
    if command:
        lines.extend(["", "## Final Wrapper Command", "", f"`{shlex.join(command)}`"])
    lines.extend(
        [
            "",
            "The final production claim still requires `benchmark/run_production_gate.py` and a saved "
            "`benchmark/verify_release_gate_report.py` PASS report with `--expect-missing-checks none`.",
        ]
    )
    return "\n".join(lines)


def write_reports(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.out_md.parent.mkdir(parents=True, exist_ok=True)
    args.out_md.write_text(render_markdown(payload, args.out_json) + "\n", encoding="utf-8")


def canonical_argv(args: argparse.Namespace) -> list[str]:
    argv = [AUDITOR]
    for flag, value in [
        ("--external-trial-json", args.external_trial_json),
        ("--external-trial-root", args.external_trial_root),
        ("--external-evidence-package-dir", args.external_evidence_package_dir),
        ("--external-trial-verification-report", args.external_trial_verification_report),
        ("--external-evidence-package-verification-report", args.external_evidence_package_verification_report),
        ("--github-release-verification-report", args.github_release_verification_report),
        ("--github-workflow-verification-report", args.github_workflow_verification_report),
        ("--github-release-tag", args.github_release_tag),
        ("--out-json", args.out_json),
        ("--out-md", args.out_md),
    ]:
        if value is not None:
            if isinstance(value, Path):
                argv.extend([flag, absolute_path_text(value)])
            else:
                argv.extend([flag, str(value)])
    if args.verify_live_github_release:
        argv.append("--verify-live-github-release")
    if args.require_ready:
        argv.append("--require-ready")
    return argv


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


def normalized_path(path: Path) -> str:
    return str(path.expanduser().resolve(strict=False))


def audit_report_argv_issues(
    argv: list[str],
    metadata: dict[str, Any],
    report_path: Path | None = None,
) -> list[str]:
    failures: list[str] = []
    if not argv:
        return ["metadata.argv must be non-empty"]
    if argv[0] != AUDITOR:
        failures.append(f"metadata.argv[0]={argv[0]}")
    if "--verify-report" in argv:
        failures.append("metadata.argv must not include --verify-report for a generated audit report")
    for flag in ["--verify-live-github-release", "--require-ready"]:
        if argv.count(flag) > 1:
            failures.append(f"metadata.argv has duplicate {flag}")
    if bool(metadata.get("verify_live_github_release")) != ("--verify-live-github-release" in argv):
        failures.append("metadata.verify_live_github_release must match metadata.argv --verify-live-github-release")

    github_release_tag = metadata.get("github_release_tag")
    tag_values = argv_values(argv, "--github-release-tag")
    if len(tag_values) != 1:
        failures.append("metadata.argv must include exactly one --github-release-tag")
    elif tag_values[0] is None:
        failures.append("metadata.argv --github-release-tag must include a value")
    elif github_release_tag != tag_values[0]:
        failures.append(f"metadata.github_release_tag must match metadata.argv --github-release-tag {tag_values[0]}")

    inputs = metadata.get("inputs")
    if not isinstance(inputs, dict):
        failures.append("metadata.inputs must be an object")
        inputs = {}
    path_flags = [
        ("--external-trial-json", "external_trial_json"),
        ("--external-trial-root", "external_trial_root"),
        ("--external-evidence-package-dir", "external_evidence_package_dir"),
        ("--external-trial-verification-report", "external_trial_verification_report"),
        ("--external-evidence-package-verification-report", "external_evidence_package_verification_report"),
        ("--github-release-verification-report", "github_release_verification_report"),
        ("--github-workflow-verification-report", "github_workflow_verification_report"),
    ]
    for flag, input_key in path_flags:
        expected = inputs.get(input_key)
        values = argv_values(argv, flag)
        if expected is None:
            if values:
                failures.append(f"metadata.argv must not include {flag} when metadata.inputs.{input_key} is null")
            continue
        if not isinstance(expected, str) or not expected.strip():
            failures.append(f"metadata.inputs.{input_key} must be a non-empty string or null")
            continue
        if len(values) != 1:
            failures.append(f"metadata.argv must include exactly one {flag}")
            continue
        value = values[0]
        if value is None:
            failures.append(f"metadata.argv {flag} must include a value")
            continue
        if not Path(value).is_absolute():
            failures.append(f"metadata.argv {flag} must use an absolute path: {value}")
        if normalized_path(Path(value)) != normalized_path(Path(expected)):
            failures.append(f"metadata.inputs.{input_key} must match metadata.argv {flag} {value}")

    for flag in ["--out-json", "--out-md"]:
        values = argv_values(argv, flag)
        if len(values) != 1:
            failures.append(f"metadata.argv must include exactly one {flag}")
            continue
        value = values[0]
        if value is None:
            failures.append(f"metadata.argv {flag} must include a value")
            continue
        if not Path(value).is_absolute():
            failures.append(f"metadata.argv {flag} must use an absolute path: {value}")
        if flag == "--out-json" and report_path is not None:
            if normalized_path(Path(value)) != normalized_path(report_path):
                failures.append(f"metadata.argv --out-json must match verified audit report path: {value}")
    return failures


def replay_args_from_metadata(metadata: dict[str, Any]) -> argparse.Namespace:
    argv = metadata["argv"]
    args = parse_args(argv[1:])
    args.verify_report = None
    return args


def compare_recomputed_payload(payload: dict[str, Any], recomputed: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for key in ["status", "production_claim_status", "missing_or_failed_checks", "failed_checks"]:
        if payload.get(key) != recomputed.get(key):
            failures.append(f"{key} changed after recomputing audit evidence")
    metadata = payload.get("metadata")
    recomputed_metadata = recomputed.get("metadata")
    if isinstance(metadata, dict) and isinstance(recomputed_metadata, dict):
        for key in [
            "github_release_tag",
            "verify_live_github_release",
            "inputs",
            "final_wrapper_command",
        ]:
            if metadata.get(key) != recomputed_metadata.get(key):
                failures.append(f"metadata.{key} changed after recomputing audit evidence")
    else:
        failures.append("metadata must be objects before recomputing audit evidence")
    saved_checks = payload.get("checks")
    recomputed_checks = recomputed.get("checks")
    if isinstance(saved_checks, list) and isinstance(recomputed_checks, list):
        saved_statuses = [
            (item.get("name"), item.get("status")) for item in saved_checks if isinstance(item, dict)
        ]
        recomputed_statuses = [
            (item.get("name"), item.get("status")) for item in recomputed_checks if isinstance(item, dict)
        ]
        if saved_statuses != recomputed_statuses:
            failures.append("check statuses changed after recomputing audit evidence")
    else:
        failures.append("checks must be lists before recomputing audit evidence")
    return failures


def verify_saved_files(payload: dict[str, Any], report_path: Path | None = None) -> list[str]:
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        return ["metadata must be an object before file recheck"]
    argv = metadata.get("argv")
    if not isinstance(argv, list) or not all(isinstance(item, str) for item in argv):
        return ["metadata.argv must be a string list before file recheck"]
    failures = audit_report_argv_issues(argv, metadata, report_path=report_path)
    git_commit = metadata.get("git_commit")
    if git_commit != release_gate.git_commit():
        failures.append(f"metadata.git_commit does not match current git commit: {git_commit}")
    if payload.get("production_claim_status") == READY_STATUS:
        if metadata.get("git_dirty") is not False:
            failures.append("metadata.git_dirty must be false for ready audit reports")
        if metadata.get("git_status") != []:
            failures.append("metadata.git_status must be empty for ready audit reports")
    if failures:
        return failures
    replay_args = replay_args_from_metadata(metadata)
    recomputed = build_payload(replay_args)
    return compare_recomputed_payload(payload, recomputed)


def validate_payload(
    payload: object,
    require_ready: bool = False,
    verify_files: bool = False,
    report_path: Path | None = None,
) -> list[str]:
    failures: list[str] = []
    if not isinstance(payload, dict):
        return ["production evidence audit report must be a JSON object"]
    if require_ready and not verify_files:
        failures.append("--require-ready requires --verify-report-files")
    if payload.get("schema_version") != 1:
        failures.append(f"schema_version={payload.get('schema_version')}")
    if payload.get("auditor") != AUDITOR:
        failures.append(f"auditor={payload.get('auditor')}")
    if payload.get("claim_status") != release_gate.NON_FINAL_CLAIM_STATUS:
        failures.append(f"claim_status={payload.get('claim_status')}")
    if payload.get("evidence_scope") != EVIDENCE_SCOPE:
        failures.append(f"evidence_scope={payload.get('evidence_scope')}")
    if payload.get("final_production_signoff") is not release_gate.NON_FINAL_PRODUCTION_SIGNOFF:
        failures.append("final_production_signoff must be false")
    if payload.get("status") not in {"PASS", "FAIL"}:
        failures.append(f"status={payload.get('status')}")
    if payload.get("production_claim_status") not in release_gate.PRODUCTION_CLAIM_STATUSES:
        failures.append(f"production_claim_status={payload.get('production_claim_status')}")
    generated_at = payload.get("generated_at_utc")
    if isinstance(generated_at, str):
        try:
            parsed = datetime.fromisoformat(generated_at)
            if parsed.tzinfo is None or not is_utc_datetime(parsed):
                failures.append("generated_at_utc must be UTC")
        except ValueError:
            failures.append(f"generated_at_utc is invalid: {generated_at}")
    else:
        failures.append("generated_at_utc must be a string")
    checks = payload.get("checks")
    if not isinstance(checks, list):
        failures.append("checks must be a list")
        checks = []
    check_names = [check.get("name") for check in checks if isinstance(check, dict)]
    if check_names != AUDITED_CHECK_NAMES:
        failures.append(f"checks names={check_names}")
    observed_missing = [
        check.get("name")
        for check in checks
        if isinstance(check, dict) and check.get("status") != release_gate.PRODUCTION_AUDIT_PASS_STATUS
    ]
    if payload.get("missing_or_failed_checks") != observed_missing:
        failures.append("missing_or_failed_checks do not match checks")
    for check in checks:
        if not isinstance(check, dict):
            failures.append("check entries must be objects")
            continue
        if check.get("status") not in release_gate.PRODUCTION_AUDIT_CHECK_STATUSES:
            failures.append(f"{check.get('name')}.status={check.get('status')}")
        for key in ["detail", "required_evidence", "next_action"]:
            if not isinstance(check.get(key), str) or not check.get(key):
                failures.append(f"{check.get('name')}.{key} must be a non-empty string")
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        failures.append("metadata must be an object")
    elif not isinstance(metadata.get("argv"), list) or not all(isinstance(item, str) for item in metadata["argv"]):
        failures.append("metadata.argv must be a string list")
    if verify_files and not failures:
        failures.extend(verify_saved_files(payload, report_path=report_path))
    if require_ready:
        if payload.get("status") != "PASS":
            failures.append(f"status is not PASS: {payload.get('status')}")
        if payload.get("production_claim_status") != READY_STATUS:
            failures.append(f"production_claim_status is not PASS: {payload.get('production_claim_status')}")
        if payload.get("missing_or_failed_checks") != []:
            failures.append("missing_or_failed_checks is not empty")
    return failures


def verify_report(path: Path, require_ready: bool = False, verify_files: bool = False) -> int:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - report parse failure.
        print(f"FAIL: cannot read audit report: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    failures = validate_payload(
        payload,
        require_ready=require_ready,
        verify_files=verify_files,
        report_path=path,
    )
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print(f"production evidence audit report ok: {path}")
    print(f"status={payload['status']}")
    print(f"production_claim_status={payload['production_claim_status']}")
    print("missing_or_failed_checks=" + ",".join(payload["missing_or_failed_checks"]))
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--external-trial-json", type=Path)
    parser.add_argument("--external-trial-root", type=Path)
    parser.add_argument("--external-evidence-package-dir", type=Path)
    parser.add_argument("--external-trial-verification-report", type=Path)
    parser.add_argument("--external-evidence-package-verification-report", type=Path)
    parser.add_argument("--github-release-verification-report", type=Path)
    parser.add_argument("--github-workflow-verification-report", type=Path)
    parser.add_argument("--github-release-tag", default=release_gate.DEFAULT_STABLE_RELEASE_TAG)
    parser.add_argument("--verify-live-github-release", action="store_true")
    parser.add_argument("--out-json", type=Path, default=DEFAULT_OUT_JSON)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--require-ready", action="store_true")
    parser.add_argument("--verify-report-files", action="store_true", help="Recompute audit gates from saved metadata paths")
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args(argv)
    if args.github_release_tag and not release_gate.is_stable_release_tag(args.github_release_tag):
        parser.error(
            f"--github-release-tag must be a stable release tag like {release_gate.DEFAULT_STABLE_RELEASE_TAG}"
        )
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.verify_report:
        return verify_report(
            args.verify_report,
            require_ready=args.require_ready,
            verify_files=args.verify_report_files,
        )
    payload = build_payload(args)
    write_reports(args, payload)
    print(f"wrote {args.out_json}")
    print(f"wrote {args.out_md}")
    print(f"status={payload['status']}")
    print(f"production_claim_status={payload['production_claim_status']}")
    if args.require_ready and (
        payload["status"] != "PASS" or payload["production_claim_status"] != READY_STATUS
    ):
        return 1
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
