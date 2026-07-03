#!/usr/bin/env python3
"""Validate an external L4 handoff trial report."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

import release_gate


def verify_external_trial_report(
    trial_json: Path,
    trial_root: Path,
    json_out: Path | None = None,
    require_pass: bool = True,
) -> int:
    gate = release_gate.validate_external_trial_report(trial_json, trial_root)
    payload = {
        "status": gate.status,
        "trial_json": str(trial_json),
        "trial_root": str(trial_root),
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("trial_json", type=Path, help="External handoff trial report JSON")
    parser.add_argument(
        "--trial-root",
        type=Path,
        required=True,
        help="Root directory for resolving trial artifact paths",
    )
    parser.add_argument("--json-out", type=Path, help="Optional machine-readable verifier report")
    parser.add_argument(
        "--allow-fail-report",
        action="store_true",
        help="Write/print a FAIL report but exit 0; intended only for diagnostics",
    )
    args = parser.parse_args()
    return verify_external_trial_report(
        args.trial_json,
        args.trial_root,
        json_out=args.json_out,
        require_pass=not args.allow_fail_report,
    )


if __name__ == "__main__":
    raise SystemExit(main())
