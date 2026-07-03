#!/usr/bin/env python3
"""Run the final MorphoJet production-claim release gate."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import release_gate


DEFAULT_OUT_JSON = Path("benchmark/results/release-gate/production-claim.json")
DEFAULT_OUT_MD = Path("benchmark/results/release-gate/production-claim.md")
DEFAULT_LOCAL_PREFLIGHT_JSON = Path("benchmark/results/release-gate/local-evidence-preflight.json")
DEFAULT_LOCAL_PREFLIGHT_MD = Path("benchmark/results/release-gate/local-evidence-preflight.md")
LOCAL_PREFLIGHT_VALIDATED_CHECKS = [
    "external_l4_workflow_trial",
    "external_l4_evidence_package",
]
LOCAL_PREFLIGHT_SKIPPED_FINAL_CHECKS = [
    "clean_git_worktree",
    "standard_code_and_artifact_gates",
    "l3_provenance_hashes",
    "stable_github_release",
    "production_claim_enforcement",
]
STABLE_TAG_PATTERN = re.compile(r"^v\d+\.\d+\.\d+(?:\+\S+)?$")


class ProductionGateError(Exception):
    """Raised when the final production gate cannot be assembled safely."""


def validate_stable_tag(tag: str) -> None:
    if not STABLE_TAG_PATTERN.fullmatch(tag):
        raise ProductionGateError(
            f"{tag!r} is not a stable release tag; expected a non-RC tag like v0.1.0"
        )


def validate_existing_inputs(args: argparse.Namespace) -> None:
    if not args.external_trial_json.is_file():
        raise ProductionGateError(f"--external-trial-json is not a file: {args.external_trial_json}")
    if not args.external_trial_root.is_dir():
        raise ProductionGateError(f"--external-trial-root is not a directory: {args.external_trial_root}")
    if not args.external_evidence_package_dir.is_dir():
        raise ProductionGateError(
            f"--external-evidence-package-dir is not a directory: {args.external_evidence_package_dir}"
        )


def build_release_gate_command(args: argparse.Namespace) -> list[str]:
    validate_stable_tag(args.github_release_tag)
    command = [
        sys.executable,
        "benchmark/release_gate.py",
        "--require-clean-git",
        "--require-l3-provenance",
        "--require-production-claim",
        "--external-trial-json",
        str(args.external_trial_json),
        "--external-trial-root",
        str(args.external_trial_root),
        "--external-evidence-package-dir",
        str(args.external_evidence_package_dir),
        "--verify-github-release",
        args.github_release_tag,
        "--github-release-kind",
        "stable",
        "--out-json",
        str(args.out_json),
        "--out-md",
        str(args.out_md),
    ]
    if args.run_l3:
        command.append("--run-l3")
    if args.build_release_artifact:
        command.extend(
            [
                "--build-release-artifact",
                "--release-version",
                args.release_version,
            ]
        )
    return command


def build_local_evidence_preflight_payload(args: argparse.Namespace, gates: list[release_gate.Gate]) -> dict:
    git_status_lines = release_gate.git_status_porcelain()
    return {
        "schema_version": 1,
        "status": "PASS" if all(gate.status == "PASS" for gate in gates) else "FAIL",
        "claim_status": "NOT_PRODUCTION_CLAIM",
        "validated_checks": LOCAL_PREFLIGHT_VALIDATED_CHECKS,
        "skipped_final_checks": LOCAL_PREFLIGHT_SKIPPED_FINAL_CHECKS,
        "metadata": {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "git_commit": release_gate.git_commit(),
            "git_dirty": bool(git_status_lines),
            "git_status": git_status_lines,
            "argv": ["benchmark/run_production_gate.py", *sys.argv[1:]],
            "external_trial_json": str(args.external_trial_json),
            "external_trial_root": str(args.external_trial_root),
            "external_evidence_package_dir": str(args.external_evidence_package_dir),
            "github_release_tag": args.github_release_tag,
            "local_evidence_preflight_only": args.local_evidence_preflight_only,
        },
        "gates": [asdict(gate) for gate in gates],
    }


def render_local_evidence_preflight_markdown(payload: dict, out_json: Path) -> str:
    metadata = payload["metadata"]
    lines = [
        "# Local External L4 Evidence Preflight",
        "",
        f"- status: `{payload['status']}`",
        f"- claim_status: `{payload['claim_status']}`",
        f"- json: `{out_json}`",
        f"- generated_at_utc: `{metadata['generated_at_utc']}`",
        f"- git_commit: `{metadata['git_commit']}`",
        f"- git_dirty: `{metadata['git_dirty']}`",
        f"- external_trial_json: `{metadata['external_trial_json']}`",
        f"- external_trial_root: `{metadata['external_trial_root']}`",
        f"- external_evidence_package_dir: `{metadata['external_evidence_package_dir']}`",
        f"- github_release_tag: `{metadata['github_release_tag']}`",
        f"- validated_checks: `{', '.join(payload['validated_checks'])}`",
        f"- skipped_final_checks: `{', '.join(payload['skipped_final_checks'])}`",
        "",
        "| Gate | Status | Detail |",
        "|---|---:|---|",
    ]
    for gate in payload["gates"]:
        lines.append(f"| {gate['name']} | {gate['status']} | {gate['detail']} |")
    lines.extend(
        [
            "",
            "This preflight validates only the external L4 trial report and evidence package. "
            "It does not satisfy the stable GitHub release or final production-claim gates.",
        ]
    )
    return "\n".join(lines)


def write_local_evidence_preflight_report(
    args: argparse.Namespace,
    gates: list[release_gate.Gate],
) -> dict:
    payload = build_local_evidence_preflight_payload(args, gates)
    args.local_evidence_preflight_json.parent.mkdir(parents=True, exist_ok=True)
    args.local_evidence_preflight_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    args.local_evidence_preflight_md.parent.mkdir(parents=True, exist_ok=True)
    args.local_evidence_preflight_md.write_text(
        render_local_evidence_preflight_markdown(payload, args.local_evidence_preflight_json) + "\n",
        encoding="utf-8",
    )
    return payload


def run_local_evidence_preflight(args: argparse.Namespace) -> int:
    gates = [
        release_gate.validate_external_trial_report(args.external_trial_json, args.external_trial_root),
        release_gate.validate_external_evidence_package(args.external_evidence_package_dir, args.external_trial_json),
    ]
    payload = write_local_evidence_preflight_report(args, gates)
    for gate in gates:
        print(f"{gate.name}: {gate.status}")
        if gate.detail:
            print(gate.detail)
    print(f"wrote {args.local_evidence_preflight_json}")
    print(f"wrote {args.local_evidence_preflight_md}")
    print(f"status={payload['status']}")
    return 0 if payload["status"] == "PASS" else 1


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--external-trial-json", type=Path, required=True)
    parser.add_argument("--external-trial-root", type=Path, required=True)
    parser.add_argument("--external-evidence-package-dir", type=Path, required=True)
    parser.add_argument("--github-release-tag", required=True, help="Stable non-RC release tag, e.g. v0.1.0")
    parser.add_argument("--out-json", type=Path, default=DEFAULT_OUT_JSON)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--run-l3", action="store_true", help="Rerun the full CellBinDB L3 benchmark")
    parser.add_argument("--build-release-artifact", action="store_true", help="Also build and verify a local archive")
    parser.add_argument("--release-version", default="production-preflight")
    parser.add_argument("--dry-run", action="store_true", help="Print the final release-gate command without running it")
    parser.add_argument(
        "--local-evidence-preflight-only",
        action="store_true",
        help="Validate only the external L4 trial and evidence package, without running full release gate",
    )
    parser.add_argument("--local-evidence-preflight-json", type=Path, default=DEFAULT_LOCAL_PREFLIGHT_JSON)
    parser.add_argument("--local-evidence-preflight-md", type=Path, default=DEFAULT_LOCAL_PREFLIGHT_MD)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        command = build_release_gate_command(args)
        if not args.dry_run:
            validate_existing_inputs(args)
    except ProductionGateError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.dry_run:
        print(shlex.join(command))
        return 0
    if args.local_evidence_preflight_only:
        return run_local_evidence_preflight(args)
    print(shlex.join(command))
    return subprocess.run(command).returncode


if __name__ == "__main__":
    raise SystemExit(main())
