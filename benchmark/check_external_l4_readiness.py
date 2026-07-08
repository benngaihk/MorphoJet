#!/usr/bin/env python3
"""Check whether an external L4 trial workspace is ready to execute."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import check_cellprofiler_wide_contract
import materialize_morphojet_cellprofiler_wide
import prepare_external_l4_trial
import release_gate
import run_handoff_trial
import validate_handoff_manifest


CHECKER = "benchmark/check_external_l4_readiness.py"
MANIFEST_NAME = "external_manifest.json"
PLAN_NAME = "trial_plan.json"
CLAIM_STATUS = release_gate.NON_FINAL_CLAIM_STATUS
EVIDENCE_SCOPE = release_gate.EXTERNAL_READINESS_EVIDENCE_SCOPE
FINAL_PRODUCTION_SIGNOFF = release_gate.NON_FINAL_PRODUCTION_SIGNOFF


def is_utc_datetime(value: datetime) -> bool:
    return value.utcoffset() == timezone.utc.utcoffset(value)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def normalized_path_key(path: Path) -> str:
    return str(path.expanduser().resolve(strict=False))


def path_matches_or_is_inside(root: Path, path: Path) -> bool:
    normalized_root = root.expanduser().resolve(strict=False)
    normalized_path = path.expanduser().resolve(strict=False)
    try:
        normalized_path.relative_to(normalized_root)
        return True
    except ValueError:
        return False


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


def saved_trial_plan_issues(workspace: Path) -> list[str]:
    plan_path = workspace / PLAN_NAME
    if not plan_path.is_file():
        return [f"trial plan does not exist: {plan_path}"]
    try:
        payload = json.loads(plan_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - exact readiness diagnostic.
        return [f"trial plan is not readable JSON: {type(exc).__name__}: {exc}"]
    return [
        f"trial plan verification failed: {failure}"
        for failure in prepare_external_l4_trial.validate_plan_payload(payload, verify_files=True)
    ]


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
    protected_paths = [(manifest_path, f"manifest file: {manifest_path}")]
    for path in planned_report_output_paths(workspace):
        protected_paths.append((path, f"planned report output: {path}"))
    if manifest is not None:
        for path in validate_handoff_manifest.collect_paths(manifest):
            protected_paths.append((Path(path), f"manifest input: {path}"))
        for path in validate_handoff_manifest.collect_output_paths(manifest):
            protected_paths.append((Path(path), f"manifest trial output: {path}"))
        trial_id = manifest.get("trial_id")
        if isinstance(trial_id, str) and trial_id.strip():
            for path in package_output_paths(workspace, trial_id, package_name):
                protected_paths.append((path, f"package output: {path}"))
    seen = set()
    for protected_path, label in protected_paths:
        key = (normalized_path_key(protected_path), label)
        if key in seen:
            continue
        seen.add(key)
        if normalized_path_key(json_out) == normalized_path_key(protected_path):
            return [f"--json-out must not overwrite {label}"]
        if path_matches_or_is_inside(protected_path, json_out):
            return [f"--json-out must not create a file inside {label}"]
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


def morphojet_objects_csv_issues(
    path: str,
    object_set: str,
    channels: list[str],
    required_metadata_columns: list[str] | None = None,
) -> list[str]:
    csv_path = resolve_manifest_path(path)
    if not csv_path.is_file():
        return []
    columns, rows = read_csv(csv_path)
    issues = []
    missing_columns = [column for column in required_morphojet_objects_columns() if column not in columns]
    if missing_columns:
        issues.append(f"MorphoJet objects CSV missing columns for {path}: {','.join(missing_columns)}")
    missing_metadata_columns = [column for column in (required_metadata_columns or []) if column not in columns]
    if missing_metadata_columns:
        issues.append(
            "MorphoJet objects CSV missing metadata columns for "
            f"{path}: {','.join(missing_metadata_columns)}"
        )
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
    top_level_metadata = manifest.get("required_object_metadata_columns", [])
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
            required_metadata_columns = export.get("required_object_metadata_columns", top_level_metadata)
            if not isinstance(required_metadata_columns, list) or not all(
                isinstance(column, str) and column.strip() for column in required_metadata_columns
            ):
                required_metadata_columns = []
            issues.extend(
                morphojet_objects_csv_issues(
                    objects_csv,
                    object_set,
                    channels,
                    required_metadata_columns,
                )
            )
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


def readiness_argv(
    workspace: Path,
    manifest_path: Path | None = None,
    package_name: str | None = None,
    variables: dict[str, str] | None = None,
    json_out: Path | None = None,
) -> list[str]:
    argv = [CHECKER, "--workspace", str(workspace)]
    if manifest_path is not None:
        argv.extend(["--manifest", str(manifest_path)])
    if package_name is not None:
        argv.extend(["--package-name", package_name])
    for key, value in sorted((variables or {}).items()):
        argv.extend(["--var", f"{key}={value}"])
    if json_out is not None:
        argv.extend(["--json-out", str(json_out)])
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


def parse_argv_vars(argv: list[str]) -> dict[str, str]:
    variables = {}
    for value in argv_values(argv, "--var"):
        if value is None or "=" not in value:
            continue
        key, item = value.split("=", 1)
        variables[key] = item
    return variables


def readiness_report_argv_issues(
    argv: list[str],
    workspace: str,
    manifest: str,
    package_name: str | None,
    variables: dict[str, str],
    report_path: Path | None = None,
) -> list[str]:
    failures = []
    if argv[0] != CHECKER:
        failures.append(f"argv[0]={argv[0]}")
    if "--verify-report" in argv:
        failures.append("argv must not include --verify-report for a generated readiness report")
    workspace_values = argv_values(argv, "--workspace")
    if len(workspace_values) > 1:
        failures.append("argv has duplicate --workspace")
    if not workspace_values:
        failures.append("argv missing --workspace")
    for value in workspace_values:
        if value is None:
            failures.append("argv --workspace must include a value")
        elif value != workspace:
            failures.append(f"workspace must match argv --workspace {value}")
    manifest_values = argv_values(argv, "--manifest")
    if len(manifest_values) > 1:
        failures.append("argv has duplicate --manifest")
    expected_default_manifest = str(Path(workspace) / MANIFEST_NAME)
    if not manifest_values and manifest != expected_default_manifest:
        failures.append("argv missing --manifest for non-default manifest")
    for value in manifest_values:
        if value is None:
            failures.append("argv --manifest must include a value")
        elif value != manifest:
            failures.append(f"manifest must match argv --manifest {value}")
    package_name_values = argv_values(argv, "--package-name")
    if len(package_name_values) > 1:
        failures.append("argv has duplicate --package-name")
    if package_name is None and package_name_values:
        failures.append("argv must not include --package-name when package_name is null")
    elif package_name is not None and not package_name_values:
        failures.append("argv missing --package-name for package_name")
    for value in package_name_values:
        if value is None:
            failures.append("argv --package-name must include a value")
        elif package_name is not None and prepare_external_l4_trial.slugify(value) != package_name:
            failures.append(f"package_name must match argv --package-name {value}")
    var_values = argv_values(argv, "--var")
    if any(value is None or "=" not in value for value in var_values):
        failures.append("argv --var values must use key=value")
    expected_variables = {"base_dir": workspace, **parse_argv_vars(argv)}
    if variables != expected_variables:
        failures.append("variables must match argv --var values plus default base_dir")
    json_out_values = argv_values(argv, "--json-out")
    if len(json_out_values) > 1:
        failures.append("argv has duplicate --json-out")
    if report_path is not None and not json_out_values:
        failures.append("argv missing --json-out for saved readiness report")
    for value in json_out_values:
        if value is None:
            failures.append("argv --json-out must include a value")
        elif not Path(value).is_absolute():
            failures.append("argv --json-out must be an absolute path")
        elif report_path is not None and normalized_path_key(Path(value)) != normalized_path_key(report_path):
            failures.append("argv --json-out must match saved readiness report path")
    return failures


def validate_readiness_report_payload(
    payload: Any,
    report_path: Path | None = None,
    require_ready: bool = False,
) -> list[str]:
    failures: list[str] = []
    if not isinstance(payload, dict):
        return ["readiness report must be a JSON object"]
    if payload.get("schema_version") != 1:
        failures.append(f"schema_version={payload.get('schema_version')}")
    if payload.get("checker") != CHECKER:
        failures.append(f"checker={payload.get('checker')}")
    generated_at = payload.get("generated_at_utc")
    if not isinstance(generated_at, str) or not generated_at.strip():
        failures.append("generated_at_utc must be a non-empty string")
    else:
        try:
            parsed_generated_at = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
            if parsed_generated_at.tzinfo is None:
                failures.append("generated_at_utc must include timezone")
            elif not is_utc_datetime(parsed_generated_at):
                failures.append("generated_at_utc must be UTC")
        except ValueError:
            failures.append(f"generated_at_utc is invalid: {generated_at}")
    status = payload.get("status")
    if status not in {"READY", "NOT_READY"}:
        failures.append(f"status={status}")
    if require_ready and status != "READY":
        failures.append(f"readiness report status is not READY: {status}")
    if payload.get("claim_status") != CLAIM_STATUS:
        failures.append(f"claim_status={payload.get('claim_status')}")
    if payload.get("evidence_scope") != EVIDENCE_SCOPE:
        failures.append(f"evidence_scope={payload.get('evidence_scope')}")
    if payload.get("final_production_signoff") is not FINAL_PRODUCTION_SIGNOFF:
        failures.append("final_production_signoff must be false")
    workspace = payload.get("workspace")
    if not isinstance(workspace, str) or not workspace.strip():
        failures.append("workspace must be a non-empty string")
    elif not Path(workspace).is_absolute():
        failures.append("workspace must be an absolute path")
    manifest = payload.get("manifest")
    if not isinstance(manifest, str) or not manifest.strip():
        failures.append("manifest must be a non-empty string")
    elif not Path(manifest).is_absolute():
        failures.append("manifest must be an absolute path")
    variables = payload.get("variables")
    if not isinstance(variables, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in variables.items()
    ):
        failures.append("variables must be a string map")
        variables = {}
    package_name = payload.get("package_name")
    if package_name is not None:
        if not isinstance(package_name, str) or not package_name.strip():
            failures.append("package_name must be null or a non-empty string")
            package_name = None
        elif prepare_external_l4_trial.slugify(package_name) != package_name:
            failures.append("package_name must be a canonical slug")
    checks = payload.get("checks")
    collected_issues: list[str] = []
    if not isinstance(checks, list):
        failures.append("checks must be a list")
    else:
        check_names = []
        for check in checks:
            if not isinstance(check, dict):
                failures.append("check entries must be objects")
                continue
            name = check.get("name")
            if not isinstance(name, str) or not name.strip():
                failures.append("check.name must be a non-empty string")
            else:
                check_names.append(name)
            if check.get("status") not in {"PASS", "FAIL"}:
                failures.append(f"check.status invalid: {name}")
            check_issues = check.get("issues")
            if not isinstance(check_issues, list) or not all(isinstance(issue, str) for issue in check_issues):
                failures.append(f"check.issues must be a string list: {name}")
            else:
                collected_issues.extend(check_issues)
        duplicated_names = sorted(name for name in set(check_names) if check_names.count(name) > 1)
        for name in duplicated_names:
            failures.append(f"check name is duplicated: {name}")
    issues = payload.get("issues")
    if not isinstance(issues, list) or not all(isinstance(issue, str) for issue in issues):
        failures.append("issues must be a string list")
        issues = []
    else:
        expected_status = "READY" if not issues else "NOT_READY"
        if status in {"READY", "NOT_READY"} and status != expected_status:
            failures.append("status does not match issues")
        missing_check_issues = [issue for issue in unique_issues(collected_issues) if issue not in issues]
        if isinstance(checks, list) and missing_check_issues:
            failures.append("issues must include flattened check issues")
    argv = payload.get("argv")
    if not isinstance(argv, list) or not argv or not all(isinstance(item, str) and item for item in argv):
        failures.append("argv must be a non-empty string list")
    elif (
        isinstance(workspace, str)
        and workspace.strip()
        and isinstance(manifest, str)
        and manifest.strip()
        and isinstance(variables, dict)
    ):
        failures.extend(
            readiness_report_argv_issues(
                argv,
                workspace,
                manifest,
                package_name,
                variables,
                report_path=report_path,
            )
        )
    return failures


def verify_saved_readiness_report(
    report: Path,
    require_ready: bool = False,
    verify_files: bool = False,
) -> int:
    try:
        payload = json.loads(report.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - exact report verification failure.
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    failures = validate_readiness_report_payload(payload, report_path=report, require_ready=require_ready)
    if not failures and verify_files:
        argv = payload["argv"]
        fresh = readiness_report(
            Path(payload["workspace"]),
            manifest_path=Path(payload["manifest"]),
            package_name=payload.get("package_name"),
            variables=parse_argv_vars(argv),
            json_out=report,
        )
        for key in ["status", "workspace", "manifest", "package_name", "variables", "checks", "issues"]:
            if payload.get(key) != fresh.get(key):
                failures.append(f"saved readiness report {key} changed after report was written")
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print(f"readiness report ok: {report}")
    print(f"status={payload['status']}")
    return 0


def readiness_report(
    workspace: Path,
    manifest_path: Path | None = None,
    package_name: str | None = None,
    variables: dict[str, str] | None = None,
    json_out: Path | None = None,
) -> dict[str, Any]:
    workspace = workspace.resolve()
    if manifest_path is not None:
        manifest_path = manifest_path.resolve()
    if json_out is not None:
        json_out = json_out.resolve()
    explicit_variables = variables or {}
    variables = {"base_dir": str(workspace), **explicit_variables}
    manifest_path = manifest_path or workspace / MANIFEST_NAME
    canonical_package_name = (
        prepare_external_l4_trial.slugify(package_name)
        if package_name is not None
        else None
    )
    issues: list[str] = []
    checks: list[dict[str, Any]] = []
    plan_issues = saved_trial_plan_issues(workspace)
    checks.append(
        {
            "name": "saved_trial_plan",
            "status": "PASS" if not plan_issues else "FAIL",
            "issues": plan_issues,
        }
    )
    issues.extend(plan_issues)

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
            package_output_issues(workspace, trial_id, canonical_package_name)
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
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "argv": readiness_argv(
            workspace,
            manifest_path=manifest_path if manifest_path != workspace / MANIFEST_NAME else None,
            package_name=package_name,
            variables=explicit_variables,
            json_out=json_out,
        ),
        "status": status,
        "claim_status": CLAIM_STATUS,
        "evidence_scope": EVIDENCE_SCOPE,
        "final_production_signoff": FINAL_PRODUCTION_SIGNOFF,
        "workspace": str(workspace),
        "manifest": str(manifest_path),
        "package_name": canonical_package_name,
        "variables": variables,
        "checks": checks,
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--package-name")
    parser.add_argument("--var", action="append", default=[], help="Additional template variable key=value")
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--verify-report", type=Path, help="Validate a saved readiness JSON report")
    parser.add_argument("--verify-report-files", action="store_true", help="Recompute readiness checks from saved report paths")
    parser.add_argument("--require-ready", action="store_true", help="Reject saved readiness reports that are not READY")
    args = parser.parse_args()
    if args.verify_report:
        return verify_saved_readiness_report(
            args.verify_report,
            require_ready=args.require_ready,
            verify_files=args.verify_report_files,
        )
    if args.workspace is None:
        parser.error("--workspace is required unless --verify-report is used")

    try:
        workspace = args.workspace.resolve()
        manifest_arg = args.manifest.resolve() if args.manifest is not None else None
        json_out_arg = args.json_out.resolve() if args.json_out is not None else None
        variables = run_handoff_trial.parse_vars(args.var)
        payload = readiness_report(
            workspace,
            manifest_path=manifest_arg,
            package_name=args.package_name,
            variables=variables,
            json_out=json_out_arg,
        )
    except Exception as exc:  # noqa: BLE001 - keep CLI report failures explicit.
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    if json_out_arg:
        manifest = None
        manifest_path = manifest_arg or workspace / MANIFEST_NAME
        if manifest_path.is_file():
            raw_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            rendered = run_handoff_trial.render(raw_manifest, payload["variables"])
            if isinstance(rendered, dict):
                manifest = rendered
        json_out_issues = readiness_json_out_issues(
            json_out_arg,
            workspace,
            manifest_path,
            manifest,
            args.package_name,
        )
        if json_out_issues:
            for issue in json_out_issues:
                print(f"ERROR: {issue}", file=sys.stderr)
            return 1
        write_json(json_out_arg, payload)
        print(f"wrote {json_out_arg}")
    print(f"status={payload['status']}")
    for issue in payload["issues"]:
        print(f"ERROR: {issue}")
    return 0 if payload["status"] == "READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
