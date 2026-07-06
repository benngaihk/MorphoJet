#!/usr/bin/env python3
"""Check whether an external L4 trial workspace is ready to execute."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import prepare_external_l4_trial
import run_handoff_trial
import validate_handoff_manifest


CHECKER = "benchmark/check_external_l4_readiness.py"
MANIFEST_NAME = "external_manifest.json"


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


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
    package_slug = prepare_external_l4_trial.slugify(package_name or f"external-l4-{trial_id}")
    out_dir = workspace / "evidence-package"
    paths = [
        out_dir / package_slug,
        out_dir / f"{package_slug}.zip",
        out_dir / f"{package_slug}.zip.sha256",
    ]
    return [f"package output already exists: {path}" for path in paths if path.exists()]


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
        report_output_issues = check_report_outputs(manifest_path, manifest, workspace)
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
                    "name": "report_output_paths",
                    "status": "PASS" if not report_output_issues else "FAIL",
                    "issues": report_output_issues,
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
        write_json(args.json_out, payload)
        print(f"wrote {args.json_out}")
    print(f"status={payload['status']}")
    for issue in payload["issues"]:
        print(f"ERROR: {issue}")
    return 0 if payload["status"] == "READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
