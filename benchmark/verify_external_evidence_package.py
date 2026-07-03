#!/usr/bin/env python3
"""Validate a packaged external L4 trial evidence bundle."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

import release_gate


def verify_external_evidence_package(
    package_dir: Path,
    trial_json: Path | None = None,
    json_out: Path | None = None,
    require_pass: bool = True,
) -> int:
    gate = release_gate.validate_external_evidence_package(package_dir, trial_json)
    payload = {
        "status": gate.status,
        "package_dir": str(package_dir),
        "trial_json": str(trial_json) if trial_json else None,
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


def validate_verification_report_payload(payload: Any, require_report_pass: bool = False) -> list[str]:
    failures: list[str] = []
    if not isinstance(payload, dict):
        return ["external evidence package verification report must be a JSON object"]
    status = payload.get("status")
    if status not in {"PASS", "FAIL"}:
        failures.append(f"status={status}")
    if require_report_pass and status != "PASS":
        failures.append(f"external evidence package verification report status is not PASS: {status}")
    package_dir = payload.get("package_dir")
    if not isinstance(package_dir, str) or not package_dir.strip():
        failures.append("package_dir must be a non-empty string")
    trial_json = payload.get("trial_json")
    if trial_json is not None and (not isinstance(trial_json, str) or not trial_json.strip()):
        failures.append("trial_json must be null or a non-empty string")
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


def verify_saved_external_evidence_package_report(
    report: Path,
    require_report_pass: bool = False,
    verify_files: bool = False,
) -> int:
    try:
        payload = json.loads(report.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - exact report verification failure.
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    failures = validate_verification_report_payload(payload, require_report_pass=require_report_pass)
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
