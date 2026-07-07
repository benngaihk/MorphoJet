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
    "package_readiness_json",
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
GITHUB_RELEASE_REPO = "benngaihk/MorphoJet"
STABLE_TAG_PATTERN = re.compile(r"^v\d+\.\d+\.\d+(?:\+\S+)?$")


def is_utc_datetime(value: datetime) -> bool:
    return value.utcoffset() == timezone.utc.utcoffset(value)


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


def normalized_path_key(path: Path) -> str:
    return str(path.expanduser().resolve(strict=False))


def absolute_path_text(path: Path) -> str:
    return normalized_path_key(path)


def path_matches_or_is_inside(root: Path, path: Path) -> bool:
    normalized_root = root.expanduser().resolve(strict=False)
    normalized_path = path.expanduser().resolve(strict=False)
    try:
        normalized_path.relative_to(normalized_root)
        return True
    except ValueError:
        return False


def add_protected_path(paths: dict[Path, str], path: Path, label: str) -> None:
    paths[path] = label


def load_json_if_file(path: Path) -> object | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def add_trial_artifact_paths(paths: dict[Path, str], args: argparse.Namespace) -> None:
    trial = load_json_if_file(args.external_trial_json)
    if not isinstance(trial, dict):
        return
    artifacts = trial.get("artifacts")
    if not isinstance(artifacts, list):
        return
    for artifact in artifacts:
        if isinstance(artifact, str) and artifact:
            add_protected_path(
                paths,
                release_gate.resolve_artifact_path(artifact, args.external_trial_root),
                f"external trial artifact: {artifact}",
            )


def add_package_artifact_paths(paths: dict[Path, str], args: argparse.Namespace) -> None:
    artifact_manifest = load_json_if_file(args.external_evidence_package_dir / "artifact_manifest.json")
    if not isinstance(artifact_manifest, dict):
        return
    for entry in artifact_manifest.get("review_files", []):
        if isinstance(entry, dict) and isinstance(entry.get("path"), str) and entry["path"]:
            add_protected_path(
                paths,
                args.external_evidence_package_dir / entry["path"],
                f"evidence package review file: {entry['path']}",
            )
    for entry in artifact_manifest.get("artifacts", []):
        if isinstance(entry, dict) and isinstance(entry.get("package_path"), str) and entry["package_path"]:
            add_protected_path(
                paths,
                args.external_evidence_package_dir / entry["package_path"],
                f"evidence package artifact: {entry['package_path']}",
            )


def protected_input_path_entries(args: argparse.Namespace) -> dict[Path, str]:
    paths = {
        args.external_trial_json: "--external-trial-json",
        args.external_trial_root: "--external-trial-root",
        args.external_evidence_package_dir: "--external-evidence-package-dir",
        args.external_evidence_package_dir / "handoff_trial.json": "packaged handoff_trial.json",
        args.external_evidence_package_dir / "readiness.json": "packaged readiness.json",
        args.external_evidence_package_dir / "external_evidence.json": "packaged external_evidence.json",
        args.external_evidence_package_dir / "rendered_manifest.json": "packaged rendered_manifest.json",
        args.external_evidence_package_dir / "artifact_manifest.json": "packaged artifact_manifest.json",
        args.external_evidence_package_dir.parent / f"{args.external_evidence_package_dir.name}.zip": "evidence package zip",
        args.external_evidence_package_dir.parent / f"{args.external_evidence_package_dir.name}.zip.sha256": (
            "evidence package checksum"
        ),
    }
    for path, label in [
        (args.external_trial_verification_report, "--external-trial-verification-report"),
        (
            args.external_evidence_package_verification_report,
            "--external-evidence-package-verification-report",
        ),
        (args.github_release_verification_report, "--github-release-verification-report"),
    ]:
        if path is not None:
            paths[path] = label
    add_trial_artifact_paths(paths, args)
    add_package_artifact_paths(paths, args)
    return paths


def protected_input_paths(args: argparse.Namespace) -> dict[str, str]:
    paths = protected_input_path_entries(args)
    return {normalized_path_key(path): label for path, label in paths.items()}


def validate_report_output_paths(args: argparse.Namespace, outputs: list[tuple[str, Path]]) -> None:
    protected = protected_input_paths(args)
    protected_entries = protected_input_path_entries(args)
    output_keys: dict[str, str] = {}
    output_paths: dict[str, Path] = {}
    failures = []
    for label, path in outputs:
        key = normalized_path_key(path)
        if key in output_keys:
            failures.append(f"{label} must not use the same path as {output_keys[key]}")
        else:
            output_keys[key] = label
            output_paths[label] = path
        protected_label = protected.get(key)
        if protected_label:
            failures.append(f"{label} must not overwrite {protected_label}: {path}")
            continue
        for protected_path, protected_label in protected_entries.items():
            if protected_label == "--external-trial-root":
                continue
            if path_matches_or_is_inside(protected_path, path):
                failures.append(f"{label} must not create a file inside {protected_label}: {path}")
                break
        for prior_label, prior_path in output_paths.items():
            if prior_label == label:
                continue
            if path_matches_or_is_inside(prior_path, path):
                failures.append(f"{label} must not create a file inside {prior_label}: {path}")
                break
            if path_matches_or_is_inside(path, prior_path):
                failures.append(f"{prior_label} must not create a file inside {label}: {prior_path}")
                break
    if failures:
        raise ProductionGateError("; ".join(failures))


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
            "argv": canonical_wrapper_argv(args, resolve_paths=True),
            "external_trial_json": absolute_path_text(args.external_trial_json),
            "external_trial_root": absolute_path_text(args.external_trial_root),
            "external_evidence_package_dir": absolute_path_text(args.external_evidence_package_dir),
            "external_trial_verification_report": absolute_path_text(args.external_trial_verification_report)
            if args.external_trial_verification_report
            else None,
            "external_evidence_package_verification_report": absolute_path_text(
                args.external_evidence_package_verification_report
            )
            if args.external_evidence_package_verification_report
            else None,
            "github_release_tag": args.github_release_tag,
            "local_evidence_preflight_only": args.local_evidence_preflight_only,
        },
        "gates": [asdict(gate) for gate in gates],
    }


def local_evidence_input_artifacts(args: argparse.Namespace) -> list[dict]:
    package_dir = args.external_evidence_package_dir
    package_readiness = file_summary("package_readiness_json", package_dir / "readiness.json")
    package_readiness["package_name"] = readiness_package_name(package_dir / "readiness.json")
    return [
        file_summary("external_trial_json", args.external_trial_json),
        file_summary("package_handoff_trial_json", package_dir / "handoff_trial.json"),
        package_readiness,
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


def load_saved_reviewer_payload(report: Path) -> dict:
    try:
        payload = json.loads(report.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - reviewer report binding must fail closed.
        raise ProductionGateError(f"cannot read saved reviewer report {report}: {type(exc).__name__}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ProductionGateError(f"saved reviewer report must be a JSON object: {report}")
    return payload


def paths_match(recorded: object, expected: Path) -> bool:
    if not isinstance(recorded, str) or not recorded.strip():
        return False
    return Path(recorded).resolve() == expected.resolve()


def gate_with_binding_failures(gate: release_gate.Gate, failures: list[str]) -> release_gate.Gate:
    if not failures:
        return gate
    detail_parts = [gate.detail] if gate.detail else []
    detail_parts.extend(f"FAIL: {failure}" for failure in failures)
    return release_gate.Gate(
        name=gate.name,
        command=gate.command,
        status="FAIL",
        elapsed_seconds=gate.elapsed_seconds,
        detail="\n".join(detail_parts),
    )


def external_trial_report_binding_failures(report: Path, args: argparse.Namespace) -> list[str]:
    payload = load_saved_reviewer_payload(report)
    failures = []
    if not paths_match(payload.get("trial_json"), args.external_trial_json):
        failures.append("saved external trial report trial_json does not match --external-trial-json")
    if not paths_match(payload.get("trial_root"), args.external_trial_root):
        failures.append("saved external trial report trial_root does not match --external-trial-root")
    return failures


def external_package_report_binding_failures(report: Path, args: argparse.Namespace) -> list[str]:
    payload = load_saved_reviewer_payload(report)
    failures = []
    if not paths_match(payload.get("package_dir"), args.external_evidence_package_dir):
        failures.append("saved external evidence package report package_dir does not match --external-evidence-package-dir")
    if not paths_match(payload.get("trial_json"), args.external_trial_json):
        failures.append("saved external evidence package report trial_json does not match --external-trial-json")
    return failures


def github_release_report_binding_failures(report: Path, args: argparse.Namespace) -> list[str]:
    payload = load_saved_reviewer_payload(report)
    failures = []
    if payload.get("repo") != GITHUB_RELEASE_REPO:
        failures.append(
            f"saved GitHub release report repo does not match production repo: {payload.get('repo')} != {GITHUB_RELEASE_REPO}"
        )
    if payload.get("tag") != args.github_release_tag:
        failures.append("saved GitHub release report tag does not match --github-release-tag")
    return failures


def saved_reviewer_report_gates(
    args: argparse.Namespace,
    include_github_release: bool = False,
) -> list[release_gate.Gate]:
    gates = []
    if args.external_trial_verification_report:
        gate = saved_verifier_gate(
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
        gates.append(
            gate_with_binding_failures(
                gate,
                external_trial_report_binding_failures(args.external_trial_verification_report, args)
                if gate.status == "PASS"
                else [],
            )
        )
    if args.external_evidence_package_verification_report:
        gate = saved_verifier_gate(
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
        gates.append(
            gate_with_binding_failures(
                gate,
                external_package_report_binding_failures(args.external_evidence_package_verification_report, args)
                if gate.status == "PASS"
                else [],
            )
        )
    if include_github_release and args.github_release_verification_report:
        gate = saved_verifier_gate(
            "Verify saved stable GitHub release report",
            [
                sys.executable,
                "benchmark/verify_github_release.py",
                "--verify-report",
                str(args.github_release_verification_report),
                "--verify-report-files",
                "--require-report-pass",
                "--require-stable-report",
                "--verify-git-commit",
                "--expect-tag",
                args.github_release_tag,
            ],
            verify_github_release.verify_saved_github_release_report,
            args.github_release_verification_report,
            verifier_kwargs={
                "require_report_pass": True,
                "require_stable_report": True,
                "verify_files": True,
                "expect_tag": args.github_release_tag,
                "verify_git_commit": True,
            },
        )
        gates.append(
            gate_with_binding_failures(
                gate,
                github_release_report_binding_failures(args.github_release_verification_report, args)
                if gate.status == "PASS"
                else [],
            )
        )
    return gates


def file_summary(name: str, path: Path) -> dict:
    report_path = Path(absolute_path_text(path))
    summary = {
        "name": name,
        "path": str(report_path),
        "exists": report_path.is_file(),
        "size_bytes": None,
        "sha256": None,
    }
    if report_path.is_file():
        summary["size_bytes"] = report_path.stat().st_size
        summary["sha256"] = release_gate.sha256_file(report_path)
    return summary


def readiness_package_name(path: Path) -> str | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - missing/malformed evidence is reported by the package gate.
        return None
    if not isinstance(payload, dict):
        return None
    package_name = payload.get("package_name")
    return package_name if isinstance(package_name, str) and package_name.strip() else None


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
            "| Name | Exists | Size Bytes | SHA-256 | Package Name | Path |",
            "|---|---:|---:|---|---|---|",
        ]
    )
    for artifact in payload["input_artifacts"]:
        lines.append(
            "| "
            f"{artifact['name']} | "
            f"{artifact['exists']} | "
            f"{artifact['size_bytes'] if artifact['size_bytes'] is not None else ''} | "
            f"{artifact['sha256'] or ''} | "
            f"{artifact.get('package_name') or ''} | "
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
    validate_report_output_paths(
        args,
        [
            ("--local-evidence-preflight-json", args.local_evidence_preflight_json),
            ("--local-evidence-preflight-md", args.local_evidence_preflight_md),
        ],
    )
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


def canonical_wrapper_argv(args: argparse.Namespace, resolve_paths: bool = False) -> list[str]:
    argv = ["benchmark/run_production_gate.py"]
    value_flags = [
        ("--external-trial-json", args.external_trial_json),
        ("--external-trial-root", args.external_trial_root),
        ("--external-evidence-package-dir", args.external_evidence_package_dir),
        ("--external-trial-verification-report", args.external_trial_verification_report),
        (
            "--external-evidence-package-verification-report",
            args.external_evidence_package_verification_report,
        ),
        ("--github-release-verification-report", args.github_release_verification_report),
        ("--github-release-tag", args.github_release_tag),
        ("--out-json", args.out_json),
        ("--out-md", args.out_md),
        ("--release-version", args.release_version),
        ("--local-evidence-preflight-json", args.local_evidence_preflight_json),
        ("--local-evidence-preflight-md", args.local_evidence_preflight_md),
        ("--verify-local-evidence-preflight-report", args.verify_local_evidence_preflight_report),
    ]
    for flag, value in value_flags:
        if value is not None:
            if resolve_paths and isinstance(value, Path):
                value = Path(absolute_path_text(value))
            argv.extend([flag, str(value)])
    for flag, enabled in [
        ("--run-l3", args.run_l3),
        ("--build-release-artifact", args.build_release_artifact),
        ("--dry-run", args.dry_run),
        ("--local-evidence-preflight-only", args.local_evidence_preflight_only),
        ("--verify-local-evidence-preflight-files", args.verify_local_evidence_preflight_files),
        ("--verify-local-evidence-preflight-gates", args.verify_local_evidence_preflight_gates),
        ("--require-local-evidence-preflight-pass", args.require_local_evidence_preflight_pass),
    ]:
        if enabled:
            argv.append(flag)
    return argv


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
        "--verify-local-evidence-preflight-gates",
        action="store_true",
        help="With --verify-local-evidence-preflight-report, rerun recorded external L4 gates and compare results",
    )
    parser.add_argument(
        "--require-local-evidence-preflight-pass",
        action="store_true",
        help="With --verify-local-evidence-preflight-report, fail unless the saved report status is PASS",
    )
    args = parser.parse_args(argv)
    args.argv = canonical_wrapper_argv(args)
    return args


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        if args.verify_local_evidence_preflight_report:
            return verify_local_evidence_preflight_report(
                args.verify_local_evidence_preflight_report,
                verify_files=args.verify_local_evidence_preflight_files,
                verify_gates=args.verify_local_evidence_preflight_gates,
                require_pass=args.require_local_evidence_preflight_pass,
            )
        require_final_gate_args(args)
        command = build_release_gate_command(args)
        if args.local_evidence_preflight_only:
            if args.github_release_verification_report:
                raise ProductionGateError(
                    "--github-release-verification-report is not used with --local-evidence-preflight-only"
                )
            validate_report_output_paths(
                args,
                [
                    ("--local-evidence-preflight-json", args.local_evidence_preflight_json),
                    ("--local-evidence-preflight-md", args.local_evidence_preflight_md),
                ],
            )
        else:
            validate_report_output_paths(
                args,
                [
                    ("--out-json", args.out_json),
                    ("--out-md", args.out_md),
                ],
            )
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
                elif not is_utc_datetime(parsed_generated_at):
                    failures.append("metadata.generated_at_utc must be UTC")
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
        argv = metadata.get("argv")
        if isinstance(argv, list) and all(isinstance(item, str) for item in argv):
            failures.extend(validate_local_evidence_preflight_argv(metadata, argv))
        for path_key in [
            "external_trial_json",
            "external_trial_root",
            "external_evidence_package_dir",
        ]:
            value = metadata.get(path_key)
            if not isinstance(value, str) or not value.strip():
                failures.append(f"metadata.{path_key} must be a non-empty string")
            elif not Path(value).is_absolute():
                failures.append(f"metadata.{path_key} must be an absolute path")
        for optional_path_key in [
            "external_trial_verification_report",
            "external_evidence_package_verification_report",
        ]:
            value = metadata.get(optional_path_key)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                failures.append(f"metadata.{optional_path_key} must be null or a non-empty string")
            elif isinstance(value, str) and value.strip() and not Path(value).is_absolute():
                failures.append(f"metadata.{optional_path_key} must be an absolute path")
        github_release_tag = metadata.get("github_release_tag")
        if github_release_tag is not None and (
            not isinstance(github_release_tag, str) or not github_release_tag.strip()
        ):
            failures.append("metadata.github_release_tag must be null or a non-empty string")
        if metadata.get("local_evidence_preflight_only") is not True:
            failures.append("metadata.local_evidence_preflight_only must be true")

    artifacts = payload.get("input_artifacts")
    if not isinstance(artifacts, list):
        failures.append("input_artifacts must be a list")
    else:
        names = {artifact.get("name") for artifact in artifacts if isinstance(artifact, dict)}
        artifact_paths: dict[str, str] = {}
        artifact_path_keys: dict[str, str] = {}
        artifact_summaries: dict[str, dict] = {}
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
            path_value = artifact.get("path")
            if not isinstance(path_value, str) or not path_value:
                failures.append(f"input artifact path must be a non-empty string: {name}")
            elif not Path(path_value).is_absolute():
                failures.append(f"input artifact path must be absolute: {name}")
            elif isinstance(name, str) and name:
                if name in artifact_paths:
                    failures.append(f"duplicate input artifact name: {name}")
                else:
                    artifact_paths[name] = path_value
                    artifact_summaries[name] = artifact
                path_key = normalized_path_key(Path(path_value))
                previous_name = artifact_path_keys.get(path_key)
                if previous_name is not None:
                    failures.append(f"duplicate input artifact path: {previous_name} and {name}")
                else:
                    artifact_path_keys[path_key] = name
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
            if name == "package_readiness_json":
                failures.extend(package_readiness_artifact_package_name_issues(artifact))
        if isinstance(metadata, dict):
            failures.extend(validate_local_evidence_preflight_path_bindings(metadata, artifact_paths))
            failures.extend(validate_local_evidence_preflight_package_name_binding(metadata, artifact_summaries))

    gates = payload.get("gates")
    if not isinstance(gates, list):
        failures.append("gates must be a list")
    else:
        gate_names = set()
        failed_gate_names = []
        allowed_gate_names = LOCAL_PREFLIGHT_GATE_NAMES | LOCAL_PREFLIGHT_OPTIONAL_GATE_NAMES
        for gate in gates:
            if not isinstance(gate, dict):
                failures.append("gate entries must be objects")
                continue
            name = gate.get("name")
            if not isinstance(name, str) or not name:
                failures.append("gate name must be a non-empty string")
            else:
                if name in gate_names:
                    failures.append(f"duplicate gate name: {name}")
                else:
                    gate_names.add(name)
            command = gate.get("command")
            if command is not None and (
                not isinstance(command, list) or not all(isinstance(item, str) for item in command)
            ):
                failures.append(f"gate command must be null or a string list: {name}")
            elapsed = gate.get("elapsed_seconds")
            if not isinstance(elapsed, (int, float)) or elapsed < 0:
                failures.append(f"gate elapsed_seconds must be non-negative: {name}")
            if gate.get("status") not in {"PASS", "FAIL"}:
                failures.append(f"gate status invalid for {gate.get('name')}: {gate.get('status')}")
            elif gate.get("status") == "FAIL" and isinstance(gate.get("name"), str):
                failed_gate_names.append(gate["name"])
            if not isinstance(gate.get("detail"), str):
                failures.append(f"gate detail must be a string: {gate.get('name')}")
        if not LOCAL_PREFLIGHT_GATE_NAMES.issubset(gate_names) or gate_names - allowed_gate_names:
            failures.append(f"gate names={sorted(str(name) for name in gate_names)}")
        expected_status = "FAIL" if failed_gate_names else "PASS"
        if payload.get("status") in {"PASS", "FAIL"} and payload.get("status") != expected_status:
            failures.append(
                "local evidence preflight status does not match gate statuses: "
                f"{payload.get('status')} != {expected_status}"
            )
    return failures


def package_readiness_artifact_package_name_issues(artifact: dict) -> list[str]:
    if "package_name" not in artifact:
        return ["input_artifacts.package_readiness_json.package_name must be present"]
    package_name = artifact.get("package_name")
    if package_name is None:
        return []
    if not isinstance(package_name, str) or not package_name.strip():
        return ["input_artifacts.package_readiness_json.package_name must be null or a non-empty string"]
    if release_gate.slugify(package_name) != package_name:
        return ["input_artifacts.package_readiness_json.package_name must be a canonical slug"]
    return []


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


def validate_local_evidence_preflight_argv(metadata: dict, argv: list[str]) -> list[str]:
    failures = []
    if not argv:
        return ["metadata.argv must not be empty"]
    if argv[0] != "benchmark/run_production_gate.py":
        failures.append(f"metadata.argv[0]={argv[0]}")

    preflight_flag = "--local-evidence-preflight-only"
    if argv.count(preflight_flag) != 1:
        failures.append(f"metadata.argv must include exactly one {preflight_flag}")
    if metadata.get("local_evidence_preflight_only") is not True:
        failures.append("metadata.local_evidence_preflight_only must be true for metadata.argv validation")
    if "--dry-run" in argv:
        failures.append("metadata.argv must not include --dry-run for a saved local evidence preflight report")
    if "--github-release-verification-report" in argv:
        failures.append(
            "metadata.argv must not include --github-release-verification-report for local evidence preflight"
        )

    required_value_flags = {
        "external_trial_json": "--external-trial-json",
        "external_trial_root": "--external-trial-root",
        "external_evidence_package_dir": "--external-evidence-package-dir",
        "github_release_tag": "--github-release-tag",
    }
    optional_value_flags = {
        "external_trial_verification_report": "--external-trial-verification-report",
        "external_evidence_package_verification_report": "--external-evidence-package-verification-report",
    }
    path_value_flags = set(required_value_flags.values()) | set(optional_value_flags.values())
    path_value_flags.discard("--github-release-tag")
    for metadata_key, flag in {**required_value_flags, **optional_value_flags}.items():
        values = argv_values(argv, flag)
        if len(values) > 1:
            failures.append(f"metadata.argv has duplicate {flag}")
        metadata_value = metadata.get(metadata_key)
        if metadata_key in required_value_flags and not values:
            failures.append(f"metadata.argv missing {flag} for metadata.{metadata_key}")
        if isinstance(metadata_value, str) and metadata_value.strip() and not values:
            failures.append(f"metadata.argv missing {flag} {metadata_value}")
        for argv_value in values:
            if argv_value is None:
                failures.append(f"metadata.argv {flag} must include a value")
            elif flag in path_value_flags and not Path(argv_value).is_absolute():
                failures.append(f"metadata.argv {flag} must use an absolute path: {argv_value}")
            elif metadata_value != argv_value:
                failures.append(f"metadata.{metadata_key} must match metadata.argv {flag} {argv_value}")
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
        if name == "package_readiness_json":
            actual_package_name = readiness_package_name(path)
            if actual_package_name != artifact.get("package_name"):
                failures.append("input artifact package_name mismatch: package_readiness_json")
    return failures


def validate_local_evidence_preflight_gates(payload: dict) -> list[str]:
    failures = []
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        return ["metadata must be an object before gate recheck"]
    try:
        args = argparse.Namespace(
            external_trial_json=Path(metadata["external_trial_json"]),
            external_trial_root=Path(metadata["external_trial_root"]),
            external_evidence_package_dir=Path(metadata["external_evidence_package_dir"]),
            external_trial_verification_report=Path(metadata["external_trial_verification_report"])
            if metadata.get("external_trial_verification_report")
            else None,
            external_evidence_package_verification_report=Path(
                metadata["external_evidence_package_verification_report"]
            )
            if metadata.get("external_evidence_package_verification_report")
            else None,
            github_release_verification_report=None,
        )
    except (KeyError, TypeError) as exc:
        return [f"metadata cannot be used for gate recheck: {type(exc).__name__}: {exc}"]
    recomputed_gates = [
        release_gate.validate_external_trial_report(args.external_trial_json, args.external_trial_root),
        release_gate.validate_external_evidence_package(args.external_evidence_package_dir, args.external_trial_json),
        *saved_reviewer_report_gates(args),
    ]
    recorded_gates = payload.get("gates")
    if not isinstance(recorded_gates, list):
        return ["gates must be a list before gate recheck"]
    if len(recorded_gates) != len(recomputed_gates):
        failures.append(f"gate count changed: {len(recorded_gates)} != {len(recomputed_gates)}")
    for index, recomputed in enumerate(recomputed_gates):
        if index >= len(recorded_gates):
            continue
        recorded = recorded_gates[index]
        if not isinstance(recorded, dict):
            failures.append(f"gate entry is not an object at index {index}")
            continue
        if recorded.get("name") != recomputed.name:
            failures.append(f"gate.name changed at index {index}: {recorded.get('name')} != {recomputed.name}")
        if recorded.get("status") != recomputed.status:
            failures.append(
                f"gate.status changed for {recomputed.name}: {recorded.get('status')} != {recomputed.status}"
            )
        if recorded.get("detail") != recomputed.detail:
            failures.append(f"gate.detail changed for {recomputed.name}")
        if recorded.get("command") != recomputed.command:
            failures.append(f"gate.command changed for {recomputed.name}")
    return failures


def artifact_path_matches(artifact_paths: dict[str, str], name: str, expected: Path) -> bool:
    recorded = artifact_paths.get(name)
    return recorded is not None and paths_match(recorded, expected)


def validate_local_evidence_preflight_path_bindings(
    metadata: dict,
    artifact_paths: dict[str, str],
) -> list[str]:
    failures = []
    external_trial_json = metadata.get("external_trial_json")
    if isinstance(external_trial_json, str) and external_trial_json.strip():
        if not artifact_path_matches(artifact_paths, "external_trial_json", Path(external_trial_json)):
            failures.append("input_artifacts.external_trial_json.path does not match metadata.external_trial_json")

    package_dir_value = metadata.get("external_evidence_package_dir")
    if isinstance(package_dir_value, str) and package_dir_value.strip():
        package_dir = Path(package_dir_value)
        expected_package_paths = {
            "package_handoff_trial_json": package_dir / "handoff_trial.json",
            "package_readiness_json": package_dir / "readiness.json",
            "package_zip": package_dir.parent / f"{package_dir.name}.zip",
            "package_zip_sha256": package_dir.parent / f"{package_dir.name}.zip.sha256",
        }
        for name, expected in expected_package_paths.items():
            if not artifact_path_matches(artifact_paths, name, expected):
                failures.append(f"input_artifacts.{name}.path does not match metadata.external_evidence_package_dir")

    optional_metadata_artifacts = {
        "external_trial_verification_report": "external_trial_verification_report",
        "external_evidence_package_verification_report": "external_evidence_package_verification_report",
    }
    for metadata_key, artifact_name in optional_metadata_artifacts.items():
        value = metadata.get(metadata_key)
        if isinstance(value, str) and value.strip():
            if not artifact_path_matches(artifact_paths, artifact_name, Path(value)):
                failures.append(f"input_artifacts.{artifact_name}.path does not match metadata.{metadata_key}")
        elif artifact_name in artifact_paths:
            failures.append(f"input_artifacts.{artifact_name} is present but metadata.{metadata_key} is empty")
    return failures


def validate_local_evidence_preflight_package_name_binding(
    metadata: dict,
    artifact_summaries: dict[str, dict],
) -> list[str]:
    failures = []
    package_dir_value = metadata.get("external_evidence_package_dir")
    readiness_summary = artifact_summaries.get("package_readiness_json")
    if not isinstance(package_dir_value, str) or not package_dir_value.strip() or readiness_summary is None:
        return failures
    readiness_path = Path(package_dir_value) / "readiness.json"
    if not readiness_path.is_file():
        return failures
    expected_package_name = readiness_package_name(readiness_path)
    if readiness_summary.get("package_name") != expected_package_name:
        failures.append("input_artifacts.package_readiness_json.package_name must match package readiness report")
    return failures


def verify_local_evidence_preflight_report(
    path: Path,
    verify_files: bool = False,
    verify_gates: bool = False,
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
    if not failures and verify_gates:
        failures.extend(validate_local_evidence_preflight_gates(payload))
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print(f"local evidence preflight report ok: {path}")
    print(f"status={payload['status']}")
    print(f"claim_status={payload['claim_status']}")
    print(f"verified_files={verify_files}")
    print(f"verified_gates={verify_gates}")
    print(f"required_pass={require_pass}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
