#!/usr/bin/env python3
"""Validate a MorphoJet handoff trial manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from run_handoff_trial import parse_vars, render


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
    if not isinstance(channels, list) or not channels or not all(isinstance(item, str) and item for item in channels):
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
    if not isinstance(command, list) or not command or not all(isinstance(item, str) and item for item in command):
        issues.append(f"{prefix}.command must be a non-empty string list")
    artifacts = check.get("artifacts", [])
    if not isinstance(artifacts, list) or not all(isinstance(item, str) and item for item in artifacts):
        issues.append(f"{prefix}.artifacts must be a string list when present")


def validate_schema(data: dict[str, Any], require_downstream_check: bool) -> list[str]:
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

    return issues


def collect_paths(data: dict[str, Any]) -> list[str]:
    paths = [data["morphojet_objects_csv"]]
    for export in data.get("exports", []):
        paths.append(export.get("objects_csv", data["morphojet_objects_csv"]))
        if "expected_cellprofiler_csv" in export:
            paths.append(export["expected_cellprofiler_csv"])
    return paths


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
    args = parser.parse_args()

    variables = parse_vars(args.var)
    raw_manifest = json.loads(args.manifest.read_text())
    manifest = render(raw_manifest, variables)
    if not isinstance(manifest, dict):
        raise SystemExit("manifest root must be an object")

    issues = validate_schema(manifest, args.require_downstream_check)
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
