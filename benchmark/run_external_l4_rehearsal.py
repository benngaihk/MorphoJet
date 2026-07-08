#!/usr/bin/env python3
"""Run a reproducible internal rehearsal of the external L4 evidence chain."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import prepare_external_l4_trial
import release_gate


ROOT = Path(__file__).resolve().parents[1]
RUNNER = "benchmark/run_external_l4_rehearsal.py"
DEFAULT_TEMPLATE = ROOT / "benchmark/handoff/cellbindb_supported_columns.json"
DEFAULT_MORPHOJET_OBJECTS = ROOT / "benchmark/results/cellbindb/oracle-full/morphojet/Objects.csv"
DEFAULT_CELLPROFILER_CELLS = ROOT / "benchmark/results/cellbindb/oracle-full/cellprofiler/Cells.csv"
DEFAULT_PACKAGE_NAME = "cellbindb-external-rehearsal"
EVIDENCE_SCOPE = "EXTERNAL_L4_INTERNAL_REHEARSAL"
COMMAND_SEQUENCE = [
    "verify_plan",
    "validate_manifest",
    "check_readiness",
    "verify_readiness",
    "run_trial",
    "verify_trial",
    "verify_trial_report",
    "package_evidence",
    "verify_package",
    "verify_package_report",
    "local_evidence_preflight",
    "verify_local_evidence_preflight",
]
SKIPPED_FINAL_COMMANDS = [
    "verify_stable_release",
    "verify_stable_release_report",
    "final_production_gate",
    "verify_final_production_report",
]


class RehearsalError(Exception):
    """Raised when the internal rehearsal cannot be completed."""


@dataclass
class CommandResult:
    name: str
    command: list[str]
    status: str
    elapsed_seconds: float
    stdout: str
    stderr: str


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RehearsalError(f"{path} must contain a JSON object")
    return data


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def file_summary(path: Path) -> dict[str, Any]:
    summary: dict[str, Any] = {"path": str(path.resolve()), "exists": path.is_file()}
    if path.is_file():
        summary["size_bytes"] = path.stat().st_size
        summary["sha256"] = release_gate.sha256_file(path)
    else:
        summary["size_bytes"] = None
        summary["sha256"] = None
    return summary


def is_utc_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() == timedelta(0)


def file_summary_failures(name: str, summary: Any, require_exists: bool) -> list[str]:
    failures: list[str] = []
    if not isinstance(summary, dict):
        return [f"{name} must be an object"]
    path = summary.get("path")
    if not isinstance(path, str) or not path:
        failures.append(f"{name}.path must be a non-empty string")
    elif not Path(path).is_absolute():
        failures.append(f"{name}.path must be absolute")
    exists = summary.get("exists")
    if not isinstance(exists, bool):
        failures.append(f"{name}.exists must be boolean")
    elif require_exists and not exists:
        failures.append(f"{name}.exists must be true")
    size = summary.get("size_bytes")
    digest = summary.get("sha256")
    if exists:
        if not isinstance(size, int) or size < 0:
            failures.append(f"{name}.size_bytes must be a non-negative integer")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            failures.append(f"{name}.sha256 must be a SHA-256 digest")
    else:
        if size is not None:
            failures.append(f"{name}.size_bytes must be null when missing")
        if digest is not None:
            failures.append(f"{name}.sha256 must be null when missing")
    return failures


def verify_file_summary(name: str, summary: dict[str, Any]) -> list[str]:
    failures = file_summary_failures(name, summary, require_exists=True)
    if failures:
        return failures
    path = Path(summary["path"])
    if not path.is_file():
        return [f"{name}.path does not exist: {path}"]
    if summary.get("size_bytes") != path.stat().st_size:
        failures.append(f"{name}.size_bytes does not match current file")
    if summary.get("sha256") != release_gate.sha256_file(path):
        failures.append(f"{name}.sha256 does not match current file")
    return failures


def rehearsal_external_evidence() -> dict[str, Any]:
    reviewed_at = datetime.now(timezone.utc) + timedelta(hours=1)
    return {
        "lab_or_org": "Internal MorphoJet rehearsal only",
        "workflow_owner": "MorphoJet release engineering rehearsal",
        "dataset_name": "CellBinDB full supported-column rehearsal",
        "dataset_source": "benchmark/results/cellbindb/oracle-full committed artifacts",
        "downstream_workflow": "Supported CellProfiler-style wide CSV comparison and contract check",
        "execution_environment": "Local CI-compatible rehearsal runner",
        "reviewer_name_or_role": "Internal rehearsal reviewer",
        "reviewed_at_utc": reviewed_at.isoformat(),
        "signoff_statement": (
            "Internal rehearsal only: this validates the evidence-chain mechanics and is not external L4 signoff."
        ),
        "manual_csv_editing": False,
        "acceptance_criteria": [
            "The MorphoJet Objects.csv is copied into the generated workspace without manual CSV edits.",
            "The supported wide CSV comparison passes against the expected CellProfiler Cells.csv.",
            "The evidence package and saved local preflight report verify with file and gate rechecks.",
        ],
    }


def rehearsal_template(source_template: Path) -> dict[str, Any]:
    template = load_json(source_template)
    template["external_evidence"] = rehearsal_external_evidence()
    template.setdefault("description", "")
    template["description"] = (
        f"{template['description']} Internal rehearsal only; not final external L4 evidence."
    ).strip()
    return template


def prepare_rehearsal_workspace(
    workspace: Path,
    source_template: Path,
    package_name: str,
    overwrite: bool,
) -> dict[str, Any]:
    if workspace.exists() and overwrite:
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    prepared_template = workspace / "internal_rehearsal_template.json"
    write_json(prepared_template, rehearsal_template(source_template))
    return prepare_external_l4_trial.prepare_workspace(
        prepared_template,
        workspace,
        package_name=package_name,
    )


def copy_inputs(workspace: Path, morphojet_objects: Path, cellprofiler_cells: Path) -> dict[str, str]:
    if not morphojet_objects.is_file():
        raise RehearsalError(f"--morphojet-objects is not a file: {morphojet_objects}")
    if not cellprofiler_cells.is_file():
        raise RehearsalError(f"--cellprofiler-cells is not a file: {cellprofiler_cells}")
    objects_target = workspace / "morphojet/Objects.csv"
    cells_target = workspace / "cellprofiler/Cells.csv"
    objects_target.parent.mkdir(parents=True, exist_ok=True)
    cells_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(morphojet_objects, objects_target)
    shutil.copy2(cellprofiler_cells, cells_target)
    return {
        "morphojet_objects_csv": str(objects_target.resolve()),
        "cellprofiler_cells_csv": str(cells_target.resolve()),
    }


def input_file_summaries(input_paths: dict[str, str]) -> dict[str, dict[str, Any]]:
    return {name: file_summary(Path(path)) for name, path in input_paths.items()}


def output_file_summaries(workspace: Path, package_name: str) -> dict[str, dict[str, Any]]:
    package_dir = workspace / "evidence-package" / package_name
    return {
        "trial_plan": file_summary(workspace / "trial_plan.json"),
        "readiness_report": file_summary(workspace / "readiness.json"),
        "handoff_trial_json": file_summary(workspace / "handoff_trial.json"),
        "handoff_trial_verification": file_summary(workspace / "handoff_trial-verification.json"),
        "evidence_package_verification": file_summary(workspace / "evidence-package-verification.json"),
        "local_evidence_preflight": file_summary(workspace / "local-evidence-preflight.json"),
        "package_artifact_manifest": file_summary(package_dir / "artifact_manifest.json"),
        "package_readme": file_summary(package_dir / "README.md"),
        "package_readme_zh": file_summary(package_dir / "README.zh-CN.md"),
    }


def run_command(name: str, command: list[str]) -> CommandResult:
    started = time.perf_counter()
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    elapsed = time.perf_counter() - started
    return CommandResult(
        name=name,
        command=command,
        status="PASS" if completed.returncode == 0 else "FAIL",
        elapsed_seconds=elapsed,
        stdout=completed.stdout[-4000:],
        stderr=completed.stderr[-4000:],
    )


def run_command_sequence(plan: dict[str, Any]) -> list[CommandResult]:
    commands = plan.get("commands")
    if not isinstance(commands, dict):
        raise RehearsalError("trial plan must contain commands")
    results = []
    for name in COMMAND_SEQUENCE:
        command = commands.get(name)
        if not isinstance(command, list) or not all(isinstance(item, str) and item for item in command):
            raise RehearsalError(f"trial plan command is missing or invalid: {name}")
        result = run_command(name, command)
        results.append(result)
        if result.status != "PASS":
            raise RehearsalError(f"{name} failed; see rehearsal summary or stderr")
    return results


def require_clean_git_worktree() -> None:
    status = release_gate.git_status_porcelain()
    if status:
        raise RehearsalError("internal rehearsal requires a clean git worktree before generating evidence")


def read_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return load_json(path)


def build_summary(
    args: argparse.Namespace,
    plan: dict[str, Any],
    input_paths: dict[str, str],
    command_results: list[CommandResult],
) -> dict[str, Any]:
    workspace = args.workspace.resolve()
    local_preflight = read_optional_json(workspace / "local-evidence-preflight.json")
    package_dir = workspace / "evidence-package" / args.package_name
    git_status = release_gate.git_status_porcelain()
    return {
        "schema_version": 1,
        "runner": RUNNER,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "metadata": {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "git_commit": release_gate.git_commit(),
            "git_dirty": bool(git_status),
            "git_status": git_status,
            "argv": runner_argv(args, resolve_paths=True),
        },
        "argv": runner_argv(args, resolve_paths=True),
        "status": "PASS" if all(result.status == "PASS" for result in command_results) else "FAIL",
        "claim_status": release_gate.NON_FINAL_CLAIM_STATUS,
        "evidence_scope": EVIDENCE_SCOPE,
        "final_production_signoff": release_gate.NON_FINAL_PRODUCTION_SIGNOFF,
        "final_evidence_acceptable": False,
        "workspace": str(workspace),
        "source_template": str(args.template.resolve()),
        "prepared_template": str((workspace / "internal_rehearsal_template.json").resolve()),
        "package_name": args.package_name,
        "input_files": input_paths,
        "input_file_summaries": input_file_summaries(input_paths),
        "trial_plan": str((workspace / "trial_plan.json").resolve()),
        "handoff_trial_json": str((workspace / "handoff_trial.json").resolve()),
        "evidence_package_dir": str(package_dir.resolve()),
        "local_evidence_preflight_json": str((workspace / "local-evidence-preflight.json").resolve()),
        "output_files": output_file_summaries(workspace, args.package_name),
        "local_evidence_preflight_status": local_preflight.get("status") if local_preflight else None,
        "validated_checks": local_preflight.get("validated_checks") if local_preflight else [],
        "skipped_final_checks": local_preflight.get("skipped_final_checks") if local_preflight else [],
        "skipped_final_commands": list(SKIPPED_FINAL_COMMANDS),
        "production_claim_blockers": plan.get("production_claim_blockers", []),
        "commands": [asdict(result) for result in command_results],
    }


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# External L4 Internal Rehearsal",
        "",
        "This is not a final production signoff and is not external L4 evidence by itself.",
        "",
        "## Summary",
        "",
        f"- status: `{summary['status']}`",
        f"- claim_status: `{summary['claim_status']}`",
        f"- evidence_scope: `{summary['evidence_scope']}`",
        f"- final_production_signoff: `{summary['final_production_signoff']}`",
        f"- final_evidence_acceptable: `{summary['final_evidence_acceptable']}`",
        f"- workspace: `{summary['workspace']}`",
        f"- local_evidence_preflight_status: `{summary['local_evidence_preflight_status']}`",
        "",
        "## Commands",
        "",
        "| Step | Status | Seconds |",
        "|---|---:|---:|",
    ]
    for command in summary["commands"]:
        lines.append(f"| {command['name']} | {command['status']} | {command['elapsed_seconds']:.3f} |")
    lines.extend(
        [
            "",
            "## Remaining Final Checks",
            "",
            "The stable GitHub release, saved stable-release verifier report, final production gate, "
            "and final saved-report verifier are intentionally skipped by this rehearsal.",
            "",
        ]
    )
    for check in summary["skipped_final_checks"]:
        lines.append(f"- `{check}`")
    return "\n".join(lines)


def validate_saved_summary(payload: dict[str, Any], *, require_pass: bool = False) -> list[str]:
    failures: list[str] = []
    if payload.get("schema_version") != 1:
        failures.append(f"schema_version={payload.get('schema_version')}")
    if payload.get("runner") != RUNNER:
        failures.append(f"runner={payload.get('runner')}")
    status = payload.get("status")
    if status not in {"PASS", "FAIL"}:
        failures.append(f"status={status}")
    if require_pass and status != "PASS":
        failures.append(f"status is not PASS: {status}")
    if payload.get("claim_status") != release_gate.NON_FINAL_CLAIM_STATUS:
        failures.append(f"claim_status={payload.get('claim_status')}")
    if payload.get("evidence_scope") != EVIDENCE_SCOPE:
        failures.append(f"evidence_scope={payload.get('evidence_scope')}")
    if payload.get("final_production_signoff") is not release_gate.NON_FINAL_PRODUCTION_SIGNOFF:
        failures.append(f"final_production_signoff={payload.get('final_production_signoff')}")
    if payload.get("final_evidence_acceptable") is not False:
        failures.append(f"final_evidence_acceptable={payload.get('final_evidence_acceptable')}")
    if payload.get("skipped_final_commands") != SKIPPED_FINAL_COMMANDS:
        failures.append("skipped_final_commands does not match expected final skips")
    commands = payload.get("commands")
    if not isinstance(commands, list):
        failures.append("commands must be a list")
    else:
        names = [command.get("name") for command in commands if isinstance(command, dict)]
        if names != COMMAND_SEQUENCE:
            failures.append("commands do not match expected rehearsal sequence")
        for index, command in enumerate(commands):
            if not isinstance(command, dict):
                failures.append(f"commands[{index}] must be an object")
                continue
            command_status = command.get("status")
            if command_status not in {"PASS", "FAIL"}:
                failures.append(f"commands[{index}].status={command_status}")
            if status == "PASS" and command_status != "PASS":
                failures.append(f"commands[{index}] must be PASS when summary is PASS")
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        failures.append("metadata must be an object")
    else:
        if not is_utc_timestamp(metadata.get("generated_at_utc")):
            failures.append("metadata.generated_at_utc must be UTC")
        if not release_gate.is_git_commit(metadata.get("git_commit")):
            failures.append("metadata.git_commit must be a git commit")
        if metadata.get("git_dirty") is not False:
            failures.append("metadata.git_dirty must be false")
        if metadata.get("git_status") != []:
            failures.append("metadata.git_status must be empty")
        argv = metadata.get("argv")
        if not isinstance(argv, list) or RUNNER not in argv:
            failures.append("metadata.argv must contain the runner command")
    for key in ["workspace", "source_template", "prepared_template", "trial_plan", "handoff_trial_json", "evidence_package_dir", "local_evidence_preflight_json"]:
        value = payload.get(key)
        if not isinstance(value, str) or not value:
            failures.append(f"{key} must be a non-empty string")
        elif not Path(value).is_absolute():
            failures.append(f"{key} must be absolute")
    input_summaries = payload.get("input_file_summaries")
    if not isinstance(input_summaries, dict):
        failures.append("input_file_summaries must be an object")
    else:
        for name in ["morphojet_objects_csv", "cellprofiler_cells_csv"]:
            failures.extend(file_summary_failures(f"input_file_summaries.{name}", input_summaries.get(name), require_exists=status == "PASS"))
    output_files = payload.get("output_files")
    if not isinstance(output_files, dict):
        failures.append("output_files must be an object")
    else:
        for name in [
            "trial_plan",
            "readiness_report",
            "handoff_trial_json",
            "handoff_trial_verification",
            "evidence_package_verification",
            "local_evidence_preflight",
            "package_artifact_manifest",
            "package_readme",
            "package_readme_zh",
        ]:
            failures.extend(file_summary_failures(f"output_files.{name}", output_files.get(name), require_exists=status == "PASS"))
    return failures


def verify_saved_summary_files(payload: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    input_summaries = payload.get("input_file_summaries")
    if isinstance(input_summaries, dict):
        for name, summary in input_summaries.items():
            if isinstance(summary, dict):
                failures.extend(verify_file_summary(f"input_file_summaries.{name}", summary))
    output_files = payload.get("output_files")
    if isinstance(output_files, dict):
        for name, summary in output_files.items():
            if isinstance(summary, dict):
                failures.extend(verify_file_summary(f"output_files.{name}", summary))
    local_preflight_path = payload.get("local_evidence_preflight_json")
    if isinstance(local_preflight_path, str) and Path(local_preflight_path).is_file():
        local_preflight = load_json(Path(local_preflight_path))
        if payload.get("local_evidence_preflight_status") != local_preflight.get("status"):
            failures.append("local_evidence_preflight_status must match saved local preflight report")
        if payload.get("validated_checks") != local_preflight.get("validated_checks"):
            failures.append("validated_checks must match saved local preflight report")
        if payload.get("skipped_final_checks") != local_preflight.get("skipped_final_checks"):
            failures.append("skipped_final_checks must match saved local preflight report")
    return failures


def verify_report(path: Path, *, verify_files: bool, require_pass: bool) -> int:
    payload = load_json(path)
    failures = validate_saved_summary(payload, require_pass=require_pass)
    if require_pass and not verify_files:
        failures.append("--require-report-pass requires --verify-report-files")
    if verify_files:
        failures.extend(verify_saved_summary_files(payload))
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print(f"external L4 rehearsal report ok: {path}")
    print(f"status={payload['status']}")
    print(f"claim_status={payload['claim_status']}")
    print(f"evidence_scope={payload['evidence_scope']}")
    print(f"final_production_signoff={payload['final_production_signoff']}")
    print(f"final_evidence_acceptable={payload['final_evidence_acceptable']}")
    return 0


def runner_argv(args: argparse.Namespace, resolve_paths: bool = False) -> list[str]:
    def path_value(path: Path) -> str:
        return str(path.resolve()) if resolve_paths else str(path)

    argv = [
        RUNNER,
        "--workspace",
        path_value(args.workspace),
        "--template",
        path_value(args.template),
        "--morphojet-objects",
        path_value(args.morphojet_objects),
        "--cellprofiler-cells",
        path_value(args.cellprofiler_cells),
        "--package-name",
        args.package_name,
    ]
    if args.json_out is not None:
        argv.extend(["--json-out", path_value(args.json_out)])
    if args.md_out is not None:
        argv.extend(["--md-out", path_value(args.md_out)])
    if args.overwrite:
        argv.append("--overwrite")
    return argv


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--morphojet-objects", type=Path, default=DEFAULT_MORPHOJET_OBJECTS)
    parser.add_argument("--cellprofiler-cells", type=Path, default=DEFAULT_CELLPROFILER_CELLS)
    parser.add_argument("--package-name", default=DEFAULT_PACKAGE_NAME)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--md-out", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--verify-report", type=Path)
    parser.add_argument("--verify-report-files", action="store_true")
    parser.add_argument("--require-report-pass", action="store_true")
    args = parser.parse_args(argv)
    if args.verify_report is None and args.workspace is None:
        parser.error("--workspace is required unless --verify-report is used")
    if args.verify_report is None and args.json_out is None:
        args.json_out = args.workspace / "external-l4-rehearsal-summary.json"
    if args.verify_report is None and args.md_out is None:
        args.md_out = args.workspace / "external-l4-rehearsal-summary.md"
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.verify_report is not None:
        return verify_report(
            args.verify_report.resolve(),
            verify_files=args.verify_report_files,
            require_pass=args.require_report_pass,
        )
    try:
        require_clean_git_worktree()
        workspace = args.workspace.resolve()
        plan = prepare_rehearsal_workspace(
            workspace,
            args.template.resolve(),
            args.package_name,
            overwrite=args.overwrite,
        )
        input_paths = copy_inputs(
            workspace,
            args.morphojet_objects.resolve(),
            args.cellprofiler_cells.resolve(),
        )
        results = run_command_sequence(plan)
        summary = build_summary(args, plan, input_paths, results)
        write_json(args.json_out.resolve(), summary)
        args.md_out.resolve().parent.mkdir(parents=True, exist_ok=True)
        args.md_out.resolve().write_text(render_markdown(summary) + "\n", encoding="utf-8")
    except Exception as exc:  # noqa: BLE001 - command-line audit should report exact failure.
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(f"wrote {args.json_out}")
    print(f"wrote {args.md_out}")
    print(f"status={summary['status']}")
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
