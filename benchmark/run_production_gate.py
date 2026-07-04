#!/usr/bin/env python3
"""Run the final MorphoJet production-claim release gate."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
import shlex
import subprocess
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import release_gate
import verify_external_evidence_package
import verify_external_trial_report
import verify_github_release


DEFAULT_OUT_JSON = Path("benchmark/results/release-gate/production-claim.json")
DEFAULT_OUT_MD = Path("benchmark/results/release-gate/production-claim.md")
DEFAULT_LOCAL_PREFLIGHT_JSON = Path("benchmark/results/release-gate/local-evidence-preflight.json")
DEFAULT_LOCAL_PREFLIGHT_MD = Path("benchmark/results/release-gate/local-evidence-preflight.md")
LOCAL_PREFLIGHT_EVIDENCE_SCOPE = "LOCAL_EXTERNAL_L4_PREFLIGHT"
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
LOCAL_PREFLIGHT_INPUT_NAMES = {
    "external_trial_json",
    "package_handoff_trial_json",
    "package_zip",
    "package_zip_sha256",
}
LOCAL_PREFLIGHT_OPTIONAL_INPUT_NAMES = {
    "external_trial_verification_report",
    "external_evidence_package_verification_report",
}
LOCAL_PREFLIGHT_GATE_NAMES = {
    "Validate external L4 workflow trial report",
    "Validate external L4 evidence package",
}
LOCAL_PREFLIGHT_OPTIONAL_GATE_NAMES = {
    "Verify saved external L4 trial report",
    "Verify saved external L4 evidence package report",
}
STABLE_TAG_PATTERN = re.compile(r"^v\d+\.\d+\.\d+(?:\+\S+)?$")


class ProductionGateError(Exception):
    """Raised when the final production gate cannot be assembled safely."""


def validate_stable_tag(tag: str) -> None:
    if not STABLE_TAG_PATTERN.fullmatch(tag):
        raise ProductionGateError(
            f"{tag!r} is not a stable release tag; expected a non-RC tag like v0.1.0"
        )


def require_final_gate_args(args: argparse.Namespace) -> None:
    missing = []
    for name in [
        "external_trial_json",
        "external_trial_root",
        "external_evidence_package_dir",
        "github_release_tag",
    ]:
        if getattr(args, name) is None:
            missing.append("--" + name.replace("_", "-"))
    if missing:
        raise ProductionGateError("missing required arguments: " + ", ".join(missing))


def validate_existing_inputs(args: argparse.Namespace) -> None:
    if not args.external_trial_json.is_file():
        raise ProductionGateError(f"--external-trial-json is not a file: {args.external_trial_json}")
    if not args.external_trial_root.is_dir():
        raise ProductionGateError(f"--external-trial-root is not a directory: {args.external_trial_root}")
    if not args.external_evidence_package_dir.is_dir():
        raise ProductionGateError(
            f"--external-evidence-package-dir is not a directory: {args.external_evidence_package_dir}"
        )
    if args.external_trial_verification_report and not args.external_trial_verification_report.is_file():
        raise ProductionGateError(
            "--external-trial-verification-report is not a file: "
            f"{args.external_trial_verification_report}"
        )
    if (
        args.external_evidence_package_verification_report
        and not args.external_evidence_package_verification_report.is_file()
    ):
        raise ProductionGateError(
            "--external-evidence-package-verification-report is not a file: "
            f"{args.external_evidence_package_verification_report}"
        )
    if args.github_release_verification_report and not args.github_release_verification_report.is_file():
        raise ProductionGateError(
            "--github-release-verification-report is not a file: "
            f"{args.github_release_verification_report}"
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
    if args.external_trial_verification_report:
        command.extend(
            [
                "--external-trial-verification-report",
                str(args.external_trial_verification_report),
            ]
        )
    if args.external_evidence_package_verification_report:
        command.extend(
            [
                "--external-evidence-package-verification-report",
                str(args.external_evidence_package_verification_report),
            ]
        )
    if args.github_release_verification_report:
        command.extend(
            [
                "--github-release-verification-report",
                str(args.github_release_verification_report),
            ]
        )
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
        "evidence_scope": LOCAL_PREFLIGHT_EVIDENCE_SCOPE,
        "final_evidence_acceptable": False,
        "validated_checks": LOCAL_PREFLIGHT_VALIDATED_CHECKS,
        "skipped_final_checks": LOCAL_PREFLIGHT_SKIPPED_FINAL_CHECKS,
        "input_artifacts": local_evidence_input_artifacts(args),
        "metadata": {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "git_commit": release_gate.git_commit(),
            "git_dirty": bool(git_status_lines),
            "git_status": git_status_lines,
            "argv": ["benchmark/run_production_gate.py", *sys.argv[1:]],
            "external_trial_json": str(args.external_trial_json),
            "external_trial_root": str(args.external_trial_root),
            "external_evidence_package_dir": str(args.external_evidence_package_dir),
            "external_trial_verification_report": str(args.external_trial_verification_report)
            if args.external_trial_verification_report
            else None,
            "external_evidence_package_verification_report": str(args.external_evidence_package_verification_report)
            if args.external_evidence_package_verification_report
            else None,
            "github_release_tag": args.github_release_tag,
            "local_evidence_preflight_only": args.local_evidence_preflight_only,
        },
        "gates": [asdict(gate) for gate in gates],
    }


def local_evidence_input_artifacts(args: argparse.Namespace) -> list[dict]:
    package_dir = args.external_evidence_package_dir
    return [
        file_summary("external_trial_json", args.external_trial_json),
        file_summary("package_handoff_trial_json", package_dir / "handoff_trial.json"),
        file_summary("package_zip", package_dir.parent / f"{package_dir.name}.zip"),
        file_summary("package_zip_sha256", package_dir.parent / f"{package_dir.name}.zip.sha256"),
        *optional_file_summaries(
            [
                ("external_trial_verification_report", args.external_trial_verification_report),
                (
                    "external_evidence_package_verification_report",
                    args.external_evidence_package_verification_report,
                ),
            ]
        ),
    ]


def optional_file_summaries(named_paths: list[tuple[str, Path | None]]) -> list[dict]:
    return [file_summary(name, path) for name, path in named_paths if path is not None]


def saved_verifier_gate(
    name: str,
    command: list[str],
    verifier,
    report: Path,
    verifier_kwargs: dict | None = None,
) -> release_gate.Gate:
    started = datetime.now(timezone.utc)
    stdout = io.StringIO()
    stderr = io.StringIO()
    kwargs = verifier_kwargs or {
        "require_report_pass": True,
        "verify_files": True,
    }
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        status_code = verifier(report, **kwargs)
    detail = (stdout.getvalue() + stderr.getvalue()).strip()
    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    return release_gate.Gate(
        name=name,
        command=command,
        status="PASS" if status_code == 0 else "FAIL",
        elapsed_seconds=elapsed,
        detail=detail,
    )


def saved_reviewer_report_gates(
    args: argparse.Namespace,
    include_github_release: bool = False,
) -> list[release_gate.Gate]:
    gates = []
    if args.external_trial_verification_report:
        gates.append(
            saved_verifier_gate(
                "Verify saved external L4 trial report",
                [
                    sys.executable,
                    "benchmark/verify_external_trial_report.py",
                    "--verify-report",
                    str(args.external_trial_verification_report),
                    "--verify-report-files",
                    "--require-report-pass",
                ],
                verify_external_trial_report.verify_saved_external_trial_report,
                args.external_trial_verification_report,
            )
        )
    if args.external_evidence_package_verification_report:
        gates.append(
            saved_verifier_gate(
                "Verify saved external L4 evidence package report",
                [
                    sys.executable,
                    "benchmark/verify_external_evidence_package.py",
                    "--verify-report",
                    str(args.external_evidence_package_verification_report),
                    "--verify-report-files",
                    "--require-report-pass",
                    "--require-trial-json",
                ],
                verify_external_evidence_package.verify_saved_external_evidence_package_report,
                args.external_evidence_package_verification_report,
                verifier_kwargs={
                    "require_report_pass": True,
                    "verify_files": True,
                    "require_trial_json": True,
                },
            )
        )
    if include_github_release and args.github_release_verification_report:
        gates.append(
            saved_verifier_gate(
                "Verify saved stable GitHub release report",
                [
                    sys.executable,
                    "benchmark/verify_github_release.py",
                    "--verify-report",
                    str(args.github_release_verification_report),
                    "--verify-report-files",
                    "--require-report-pass",
                    "--require-stable-report",
                ],
                verify_github_release.verify_saved_github_release_report,
                args.github_release_verification_report,
                verifier_kwargs={
                    "require_report_pass": True,
                    "require_stable_report": True,
                    "verify_files": True,
                },
            )
        )
    return gates


def file_summary(name: str, path: Path) -> dict:
    summary = {
        "name": name,
        "path": str(path),
        "exists": path.is_file(),
        "size_bytes": None,
        "sha256": None,
    }
    if path.is_file():
        summary["size_bytes"] = path.stat().st_size
        summary["sha256"] = release_gate.sha256_file(path)
    return summary


def git_commit_is_reachable(commit: str) -> bool:
    completed = subprocess.run(
        ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
        cwd=release_gate.ROOT,
        text=True,
        capture_output=True,
    )
    return completed.returncode == 0


def render_local_evidence_preflight_markdown(payload: dict, out_json: Path) -> str:
    metadata = payload["metadata"]
    lines = [
        "# Local External L4 Evidence Preflight",
        "",
        f"- status: `{payload['status']}`",
        f"- claim_status: `{payload['claim_status']}`",
        f"- evidence_scope: `{payload['evidence_scope']}`",
        f"- final_evidence_acceptable: `{payload['final_evidence_acceptable']}`",
        f"- json: `{out_json}`",
        f"- generated_at_utc: `{metadata['generated_at_utc']}`",
        f"- git_commit: `{metadata['git_commit']}`",
        f"- git_dirty: `{metadata['git_dirty']}`",
        f"- external_trial_json: `{metadata['external_trial_json']}`",
        f"- external_trial_root: `{metadata['external_trial_root']}`",
        f"- external_evidence_package_dir: `{metadata['external_evidence_package_dir']}`",
        f"- external_trial_verification_report: `{metadata['external_trial_verification_report']}`",
        "- external_evidence_package_verification_report: "
        f"`{metadata['external_evidence_package_verification_report']}`",
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
            "## Input Artifacts",
            "",
            "| Name | Exists | Size Bytes | SHA-256 | Path |",
            "|---|---:|---:|---|---|",
        ]
    )
    for artifact in payload["input_artifacts"]:
        lines.append(
            "| "
            f"{artifact['name']} | "
            f"{artifact['exists']} | "
            f"{artifact['size_bytes'] if artifact['size_bytes'] is not None else ''} | "
            f"{artifact['sha256'] or ''} | "
            f"{artifact['path']} |"
        )
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
        *saved_reviewer_report_gates(args),
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
    parser.add_argument("--external-trial-json", type=Path)
    parser.add_argument("--external-trial-root", type=Path)
    parser.add_argument("--external-evidence-package-dir", type=Path)
    parser.add_argument("--external-trial-verification-report", type=Path)
    parser.add_argument("--external-evidence-package-verification-report", type=Path)
    parser.add_argument("--github-release-verification-report", type=Path)
    parser.add_argument("--github-release-tag", help="Stable non-RC release tag, e.g. v0.1.0")
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
    parser.add_argument(
        "--verify-local-evidence-preflight-report",
        type=Path,
        help="Validate an existing local evidence preflight JSON report and exit",
    )
    parser.add_argument(
        "--verify-local-evidence-preflight-files",
        action="store_true",
        help="With --verify-local-evidence-preflight-report, recompute recorded input artifact sizes and SHA-256 hashes",
    )
    parser.add_argument(
        "--require-local-evidence-preflight-pass",
        action="store_true",
        help="With --verify-local-evidence-preflight-report, fail unless the saved report status is PASS",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        if args.verify_local_evidence_preflight_report:
            return verify_local_evidence_preflight_report(
                args.verify_local_evidence_preflight_report,
                verify_files=args.verify_local_evidence_preflight_files,
                require_pass=args.require_local_evidence_preflight_pass,
            )
        require_final_gate_args(args)
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
    reviewer_gates = saved_reviewer_report_gates(args, include_github_release=True)
    if reviewer_gates:
        for gate in reviewer_gates:
            print(f"{gate.name}: {gate.status}")
            if gate.detail:
                print(gate.detail)
        if not all(gate.status == "PASS" for gate in reviewer_gates):
            return 1
    print(shlex.join(command))
    return subprocess.run(command).returncode


def validate_local_evidence_preflight_payload(payload: object) -> list[str]:
    failures = []
    if not isinstance(payload, dict):
        return ["local evidence preflight report must be a JSON object"]
    if payload.get("schema_version") != 1:
        failures.append(f"schema_version={payload.get('schema_version')}")
    if payload.get("status") not in {"PASS", "FAIL"}:
        failures.append(f"status={payload.get('status')}")
    if payload.get("claim_status") != "NOT_PRODUCTION_CLAIM":
        failures.append(f"claim_status={payload.get('claim_status')}")
    if payload.get("evidence_scope") != LOCAL_PREFLIGHT_EVIDENCE_SCOPE:
        failures.append(f"evidence_scope={payload.get('evidence_scope')}")
    if payload.get("final_evidence_acceptable") is not False:
        failures.append(f"final_evidence_acceptable={payload.get('final_evidence_acceptable')}")
    if payload.get("validated_checks") != LOCAL_PREFLIGHT_VALIDATED_CHECKS:
        failures.append("validated_checks do not match local evidence preflight contract")
    if payload.get("skipped_final_checks") != LOCAL_PREFLIGHT_SKIPPED_FINAL_CHECKS:
        failures.append("skipped_final_checks do not match local evidence preflight contract")

    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        failures.append("metadata must be an object")
    else:
        for key in [
            "generated_at_utc",
            "git_commit",
            "git_dirty",
            "git_status",
            "argv",
            "external_trial_json",
            "external_trial_root",
            "external_evidence_package_dir",
            "external_trial_verification_report",
            "external_evidence_package_verification_report",
            "github_release_tag",
            "local_evidence_preflight_only",
        ]:
            if key not in metadata:
                failures.append(f"metadata missing {key}")
        generated_at = metadata.get("generated_at_utc")
        if isinstance(generated_at, str):
            try:
                parsed_generated_at = datetime.fromisoformat(generated_at)
                if parsed_generated_at.tzinfo is None:
                    failures.append("metadata.generated_at_utc must include timezone")
            except ValueError:
                failures.append(f"metadata.generated_at_utc is invalid: {generated_at}")
        elif "generated_at_utc" in metadata:
            failures.append("metadata.generated_at_utc must be a string")
        git_commit = metadata.get("git_commit")
        if isinstance(git_commit, str):
            if not re.fullmatch(r"[0-9a-f]{40}", git_commit):
                failures.append(f"metadata.git_commit is not a 40-character SHA: {git_commit}")
            elif not git_commit_is_reachable(git_commit):
                failures.append(f"metadata.git_commit is not reachable: {git_commit}")
        elif "git_commit" in metadata:
            failures.append("metadata.git_commit must be a string")
        if "git_dirty" in metadata and not isinstance(metadata.get("git_dirty"), bool):
            failures.append("metadata.git_dirty must be a boolean")
        for list_key in ["git_status", "argv"]:
            value = metadata.get(list_key)
            if list_key in metadata and (
                not isinstance(value, list) or not all(isinstance(item, str) for item in value)
            ):
                failures.append(f"metadata.{list_key} must be a string list")
        if metadata.get("local_evidence_preflight_only") is not True:
            failures.append("metadata.local_evidence_preflight_only must be true")

    artifacts = payload.get("input_artifacts")
    if not isinstance(artifacts, list):
        failures.append("input_artifacts must be a list")
    else:
        names = {artifact.get("name") for artifact in artifacts if isinstance(artifact, dict)}
        allowed_names = LOCAL_PREFLIGHT_INPUT_NAMES | LOCAL_PREFLIGHT_OPTIONAL_INPUT_NAMES
        if not LOCAL_PREFLIGHT_INPUT_NAMES.issubset(names) or names - allowed_names:
            failures.append(f"input_artifacts names={sorted(str(name) for name in names)}")
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                failures.append("input_artifacts entries must be objects")
                continue
            name = artifact.get("name")
            if not isinstance(name, str) or not name:
                failures.append("input artifact name must be a non-empty string")
            if not isinstance(artifact.get("path"), str) or not artifact.get("path"):
                failures.append(f"input artifact path must be a non-empty string: {name}")
            exists = artifact.get("exists")
            if not isinstance(exists, bool):
                failures.append(f"input artifact exists must be boolean: {name}")
                continue
            if exists:
                if not isinstance(artifact.get("size_bytes"), int) or artifact["size_bytes"] < 0:
                    failures.append(f"input artifact size_bytes must be a non-negative integer: {name}")
                sha256 = artifact.get("sha256")
                if not isinstance(sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", sha256):
                    failures.append(f"input artifact sha256 must be a lowercase SHA-256 digest: {name}")
            elif artifact.get("size_bytes") is not None or artifact.get("sha256") is not None:
                failures.append(f"missing input artifact must not carry size/hash: {name}")

    gates = payload.get("gates")
    if not isinstance(gates, list):
        failures.append("gates must be a list")
    else:
        gate_names = {gate.get("name") for gate in gates if isinstance(gate, dict)}
        allowed_gate_names = LOCAL_PREFLIGHT_GATE_NAMES | LOCAL_PREFLIGHT_OPTIONAL_GATE_NAMES
        if not LOCAL_PREFLIGHT_GATE_NAMES.issubset(gate_names) or gate_names - allowed_gate_names:
            failures.append(f"gate names={sorted(str(name) for name in gate_names)}")
        for gate in gates:
            if not isinstance(gate, dict):
                failures.append("gate entries must be objects")
                continue
            if gate.get("status") not in {"PASS", "FAIL"}:
                failures.append(f"gate status invalid for {gate.get('name')}: {gate.get('status')}")
            if not isinstance(gate.get("detail"), str):
                failures.append(f"gate detail must be a string: {gate.get('name')}")
    return failures


def validate_local_evidence_preflight_files(payload: dict) -> list[str]:
    failures = []
    for artifact in payload.get("input_artifacts", []):
        if not isinstance(artifact, dict):
            continue
        name = artifact.get("name")
        path_value = artifact.get("path")
        if not isinstance(path_value, str) or not path_value:
            continue
        if artifact.get("exists") is not True:
            continue
        path = Path(path_value)
        if not path.is_file():
            failures.append(f"input artifact no longer exists: {name} {path}")
            continue
        actual_size = path.stat().st_size
        if actual_size != artifact.get("size_bytes"):
            failures.append(f"input artifact size mismatch: {name}")
        actual_hash = release_gate.sha256_file(path)
        if actual_hash != artifact.get("sha256"):
            failures.append(f"input artifact sha256 mismatch: {name}")
    return failures


def verify_local_evidence_preflight_report(
    path: Path,
    verify_files: bool = False,
    require_pass: bool = False,
) -> int:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - exact report verification failure.
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    failures = validate_local_evidence_preflight_payload(payload)
    if not failures and require_pass and payload.get("status") != "PASS":
        failures.append(f"local evidence preflight status is not PASS: {payload.get('status')}")
    if not failures and verify_files:
        failures.extend(validate_local_evidence_preflight_files(payload))
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print(f"local evidence preflight report ok: {path}")
    print(f"status={payload['status']}")
    print(f"claim_status={payload['claim_status']}")
    print(f"verified_files={verify_files}")
    print(f"required_pass={require_pass}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
