#!/usr/bin/env python3
"""Run an auditable no-manual-CSV-edit handoff trial."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


@dataclass
class TrialStep:
    name: str
    command: list[str] | None
    status: str
    elapsed_seconds: float
    detail: str


class Vars(dict[str, str]):
    def __missing__(self, key: str) -> str:
        raise KeyError(key)


def parse_vars(values: list[str]) -> dict[str, str]:
    parsed = {}
    for value in values:
        if "=" not in value:
            raise SystemExit(f"--var must be key=value: {value}")
        key, raw = value.split("=", 1)
        if not key:
            raise SystemExit(f"--var key is empty: {value}")
        parsed[key] = raw
    return parsed


def render(value: Any, variables: dict[str, str]) -> Any:
    if isinstance(value, str):
        try:
            return value.format_map(Vars(variables))
        except KeyError as exc:
            raise SystemExit(f"missing --var {exc.args[0]} for template {value!r}") from exc
    if isinstance(value, list):
        return [render(item, variables) for item in value]
    if isinstance(value, dict):
        return {key: render(item, variables) for key, item in value.items()}
    return value


def run_command(name: str, command: list[str]) -> TrialStep:
    started = time.perf_counter()
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    detail = completed.stdout[-4000:]
    if completed.stderr:
        detail = (detail + "\n" + completed.stderr[-4000:]).strip()
    return TrialStep(
        name=name,
        command=command,
        status="PASS" if completed.returncode == 0 else "FAIL",
        elapsed_seconds=time.perf_counter() - started,
        detail=detail,
    )


def require(data: dict[str, Any], key: str) -> Any:
    if key not in data:
        raise SystemExit(f"missing required manifest field: {key}")
    return data[key]


def validate_manifest(manifest: dict[str, Any]) -> None:
    import validate_handoff_manifest

    issues = validate_handoff_manifest.validate_schema(manifest, require_downstream_check=True)
    if issues:
        raise SystemExit("\n".join(f"ERROR: {issue}" for issue in issues))


def render_markdown(payload: dict[str, Any], out_json: Path) -> str:
    lines = [
        "# Handoff Trial Report",
        "",
        f"- trial_id: `{payload['trial_id']}`",
        f"- status: `{payload['status']}`",
        f"- json: `{out_json}`",
        "",
    ]
    evidence = payload.get("external_evidence")
    if evidence:
        lines.extend(
            [
                "## External Evidence",
                "",
                f"- lab_or_org: `{evidence['lab_or_org']}`",
                f"- workflow_owner: `{evidence['workflow_owner']}`",
                f"- dataset_name: `{evidence['dataset_name']}`",
                f"- dataset_source: `{evidence['dataset_source']}`",
                f"- downstream_workflow: `{evidence['downstream_workflow']}`",
                f"- execution_environment: `{evidence['execution_environment']}`",
                f"- manual_csv_editing: `{evidence['manual_csv_editing']}`",
                "",
                "Acceptance criteria:",
                "",
            ]
        )
        for criterion in evidence["acceptance_criteria"]:
            lines.append(f"- {criterion}")
        lines.append("")
    lines.extend(
        [
            "| Step | Status | Seconds |",
            "|---|---:|---:|",
        ]
    )
    for step in payload["steps"]:
        lines.append(f"| {step['name']} | {step['status']} | {step['elapsed_seconds']:.3f} |")
    lines.extend(["", "## Artifacts", ""])
    for artifact in payload["artifacts"]:
        lines.append(f"- `{artifact}`")
    lines.extend(["", "## Details", ""])
    for step in payload["steps"]:
        lines.append(f"### {step['name']}")
        lines.append("")
        lines.append(f"- status: `{step['status']}`")
        if step["command"]:
            lines.append(f"- command: `{' '.join(step['command'])}`")
        if step["detail"]:
            lines.append("")
            lines.append("```text")
            lines.append(step["detail"])
            lines.append("```")
        lines.append("")
    return "\n".join(lines)


def run_trial(manifest: dict[str, Any]) -> tuple[list[TrialStep], list[str]]:
    steps: list[TrialStep] = []
    artifacts: list[str] = []
    objects_csv = require(manifest, "morphojet_objects_csv")

    for export in manifest.get("exports", []):
        name = require(export, "name")
        object_set = require(export, "object_set")
        channels = require(export, "channels")
        out_csv = require(export, "out_csv")
        channel_arg = ",".join(channels)
        materialize_command = [
            "python3",
            "benchmark/materialize_morphojet_cellprofiler_wide.py",
            "--objects",
            export.get("objects_csv", objects_csv),
            "--object-set",
            object_set,
            "--channels",
            channel_arg,
            "--out",
            out_csv,
        ]
        steps.append(run_command(f"Materialize {name} wide CSV", materialize_command))
        artifacts.append(out_csv)

        expected = export.get("expected_cellprofiler_csv")
        if expected:
            report = require(export, "comparison_report")
            json_report = require(export, "comparison_json")
            compare_command = [
                "python3",
                "benchmark/compare_cellprofiler_wide_subset.py",
                expected,
                out_csv,
                "--out",
                report,
                "--json-out",
                json_report,
                "--fail-on-gap",
            ]
            steps.append(run_command(f"Compare {name} supported columns", compare_command))
            artifacts.extend([report, json_report])

    for check in manifest.get("downstream_checks", []):
        command = require(check, "command")
        if not isinstance(command, list) or not command:
            raise SystemExit("downstream_checks.command must be a non-empty list")
        steps.append(run_command(require(check, "name"), command))
        artifacts.extend(check.get("artifacts", []))

    return steps, artifacts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--var", action="append", default=[], help="Template variable key=value")
    parser.add_argument("--out-json", type=Path, required=True)
    parser.add_argument("--out-md", type=Path, required=True)
    args = parser.parse_args()

    variables = parse_vars(args.var)
    raw_manifest = json.loads(args.manifest.read_text())
    manifest = render(raw_manifest, variables)
    if not isinstance(manifest, dict):
        raise SystemExit("manifest root must be an object")
    validate_manifest(manifest)
    steps, artifacts = run_trial(manifest)
    payload = {
        "trial_id": require(manifest, "trial_id"),
        "description": manifest.get("description", ""),
        "status": "PASS" if all(step.status == "PASS" for step in steps) else "FAIL",
        "manifest": str(args.manifest),
        "variables": variables,
        "external_evidence": manifest.get("external_evidence"),
        "artifacts": artifacts,
        "steps": [asdict(step) for step in steps],
    }
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(payload, indent=2) + "\n")
    args.out_md.parent.mkdir(parents=True, exist_ok=True)
    args.out_md.write_text(render_markdown(payload, args.out_json) + "\n")
    print(f"wrote {args.out_json}")
    print(f"wrote {args.out_md}")
    print(f"status={payload['status']}")
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
