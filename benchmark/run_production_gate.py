#!/usr/bin/env python3
"""Run the final MorphoJet production-claim release gate."""

from __future__ import annotations

import argparse
import re
import shlex
import subprocess
import sys
from pathlib import Path


DEFAULT_OUT_JSON = Path("benchmark/results/release-gate/production-claim.json")
DEFAULT_OUT_MD = Path("benchmark/results/release-gate/production-claim.md")
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

    print(shlex.join(command))
    if args.dry_run:
        return 0
    return subprocess.run(command).returncode


if __name__ == "__main__":
    raise SystemExit(main())
