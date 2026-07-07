#!/usr/bin/env python3
"""Validate a MorphoJet handoff trial manifest."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from run_handoff_trial import parse_vars, render


def is_utc_datetime(value: datetime) -> bool:
    return value.utcoffset() == timezone.utc.utcoffset(value)


def require_string(data: dict[str, Any], key: str, issues: list[str], prefix: str) -> None:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        issues.append(f"{prefix}.{key} must be a non-empty string")


def validate_export(export: Any, index: int, issues: list[str]) -> None:
    prefix = f"exports[{index}]"
    if not isinstance(export, dict):
        issues.append(f"{prefix} must be an object")
        return
    for key in ["name", "object_set", "out_csv"]:
        require_string(export, key, issues, prefix)
    channels = export.get("channels")
    if (
        not isinstance(channels, list)
        or not channels
        or not all(isinstance(item, str) and item for item in channels)
    ):
        issues.append(f"{prefix}.channels must be a non-empty string list")
    if "objects_csv" in export and not isinstance(export["objects_csv"], str):
        issues.append(f"{prefix}.objects_csv must be a string when present")
    if "expected_cellprofiler_csv" in export:
        for key in ["expected_cellprofiler_csv", "comparison_report", "comparison_json"]:
            require_string(export, key, issues, prefix)


def validate_downstream_check(check: Any, index: int, issues: list[str]) -> None:
    prefix = f"downstream_checks[{index}]"
    if not isinstance(check, dict):
        issues.append(f"{prefix} must be an object")
        return
    require_string(check, "name", issues, prefix)
    command = check.get("command")
    if (
        not isinstance(command, list)
        or not command
        or not all(isinstance(item, str) and item for item in command)
    ):
        issues.append(f"{prefix}.command must be a non-empty string list")
    artifacts = check.get("artifacts", [])
    if not isinstance(artifacts, list) or not all(
        isinstance(item, str) and item for item in artifacts
    ):
        issues.append(f"{prefix}.artifacts must be a string list when present")


def has_placeholder(value: str) -> bool:
    return value.startswith("REPLACE_WITH")


def validate_external_evidence(evidence: Any, issues: list[str], allow_placeholders: bool) -> None:
    prefix = "external_evidence"
    if not isinstance(evidence, dict):
        issues.append("manifest.external_evidence must be an object for an external workflow trial")
        return
    for key in [
        "lab_or_org",
        "workflow_owner",
        "dataset_name",
        "dataset_source",
        "downstream_workflow",
        "execution_environment",
        "reviewer_name_or_role",
        "reviewed_at_utc",
        "signoff_statement",
    ]:
        require_string(evidence, key, issues, prefix)
        value = evidence.get(key)
        if isinstance(value, str) and has_placeholder(value) and not allow_placeholders:
            issues.append(f"{prefix}.{key} must replace template placeholder text")
    reviewed_at = evidence.get("reviewed_at_utc")
    if isinstance(reviewed_at, str) and not has_placeholder(reviewed_at):
        try:
            parsed_reviewed_at = datetime.fromisoformat(reviewed_at)
            if parsed_reviewed_at.tzinfo is None:
                issues.append(f"{prefix}.reviewed_at_utc must include timezone")
            elif not is_utc_datetime(parsed_reviewed_at):
                issues.append(f"{prefix}.reviewed_at_utc must be UTC")
        except ValueError:
            issues.append(f"{prefix}.reviewed_at_utc is invalid: {reviewed_at}")
    criteria = evidence.get("acceptance_criteria")
    if (
        not isinstance(criteria, list)
        or not criteria
        or not all(isinstance(item, str) and item.strip() for item in criteria)
    ):
        issues.append(f"{prefix}.acceptance_criteria must be a non-empty string list")
    elif not allow_placeholders:
        for index, criterion in enumerate(criteria):
            if has_placeholder(criterion):
                issues.append(f"{prefix}.acceptance_criteria[{index}] must replace template placeholder text")
    if evidence.get("manual_csv_editing") is not False:
        issues.append(f"{prefix}.manual_csv_editing must be false")


def validate_schema(
    data: dict[str, Any],
    require_downstream_check: bool,
    require_external_evidence: bool = False,
    allow_external_evidence_placeholders: bool = False,
) -> list[str]:
    issues: list[str] = []
    for key in ["trial_id", "morphojet_objects_csv"]:
        require_string(data, key, issues, "manifest")

    exports = data.get("exports")
    if not isinstance(exports, list) or not exports:
        issues.append("manifest.exports must be a non-empty list")
    else:
        for index, export in enumerate(exports):
            validate_export(export, index, issues)

    downstream_checks = data.get("downstream_checks", [])
    if require_downstream_check and not downstream_checks:
        issues.append("manifest.downstream_checks must be non-empty for a production handoff trial")
    if not isinstance(downstream_checks, list):
        issues.append("manifest.downstream_checks must be a list when present")
    else:
        for index, check in enumerate(downstream_checks):
            validate_downstream_check(check, index, issues)

    if require_external_evidence or "external_evidence" in data:
        validate_external_evidence(
            data.get("external_evidence"),
            issues,
            allow_placeholders=allow_external_evidence_placeholders,
        )

    issues.extend(validate_path_contract(data))
    return issues


def collect_paths(data: dict[str, Any]) -> list[str]:
    paths = []
    if isinstance(data.get("morphojet_objects_csv"), str):
        paths.append(data["morphojet_objects_csv"])
    for export in data.get("exports", []):
        if not isinstance(export, dict):
            continue
        paths.append(export.get("objects_csv", data.get("morphojet_objects_csv")))
        if "expected_cellprofiler_csv" in export:
            paths.append(export["expected_cellprofiler_csv"])
    return [path for path in paths if isinstance(path, str)]


def collect_output_paths(data: dict[str, Any]) -> list[str]:
    paths = []
    for export in data.get("exports", []):
        if not isinstance(export, dict):
            continue
        for key in ["out_csv", "comparison_report", "comparison_json"]:
            value = export.get(key)
            if isinstance(value, str):
                paths.append(value)
    for check in data.get("downstream_checks", []):
        if not isinstance(check, dict):
            continue
        artifacts = check.get("artifacts", [])
        if isinstance(artifacts, list):
            paths.extend(artifact for artifact in artifacts if isinstance(artifact, str))
    return paths


def validate_path_contract(data: dict[str, Any]) -> list[str]:
    issues = []
    inputs = collect_paths(data)
    outputs = collect_output_paths(data)
    output_by_key: dict[str, list[str]] = {}
    for output in outputs:
        output_by_key.setdefault(normalized_path_key(output), []).append(output)
    for output_paths in output_by_key.values():
        if len(output_paths) > 1:
            issues.append(f"output path is duplicated: {sorted(output_paths)[0]}")
    input_keys = {normalized_path_key(path) for path in inputs}
    for output in sorted(output for output in outputs if normalized_path_key(output) in input_keys):
        issues.append(f"output path must not overwrite an input file: {output}")
    return issues


def normalized_path_key(path: str) -> str:
    return str(Path(path).expanduser().resolve(strict=False))


def validate_files(data: dict[str, Any], root: Path) -> list[str]:
    issues = []
    for path in collect_paths(data):
        resolved = root / path
        if not resolved.is_file():
            issues.append(f"required input file does not exist: {path}")
    return issues


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--var", action="append", default=[], help="Template variable key=value")
    parser.add_argument("--check-files", action="store_true")
    parser.add_argument("--require-downstream-check", action="store_true")
    parser.add_argument(
        "--require-external-evidence",
        action="store_true",
        help="Require the L4 external workflow evidence fields",
    )
    parser.add_argument(
        "--allow-external-evidence-placeholders",
        action="store_true",
        help="Allow REPLACE_WITH placeholders when validating the repository template",
    )
    args = parser.parse_args()

    variables = parse_vars(args.var)
    raw_manifest = json.loads(args.manifest.read_text())
    manifest = render(raw_manifest, variables)
    if not isinstance(manifest, dict):
        raise SystemExit("manifest root must be an object")

    issues = validate_schema(
        manifest,
        args.require_downstream_check,
        require_external_evidence=args.require_external_evidence,
        allow_external_evidence_placeholders=args.allow_external_evidence_placeholders,
    )
    if args.check_files and not issues:
        issues.extend(validate_files(manifest, Path.cwd()))

    if issues:
        for issue in issues:
            print(f"ERROR: {issue}")
        return 1

    print(f"handoff manifest ok: {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
