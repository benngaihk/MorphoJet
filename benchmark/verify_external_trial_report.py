#!/usr/bin/env python3
"""Validate an external L4 handoff trial report."""

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
VERIFIER = "benchmark/verify_external_trial_report.py"
SHA256_RE = re.compile(r"[0-9a-f]{64}")
CLAIM_STATUS = release_gate.NON_FINAL_CLAIM_STATUS
EVIDENCE_SCOPE = release_gate.EXTERNAL_TRIAL_REVIEW_EVIDENCE_SCOPE
FINAL_PRODUCTION_SIGNOFF = release_gate.NON_FINAL_PRODUCTION_SIGNOFF
SOURCE_TRIAL_EVIDENCE_SCOPE = release_gate.EXTERNAL_TRIAL_EVIDENCE_SCOPE
READINESS_STATUS = release_gate.EXTERNAL_READINESS_STATUS
READINESS_CLAIM_STATUS = release_gate.NON_FINAL_CLAIM_STATUS
READINESS_EVIDENCE_SCOPE = release_gate.EXTERNAL_READINESS_EVIDENCE_SCOPE


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


def verifier_argv(trial_json: Path, trial_root: Path, json_out: Path | None) -> list[str]:
    argv = [VERIFIER, str(trial_json), "--trial-root", str(trial_root)]
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


def trial_report_summary(trial_json: Path) -> dict[str, Any]:
    summary = file_summary(trial_json)
    trial = load_trial_payload(trial_json)
    summary.update(
        {
            "claim_status": trial.get("claim_status") if isinstance(trial, dict) else None,
            "evidence_scope": trial.get("evidence_scope") if isinstance(trial, dict) else None,
            "final_production_signoff": (
                trial.get("final_production_signoff") if isinstance(trial, dict) else None
            ),
        }
    )
    return summary


def load_trial_artifacts(trial_json: Path) -> list[str]:
    trial = load_trial_payload(trial_json)
    artifacts = trial.get("artifacts") if isinstance(trial, dict) else None
    if not isinstance(artifacts, list):
        return []
    return [artifact for artifact in artifacts if isinstance(artifact, str)]


def load_trial_payload(trial_json: Path) -> dict[str, Any] | None:
    try:
        with trial_json.open("r", encoding="utf-8") as handle:
            trial = json.load(handle)
    except Exception:  # noqa: BLE001 - malformed reports still need diagnostic summaries.
        return None
    return trial if isinstance(trial, dict) else None


def load_trial_readiness_report_path(trial_json: Path) -> Path | None:
    trial = load_trial_payload(trial_json)
    readiness = trial.get("readiness_report") if isinstance(trial, dict) else None
    path = readiness.get("path") if isinstance(readiness, dict) else None
    if isinstance(path, str) and path.strip():
        return Path(path)
    return None


def load_trial_readiness_report_package_name(trial_json: Path) -> str | None:
    trial = load_trial_payload(trial_json)
    readiness = trial.get("readiness_report") if isinstance(trial, dict) else None
    package_name = readiness.get("package_name") if isinstance(readiness, dict) else None
    return package_name if isinstance(package_name, str) and package_name.strip() else None


def load_trial_readiness_report_field(trial_json: Path, field: str) -> str | None:
    trial = load_trial_payload(trial_json)
    readiness = trial.get("readiness_report") if isinstance(trial, dict) else None
    value = readiness.get(field) if isinstance(readiness, dict) else None
    return value if isinstance(value, str) and value.strip() else None


def load_trial_readiness_report_value(trial_json: Path, field: str) -> Any:
    trial = load_trial_payload(trial_json)
    readiness = trial.get("readiness_report") if isinstance(trial, dict) else None
    return readiness.get(field) if isinstance(readiness, dict) else None


def trial_input_files(trial_json: Path, trial_root: Path) -> dict[str, Any]:
    artifact_files = []
    for artifact in load_trial_artifacts(trial_json):
        resolved_path = release_gate.resolve_artifact_path(artifact, trial_root)
        summary = file_summary(resolved_path)
        artifact_files.append({"source_path": artifact, **summary})
    input_files = {
        "trial_json": trial_report_summary(trial_json),
        "artifact_files": sorted(artifact_files, key=lambda entry: entry["source_path"]),
    }
    readiness_path = load_trial_readiness_report_path(trial_json)
    if readiness_path is not None:
        input_files["readiness_report"] = {
            **file_summary(readiness_path),
            "status": load_trial_readiness_report_field(trial_json, "status"),
            "claim_status": load_trial_readiness_report_field(trial_json, "claim_status"),
            "evidence_scope": load_trial_readiness_report_field(trial_json, "evidence_scope"),
            "final_production_signoff": load_trial_readiness_report_value(
                trial_json,
                "final_production_signoff",
            ),
            "generated_at_utc": load_trial_readiness_report_field(trial_json, "generated_at_utc"),
            "package_name": load_trial_readiness_report_package_name(trial_json),
            "workspace": load_trial_readiness_report_field(trial_json, "workspace"),
            "manifest": load_trial_readiness_report_field(trial_json, "manifest"),
        }
    return input_files


def file_summary_issues(name: str, summary: Any, require_exists: bool) -> list[str]:
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


def input_files_issues(input_files: Any, status: Any) -> list[str]:
    failures = []
    if not isinstance(input_files, dict):
        return ["input_files must be an object"]
    trial_summary = input_files.get("trial_json")
    failures.extend(file_summary_issues("trial_json", trial_summary, require_exists=status == "PASS"))
    if isinstance(trial_summary, dict):
        if trial_summary.get("claim_status") != CLAIM_STATUS:
            failures.append(f"input_files.trial_json.claim_status={trial_summary.get('claim_status')}")
        if trial_summary.get("evidence_scope") != SOURCE_TRIAL_EVIDENCE_SCOPE:
            failures.append(f"input_files.trial_json.evidence_scope={trial_summary.get('evidence_scope')}")
        if trial_summary.get("final_production_signoff") is not FINAL_PRODUCTION_SIGNOFF:
            failures.append("input_files.trial_json.final_production_signoff must be false")
    if status == "PASS" and "readiness_report" not in input_files:
        failures.append("input_files.readiness_report must be present for PASS reports")
    if "readiness_report" in input_files:
        failures.extend(
            file_summary_issues(
                "readiness_report",
                input_files.get("readiness_report"),
                require_exists=status == "PASS",
            )
        )
        readiness_summary = input_files.get("readiness_report")
        if isinstance(readiness_summary, dict):
            if readiness_summary.get("status") != READINESS_STATUS:
                failures.append(f"input_files.readiness_report.status={readiness_summary.get('status')}")
            if readiness_summary.get("claim_status") != READINESS_CLAIM_STATUS:
                failures.append(f"input_files.readiness_report.claim_status={readiness_summary.get('claim_status')}")
            if readiness_summary.get("evidence_scope") != READINESS_EVIDENCE_SCOPE:
                failures.append(f"input_files.readiness_report.evidence_scope={readiness_summary.get('evidence_scope')}")
            if readiness_summary.get("final_production_signoff") is not FINAL_PRODUCTION_SIGNOFF:
                failures.append("input_files.readiness_report.final_production_signoff must be false")
            generated_at = readiness_summary.get("generated_at_utc")
            if not isinstance(generated_at, str) or not generated_at.strip():
                failures.append("input_files.readiness_report.generated_at_utc must be a non-empty string")
            else:
                try:
                    parsed_generated_at = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
                    if parsed_generated_at.tzinfo is None:
                        failures.append("input_files.readiness_report.generated_at_utc must include timezone")
                    elif not is_utc_datetime(parsed_generated_at):
                        failures.append("input_files.readiness_report.generated_at_utc must be UTC")
                except ValueError:
                    failures.append(f"input_files.readiness_report.generated_at_utc is invalid: {generated_at}")
            package_name = readiness_summary.get("package_name")
            if package_name is not None:
                if not isinstance(package_name, str) or not package_name.strip():
                    failures.append("input_files.readiness_report.package_name must be null or a non-empty string")
                elif release_gate.slugify(package_name) != package_name:
                    failures.append("input_files.readiness_report.package_name must be a canonical slug")
            for field in ["workspace", "manifest"]:
                value = readiness_summary.get(field)
                if not isinstance(value, str) or not value.strip():
                    failures.append(f"input_files.readiness_report.{field} must be a non-empty string")
                elif not Path(value).is_absolute():
                    failures.append(f"input_files.readiness_report.{field} must be an absolute path")
    artifact_files = input_files.get("artifact_files")
    if not isinstance(artifact_files, list):
        return failures + ["input_files.artifact_files must be a list"]
    observed_sources = []
    for index, artifact in enumerate(artifact_files):
        if not isinstance(artifact, dict):
            failures.append("input_files.artifact_files entries must be objects")
            continue
        source_path = artifact.get("source_path")
        if not isinstance(source_path, str) or not source_path.strip():
            failures.append(f"input_files.artifact_files[{index}].source_path must be a non-empty string")
            continue
        observed_sources.append(source_path)
        failures.extend(file_summary_issues(f"artifact_files[{index}]", artifact, require_exists=status == "PASS"))
    if observed_sources != sorted(observed_sources):
        failures.append("input_files.artifact_files must be sorted by source_path")
    for source_path in sorted(source for source in set(observed_sources) if observed_sources.count(source) > 1):
        failures.append(f"input_files.artifact_files source_path is duplicated: {source_path}")
    return failures


def input_file_path_binding_issues(input_files: dict[str, Any], trial_json: str, trial_root: str) -> list[str]:
    failures = []
    trial_summary = input_files.get("trial_json")
    if isinstance(trial_summary, dict) and trial_summary.get("path") != trial_json:
        failures.append("input_files.trial_json.path must match trial_json")
    trial_payload = load_trial_payload(Path(trial_json))
    if isinstance(trial_summary, dict) and isinstance(trial_payload, dict):
        expected_fields = {
            "claim_status": "claim_status",
            "evidence_scope": "evidence_scope",
            "final_production_signoff": "final_production_signoff",
        }
        for summary_key, payload_key in expected_fields.items():
            if trial_summary.get(summary_key) != trial_payload.get(payload_key):
                failures.append(f"input_files.trial_json.{summary_key} must match source trial report")
    readiness_summary = input_files.get("readiness_report")
    readiness_path = load_trial_readiness_report_path(Path(trial_json))
    if isinstance(readiness_summary, dict):
        if readiness_path is None:
            failures.append("input_files.readiness_report must match a trial readiness_report path")
        elif readiness_summary.get("path") != str(readiness_path):
            failures.append("input_files.readiness_report.path must match trial readiness_report.path")
        trial_package_name = load_trial_readiness_report_package_name(Path(trial_json))
        if readiness_summary.get("package_name") != trial_package_name:
            failures.append("input_files.readiness_report.package_name must match trial readiness_report.package_name")
        expected_fields = [
            "status",
            "claim_status",
            "evidence_scope",
            "final_production_signoff",
            "generated_at_utc",
        ]
        for field in expected_fields:
            expected = load_trial_readiness_report_value(Path(trial_json), field)
            if readiness_summary.get(field) != expected:
                failures.append(f"input_files.readiness_report.{field} must match trial readiness_report.{field}")
        for field in ["workspace", "manifest"]:
            expected = load_trial_readiness_report_field(Path(trial_json), field)
            if readiness_summary.get(field) != expected:
                failures.append(f"input_files.readiness_report.{field} must match trial readiness_report.{field}")
    artifact_files = input_files.get("artifact_files")
    if not isinstance(artifact_files, list):
        return failures
    root = Path(trial_root)
    for index, artifact in enumerate(artifact_files):
        if not isinstance(artifact, dict):
            continue
        source_path = artifact.get("source_path")
        if not isinstance(source_path, str) or not source_path.strip():
            continue
        expected_path = str(release_gate.resolve_artifact_path(source_path, root))
        if artifact.get("path") != expected_path:
            failures.append(f"input_files.artifact_files[{index}].path must match resolved source_path")
    return failures


def recomputed_input_file_issues(recorded: dict[str, Any], trial_json: Path, trial_root: Path) -> list[str]:
    failures = []
    current = trial_input_files(trial_json, trial_root)
    for field in [
        "path",
        "exists",
        "size_bytes",
        "sha256",
        "claim_status",
        "evidence_scope",
        "final_production_signoff",
    ]:
        if recorded["trial_json"].get(field) != current["trial_json"].get(field):
            failures.append(f"input_files.trial_json.{field} changed after recomputing trial validation")
    if recorded.get("readiness_report") != current.get("readiness_report"):
        failures.append("input_files.readiness_report changed after recomputing trial validation")
    recorded_artifacts = recorded.get("artifact_files")
    if not isinstance(recorded_artifacts, list):
        return failures + ["input_files.artifact_files must be a list"]
    if recorded_artifacts != current["artifact_files"]:
        failures.append("input_files.artifact_files changed after recomputing trial validation")
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


def validate_json_out_path(json_out: Path | None, trial_json: Path, trial_root: Path) -> None:
    if json_out is None:
        return
    protected_paths = [(trial_json, f"trial JSON: {trial_json}")]
    readiness_path = load_trial_readiness_report_path(trial_json)
    if readiness_path is not None:
        protected_paths.append((readiness_path, f"readiness report: {readiness_path}"))
    for artifact in load_trial_artifacts(trial_json):
        artifact_path = release_gate.resolve_artifact_path(artifact, trial_root)
        protected_paths.append((artifact_path, f"trial artifact: {artifact}"))
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


def verify_external_trial_report(
    trial_json: Path,
    trial_root: Path,
    json_out: Path | None = None,
    require_pass: bool = True,
) -> int:
    trial_json = trial_json.resolve()
    trial_root = trial_root.resolve()
    if json_out is not None:
        json_out = json_out.resolve()
    validate_json_out_path(json_out, trial_json, trial_root)
    gate = release_gate.validate_external_trial_report(trial_json, trial_root)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "verifier": VERIFIER,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "claim_status": CLAIM_STATUS,
        "evidence_scope": EVIDENCE_SCOPE,
        "final_production_signoff": FINAL_PRODUCTION_SIGNOFF,
        "status": gate.status,
        "argv": verifier_argv(trial_json, trial_root, json_out),
        "trial_json": str(trial_json),
        "trial_root": str(trial_root),
        "input_files": trial_input_files(trial_json, trial_root),
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
    report_path: Path | None = None,
) -> list[str]:
    failures: list[str] = []
    if not isinstance(payload, dict):
        return ["external trial verification report must be a JSON object"]
    status = payload.get("status")
    if status not in {"PASS", "FAIL"}:
        failures.append(f"status={status}")
    if require_report_pass and status != "PASS":
        failures.append(f"external trial verification report status is not PASS: {status}")
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
    trial_json = payload.get("trial_json")
    if not isinstance(trial_json, str) or not trial_json.strip():
        failures.append("trial_json must be a non-empty string")
    elif not Path(trial_json).is_absolute():
        failures.append("trial_json must be an absolute path")
    trial_root = payload.get("trial_root")
    if not isinstance(trial_root, str) or not trial_root.strip():
        failures.append("trial_root must be a non-empty string")
    elif not Path(trial_root).is_absolute():
        failures.append("trial_root must be an absolute path")
    argv = payload.get("argv")
    if not isinstance(argv, list) or not argv or not all(isinstance(item, str) and item for item in argv):
        failures.append("argv must be a non-empty string list")
    elif isinstance(trial_json, str) and trial_json.strip() and isinstance(trial_root, str) and trial_root.strip():
        failures.extend(verification_report_argv_issues(argv, trial_json, trial_root, report_path))
    input_files = payload.get("input_files")
    failures.extend(input_files_issues(input_files, status))
    if (
        isinstance(input_files, dict)
        and isinstance(trial_json, str)
        and trial_json.strip()
        and isinstance(trial_root, str)
        and trial_root.strip()
    ):
        failures.extend(input_file_path_binding_issues(input_files, trial_json, trial_root))
    gate = payload.get("gate")
    if not isinstance(gate, dict):
        failures.append("gate must be an object")
        return failures
    if gate.get("name") != "Validate external L4 workflow trial report":
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
    trial_json: str,
    trial_root: str,
    report_path: Path | None = None,
) -> list[str]:
    failures = []
    if argv[0] != VERIFIER:
        failures.append(f"argv[0]={argv[0]}")
    if "--verify-report" in argv:
        failures.append("argv must not include --verify-report for a generated verifier report")
    if len(argv) < 2 or argv[1].startswith("--"):
        failures.append("argv must include trial_json positional argument")
    else:
        if not Path(argv[1]).is_absolute():
            failures.append(f"argv trial_json must be an absolute path: {argv[1]}")
        if argv[1] != trial_json:
            failures.append(f"trial_json must match argv trial_json {argv[1]}")
    if argv.count(trial_json) != 1:
        failures.append(f"argv must include trial_json exactly once: {trial_json}")
    trial_root_values = argv_values(argv, "--trial-root")
    if len(trial_root_values) > 1:
        failures.append("argv has duplicate --trial-root")
    if not trial_root_values:
        failures.append("argv missing --trial-root")
    for value in trial_root_values:
        if value is None:
            failures.append("argv --trial-root must include a value")
        elif not Path(value).is_absolute():
            failures.append(f"argv --trial-root must be an absolute path: {value}")
        elif value != trial_root:
            failures.append(f"trial_root must match argv --trial-root {value}")
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


def verify_saved_external_trial_report(
    report: Path,
    require_report_pass: bool = False,
    verify_files: bool = False,
) -> int:
    try:
        payload = json.loads(report.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - exact report verification failure.
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    failures = validate_verification_report_payload(
        payload,
        require_report_pass=require_report_pass,
        report_path=report,
    )
    if not failures and verify_files:
        trial_json = Path(payload["trial_json"])
        trial_root = Path(payload["trial_root"])
        gate = release_gate.validate_external_trial_report(trial_json, trial_root)
        recorded_gate = payload["gate"]
        if recorded_gate.get("name") != gate.name:
            failures.append(f"gate.name changed: {recorded_gate.get('name')} != {gate.name}")
        if recorded_gate.get("status") != gate.status:
            failures.append(f"gate.status changed: {recorded_gate.get('status')} != {gate.status}")
        if recorded_gate.get("detail") != gate.detail:
            failures.append("gate.detail changed after recomputing trial report validation")
        if payload.get("status") != gate.status:
            failures.append(f"status changed after recomputing trial report validation: {payload.get('status')} != {gate.status}")
        failures.extend(recomputed_input_file_issues(payload["input_files"], trial_json, trial_root))
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print(f"external trial verification report ok: {report}")
    print(f"status={payload['status']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("trial_json", nargs="?", type=Path, help="External handoff trial report JSON")
    parser.add_argument(
        "--trial-root",
        type=Path,
        help="Root directory for resolving trial artifact paths",
    )
    parser.add_argument("--json-out", type=Path, help="Optional machine-readable verifier report")
    parser.add_argument("--verify-report", type=Path, help="Validate a saved verifier JSON report")
    parser.add_argument("--verify-report-files", action="store_true", help="Recompute trial validation from report paths")
    parser.add_argument("--require-report-pass", action="store_true", help="Reject saved verifier reports that are not PASS")
    parser.add_argument(
        "--allow-fail-report",
        action="store_true",
        help="Write/print a FAIL report but exit 0; intended only for diagnostics",
    )
    args = parser.parse_args()
    if args.verify_report:
        return verify_saved_external_trial_report(
            args.verify_report,
            require_report_pass=args.require_report_pass,
            verify_files=args.verify_report_files,
        )
    if args.trial_json is None:
        parser.error("trial_json is required unless --verify-report is used")
    if args.trial_root is None:
        parser.error("--trial-root is required unless --verify-report is used")
    return verify_external_trial_report(
        args.trial_json,
        args.trial_root,
        json_out=args.json_out,
        require_pass=not args.allow_fail_report,
    )


if __name__ == "__main__":
    raise SystemExit(main())
