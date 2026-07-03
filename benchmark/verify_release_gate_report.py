#!/usr/bin/env python3
"""Validate a saved MorphoJet release-gate JSON report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def validate_release_gate_report_payload(
    payload: Any,
    require_report_pass: bool = False,
    require_production_claim_pass: bool = False,
) -> list[str]:
    failures: list[str] = []
    if not isinstance(payload, dict):
        return ["release-gate report must be a JSON object"]

    if payload.get("status") not in {"PASS", "FAIL"}:
        failures.append(f"status={payload.get('status')}")
    if require_report_pass and payload.get("status") != "PASS":
        failures.append(f"release-gate report status is not PASS: {payload.get('status')}")

    audit = payload.get("production_claim_audit")
    if not isinstance(audit, dict):
        failures.append("production_claim_audit must be an object")
        audit = {}
    audit_status = audit.get("status")
    if audit_status not in {"PASS", "INCOMPLETE"}:
        failures.append(f"production_claim_audit.status={audit_status}")
    top_level_claim_status = payload.get("production_claim_status")
    if top_level_claim_status != audit_status:
        failures.append(
            "production_claim_status does not match production_claim_audit.status: "
            f"{top_level_claim_status} != {audit_status}"
        )
    if require_production_claim_pass and top_level_claim_status != "PASS":
        failures.append(f"production_claim_status is not PASS: {top_level_claim_status}")

    audit_missing = audit.get("missing_or_failed_checks")
    top_level_missing = payload.get("missing_or_failed_checks")
    if not isinstance(audit_missing, list) or not all(isinstance(item, str) for item in audit_missing):
        failures.append("production_claim_audit.missing_or_failed_checks must be a string list")
    if top_level_missing != audit_missing:
        failures.append("missing_or_failed_checks does not match production_claim_audit")
    if top_level_claim_status == "PASS" and top_level_missing != []:
        failures.append("passing production claim must have no missing_or_failed_checks")

    checks = audit.get("checks")
    if not isinstance(checks, list) or not checks:
        failures.append("production_claim_audit.checks must be a non-empty list")
    else:
        failed_check_names = [
            check.get("name")
            for check in checks
            if isinstance(check, dict) and check.get("status") != "PASS" and isinstance(check.get("name"), str)
        ]
        if isinstance(top_level_missing, list) and failed_check_names != top_level_missing:
            failures.append("missing_or_failed_checks does not match audit check statuses")

    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        failures.append("metadata must be an object")
    gates = payload.get("gates")
    if not isinstance(gates, list) or not gates:
        failures.append("gates must be a non-empty list")
    return failures


def verify_release_gate_report(
    path: Path,
    require_report_pass: bool = False,
    require_production_claim_pass: bool = False,
) -> int:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - exact report verification failure.
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    failures = validate_release_gate_report_payload(
        payload,
        require_report_pass=require_report_pass,
        require_production_claim_pass=require_production_claim_pass,
    )
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print(f"release-gate report ok: {path}")
    print(f"status={payload['status']}")
    print(f"production_claim_status={payload['production_claim_status']}")
    print(f"missing_or_failed_checks={','.join(payload['missing_or_failed_checks']) or 'none'}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path, help="Release-gate JSON report to validate")
    parser.add_argument("--require-report-pass", action="store_true")
    parser.add_argument("--require-production-claim-pass", action="store_true")
    args = parser.parse_args()
    return verify_release_gate_report(
        args.report,
        require_report_pass=args.require_report_pass,
        require_production_claim_pass=args.require_production_claim_pass,
    )


if __name__ == "__main__":
    raise SystemExit(main())
