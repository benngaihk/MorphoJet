#!/usr/bin/env python3
"""Check whether an external L4 trial workspace is ready to execute."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

import check_cellprofiler_wide_contract
import materialize_morphojet_cellprofiler_wide
import prepare_external_l4_trial
import run_handoff_trial
import validate_handoff_manifest


CHECKER = "benchmark/check_external_l4_readiness.py"
MANIFEST_NAME = "external_manifest.json"


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def normalized_path_key(path: Path) -> str:
    return str(path.expanduser().resolve(strict=False))


def check_report_outputs(manifest_path: Path, manifest: dict[str, Any], workspace: Path) -> list[str]:
    try:
        run_handoff_trial.validate_report_outputs(
            manifest_path,
            manifest,
            workspace / "handoff_trial.json",
            workspace / "handoff_trial.md",
        )
    except SystemExit as exc:
        return [
            line.removeprefix("ERROR: ")
            for line in str(exc).splitlines()
            if line.strip()
        ]
    return []


def package_output_issues(workspace: Path, trial_id: str, package_name: str | None) -> list[str]:
    return [
        f"package output already exists: {path}"
        for path in package_output_paths(workspace, trial_id, package_name)
        if path.exists()
    ]


def package_output_paths(workspace: Path, trial_id: str, package_name: str | None) -> list[Path]:
    package_slug = prepare_external_l4_trial.slugify(package_name or f"external-l4-{trial_id}")
    out_dir = workspace / "evidence-package"
    return [
        out_dir / package_slug,
        out_dir / f"{package_slug}.zip",
        out_dir / f"{package_slug}.zip.sha256",
    ]


def trial_output_issues(manifest: dict[str, Any]) -> list[str]:
    issues = []
    for path in validate_handoff_manifest.collect_output_paths(manifest):
        output = Path(path)
        if output.exists():
            issues.append(f"trial output already exists before run: {path}")
    return issues


def planned_report_output_issues(workspace: Path) -> list[str]:
    return [f"planned report output already exists before run: {path}" for path in planned_report_output_paths(workspace) if path.exists()]


def planned_report_output_paths(workspace: Path) -> list[Path]:
    return [
        workspace / "handoff_trial.json",
        workspace / "handoff_trial.md",
        workspace / "handoff_trial-verification.json",
        workspace / "evidence-package-verification.json",
        workspace / "local-evidence-preflight.json",
        workspace / "local-evidence-preflight.md",
    ]


def readiness_json_out_issues(
    json_out: Path,
    workspace: Path,
    manifest_path: Path,
    manifest: dict[str, Any] | None,
    package_name: str | None,
) -> list[str]:
    protected = {
        normalized_path_key(manifest_path): f"manifest file: {manifest_path}",
    }
    for path in planned_report_output_paths(workspace):
        protected.setdefault(normalized_path_key(path), f"planned report output: {path}")
    if manifest is not None:
        for path in validate_handoff_manifest.collect_paths(manifest):
            protected.setdefault(normalized_path_key(Path(path)), f"manifest input: {path}")
        for path in validate_handoff_manifest.collect_output_paths(manifest):
            protected.setdefault(normalized_path_key(Path(path)), f"manifest trial output: {path}")
        trial_id = manifest.get("trial_id")
        if isinstance(trial_id, str) and trial_id.strip():
            for path in package_output_paths(workspace, trial_id, package_name):
                protected.setdefault(normalized_path_key(path), f"package output: {path}")
    protected_path = protected.get(normalized_path_key(json_out))
    if protected_path:
        return [f"--json-out must not overwrite {protected_path}"]
    return []


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return reader.fieldnames or [], list(reader)


def required_morphojet_objects_columns() -> list[str]:
    columns = [
        "ImageNumber",
        "ObjectNumber",
        "Channel",
        "ObjectSet",
        "Location_Center_Z",
        *materialize_morphojet_cellprofiler_wide.SHAPE_COLUMNS,
        *materialize_morphojet_cellprofiler_wide.INTENSITY_COLUMNS,
    ]
    return list(dict.fromkeys(columns))


def resolve_manifest_path(path: str) -> Path:
    return Path(path)


def morphojet_objects_csv_issues(path: str, object_set: str, channels: list[str]) -> list[str]:
    csv_path = resolve_manifest_path(path)
    if not csv_path.is_file():
        return []
    columns, rows = read_csv(csv_path)
    issues = []
    missing_columns = [column for column in required_morphojet_objects_columns() if column not in columns]
    if missing_columns:
        issues.append(f"MorphoJet objects CSV missing columns for {path}: {','.join(missing_columns)}")
    matching_rows = [row for row in rows if row.get("ObjectSet") == object_set]
    if not matching_rows:
        issues.append(f"MorphoJet objects CSV has no rows for ObjectSet={object_set}: {path}")
    missing_channels = sorted(set(channels) - {row.get("Channel", "") for row in matching_rows})
    if missing_channels:
        issues.append(
            f"MorphoJet objects CSV missing channel rows for ObjectSet={object_set} in {path}: "
            f"{','.join(missing_channels)}"
        )
    return issues


def expected_cellprofiler_csv_issues(path: str, channels: list[str]) -> list[str]:
    csv_path = resolve_manifest_path(path)
    if not csv_path.is_file():
        return []
    columns, rows = read_csv(csv_path)
    issues = []
    required_columns = check_cellprofiler_wide_contract.required_columns(channels)
    missing_columns = [column for column in required_columns if column not in columns]
    if missing_columns:
        issues.append(f"expected CellProfiler CSV missing columns for {path}: {','.join(missing_columns)}")
    if not rows:
        issues.append(f"expected CellProfiler CSV has no data rows: {path}")
    return issues


def input_csv_schema_issues(manifest: dict[str, Any]) -> list[str]:
    issues = []
    top_level_objects = manifest.get("morphojet_objects_csv")
    for export in manifest.get("exports", []):
        if not isinstance(export, dict):
            continue
        object_set = export.get("object_set")
        channels = export.get("channels")
        if not isinstance(object_set, str) or not isinstance(channels, list):
            continue
        if not all(isinstance(channel, str) and channel for channel in channels):
            continue
        objects_csv = export.get("objects_csv", top_level_objects)
        if isinstance(objects_csv, str):
            issues.extend(morphojet_objects_csv_issues(objects_csv, object_set, channels))
        expected = export.get("expected_cellprofiler_csv")
        if isinstance(expected, str):
            issues.extend(expected_cellprofiler_csv_issues(expected, channels))
    return unique_issues(issues)


def unique_issues(issues: list[str]) -> list[str]:
    observed = set()
    deduped = []
    for issue in issues:
        if issue not in observed:
            observed.add(issue)
            deduped.append(issue)
    return deduped


def readiness_report(
    workspace: Path,
    manifest_path: Path | None = None,
    package_name: str | None = None,
    variables: dict[str, str] | None = None,
) -> dict[str, Any]:
    variables = {"base_dir": str(workspace), **(variables or {})}
    manifest_path = manifest_path or workspace / MANIFEST_NAME
    issues: list[str] = []
    checks: list[dict[str, Any]] = []

    if not manifest_path.is_file():
        issues.append(f"manifest does not exist: {manifest_path}")
        manifest: dict[str, Any] | None = None
    else:
        raw_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        rendered = run_handoff_trial.render(raw_manifest, variables)
        if not isinstance(rendered, dict):
            issues.append("manifest root must be an object")
            manifest = None
        else:
            manifest = rendered

    if manifest is not None:
        schema_issues = validate_handoff_manifest.validate_schema(
            manifest,
            require_downstream_check=True,
            require_external_evidence=True,
        )
        file_issues = validate_handoff_manifest.validate_files(manifest, Path.cwd())
        csv_schema_issues = input_csv_schema_issues(manifest) if not file_issues else []
        trial_output_path_issues = trial_output_issues(manifest)
        report_output_issues = check_report_outputs(manifest_path, manifest, workspace)
        planned_report_output_path_issues = planned_report_output_issues(workspace)
        trial_id = manifest.get("trial_id")
        package_issues = (
            package_output_issues(workspace, trial_id, package_name)
            if isinstance(trial_id, str) and trial_id.strip()
            else ["manifest.trial_id must be a non-empty string"]
        )
        checks.extend(
            [
                {"name": "manifest_schema", "status": "PASS" if not schema_issues else "FAIL", "issues": schema_issues},
                {"name": "input_files", "status": "PASS" if not file_issues else "FAIL", "issues": file_issues},
                {
                    "name": "input_csv_schema",
                    "status": "PASS" if not csv_schema_issues else "FAIL",
                    "issues": csv_schema_issues,
                },
                {
                    "name": "trial_output_paths",
                    "status": "PASS" if not trial_output_path_issues else "FAIL",
                    "issues": trial_output_path_issues,
                },
                {
                    "name": "report_output_paths",
                    "status": "PASS" if not report_output_issues else "FAIL",
                    "issues": report_output_issues,
                },
                {
                    "name": "planned_report_outputs",
                    "status": "PASS" if not planned_report_output_path_issues else "FAIL",
                    "issues": planned_report_output_path_issues,
                },
                {"name": "package_outputs", "status": "PASS" if not package_issues else "FAIL", "issues": package_issues},
            ]
        )
        for check in checks:
            check["issues"] = unique_issues(check["issues"])
            issues.extend(check["issues"])

    issues = unique_issues(issues)
    status = "READY" if not issues else "NOT_READY"
    return {
        "schema_version": 1,
        "checker": CHECKER,
        "status": status,
        "claim_status": "NOT_PRODUCTION_CLAIM",
        "workspace": str(workspace),
        "manifest": str(manifest_path),
        "variables": variables,
        "checks": checks,
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--package-name")
    parser.add_argument("--var", action="append", default=[], help="Additional template variable key=value")
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()

    try:
        variables = run_handoff_trial.parse_vars(args.var)
        payload = readiness_report(
            args.workspace,
            manifest_path=args.manifest,
            package_name=args.package_name,
            variables=variables,
        )
    except Exception as exc:  # noqa: BLE001 - keep CLI report failures explicit.
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    if args.json_out:
        manifest = None
        manifest_path = args.manifest or args.workspace / MANIFEST_NAME
        if manifest_path.is_file():
            raw_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            rendered = run_handoff_trial.render(raw_manifest, payload["variables"])
            if isinstance(rendered, dict):
                manifest = rendered
        json_out_issues = readiness_json_out_issues(
            args.json_out,
            args.workspace,
            manifest_path,
            manifest,
            args.package_name,
        )
        if json_out_issues:
            for issue in json_out_issues:
                print(f"ERROR: {issue}", file=sys.stderr)
            return 1
        write_json(args.json_out, payload)
        print(f"wrote {args.json_out}")
    print(f"status={payload['status']}")
    for issue in payload["issues"]:
        print(f"ERROR: {issue}")
    return 0 if payload["status"] == "READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
