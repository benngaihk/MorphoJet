#!/usr/bin/env python3
"""Run a reproducible internal rehearsal of the external L4 evidence chain."""

from __future__ import annotations

import argparse
import json
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
    return {
        "schema_version": 1,
        "runner": RUNNER,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
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
        "trial_plan": str((workspace / "trial_plan.json").resolve()),
        "handoff_trial_json": str((workspace / "handoff_trial.json").resolve()),
        "evidence_package_dir": str(package_dir.resolve()),
        "local_evidence_preflight_json": str((workspace / "local-evidence-preflight.json").resolve()),
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
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--morphojet-objects", type=Path, default=DEFAULT_MORPHOJET_OBJECTS)
    parser.add_argument("--cellprofiler-cells", type=Path, default=DEFAULT_CELLPROFILER_CELLS)
    parser.add_argument("--package-name", default=DEFAULT_PACKAGE_NAME)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--md-out", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    if args.json_out is None:
        args.json_out = args.workspace / "external-l4-rehearsal-summary.json"
    if args.md_out is None:
        args.md_out = args.workspace / "external-l4-rehearsal-summary.md"
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
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
