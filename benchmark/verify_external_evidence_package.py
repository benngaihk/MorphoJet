#!/usr/bin/env python3
"""Validate a packaged external L4 trial evidence bundle."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import release_gate

SCHEMA_VERSION = 1
VERIFIER = "benchmark/verify_external_evidence_package.py"
SHA256_RE = re.compile(r"[0-9a-f]{64}")
CLAIM_STATUS = "NOT_PRODUCTION_CLAIM"
EVIDENCE_SCOPE = "EXTERNAL_L4_EVIDENCE_PACKAGE_REVIEW"
FINAL_PRODUCTION_SIGNOFF = False
SOURCE_TRIAL_EVIDENCE_SCOPE = "EXTERNAL_L4_WORKFLOW_TRIAL"
READINESS_STATUS = "READY"
READINESS_CLAIM_STATUS = "NOT_PRODUCTION_CLAIM"
READINESS_EVIDENCE_SCOPE = "EXTERNAL_L4_READINESS_PRECHECK"
PACKAGE_REVIEW_FILES = {
    "package_handoff_trial": "handoff_trial.json",
    "package_readiness": "readiness.json",
    "package_rendered_manifest": "rendered_manifest.json",
    "package_external_evidence": "external_evidence.json",
    "package_artifact_manifest": "artifact_manifest.json",
    "package_readme": "README.md",
    "package_readme_zh": "README.zh-CN.md",
}


def is_utc_datetime(value: datetime) -> bool:
    return value.utcoffset() == timezone.utc.utcoffset(value)


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


def verifier_argv(package_dir: Path, trial_json: Path | None, json_out: Path | None) -> list[str]:
    argv = [VERIFIER, str(package_dir)]
    if trial_json is not None:
        argv.extend(["--trial-json", str(trial_json)])
    if json_out is not None:
        argv.extend(["--json-out", str(json_out)])
    return argv


def file_summary(path: Path) -> dict[str, Any]:
    summary: dict[str, Any] = {"path": str(path), "exists": path.is_file()}
    if path.is_file():
        summary["size_bytes"] = path.stat().st_size
        summary["sha256"] = release_gate.sha256_file(path)
    else:
        summary["size_bytes"] = None
        summary["sha256"] = None
    return summary


def trial_report_summary(path: Path) -> dict[str, Any]:
    summary = file_summary(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - missing/malformed source files are reported elsewhere.
        payload = None
    if not isinstance(payload, dict):
        payload = {}
    summary.update(
        {
            "claim_status": payload.get("claim_status"),
            "evidence_scope": payload.get("evidence_scope"),
            "final_production_signoff": payload.get("final_production_signoff"),
        }
    )
    return summary


def readiness_report_summary(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - missing/malformed package files are reported elsewhere.
        payload = None
    if not isinstance(payload, dict):
        payload = {}
    return {
        "status": payload.get("status"),
        "claim_status": payload.get("claim_status"),
        "evidence_scope": payload.get("evidence_scope"),
        "final_production_signoff": payload.get("final_production_signoff"),
        "generated_at_utc": payload.get("generated_at_utc"),
        "package_name": payload.get("package_name"),
        "workspace": payload.get("workspace"),
        "manifest": payload.get("manifest"),
    }


def readiness_package_name(path: Path) -> str | None:
    package_name = readiness_report_summary(path).get("package_name")
    return package_name if isinstance(package_name, str) and package_name.strip() else None


def parse_readme_value(value: str) -> Any:
    if value == "False":
        return False
    if value == "True":
        return True
    if value == "None":
        return None
    return value


def readme_scope_summary(path: Path) -> dict[str, Any]:
    fields = {
        "claim_status": None,
        "evidence_scope": None,
        "final_production_signoff": None,
        "readiness_status": None,
        "readiness_claim_status": None,
        "readiness_evidence_scope": None,
        "readiness_final_production_signoff": None,
        "readiness_generated_at_utc": None,
        "readiness_package_name": None,
        "readiness_workspace": None,
        "readiness_manifest": None,
        "handoff_contract": {},
    }
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001 - missing/malformed package files are reported elsewhere.
        return fields
    values = dict(fields)
    for line in text.splitlines():
        match = re.fullmatch(r"- ([A-Za-z0-9_.\[\]]+): `(.+)`", line)
        if not match:
            continue
        key, raw_value = match.groups()
        if key in values:
            values[key] = parse_readme_value(raw_value)
        if is_handoff_contract_key(key):
            values["handoff_contract"][key] = raw_value
    return values


def is_handoff_contract_key(key: str) -> bool:
    return (
        key == "morphojet_objects_csv"
        or key == "required_object_metadata_columns"
        or key.startswith("export[")
    )


def rendered_manifest_contract_summary(path: Path) -> dict[str, str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - package file validation reports malformed files elsewhere.
        payload = None
    if not isinstance(payload, dict):
        return {}
    fields = {
        "morphojet_objects_csv": str(payload.get("morphojet_objects_csv")),
        "required_object_metadata_columns": format_manifest_list(
            payload.get("required_object_metadata_columns", [])
        ),
    }
    top_level_metadata = payload.get("required_object_metadata_columns", [])
    for index, export in enumerate(payload.get("exports", [])):
        if not isinstance(export, dict):
            continue
        metadata_columns = export.get("required_object_metadata_columns", top_level_metadata)
        fields[f"export[{index}].name"] = str(export.get("name"))
        fields[f"export[{index}].object_set"] = str(export.get("object_set"))
        fields[f"export[{index}].channels"] = format_manifest_list(export.get("channels", []))
        fields[f"export[{index}].required_object_metadata_columns"] = format_manifest_list(metadata_columns)
        fields[f"export[{index}].out_csv"] = str(export.get("out_csv"))
        for key in ["expected_cellprofiler_csv", "comparison_report", "comparison_json"]:
            if key in export:
                fields[f"export[{index}].{key}"] = str(export.get(key))
    return fields


def format_manifest_list(value: Any) -> str:
    if not isinstance(value, list):
        return "none"
    items = [str(item) for item in value if isinstance(item, str) and item.strip()]
    return ", ".join(items) if items else "none"


def artifact_manifest_claim_scope(path: Path) -> dict[str, Any]:
    fields = {
        "claim_status": None,
        "evidence_scope": None,
        "final_production_signoff": None,
        "trial_claim_status": None,
        "trial_evidence_scope": None,
        "trial_final_production_signoff": None,
    }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - missing/malformed package files are reported elsewhere.
        return fields
    if not isinstance(payload, dict):
        return fields
    return {field: payload.get(field) for field in fields}


def package_input_files(package_dir: Path, trial_json: Path | None = None) -> dict[str, dict[str, Any]]:
    files = {key: file_summary(package_dir / filename) for key, filename in PACKAGE_REVIEW_FILES.items()}
    files["package_artifact_manifest"].update(
        artifact_manifest_claim_scope(package_dir / "artifact_manifest.json")
    )
    files["package_readiness"].update(readiness_report_summary(package_dir / "readiness.json"))
    files["package_readme"].update(readme_scope_summary(package_dir / "README.md"))
    files["package_readme_zh"].update(readme_scope_summary(package_dir / "README.zh-CN.md"))
    files["package_zip"] = file_summary(package_dir.parent / f"{package_dir.name}.zip")
    files["package_zip_sha256"] = file_summary(package_dir.parent / f"{package_dir.name}.zip.sha256")
    if trial_json is not None:
        files["source_trial_json"] = trial_report_summary(trial_json)
    return files


def input_file_summary_issues(name: str, summary: Any, require_exists: bool) -> list[str]:
    failures = []
    if not isinstance(summary, dict):
        return [f"input_files.{name} must be an object"]
    path = summary.get("path")
    if not isinstance(path, str) or not path.strip():
        failures.append(f"input_files.{name}.path must be a non-empty string")
    exists = summary.get("exists")
    if not isinstance(exists, bool):
        failures.append(f"input_files.{name}.exists must be a boolean")
    elif require_exists and not exists:
        failures.append(f"input_files.{name}.exists must be true")
    size = summary.get("size_bytes")
    digest = summary.get("sha256")
    if exists is True:
        if not isinstance(size, int) or size <= 0:
            failures.append(f"input_files.{name}.size_bytes must be a positive integer")
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            failures.append(f"input_files.{name}.sha256 must be a SHA-256 digest")
    else:
        if size is not None:
            failures.append(f"input_files.{name}.size_bytes must be null when missing")
        if digest is not None:
            failures.append(f"input_files.{name}.sha256 must be null when missing")
    return failures


def input_files_issues(input_files: Any, status: Any, require_trial_json: bool) -> list[str]:
    failures = []
    if not isinstance(input_files, dict):
        return ["input_files must be an object"]
    required_keys = set(PACKAGE_REVIEW_FILES) | {"package_zip", "package_zip_sha256"}
    if require_trial_json:
        required_keys.add("source_trial_json")
    allowed_keys = set(required_keys)
    allowed_keys.add("source_trial_json")
    for missing in sorted(required_keys - set(input_files)):
        failures.append(f"input_files missing required entry: {missing}")
    for extra in sorted(set(input_files) - allowed_keys):
        failures.append(f"input_files has unexpected entry: {extra}")
    for name, summary in input_files.items():
        if not isinstance(name, str) or not name.strip():
            failures.append("input_files keys must be non-empty strings")
            continue
        require_exists = status == "PASS" and (name in required_keys or name == "source_trial_json")
        failures.extend(input_file_summary_issues(name, summary, require_exists=require_exists))
        if name == "package_readiness" and isinstance(summary, dict):
            if summary.get("exists"):
                if summary.get("status") != READINESS_STATUS:
                    failures.append(f"input_files.package_readiness.status={summary.get('status')}")
                if summary.get("claim_status") != READINESS_CLAIM_STATUS:
                    failures.append(f"input_files.package_readiness.claim_status={summary.get('claim_status')}")
                if summary.get("evidence_scope") != READINESS_EVIDENCE_SCOPE:
                    failures.append(f"input_files.package_readiness.evidence_scope={summary.get('evidence_scope')}")
                if summary.get("final_production_signoff") is not FINAL_PRODUCTION_SIGNOFF:
                    failures.append("input_files.package_readiness.final_production_signoff must be false")
                generated_at = summary.get("generated_at_utc")
                if not isinstance(generated_at, str) or not generated_at.strip():
                    failures.append("input_files.package_readiness.generated_at_utc must be a non-empty string")
                else:
                    try:
                        parsed_generated_at = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
                        if parsed_generated_at.tzinfo is None:
                            failures.append("input_files.package_readiness.generated_at_utc must include timezone")
                        elif not is_utc_datetime(parsed_generated_at):
                            failures.append("input_files.package_readiness.generated_at_utc must be UTC")
                    except ValueError:
                        failures.append(
                            f"input_files.package_readiness.generated_at_utc is invalid: {generated_at}"
                        )
            if "package_name" not in summary:
                failures.append("input_files.package_readiness.package_name must be present")
            else:
                package_name = summary.get("package_name")
                if package_name is not None:
                    if not isinstance(package_name, str) or not package_name.strip():
                        failures.append("input_files.package_readiness.package_name must be null or a non-empty string")
                    elif release_gate.slugify(package_name) != package_name:
                        failures.append("input_files.package_readiness.package_name must be a canonical slug")
            if summary.get("exists"):
                for field in ["workspace", "manifest"]:
                    value = summary.get(field)
                    if not isinstance(value, str) or not value.strip():
                        failures.append(f"input_files.package_readiness.{field} must be a non-empty string")
                    elif not Path(value).is_absolute():
                        failures.append(f"input_files.package_readiness.{field} must be an absolute path")
        if name in {"package_readme", "package_readme_zh"} and isinstance(summary, dict):
            label = f"input_files.{name}"
            if summary.get("exists"):
                handoff_contract = summary.get("handoff_contract")
                if not isinstance(handoff_contract, dict) or not handoff_contract:
                    failures.append(f"{label}.handoff_contract must be a non-empty object")
                if summary.get("claim_status") != "NOT_PRODUCTION_CLAIM":
                    failures.append(f"{label}.claim_status={summary.get('claim_status')}")
                if summary.get("evidence_scope") != "EXTERNAL_L4_EVIDENCE_PACKAGE":
                    failures.append(f"{label}.evidence_scope={summary.get('evidence_scope')}")
                if summary.get("final_production_signoff") is not False:
                    failures.append(f"{label}.final_production_signoff must be false")
                if summary.get("readiness_status") != READINESS_STATUS:
                    failures.append(f"{label}.readiness_status={summary.get('readiness_status')}")
                if summary.get("readiness_claim_status") != READINESS_CLAIM_STATUS:
                    failures.append(f"{label}.readiness_claim_status={summary.get('readiness_claim_status')}")
                if summary.get("readiness_evidence_scope") != READINESS_EVIDENCE_SCOPE:
                    failures.append(f"{label}.readiness_evidence_scope={summary.get('readiness_evidence_scope')}")
                if summary.get("readiness_final_production_signoff") is not FINAL_PRODUCTION_SIGNOFF:
                    failures.append(f"{label}.readiness_final_production_signoff must be false")
                generated_at = summary.get("readiness_generated_at_utc")
                if not isinstance(generated_at, str) or not generated_at.strip():
                    failures.append(f"{label}.readiness_generated_at_utc must be a non-empty string")
                else:
                    try:
                        parsed_generated_at = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
                        if parsed_generated_at.tzinfo is None:
                            failures.append(f"{label}.readiness_generated_at_utc must include timezone")
                        elif not is_utc_datetime(parsed_generated_at):
                            failures.append(f"{label}.readiness_generated_at_utc must be UTC")
                    except ValueError:
                        failures.append(f"{label}.readiness_generated_at_utc is invalid: {generated_at}")
                if "readiness_package_name" not in summary:
                    failures.append(f"{label}.readiness_package_name must be present")
                else:
                    package_name = summary.get("readiness_package_name")
                    if package_name is not None:
                        if not isinstance(package_name, str) or not package_name.strip():
                            failures.append(f"{label}.readiness_package_name must be null or a non-empty string")
                        elif release_gate.slugify(package_name) != package_name:
                            failures.append(f"{label}.readiness_package_name must be a canonical slug")
                for field in ["readiness_workspace", "readiness_manifest"]:
                    value = summary.get(field)
                    if not isinstance(value, str) or not value.strip():
                        failures.append(f"{label}.{field} must be a non-empty string")
                    elif not Path(value).is_absolute():
                        failures.append(f"{label}.{field} must be an absolute path")
        if name == "package_artifact_manifest" and isinstance(summary, dict):
            for field in [
                "claim_status",
                "evidence_scope",
                "final_production_signoff",
                "trial_claim_status",
                "trial_evidence_scope",
                "trial_final_production_signoff",
            ]:
                if field not in summary:
                    failures.append(f"input_files.package_artifact_manifest.{field} must be present")
            if status == "PASS":
                if summary.get("claim_status") != "NOT_PRODUCTION_CLAIM":
                    failures.append(
                        f"input_files.package_artifact_manifest.claim_status={summary.get('claim_status')}"
                    )
                if summary.get("evidence_scope") != "EXTERNAL_L4_EVIDENCE_PACKAGE":
                    failures.append(
                        f"input_files.package_artifact_manifest.evidence_scope={summary.get('evidence_scope')}"
                    )
                if summary.get("final_production_signoff") is not False:
                    failures.append(
                        "input_files.package_artifact_manifest.final_production_signoff must be false"
                    )
                if summary.get("trial_claim_status") != CLAIM_STATUS:
                    failures.append(
                        f"input_files.package_artifact_manifest.trial_claim_status={summary.get('trial_claim_status')}"
                    )
                if summary.get("trial_evidence_scope") != SOURCE_TRIAL_EVIDENCE_SCOPE:
                    failures.append(
                        "input_files.package_artifact_manifest.trial_evidence_scope="
                        f"{summary.get('trial_evidence_scope')}"
                    )
                if summary.get("trial_final_production_signoff") is not FINAL_PRODUCTION_SIGNOFF:
                    failures.append(
                        "input_files.package_artifact_manifest.trial_final_production_signoff must be false"
                    )
        if name == "source_trial_json" and isinstance(summary, dict):
            for field in ["claim_status", "evidence_scope", "final_production_signoff"]:
                if field not in summary:
                    failures.append(f"input_files.source_trial_json.{field} must be present")
            if status == "PASS":
                if summary.get("claim_status") != CLAIM_STATUS:
                    failures.append(f"input_files.source_trial_json.claim_status={summary.get('claim_status')}")
                if summary.get("evidence_scope") != SOURCE_TRIAL_EVIDENCE_SCOPE:
                    failures.append(
                        f"input_files.source_trial_json.evidence_scope={summary.get('evidence_scope')}"
                    )
                if summary.get("final_production_signoff") is not FINAL_PRODUCTION_SIGNOFF:
                    failures.append("input_files.source_trial_json.final_production_signoff must be false")
    return failures


def input_file_path_binding_issues(
    input_files: dict[str, Any],
    package_dir: str,
    trial_json: str | None,
) -> list[str]:
    failures = []
    root = Path(package_dir)
    expected_paths = {
        key: str(root / filename)
        for key, filename in PACKAGE_REVIEW_FILES.items()
    }
    expected_paths["package_zip"] = str(root.parent / f"{root.name}.zip")
    expected_paths["package_zip_sha256"] = str(root.parent / f"{root.name}.zip.sha256")
    if trial_json is not None:
        expected_paths["source_trial_json"] = trial_json
    for name, expected_path in expected_paths.items():
        summary = input_files.get(name)
        if isinstance(summary, dict) and summary.get("path") != expected_path:
            failures.append(f"input_files.{name}.path must match report inputs")
    readiness_summary = input_files.get("package_readiness")
    if isinstance(readiness_summary, dict):
        expected_readiness = readiness_report_summary(root / "readiness.json")
        for field in [
            "status",
            "claim_status",
            "evidence_scope",
            "final_production_signoff",
            "generated_at_utc",
            "package_name",
            "workspace",
            "manifest",
        ]:
            if readiness_summary.get(field) != expected_readiness.get(field):
                failures.append(f"input_files.package_readiness.{field} must match package readiness report")
    readiness_path = root / "readiness.json"
    expected_readiness = readiness_report_summary(readiness_path)
    expected_contract = rendered_manifest_contract_summary(root / "rendered_manifest.json")
    expected_manifest_scope = artifact_manifest_claim_scope(root / "artifact_manifest.json")
    for readme_name, readme_file in [
        ("package_readme", root / "README.md"),
        ("package_readme_zh", root / "README.zh-CN.md"),
    ]:
        readme_summary = input_files.get(readme_name)
        if not isinstance(readme_summary, dict):
            continue
        expected_readme = readme_scope_summary(readme_file)
        for field in [
            "claim_status",
            "evidence_scope",
            "final_production_signoff",
            "readiness_status",
            "readiness_claim_status",
            "readiness_evidence_scope",
            "readiness_final_production_signoff",
            "readiness_generated_at_utc",
            "readiness_package_name",
            "readiness_workspace",
            "readiness_manifest",
        ]:
            if readme_summary.get(field) != expected_readme.get(field):
                failures.append(f"input_files.{readme_name}.{field} must match package README")
        if readme_summary.get("handoff_contract") != expected_readme.get("handoff_contract"):
            failures.append(f"input_files.{readme_name}.handoff_contract must match package README")
        if readme_summary.get("handoff_contract") != expected_contract:
            failures.append(f"input_files.{readme_name}.handoff_contract must match rendered manifest")
        readme_to_manifest = {
            "claim_status": "claim_status",
            "evidence_scope": "evidence_scope",
            "final_production_signoff": "final_production_signoff",
        }
        for readme_field, manifest_field in readme_to_manifest.items():
            if readme_summary.get(readme_field) != expected_manifest_scope.get(manifest_field):
                failures.append(f"input_files.{readme_name}.{readme_field} must match package artifact manifest")
        if readiness_path.is_file():
            readme_to_readiness = {
                "readiness_status": "status",
                "readiness_claim_status": "claim_status",
                "readiness_evidence_scope": "evidence_scope",
                "readiness_final_production_signoff": "final_production_signoff",
                "readiness_generated_at_utc": "generated_at_utc",
                "readiness_package_name": "package_name",
                "readiness_workspace": "workspace",
                "readiness_manifest": "manifest",
            }
            for readme_field, readiness_field in readme_to_readiness.items():
                if readme_summary.get(readme_field) != expected_readiness.get(readiness_field):
                    failures.append(f"input_files.{readme_name}.{readme_field} must match package readiness report")
    source_trial_summary = input_files.get("source_trial_json")
    if isinstance(source_trial_summary, dict) and trial_json is not None:
        try:
            source_trial_payload = json.loads(Path(trial_json).read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - malformed files are covered by gate/file checks.
            source_trial_payload = None
        if isinstance(source_trial_payload, dict):
            expected_fields = {
                "claim_status": "claim_status",
                "evidence_scope": "evidence_scope",
                "final_production_signoff": "final_production_signoff",
            }
            for summary_key, payload_key in expected_fields.items():
                if source_trial_summary.get(summary_key) != source_trial_payload.get(payload_key):
                    failures.append(f"input_files.source_trial_json.{summary_key} must match source trial report")
    return failures


def recomputed_input_file_issues(recorded: dict[str, Any], package_dir: Path, trial_json: Path | None) -> list[str]:
    failures = []
    current = package_input_files(package_dir, trial_json)
    for name, current_summary in current.items():
        recorded_summary = recorded.get(name)
        if not isinstance(recorded_summary, dict):
            failures.append(f"input_files.{name} missing from saved report")
            continue
        for field in [
            "path",
            "exists",
            "size_bytes",
            "sha256",
            "status",
            "generated_at_utc",
            "package_name",
            "workspace",
            "manifest",
            "claim_status",
            "evidence_scope",
            "final_production_signoff",
            "trial_claim_status",
            "trial_evidence_scope",
            "trial_final_production_signoff",
            "readiness_status",
            "readiness_claim_status",
            "readiness_evidence_scope",
            "readiness_final_production_signoff",
            "readiness_generated_at_utc",
            "readiness_package_name",
            "readiness_workspace",
            "readiness_manifest",
            "handoff_contract",
        ]:
            if recorded_summary.get(field) != current_summary.get(field):
                failures.append(f"input_files.{name}.{field} changed after recomputing evidence package validation")
    for name in sorted(set(recorded) - set(current)):
        failures.append(f"input_files has unexpected saved entry: {name}")
    return failures


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


def package_artifact_paths(package_dir: Path) -> dict[str, Path]:
    manifest_path = package_dir / "artifact_manifest.json"
    if not manifest_path.is_file():
        return {}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(manifest, dict):
        return {}
    paths = {}
    for entry in manifest.get("artifacts", []):
        if isinstance(entry, dict) and isinstance(entry.get("package_path"), str) and entry["package_path"]:
            paths[f"package artifact: {entry['package_path']}"] = package_dir / entry["package_path"]
    return paths


def validate_json_out_path(json_out: Path | None, package_dir: Path, trial_json: Path | None) -> None:
    if json_out is None:
        return
    protected_paths = [
        (package_dir / filename, f"package review file: {filename}")
        for filename in PACKAGE_REVIEW_FILES.values()
    ]
    protected_paths.append((package_dir.parent / f"{package_dir.name}.zip", f"package zip: {package_dir.name}.zip"))
    protected_paths.append(
        (package_dir.parent / f"{package_dir.name}.zip.sha256", f"package checksum: {package_dir.name}.zip.sha256")
    )
    if trial_json is not None:
        protected_paths.append((trial_json, f"source trial JSON: {trial_json}"))
    for label, path in package_artifact_paths(package_dir).items():
        protected_paths.append((path, label))
    seen = set()
    for protected_path, protected_label in protected_paths:
        key = (normalized_path_key(protected_path), protected_label)
        if key in seen:
            continue
        seen.add(key)
        if normalized_path_key(json_out) == normalized_path_key(protected_path):
            raise SystemExit(f"--json-out must not overwrite {protected_label}")
        if path_matches_or_is_inside(protected_path, json_out):
            raise SystemExit(f"--json-out must not create a file inside {protected_label}")


def verify_external_evidence_package(
    package_dir: Path,
    trial_json: Path | None = None,
    json_out: Path | None = None,
    require_pass: bool = True,
) -> int:
    package_dir = package_dir.resolve()
    if trial_json is not None:
        trial_json = trial_json.resolve()
    if json_out is not None:
        json_out = json_out.resolve()
    validate_json_out_path(json_out, package_dir, trial_json)
    gate = release_gate.validate_external_evidence_package(package_dir, trial_json)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "verifier": VERIFIER,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "claim_status": CLAIM_STATUS,
        "evidence_scope": EVIDENCE_SCOPE,
        "final_production_signoff": FINAL_PRODUCTION_SIGNOFF,
        "status": gate.status,
        "argv": verifier_argv(package_dir, trial_json, json_out),
        "package_dir": str(package_dir),
        "trial_json": str(trial_json) if trial_json else None,
        "input_files": package_input_files(package_dir, trial_json),
        "gate": asdict(gate),
    }
    if json_out:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if gate.status == "PASS":
        print(gate.detail)
        if json_out:
            print(f"wrote {json_out}")
        return 0
    print(f"FAIL: {gate.detail}", file=sys.stderr)
    if json_out:
        print(f"wrote {json_out}", file=sys.stderr)
    return 1 if require_pass else 0


def validate_verification_report_payload(
    payload: Any,
    require_report_pass: bool = False,
    require_trial_json: bool = False,
    report_path: Path | None = None,
) -> list[str]:
    failures: list[str] = []
    if not isinstance(payload, dict):
        return ["external evidence package verification report must be a JSON object"]
    status = payload.get("status")
    if status not in {"PASS", "FAIL"}:
        failures.append(f"status={status}")
    if require_report_pass and status != "PASS":
        failures.append(f"external evidence package verification report status is not PASS: {status}")
    if payload.get("schema_version") != SCHEMA_VERSION:
        failures.append(f"schema_version={payload.get('schema_version')}")
    if payload.get("verifier") != VERIFIER:
        failures.append(f"verifier={payload.get('verifier')}")
    if payload.get("claim_status") != CLAIM_STATUS:
        failures.append(f"claim_status={payload.get('claim_status')}")
    if payload.get("evidence_scope") != EVIDENCE_SCOPE:
        failures.append(f"evidence_scope={payload.get('evidence_scope')}")
    if payload.get("final_production_signoff") is not FINAL_PRODUCTION_SIGNOFF:
        failures.append("final_production_signoff must be false")
    generated_at = payload.get("generated_at_utc")
    if isinstance(generated_at, str):
        try:
            parsed_generated_at = datetime.fromisoformat(generated_at)
            if parsed_generated_at.tzinfo is None:
                failures.append("generated_at_utc must include timezone")
            elif not is_utc_datetime(parsed_generated_at):
                failures.append("generated_at_utc must be UTC")
        except ValueError:
            failures.append(f"generated_at_utc is invalid: {generated_at}")
    else:
        failures.append("generated_at_utc must be a string")
    package_dir = payload.get("package_dir")
    if not isinstance(package_dir, str) or not package_dir.strip():
        failures.append("package_dir must be a non-empty string")
    elif not Path(package_dir).is_absolute():
        failures.append("package_dir must be an absolute path")
    trial_json = payload.get("trial_json")
    if trial_json is not None and (not isinstance(trial_json, str) or not trial_json.strip()):
        failures.append("trial_json must be null or a non-empty string")
    elif isinstance(trial_json, str) and trial_json.strip() and not Path(trial_json).is_absolute():
        failures.append("trial_json must be an absolute path")
    if require_trial_json and (not isinstance(trial_json, str) or not trial_json.strip()):
        failures.append("trial_json is required for production package reviewer reports")
    argv = payload.get("argv")
    if not isinstance(argv, list) or not argv or not all(isinstance(item, str) and item for item in argv):
        failures.append("argv must be a non-empty string list")
    elif isinstance(package_dir, str) and package_dir.strip():
        failures.extend(
            verification_report_argv_issues(
                argv,
                package_dir,
                trial_json if isinstance(trial_json, str) and trial_json.strip() else None,
                report_path,
            )
        )
    input_files = payload.get("input_files")
    failures.extend(input_files_issues(input_files, status, require_trial_json))
    if isinstance(input_files, dict) and isinstance(package_dir, str) and package_dir.strip():
        failures.extend(
            input_file_path_binding_issues(
                input_files,
                package_dir,
                trial_json if isinstance(trial_json, str) else None,
            )
        )
    gate = payload.get("gate")
    if not isinstance(gate, dict):
        failures.append("gate must be an object")
        return failures
    if gate.get("name") != "Validate external L4 evidence package":
        failures.append(f"gate.name={gate.get('name')}")
    gate_status = gate.get("status")
    if gate_status not in {"PASS", "FAIL"}:
        failures.append(f"gate.status={gate_status}")
    if status != gate_status:
        failures.append(f"status does not match gate.status: {status} != {gate_status}")
    if not isinstance(gate.get("detail"), str) or not gate["detail"].strip():
        failures.append("gate.detail must be a non-empty string")
    if gate.get("command") is not None:
        failures.append("gate.command must be null")
    elapsed = gate.get("elapsed_seconds")
    if not isinstance(elapsed, (int, float)) or elapsed < 0:
        failures.append(f"gate.elapsed_seconds={elapsed}")
    return failures


def verification_report_argv_issues(
    argv: list[str],
    package_dir: str,
    trial_json: str | None,
    report_path: Path | None = None,
) -> list[str]:
    failures = []
    if argv[0] != VERIFIER:
        failures.append(f"argv[0]={argv[0]}")
    if "--verify-report" in argv:
        failures.append("argv must not include --verify-report for a generated verifier report")
    if len(argv) < 2 or argv[1].startswith("--"):
        failures.append("argv must include package_dir positional argument")
    else:
        if not Path(argv[1]).is_absolute():
            failures.append(f"argv package_dir must be an absolute path: {argv[1]}")
        if argv[1] != package_dir:
            failures.append(f"package_dir must match argv package_dir {argv[1]}")
    if argv.count(package_dir) != 1:
        failures.append(f"argv must include package_dir exactly once: {package_dir}")
    trial_json_values = argv_values(argv, "--trial-json")
    if len(trial_json_values) > 1:
        failures.append("argv has duplicate --trial-json")
    if trial_json is not None and not trial_json_values:
        failures.append(f"argv missing --trial-json {trial_json}")
    if trial_json is None and trial_json_values:
        failures.append("argv must not include --trial-json when trial_json is null")
    for value in trial_json_values:
        if value is None:
            failures.append("argv --trial-json must include a value")
        elif not Path(value).is_absolute():
            failures.append(f"argv --trial-json must be an absolute path: {value}")
        elif trial_json != value:
            failures.append(f"trial_json must match argv --trial-json {value}")
    json_out_values = argv_values(argv, "--json-out")
    if len(json_out_values) > 1:
        failures.append("argv has duplicate --json-out")
    if report_path is not None and not json_out_values:
        failures.append("argv missing --json-out for saved verifier report")
    for value in json_out_values:
        if value is None:
            failures.append("argv --json-out must include a value")
        elif not Path(value).is_absolute():
            failures.append("argv --json-out must be an absolute path")
        elif report_path is not None and normalized_path_key(Path(value)) != normalized_path_key(report_path):
            failures.append("argv --json-out must match saved verifier report path")
    return failures


def verify_saved_external_evidence_package_report(
    report: Path,
    require_report_pass: bool = False,
    verify_files: bool = False,
    require_trial_json: bool = False,
) -> int:
    try:
        payload = json.loads(report.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - exact report verification failure.
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    failures = validate_verification_report_payload(
        payload,
        require_report_pass=require_report_pass,
        require_trial_json=require_trial_json,
        report_path=report,
    )
    if not failures and verify_files:
        package_dir = Path(payload["package_dir"])
        trial_json = Path(payload["trial_json"]) if payload.get("trial_json") is not None else None
        gate = release_gate.validate_external_evidence_package(package_dir, trial_json)
        recorded_gate = payload["gate"]
        if recorded_gate.get("name") != gate.name:
            failures.append(f"gate.name changed: {recorded_gate.get('name')} != {gate.name}")
        if recorded_gate.get("status") != gate.status:
            failures.append(f"gate.status changed: {recorded_gate.get('status')} != {gate.status}")
        if recorded_gate.get("detail") != gate.detail:
            failures.append("gate.detail changed after recomputing evidence package validation")
        if payload.get("status") != gate.status:
            failures.append(
                "status changed after recomputing evidence package validation: "
                f"{payload.get('status')} != {gate.status}"
            )
        failures.extend(recomputed_input_file_issues(payload["input_files"], package_dir, trial_json))
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print(f"external evidence package verification report ok: {report}")
    print(f"status={payload['status']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("package_dir", nargs="?", type=Path, help="External L4 evidence package directory")
    parser.add_argument(
        "--trial-json",
        type=Path,
        help="Optional source handoff_trial.json to bind the package to a specific trial report",
    )
    parser.add_argument("--json-out", type=Path, help="Optional machine-readable verifier report")
    parser.add_argument("--verify-report", type=Path, help="Validate a saved verifier JSON report")
    parser.add_argument("--verify-report-files", action="store_true", help="Recompute package validation from report paths")
    parser.add_argument("--require-report-pass", action="store_true", help="Reject saved verifier reports that are not PASS")
    parser.add_argument(
        "--require-trial-json",
        action="store_true",
        help="With --verify-report, require the saved package reviewer report to be bound to a source trial JSON",
    )
    parser.add_argument(
        "--allow-fail-report",
        action="store_true",
        help="Write/print a FAIL report but exit 0; intended only for diagnostics",
    )
    args = parser.parse_args()
    if args.verify_report:
        return verify_saved_external_evidence_package_report(
            args.verify_report,
            require_report_pass=args.require_report_pass,
            verify_files=args.verify_report_files,
            require_trial_json=args.require_trial_json,
        )
    if args.package_dir is None:
        parser.error("package_dir is required unless --verify-report is used")
    return verify_external_evidence_package(
        args.package_dir,
        trial_json=args.trial_json,
        json_out=args.json_out,
        require_pass=not args.allow_fail_report,
    )


if __name__ == "__main__":
    raise SystemExit(main())
