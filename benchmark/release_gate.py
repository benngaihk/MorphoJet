#!/usr/bin/env python3
"""Run MorphoJet release-readiness gates and write an auditable report."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GITHUB_RELEASE_REPO = "benngaihk/MorphoJet"
DEFAULT_STABLE_RELEASE_TAG = "v0.1.0"
STABLE_RELEASE_TAG_PATTERN = re.compile(r"^v\d+\.\d+\.\d+(?:\+\S+)?$")
FINAL_CLAIM_STATUS = "FINAL_PRODUCTION_CLAIM"
NON_FINAL_CLAIM_STATUS = "NOT_PRODUCTION_CLAIM"
FINAL_EVIDENCE_SCOPE = "FINAL_PRODUCTION_RELEASE_GATE"
NON_FINAL_EVIDENCE_SCOPE = "RELEASE_GATE_PRECHECK"
FINAL_PRODUCTION_SIGNOFF = True
NON_FINAL_PRODUCTION_SIGNOFF = False
EXTERNAL_TRIAL_PLAN_EVIDENCE_SCOPE = "EXTERNAL_L4_TRIAL_PLAN"
EXTERNAL_TRIAL_EVIDENCE_SCOPE = "EXTERNAL_L4_WORKFLOW_TRIAL"
EXTERNAL_TRIAL_REVIEW_EVIDENCE_SCOPE = "EXTERNAL_L4_WORKFLOW_TRIAL_REVIEW"
EXTERNAL_PACKAGE_EVIDENCE_SCOPE = "EXTERNAL_L4_EVIDENCE_PACKAGE"
EXTERNAL_PACKAGE_REVIEW_EVIDENCE_SCOPE = "EXTERNAL_L4_EVIDENCE_PACKAGE_REVIEW"
EXTERNAL_READINESS_STATUS = "READY"
EXTERNAL_READINESS_EVIDENCE_SCOPE = "EXTERNAL_L4_READINESS_PRECHECK"
LOCAL_PREFLIGHT_EVIDENCE_SCOPE = "LOCAL_EXTERNAL_L4_PREFLIGHT"
GITHUB_STABLE_RELEASE_EVIDENCE_SCOPE = "GITHUB_STABLE_RELEASE_VERIFICATION"
GITHUB_ACTIONS_WORKFLOW_EVIDENCE_SCOPE = "GITHUB_ACTIONS_WORKFLOW_VERIFICATION"
GITHUB_ACTIONS_WORKFLOW_BRANCH = "main"
GITHUB_ACTIONS_REQUIRED_WORKFLOWS = ["ci.yml", "external-l4-rehearsal.yml"]
MIN_EXTERNAL_ACCEPTANCE_CRITERIA = 3
PRODUCTION_AUDIT_PASS_STATUS = "PASS"
PRODUCTION_AUDIT_FAIL_STATUS = "FAIL"
PRODUCTION_AUDIT_MISSING_STATUS = "MISSING"
PRODUCTION_AUDIT_INCOMPLETE_STATUS = "INCOMPLETE"
PRODUCTION_AUDIT_CHECK_STATUSES = frozenset(
    [
        PRODUCTION_AUDIT_PASS_STATUS,
        PRODUCTION_AUDIT_FAIL_STATUS,
        PRODUCTION_AUDIT_MISSING_STATUS,
    ]
)
PRODUCTION_CLAIM_STATUSES = frozenset(
    [
        PRODUCTION_AUDIT_PASS_STATUS,
        PRODUCTION_AUDIT_INCOMPLETE_STATUS,
    ]
)
PRODUCTION_PATH_METADATA_KEYS = frozenset(
    [
        "external_trial_json",
        "external_trial_root",
        "external_evidence_package_dir",
        "external_trial_verification_report",
        "external_evidence_package_verification_report",
        "github_release_verification_report",
        "github_workflow_verification_report",
        "production_evidence_audit_report",
    ]
)
RELEASE_GATE_ARGV_PATH_FLAGS = frozenset(
    [
        "--out-json",
        "--out-md",
        "--external-trial-json",
        "--external-trial-root",
        "--external-evidence-package-dir",
        "--external-trial-verification-report",
        "--external-evidence-package-verification-report",
        "--github-release-verification-report",
        "--github-workflow-verification-report",
        "--production-evidence-audit-report",
    ]
)
PRODUCTION_AUDIT_CHECK_NAMES = [
    "clean_git_worktree",
    "standard_code_and_artifact_gates",
    "github_actions_workflow_verification",
    "l3_provenance_hashes",
    "external_l4_workflow_trial",
    "external_l4_evidence_package",
    "external_l4_saved_reviewer_reports",
    "stable_github_release",
    "stable_github_release_saved_report",
    "production_evidence_readiness_audit",
]
PRODUCTION_FINAL_BLOCKER_NAMES = [
    name
    for name in PRODUCTION_AUDIT_CHECK_NAMES
    if name not in {"standard_code_and_artifact_gates", "production_evidence_readiness_audit"}
]
PRODUCTION_STANDARD_GATE_NAMES = [
    "Rust formatting",
    "Rust tests",
    "Rust clippy",
    "Python helper compilation",
    "Python helper tests",
    "Validate claim language",
    "Validate handoff manifests",
    "Validate external lab handoff template",
    "Validate CellBinDB direct-mask inspection",
    "Validate existing CellBinDB L3 artifacts",
    "Validate CellBinDB workflow bridge artifacts",
    "Validate CellBinDB handoff trial artifacts",
]
REQUIRED_PRODUCTION_GATE_NAMES = frozenset(
    [
        "Require clean git worktree",
        *PRODUCTION_STANDARD_GATE_NAMES,
        "Verify saved GitHub Actions workflow report",
        "Validate CellBinDB L3 provenance",
        "Validate external L4 workflow trial report",
        "Validate external L4 evidence package",
        "Verify saved external L4 trial report",
        "Verify saved external L4 evidence package report",
        "Verify saved external L4 reviewer report pair",
        "Verify GitHub release assets",
        "Verify saved stable GitHub release report",
        "Verify saved production evidence audit report",
    ]
)


def non_final_claim_scope(evidence_scope: str) -> dict[str, object]:
    return {
        "claim_status": NON_FINAL_CLAIM_STATUS,
        "evidence_scope": evidence_scope,
        "final_production_signoff": NON_FINAL_PRODUCTION_SIGNOFF,
    }


def external_readiness_scope() -> dict[str, object]:
    return {
        "status": EXTERNAL_READINESS_STATUS,
        **non_final_claim_scope(EXTERNAL_READINESS_EVIDENCE_SCOPE),
    }


def external_package_manifest_claim_scope() -> dict[str, object]:
    return {
        **non_final_claim_scope(EXTERNAL_PACKAGE_EVIDENCE_SCOPE),
        "trial_claim_status": NON_FINAL_CLAIM_STATUS,
        "trial_evidence_scope": EXTERNAL_TRIAL_EVIDENCE_SCOPE,
        "trial_final_production_signoff": NON_FINAL_PRODUCTION_SIGNOFF,
    }


def is_stable_release_tag(tag: str) -> bool:
    return bool(STABLE_RELEASE_TAG_PATTERN.fullmatch(tag))


def stable_release_url(tag: str = DEFAULT_STABLE_RELEASE_TAG, repo: str = GITHUB_RELEASE_REPO) -> str:
    return f"https://github.com/{repo}/releases/tag/{tag}"


def is_utc_datetime(value: datetime) -> bool:
    return value.utcoffset() == timezone.utc.utcoffset(value)


def slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-")
    return slug or "external-l4-trial"


@dataclass
class Gate:
    name: str
    command: list[str] | None
    status: str
    elapsed_seconds: float
    detail: str


def run_command(name: str, command: list[str]) -> Gate:
    started = time.perf_counter()
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    elapsed = time.perf_counter() - started
    detail = completed.stdout[-4000:]
    if completed.stderr:
        detail = (detail + "\n" + completed.stderr[-4000:]).strip()
    return Gate(
        name=name,
        command=command,
        status="PASS" if completed.returncode == 0 else "FAIL",
        elapsed_seconds=elapsed,
        detail=detail,
    )


def cargo_bin() -> str:
    env_cargo = os.environ.get("CARGO")
    if env_cargo:
        return env_cargo
    cargo = shutil.which("cargo")
    if cargo:
        return cargo
    home_cargo = Path.home() / ".cargo" / "bin" / "cargo"
    if home_cargo.exists():
        return str(home_cargo)
    return "cargo"


def load_json(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(path)
    return json.loads(path.read_text())


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_l3_artifacts() -> Gate:
    started = time.perf_counter()
    try:
        parity = load_json(ROOT / "benchmark/results/cellbindb/oracle-full/parity.json")
        impact = load_json(ROOT / "benchmark/results/cellbindb/oracle-full/impact.json")
        failures = []
        if parity.get("status") != "PASS":
            failures.append(f"parity status is {parity.get('status')}")
        if parity.get("expected_rows") != 107936 or parity.get("actual_rows") != 107936:
            failures.append(
                f"unexpected row counts expected={parity.get('expected_rows')} actual={parity.get('actual_rows')}"
            )
        if parity.get("numeric_failures") != 0:
            failures.append(f"numeric_failures={parity.get('numeric_failures')}")
        if impact.get("status") != "PASS":
            failures.append(f"impact status is {impact.get('status')}")
        if not impact.get("gates") or not all(gate.get("passed") for gate in impact["gates"]):
            failures.append("one or more impact gates did not pass")
        status = "FAIL" if failures else "PASS"
        detail = "; ".join(failures) if failures else (
            "CellBinDB L3 artifacts PASS: "
            f"rows={parity.get('actual_rows')}, "
            f"speedup={impact.get('speedup'):.2f}x, "
            f"rss_ratio={impact.get('rss_ratio'):.2%}"
        )
    except Exception as exc:  # noqa: BLE001 - report exact release gate failure.
        status = "FAIL"
        detail = f"{type(exc).__name__}: {exc}"
    return Gate(
        name="Validate existing CellBinDB L3 artifacts",
        command=None,
        status=status,
        elapsed_seconds=time.perf_counter() - started,
        detail=detail,
    )


def validate_cellbindb_direct_masks() -> Gate:
    started = time.perf_counter()
    try:
        import inspect_cellbindb_direct_masks

        payload = inspect_cellbindb_direct_masks.build_payload(
            ROOT / "benchmark/data/cellbindb/CellBinDB.zip",
            ROOT / "benchmark/data/cellbindb/zenodo_metadata.json",
            ROOT / "benchmark/cellprofiler/public_corpora.json",
            "cellbindb",
            None,
            1000,
            True,
            [
                "benchmark/inspect_cellbindb_direct_masks.py",
                "--full",
                "--verify-md5",
                "--require-pass",
            ],
        )
        summary = payload["summary"]
        issues = summary.get("issues") or []
        status = "FAIL" if payload.get("status") != "PASS" or issues else "PASS"
        detail = "; ".join(issues) if issues else (
            "CellBinDB direct-mask inspection PASS: "
            f"samples={summary.get('inspected_sample_groups')}/{summary.get('total_sample_groups')}, "
            f"semantic_masks={summary.get('samples_with_semantic_masks')}, "
            f"positive_labels={summary.get('inspected_positive_label_count')}, "
            f"md5={payload.get('zip', {}).get('observed_md5')}"
        )
    except Exception as exc:  # noqa: BLE001 - report exact release gate failure.
        status = "FAIL"
        detail = f"{type(exc).__name__}: {exc}"
    return Gate(
        name="Validate CellBinDB direct-mask inspection",
        command=[
            "python3",
            "benchmark/inspect_cellbindb_direct_masks.py",
            "--full",
            "--verify-md5",
            "--require-pass",
        ],
        status=status,
        elapsed_seconds=time.perf_counter() - started,
        detail=detail,
    )


def validate_l3_provenance_artifact() -> Gate:
    started = time.perf_counter()
    path = ROOT / "benchmark/results/cellbindb/oracle-full/provenance.json"
    try:
        provenance = load_json(path)
        failures = []
        if provenance.get("schema_version") != 1:
            failures.append(f"schema_version={provenance.get('schema_version')}")
        if provenance.get("generator") != "benchmark/run_cellbindb_oracle.py":
            failures.append(f"generator={provenance.get('generator')}")
        current_commit = git_commit()
        provenance_commit = provenance.get("git_commit")
        compatible_delta = False
        if provenance_commit != current_commit:
            changed_paths = git_changed_paths(str(provenance_commit), current_commit)
            compatible_delta = bool(changed_paths) and all(
                is_l3_provenance_compatible_path(path) for path in changed_paths
            )
            if not compatible_delta:
                failures.append(
                    "git_commit mismatch "
                    f"provenance={provenance_commit} current={current_commit} "
                    f"changed_paths={','.join(changed_paths[:20])}"
                )
        if provenance.get("run_name") != "full":
            failures.append(f"run_name={provenance.get('run_name')}")
        if provenance.get("skip_cellprofiler") is not False:
            failures.append("provenance was generated with skip_cellprofiler=true")
        artifacts = provenance.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            failures.append("artifacts must be a non-empty list")
            artifacts = []
        required_paths = {
            "benchmark/results/cellbindb/oracle-full/parity.json",
            "benchmark/results/cellbindb/oracle-full/impact.json",
            "benchmark/results/cellbindb/oracle-full/workflow_bridge.json",
            "benchmark/results/cellbindb/oracle-full/handoff_trial.json",
            "benchmark/results/cellbindb/oracle-full/morphojet/Objects.csv",
            "benchmark/results/cellbindb/oracle-full/cellprofiler/Cells.csv",
        }
        observed_paths = {artifact.get("path") for artifact in artifacts if isinstance(artifact, dict)}
        missing_required = sorted(required_paths - observed_paths)
        if missing_required:
            failures.append(f"missing provenance artifacts={','.join(missing_required)}")
        checked = 0
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                failures.append("artifact entry must be an object")
                continue
            artifact_path = artifact.get("path")
            expected_hash = artifact.get("sha256")
            if not isinstance(artifact_path, str) or not isinstance(expected_hash, str):
                failures.append(f"invalid artifact entry={artifact}")
                continue
            full_path = ROOT / artifact_path
            if not full_path.is_file():
                failures.append(f"artifact missing on disk={artifact_path}")
                continue
            actual_hash = sha256_file(full_path)
            if actual_hash != expected_hash:
                failures.append(f"sha256 mismatch for {artifact_path}")
            checked += 1
        status = "FAIL" if failures else "PASS"
        detail = "; ".join(failures) if failures else (
            "CellBinDB provenance PASS: "
            f"commit={provenance.get('git_commit')[:12]}, "
            f"current={current_commit[:12]}, compatible_delta={compatible_delta}, "
            f"artifacts={checked}"
        )
    except Exception as exc:  # noqa: BLE001 - report exact release gate failure.
        status = "FAIL"
        detail = f"{type(exc).__name__}: {exc}"
    return Gate(
        name="Validate CellBinDB L3 provenance",
        command=None,
        status=status,
        elapsed_seconds=time.perf_counter() - started,
        detail=detail,
    )


def validate_workflow_bridge_artifacts() -> Gate:
    started = time.perf_counter()
    try:
        bridge = load_json(ROOT / "benchmark/results/cellbindb/oracle-full/workflow_bridge.json")
        contract = load_json(ROOT / "benchmark/results/cellbindb/oracle-full/handoff_contract.json")
        failures = []
        if bridge.get("status") != "PASS":
            failures.append(f"bridge status is {bridge.get('status')}")
        if bridge.get("cellprofiler_rows") != 107936 or bridge.get("morphojet_rows") != 107936:
            failures.append(
                "unexpected row counts "
                f"cellprofiler={bridge.get('cellprofiler_rows')} morphojet={bridge.get('morphojet_rows')}"
            )
        if bridge.get("missing_rows") != 0 or bridge.get("extra_rows") != 0:
            failures.append(f"row gaps missing={bridge.get('missing_rows')} extra={bridge.get('extra_rows')}")
        if bridge.get("numeric_failures") != 0:
            failures.append(f"numeric_failures={bridge.get('numeric_failures')}")
        compared_columns = bridge.get("compared_columns") or []
        expected_value_columns = [
            column
            for column in contract.get("required_columns", [])
            if column not in {"ImageNumber", "ObjectNumber"}
        ]
        if len(compared_columns) < len(expected_value_columns):
            failures.append(
                f"compared_columns={len(compared_columns)} expected={len(expected_value_columns)}"
            )
        status = "FAIL" if failures else "PASS"
        detail = "; ".join(failures) if failures else (
            "CellBinDB workflow bridge artifacts PASS: "
            f"rows={bridge.get('morphojet_rows')}, "
            f"compared_columns={len(compared_columns)}, "
            f"numeric_compared={bridge.get('numeric_compared')}"
        )
    except Exception as exc:  # noqa: BLE001 - report exact release gate failure.
        status = "FAIL"
        detail = f"{type(exc).__name__}: {exc}"
    return Gate(
        name="Validate CellBinDB workflow bridge artifacts",
        command=None,
        status=status,
        elapsed_seconds=time.perf_counter() - started,
        detail=detail,
    )


def validate_handoff_trial_artifacts() -> Gate:
    started = time.perf_counter()
    try:
        trial = load_json(ROOT / "benchmark/results/cellbindb/oracle-full/handoff_trial.json")
        contract = load_json(ROOT / "benchmark/results/cellbindb/oracle-full/handoff_contract.json")
        failures = []
        if trial.get("status") != "PASS":
            failures.append(f"trial status is {trial.get('status')}")
        steps = trial.get("steps") or []
        if not steps:
            failures.append("trial has no steps")
        failed_steps = [step.get("name", "<unnamed>") for step in steps if step.get("status") != "PASS"]
        if failed_steps:
            failures.append(f"failed trial steps={','.join(failed_steps)}")
        if contract.get("status") != "PASS":
            failures.append(f"contract status is {contract.get('status')}")
        if contract.get("rows") != 107936:
            failures.append(f"contract rows={contract.get('rows')}")
        if contract.get("missing_columns"):
            failures.append(f"missing contract columns={','.join(contract.get('missing_columns', []))}")
        status = "FAIL" if failures else "PASS"
        detail = "; ".join(failures) if failures else (
            "CellBinDB handoff trial PASS: "
            f"steps={len(steps)}, rows={contract.get('rows')}, "
            f"columns={contract.get('columns')}"
        )
    except Exception as exc:  # noqa: BLE001 - report exact release gate failure.
        status = "FAIL"
        detail = f"{type(exc).__name__}: {exc}"
    return Gate(
        name="Validate CellBinDB handoff trial artifacts",
        command=None,
        status=status,
        elapsed_seconds=time.perf_counter() - started,
        detail=detail,
    )


def has_placeholder(value: str) -> bool:
    return value.startswith("REPLACE_WITH")


def resolve_artifact_path(artifact: str, artifact_root: Path) -> Path:
    path = Path(artifact)
    if path.is_absolute():
        return path
    return artifact_root / path


def github_release_verification_report_path(tag: str) -> Path:
    return Path("benchmark/results/github-release-verification") / f"{tag}.json"


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


def load_json_if_file(path: Path | None) -> object | None:
    if path is None or not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def add_protected_path(paths: dict[Path, str], path: Path | None, label: str) -> None:
    if path is not None:
        paths[path] = label


def add_external_trial_protected_paths(paths: dict[Path, str], args: argparse.Namespace) -> None:
    external_trial_json = getattr(args, "external_trial_json", None)
    external_trial_root = getattr(args, "external_trial_root", None)
    add_protected_path(paths, external_trial_json, "--external-trial-json")
    trial = load_json_if_file(external_trial_json)
    if not isinstance(trial, dict) or external_trial_root is None:
        return
    artifacts = trial.get("artifacts")
    if not isinstance(artifacts, list):
        return
    for artifact in artifacts:
        if isinstance(artifact, str) and artifact:
            add_protected_path(
                paths,
                resolve_artifact_path(artifact, external_trial_root),
                f"external trial artifact: {artifact}",
            )


def add_package_protected_paths(paths: dict[Path, str], package_dir: Path | None) -> None:
    if package_dir is None:
        return
    for filename in [
        "handoff_trial.json",
        "readiness.json",
        "external_evidence.json",
        "rendered_manifest.json",
        "artifact_manifest.json",
        "README.md",
        "README.zh-CN.md",
    ]:
        add_protected_path(paths, package_dir / filename, f"evidence package file: {filename}")
    add_protected_path(paths, package_dir.parent / f"{package_dir.name}.zip", "evidence package zip")
    add_protected_path(paths, package_dir.parent / f"{package_dir.name}.zip.sha256", "evidence package checksum")
    manifest = load_json_if_file(package_dir / "artifact_manifest.json")
    if not isinstance(manifest, dict):
        return
    for entry in manifest.get("artifacts", []):
        if isinstance(entry, dict) and isinstance(entry.get("package_path"), str) and entry["package_path"]:
            add_protected_path(
                paths,
                package_dir / entry["package_path"],
                f"evidence package artifact: {entry['package_path']}",
            )


def protected_report_input_path_entries(args: argparse.Namespace) -> dict[Path, str]:
    paths: dict[Path, str] = {}
    add_external_trial_protected_paths(paths, args)
    add_package_protected_paths(paths, getattr(args, "external_evidence_package_dir", None))
    add_protected_path(
        paths,
        getattr(args, "external_trial_verification_report", None),
        "--external-trial-verification-report",
    )
    add_protected_path(
        paths,
        getattr(args, "external_evidence_package_verification_report", None),
        "--external-evidence-package-verification-report",
    )
    add_protected_path(
        paths,
        getattr(args, "github_release_verification_report", None),
        "--github-release-verification-report",
    )
    add_protected_path(
        paths,
        getattr(args, "github_workflow_verification_report", None),
        "--github-workflow-verification-report",
    )
    add_protected_path(
        paths,
        getattr(args, "production_evidence_audit_report", None),
        "--production-evidence-audit-report",
    )
    verify_github_release = getattr(args, "verify_github_release", None)
    if verify_github_release:
        add_protected_path(
            paths,
            github_release_verification_report_path(verify_github_release),
            "GitHub release verification report",
        )
    return paths


def protected_report_input_paths(args: argparse.Namespace) -> dict[str, str]:
    return {normalized_path_key(path): label for path, label in protected_report_input_path_entries(args).items()}


def validate_report_output_paths(args: argparse.Namespace) -> None:
    protected = protected_report_input_paths(args)
    protected_entries = protected_report_input_path_entries(args)
    outputs = [("--out-json", args.out_json), ("--out-md", args.out_md)]
    output_keys: dict[str, str] = {}
    output_paths: dict[str, Path] = {}
    failures = []
    for label, path in outputs:
        key = normalized_path_key(path)
        previous_label = output_keys.get(key)
        if previous_label is not None:
            failures.append(f"{label} must not use the same path as {previous_label}")
        else:
            output_keys[key] = label
            output_paths[label] = path
        protected_label = protected.get(key)
        if protected_label:
            failures.append(f"{label} must not overwrite {protected_label}: {path}")
            continue
        for protected_path, protected_label in protected_entries.items():
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
        raise SystemExit("\n".join(f"ERROR: {failure}" for failure in failures))


def production_claim_contract_failures(args: argparse.Namespace) -> list[str]:
    if not args.require_production_claim:
        return []
    failures = []
    if not args.require_clean_git:
        failures.append("--require-production-claim requires --require-clean-git")
    if not args.require_l3_provenance:
        failures.append("--require-production-claim requires --require-l3-provenance")
    if not args.verify_github_release:
        failures.append("--require-production-claim requires --verify-github-release")
    elif args.github_release_kind != "stable":
        failures.append("--require-production-claim with --verify-github-release requires --github-release-kind stable")
    if not args.github_release_verification_report:
        failures.append("--require-production-claim requires --github-release-verification-report")
    if not args.github_workflow_verification_report:
        failures.append("--require-production-claim requires --github-workflow-verification-report")
    if not args.production_evidence_audit_report:
        failures.append("--require-production-claim requires --production-evidence-audit-report")
    if not any(
        [
            args.external_trial_json,
            args.external_trial_root,
            args.external_evidence_package_dir,
            args.external_trial_verification_report,
            args.external_evidence_package_verification_report,
        ]
    ):
        failures.extend(
            [
                "--require-production-claim requires --external-trial-json",
                "--require-production-claim requires --external-trial-root",
                "--require-production-claim requires --external-evidence-package-dir",
                "--require-production-claim requires --external-trial-verification-report",
                "--require-production-claim requires --external-evidence-package-verification-report",
            ]
        )
    if args.external_trial_json and not args.external_trial_root:
        failures.append("--require-production-claim with --external-trial-json requires --external-trial-root")
    if args.external_trial_root and not args.external_trial_json:
        failures.append("--require-production-claim with --external-trial-root requires --external-trial-json")
    if args.external_evidence_package_dir and not args.external_trial_json:
        failures.append(
            "--require-production-claim with --external-evidence-package-dir requires --external-trial-json"
        )
    if args.external_trial_json and args.external_trial_root and not args.external_evidence_package_dir:
        failures.append(
            "--require-production-claim with external L4 trial evidence requires --external-evidence-package-dir"
        )
    if (
        args.external_trial_json
        and args.external_trial_root
        and args.external_evidence_package_dir
        and not args.external_trial_verification_report
    ):
        failures.append(
            "--require-production-claim with external L4 evidence requires --external-trial-verification-report"
        )
    if (
        args.external_trial_json
        and args.external_trial_root
        and args.external_evidence_package_dir
        and not args.external_evidence_package_verification_report
    ):
        failures.append(
            "--require-production-claim with external L4 evidence requires "
            "--external-evidence-package-verification-report"
        )
    if args.external_trial_verification_report and (
        not args.external_trial_json or not args.external_trial_root
    ):
        failures.append(
            "--require-production-claim with --external-trial-verification-report requires "
            "--external-trial-json and --external-trial-root"
        )
    if args.external_evidence_package_verification_report and (
        not args.external_evidence_package_dir or not args.external_trial_json
    ):
        failures.append(
            "--require-production-claim with --external-evidence-package-verification-report requires "
            "--external-evidence-package-dir and --external-trial-json"
        )
    if (
        args.external_trial_verification_report
        and args.external_trial_json
        and args.external_trial_root
        and not args.external_evidence_package_verification_report
    ):
        failures.append(
            "--require-production-claim with --external-trial-verification-report requires "
            "--external-evidence-package-verification-report"
        )
    if (
        args.external_evidence_package_verification_report
        and args.external_evidence_package_dir
        and args.external_trial_json
        and not args.external_trial_verification_report
    ):
        failures.append(
            "--require-production-claim with --external-evidence-package-verification-report requires "
            "--external-trial-verification-report"
        )
    return failures


def saved_github_release_report_command(
    report: Path,
    expected_tag: str | None = None,
    expected_commit: str | None = None,
) -> list[str]:
    command = [
        "python3",
        "benchmark/verify_github_release.py",
        "--verify-report",
        normalized_path_key(report),
        "--verify-report-files",
        "--require-report-pass",
        "--require-stable-report",
        "--verify-git-commit",
        "--expect-repo",
        GITHUB_RELEASE_REPO,
    ]
    if expected_tag:
        command.extend(["--expect-tag", expected_tag])
    if expected_commit:
        command.extend(["--expect-commit", expected_commit])
    return command


def saved_github_workflow_report_command(report: Path, expected_commit: str | None = None) -> list[str]:
    command = [
        "python3",
        "benchmark/verify_github_workflows.py",
        "--verify-report",
        normalized_path_key(report),
        "--require-report-pass",
        "--expect-repo",
        GITHUB_RELEASE_REPO,
        "--expect-branch",
        GITHUB_ACTIONS_WORKFLOW_BRANCH,
    ]
    if expected_commit:
        command.extend(["--expect-commit", expected_commit])
    for workflow in GITHUB_ACTIONS_REQUIRED_WORKFLOWS:
        command.extend(["--expect-workflow", workflow])
    return command


def saved_external_trial_report_command(report: Path, expected_commit: str | None = None) -> list[str]:
    command = [
        "python3",
        "benchmark/verify_external_trial_report.py",
        "--verify-report",
        normalized_path_key(report),
        "--verify-report-files",
        "--require-report-pass",
    ]
    if expected_commit:
        command.extend(["--expect-commit", expected_commit])
    return command


def saved_external_package_report_command(report: Path, expected_commit: str | None = None) -> list[str]:
    command = [
        "python3",
        "benchmark/verify_external_evidence_package.py",
        "--verify-report",
        normalized_path_key(report),
        "--verify-report-files",
        "--require-report-pass",
        "--require-trial-json",
    ]
    if expected_commit:
        command.extend(["--expect-commit", expected_commit])
    return command


def live_github_release_report_command(tag: str, kind: str, expected_commit: str | None = None) -> list[str]:
    release_kind_flag = "--expect-stable" if kind == "stable" else "--expect-prerelease"
    command = [
        "python3",
        "benchmark/verify_github_release.py",
        tag,
        "--repo",
        GITHUB_RELEASE_REPO,
        release_kind_flag,
        "--json-out",
        normalized_path_key(github_release_verification_report_path(tag)),
    ]
    if expected_commit:
        command.extend(["--expect-commit", expected_commit])
    return command


def saved_production_evidence_audit_report_command(report: Path) -> list[str]:
    return [
        "python3",
        "benchmark/audit_production_evidence.py",
        "--verify-report",
        normalized_path_key(report),
        "--verify-report-files",
        "--require-ready",
    ]


def paths_match(recorded: object, expected: Path | None) -> bool:
    if expected is None or not isinstance(recorded, str) or not recorded.strip():
        return False
    return Path(recorded).resolve(strict=False) == expected.resolve(strict=False)


def load_reviewer_report(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"saved reviewer report must be a JSON object: {path}")
    return payload


def gate_with_binding_failures(gate: Gate, failures: list[str]) -> Gate:
    if not failures:
        return gate
    detail_parts = [gate.detail] if gate.detail else []
    detail_parts.extend(f"FAIL: {failure}" for failure in failures)
    return Gate(
        name=gate.name,
        command=gate.command,
        status="FAIL",
        elapsed_seconds=gate.elapsed_seconds,
        detail="\n".join(detail_parts),
    )


def saved_external_trial_report_binding_failures(report: Path, args: argparse.Namespace) -> list[str]:
    try:
        payload = load_reviewer_report(report)
    except Exception as exc:  # noqa: BLE001 - binding diagnostics should fail closed.
        return [f"cannot read saved external trial report for binding: {type(exc).__name__}: {exc}"]
    failures = []
    if not paths_match(payload.get("trial_json"), args.external_trial_json):
        failures.append("saved external trial report trial_json does not match --external-trial-json")
    if not paths_match(payload.get("trial_root"), args.external_trial_root):
        failures.append("saved external trial report trial_root does not match --external-trial-root")
    return failures


def saved_external_package_report_binding_failures(report: Path, args: argparse.Namespace) -> list[str]:
    try:
        payload = load_reviewer_report(report)
    except Exception as exc:  # noqa: BLE001 - binding diagnostics should fail closed.
        return [f"cannot read saved external evidence package report for binding: {type(exc).__name__}: {exc}"]
    failures = []
    if not paths_match(payload.get("package_dir"), args.external_evidence_package_dir):
        failures.append("saved external evidence package report package_dir does not match --external-evidence-package-dir")
    if not paths_match(payload.get("trial_json"), args.external_trial_json):
        failures.append("saved external evidence package report trial_json does not match --external-trial-json")
    return failures


def saved_external_reviewer_pair_binding_failures(trial_report: Path, package_report: Path) -> list[str]:
    try:
        trial_payload = load_reviewer_report(trial_report)
    except Exception as exc:  # noqa: BLE001 - binding diagnostics should fail closed.
        return [f"cannot read saved external trial report for pair binding: {type(exc).__name__}: {exc}"]
    try:
        package_payload = load_reviewer_report(package_report)
    except Exception as exc:  # noqa: BLE001 - binding diagnostics should fail closed.
        return [f"cannot read saved external evidence package report for pair binding: {type(exc).__name__}: {exc}"]
    trial_input_files = trial_payload.get("input_files")
    package_input_files = package_payload.get("input_files")
    trial_evidence = (
        trial_input_files.get("external_evidence") if isinstance(trial_input_files, dict) else None
    )
    package_evidence = (
        package_input_files.get("package_external_evidence") if isinstance(package_input_files, dict) else None
    )
    if not isinstance(trial_evidence, dict):
        return ["saved external trial report is missing input_files.external_evidence"]
    if not isinstance(package_evidence, dict):
        return ["saved external package report is missing input_files.package_external_evidence"]
    ignored_file_fields = {"path", "exists", "size_bytes", "sha256"}
    normalized_trial_evidence = {
        key: value for key, value in trial_evidence.items() if key not in ignored_file_fields
    }
    normalized_package_evidence = {
        key: value for key, value in package_evidence.items() if key not in ignored_file_fields
    }
    if normalized_trial_evidence != normalized_package_evidence:
        return ["saved external trial/package reviewer reports do not bind the same external evidence"]
    return []


def saved_external_reviewer_pair_gate(trial_report: Path, package_report: Path) -> Gate:
    failures = saved_external_reviewer_pair_binding_failures(trial_report, package_report)
    if failures:
        return Gate(
            name="Verify saved external L4 reviewer report pair",
            command=None,
            status="FAIL",
            elapsed_seconds=0.0,
            detail="; ".join(failures),
        )
    return Gate(
        name="Verify saved external L4 reviewer report pair",
        command=None,
        status="PASS",
        elapsed_seconds=0.0,
        detail="saved external trial/package reviewer reports bind the same external evidence",
    )


def rendered_manifest_artifacts(manifest: dict) -> list[str]:
    artifacts = []
    for export in manifest.get("exports", []):
        if not isinstance(export, dict):
            continue
        out_csv = export.get("out_csv")
        if isinstance(out_csv, str) and out_csv.strip():
            artifacts.append(out_csv)
        if "expected_cellprofiler_csv" in export:
            for key in ["comparison_report", "comparison_json"]:
                path = export.get(key)
                if isinstance(path, str) and path.strip():
                    artifacts.append(path)
    for check in manifest.get("downstream_checks", []):
        if not isinstance(check, dict):
            continue
        for path in check.get("artifacts", []):
            if isinstance(path, str) and path.strip():
                artifacts.append(path)
    return artifacts


def rendered_manifest_step_names(manifest: dict) -> list[str]:
    step_names = []
    for name, _command in rendered_manifest_step_commands(manifest):
        step_names.append(name)
    return step_names


def rendered_manifest_step_commands(manifest: dict) -> list[tuple[str, list[str]]]:
    step_commands = []
    objects_csv = manifest.get("morphojet_objects_csv")
    top_level_metadata_columns = manifest.get("required_object_metadata_columns", [])
    for export in manifest.get("exports", []):
        if not isinstance(export, dict):
            continue
        name = export.get("name")
        if isinstance(name, str) and name.strip():
            channels = export.get("channels")
            channel_arg = ",".join(channels) if isinstance(channels, list) else ""
            out_csv = export.get("out_csv")
            object_set = export.get("object_set")
            metadata_columns = export.get("required_object_metadata_columns", top_level_metadata_columns)
            metadata_arg = (
                ",".join(column for column in metadata_columns if isinstance(column, str) and column.strip())
                if isinstance(metadata_columns, list)
                else ""
            )
            materialize_command = [
                "python3",
                "benchmark/materialize_morphojet_cellprofiler_wide.py",
                "--objects",
                export.get("objects_csv", objects_csv),
                "--object-set",
                object_set,
                "--channels",
                channel_arg,
                "--out",
                out_csv,
            ]
            if metadata_arg:
                materialize_command.extend(["--metadata-columns", metadata_arg])
            step_commands.append(
                (
                    f"Materialize {name} wide CSV",
                    materialize_command,
                )
            )
            if "expected_cellprofiler_csv" in export:
                compare_command = [
                    "python3",
                    "benchmark/compare_cellprofiler_wide_subset.py",
                    export.get("expected_cellprofiler_csv"),
                    out_csv,
                    "--out",
                    export.get("comparison_report"),
                    "--json-out",
                    export.get("comparison_json"),
                    "--fail-on-gap",
                ]
                if metadata_arg:
                    compare_command.extend(["--allow-extra-columns", metadata_arg])
                step_commands.append(
                    (
                        f"Compare {name} supported columns",
                        compare_command,
                    )
                )
    for check in manifest.get("downstream_checks", []):
        if not isinstance(check, dict):
            continue
        name = check.get("name")
        command = check.get("command")
        if isinstance(name, str) and name.strip() and isinstance(command, list):
            step_commands.append((name, command))
    return step_commands


def is_git_commit(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 40
        and all(character in "0123456789abcdef" for character in value)
    )


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


def external_trial_metadata_argv_failures(
    metadata: dict,
    trial: dict,
    report_path: Path | None = None,
) -> list[str]:
    failures = []
    argv = metadata.get("argv")
    if not isinstance(argv, list) or not argv or not all(isinstance(item, str) and item for item in argv):
        return ["metadata.argv must be a non-empty string list"]
    if argv[0] != "benchmark/run_handoff_trial.py":
        failures.append(f"metadata.argv[0]={argv[0]}")

    strict_flag = "--require-external-evidence"
    if argv.count(strict_flag) != 1:
        failures.append(
            "metadata.argv must include exactly one --require-external-evidence "
            "for external workflow trial reports"
        )

    manifest = trial.get("manifest")
    if not isinstance(manifest, str) or not manifest.strip():
        failures.append("trial manifest must be a non-empty string")
    elif argv.count(manifest) != 1:
        failures.append(f"metadata.argv must include trial manifest path exactly once: {manifest}")

    readiness_report = trial.get("readiness_report")
    for flag in ["--readiness-report", "--out-json", "--out-md"]:
        values = argv_values(argv, flag)
        if len(values) > 1:
            failures.append(f"metadata.argv has duplicate {flag}")
        if not values:
            failures.append(f"metadata.argv missing {flag}")
        for value in values:
            if value is None:
                failures.append(f"metadata.argv {flag} must include a value")
            elif (
                flag == "--out-json"
                and report_path is not None
                and normalized_path_key(Path(value)) != normalized_path_key(report_path)
            ):
                failures.append("metadata.argv --out-json must match external trial report path")
            elif (
                flag == "--readiness-report"
                and isinstance(readiness_report, dict)
                and normalized_path_key(Path(value)) != normalized_path_key(Path(readiness_report.get("path", "")))
            ):
                failures.append("metadata.argv --readiness-report must match readiness_report.path")
    failures.extend(canonical_external_trial_argv_failures(argv, trial, report_path))
    return failures


def canonical_external_trial_argv_failures(
    argv: list[str],
    trial: dict,
    report_path: Path | None = None,
) -> list[str]:
    manifest = trial.get("manifest")
    out_json_values = argv_values(argv, "--out-json")
    out_md_values = argv_values(argv, "--out-md")
    readiness_values = argv_values(argv, "--readiness-report")
    if (
        not isinstance(manifest, str)
        or not manifest.strip()
        or len(out_json_values) != 1
        or len(out_md_values) != 1
        or len(readiness_values) != 1
        or out_json_values[0] is None
        or out_md_values[0] is None
        or readiness_values[0] is None
        or argv.count("--require-external-evidence") != 1
    ):
        return []
    variables = trial.get("variables")
    if variables is None:
        variables = {}
    if not isinstance(variables, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in variables.items()
    ):
        return []
    expected_out_json = str(report_path) if report_path is not None else out_json_values[0]
    canonical = ["benchmark/run_handoff_trial.py", manifest]
    for key in sorted(variables):
        canonical.extend(["--var", f"{key}={variables[key]}"])
    canonical.extend(["--readiness-report", normalized_path_key(Path(readiness_values[0]))])
    canonical.extend(
        [
            "--out-json",
            normalized_path_key(Path(expected_out_json)),
            "--out-md",
            normalized_path_key(Path(out_md_values[0])),
            "--require-external-evidence",
        ]
    )
    if normalize_external_trial_metadata_argv(argv) != canonical:
        return ["metadata.argv must match canonical external trial runner argv"]
    return []


def normalize_external_trial_metadata_argv(argv: list[str]) -> list[str]:
    normalized = []
    path_flags = {"--readiness-report", "--out-json", "--out-md"}
    index = 0
    while index < len(argv):
        item = argv[index]
        normalized.append(item)
        if item in path_flags and index + 1 < len(argv) and not argv[index + 1].startswith("--"):
            normalized.append(normalized_path_key(Path(argv[index + 1])))
            index += 2
            continue
        index += 1
    return normalized


def external_trial_metadata_failures(
    metadata: object,
    trial: dict,
    report_path: Path | None = None,
) -> list[str]:
    failures = []
    if not isinstance(metadata, dict):
        return ["metadata must be present for external workflow trial reports"]
    if metadata.get("schema_version") != 1:
        failures.append(f"metadata.schema_version={metadata.get('schema_version')}")
    if metadata.get("generator") != "benchmark/run_handoff_trial.py":
        failures.append(f"metadata.generator={metadata.get('generator')}")
    generated_at = metadata.get("generated_at_utc")
    if not isinstance(generated_at, str) or not generated_at.strip():
        failures.append("metadata.generated_at_utc must be a non-empty string")
    else:
        try:
            parsed_generated_at = datetime.fromisoformat(generated_at)
            if parsed_generated_at.tzinfo is None:
                failures.append("metadata.generated_at_utc must include timezone")
            elif not is_utc_datetime(parsed_generated_at):
                failures.append("metadata.generated_at_utc must be UTC")
        except ValueError:
            failures.append(f"metadata.generated_at_utc is invalid: {generated_at}")
    report_commit = metadata.get("git_commit")
    if not is_git_commit(report_commit):
        failures.append(f"metadata.git_commit is invalid: {report_commit}")
    else:
        current_commit = git_commit()
        if report_commit != current_commit:
            try:
                changed_paths = git_changed_paths(report_commit, current_commit)
            except subprocess.CalledProcessError:
                failures.append(f"metadata.git_commit is not reachable: {report_commit}")
            else:
                compatible_delta = bool(changed_paths) and all(
                    is_external_trial_compatible_path(path) for path in changed_paths
                )
                if not compatible_delta:
                    failures.append(
                        "metadata.git_commit mismatch "
                        f"trial={report_commit} current={current_commit} "
                        f"changed_paths={','.join(changed_paths[:20])}"
                    )
    if metadata.get("git_dirty") is not False:
        failures.append("metadata.git_dirty must be false")
    git_status = metadata.get("git_status")
    if git_status != []:
        failures.append("metadata.git_status must be empty for a clean external trial")
    failures.extend(external_trial_metadata_argv_failures(metadata, trial, report_path))
    return failures


def readiness_report_summary_failures(
    summary: object,
    trial_generated_at: object,
    readiness_report_file: Path | None = None,
) -> list[str]:
    failures = []
    if not isinstance(summary, dict):
        return ["readiness_report must be present for external workflow trial reports"]
    path = summary.get("path")
    if not isinstance(path, str) or not path.strip():
        failures.append("readiness_report.path must be a non-empty string")
    elif not Path(path).is_absolute():
        failures.append("readiness_report.path must be an absolute path")
    size_bytes = summary.get("size_bytes")
    if not isinstance(size_bytes, int) or size_bytes <= 0:
        failures.append("readiness_report.size_bytes must be a positive integer")
    sha256 = summary.get("sha256")
    if not isinstance(sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", sha256):
        failures.append("readiness_report.sha256 must be a SHA-256 digest")
    for field, expected in external_readiness_scope().items():
        if summary.get(field) != expected:
            if field == "final_production_signoff":
                failures.append("readiness_report.final_production_signoff must be false")
            else:
                failures.append(f"readiness_report.{field}={summary.get(field)}")
    generated_at = summary.get("generated_at_utc")
    parsed_readiness_at = None
    if not isinstance(generated_at, str) or not generated_at.strip():
        failures.append("readiness_report.generated_at_utc must be a non-empty string")
    else:
        try:
            parsed_readiness_at = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
            if parsed_readiness_at.tzinfo is None:
                failures.append("readiness_report.generated_at_utc must include timezone")
            elif not is_utc_datetime(parsed_readiness_at):
                failures.append("readiness_report.generated_at_utc must be UTC")
        except ValueError:
            failures.append(f"readiness_report.generated_at_utc is invalid: {generated_at}")
    if parsed_readiness_at is not None and isinstance(trial_generated_at, str):
        try:
            parsed_trial_at = datetime.fromisoformat(trial_generated_at.replace("Z", "+00:00"))
            if (
                parsed_trial_at.tzinfo is not None
                and parsed_readiness_at.tzinfo is not None
                and parsed_readiness_at > parsed_trial_at
            ):
                failures.append("readiness_report.generated_at_utc must be at or before metadata.generated_at_utc")
        except ValueError:
            pass
    for key in ["workspace", "manifest"]:
        value = summary.get(key)
        if not isinstance(value, str) or not value.strip():
            failures.append(f"readiness_report.{key} must be a non-empty string")
        elif not Path(value).is_absolute():
            failures.append(f"readiness_report.{key} must be an absolute path")
    package_name = summary.get("package_name")
    if "package_name" not in summary:
        failures.append("readiness_report.package_name must be present")
    elif package_name is not None:
        if not isinstance(package_name, str) or not package_name.strip():
            failures.append("readiness_report.package_name must be null or a non-empty string")
        elif slugify(package_name) != package_name:
            failures.append("readiness_report.package_name must be a canonical slug")
    if readiness_report_file is not None:
        if not readiness_report_file.is_file():
            failures.append(f"readiness report file does not exist: {readiness_report_file}")
        else:
            if isinstance(size_bytes, int) and size_bytes != readiness_report_file.stat().st_size:
                failures.append("readiness_report.size_bytes must match readiness report file")
            if isinstance(sha256, str) and re.fullmatch(r"[0-9a-f]{64}", sha256):
                if sha256 != sha256_file(readiness_report_file):
                    failures.append("readiness_report.sha256 must match readiness report file")
            try:
                payload = load_json(readiness_report_file)
            except Exception as exc:  # noqa: BLE001 - report exact saved readiness failure.
                failures.append(f"cannot read readiness report file: {type(exc).__name__}: {exc}")
            else:
                expected_fields = {
                    "status": "status",
                    "claim_status": "claim_status",
                    "evidence_scope": "evidence_scope",
                    "final_production_signoff": "final_production_signoff",
                    "generated_at_utc": "generated_at_utc",
                    "workspace": "workspace",
                    "manifest": "manifest",
                    "package_name": "package_name",
                }
                for summary_key, payload_key in expected_fields.items():
                    if summary.get(summary_key) != payload.get(payload_key):
                        failures.append(f"readiness_report.{summary_key} must match readiness report file")
    return failures


def expected_trial_manifest_path(trial: dict) -> Path | None:
    manifest = trial.get("manifest")
    if not isinstance(manifest, str) or not manifest.strip():
        return None
    manifest_path = Path(manifest)
    if manifest_path.is_absolute():
        return manifest_path
    variables = trial.get("variables")
    if isinstance(variables, dict):
        base_dir = variables.get("base_dir")
        if isinstance(base_dir, str) and base_dir.strip():
            return Path(base_dir) / manifest_path
    return manifest_path


def readiness_report_binding_failures(summary: object, trial: dict) -> list[str]:
    failures = []
    if not isinstance(summary, dict):
        return failures
    expected_manifest = expected_trial_manifest_path(trial)
    manifest = summary.get("manifest")
    if expected_manifest is not None and isinstance(manifest, str) and manifest.strip():
        if normalized_path_key(Path(manifest)) != normalized_path_key(expected_manifest):
            failures.append("readiness_report.manifest must match trial manifest")
    workspace = summary.get("workspace")
    if isinstance(workspace, str) and workspace.strip():
        variables = trial.get("variables")
        expected_workspace: Path | None = None
        if isinstance(variables, dict):
            base_dir = variables.get("base_dir")
            if isinstance(base_dir, str) and base_dir.strip():
                expected_workspace = Path(base_dir)
        if expected_workspace is None and expected_manifest is not None:
            expected_workspace = expected_manifest.parent
        if (
            expected_workspace is not None
            and normalized_path_key(Path(workspace)) != normalized_path_key(expected_workspace)
        ):
            failures.append("readiness_report.workspace must match trial workspace")
    return failures


def external_trial_failures(
    trial: dict,
    artifact_root: Path | None = None,
    artifact_resolver=None,
    report_path: Path | None = None,
    readiness_report_file: Path | None = None,
) -> list[str]:
    failures = []
    if trial.get("status") != "PASS":
        failures.append(f"trial status is {trial.get('status')}")
    if trial.get("claim_status") != NON_FINAL_CLAIM_STATUS:
        failures.append(f"trial claim_status={trial.get('claim_status')}")
    if trial.get("evidence_scope") != EXTERNAL_TRIAL_EVIDENCE_SCOPE:
        failures.append(f"trial evidence_scope={trial.get('evidence_scope')}")
    if trial.get("final_production_signoff") is not NON_FINAL_PRODUCTION_SIGNOFF:
        failures.append("trial final_production_signoff must be false")
    failures.extend(external_trial_metadata_failures(trial.get("metadata"), trial, report_path))
    failures.extend(
        readiness_report_summary_failures(
            trial.get("readiness_report"),
            trial.get("metadata", {}).get("generated_at_utc") if isinstance(trial.get("metadata"), dict) else None,
            readiness_report_file=readiness_report_file,
        )
    )
    failures.extend(readiness_report_binding_failures(trial.get("readiness_report"), trial))
    rendered_manifest = trial.get("rendered_manifest")
    if not isinstance(rendered_manifest, dict):
        failures.append("rendered_manifest must be present for external workflow trial reports")
    else:
        import validate_handoff_manifest

        manifest_issues = validate_handoff_manifest.validate_schema(
            rendered_manifest,
            require_downstream_check=True,
            require_external_evidence=True,
        )
        failures.extend(f"rendered_manifest.{issue}" for issue in manifest_issues)
        if rendered_manifest.get("trial_id") != trial.get("trial_id"):
            failures.append("rendered_manifest.trial_id must match trial_id")
        expected_artifact_paths = rendered_manifest_artifacts(rendered_manifest)
        seen_expected_paths = set()
        for path in expected_artifact_paths:
            if path in seen_expected_paths:
                failures.append(f"rendered_manifest artifact path is duplicated: {path}")
            else:
                seen_expected_paths.add(path)
        expected_step_names = rendered_manifest_step_names(rendered_manifest)
        expected_step_commands = dict(rendered_manifest_step_commands(rendered_manifest))
        seen_expected_steps = set()
        for name in expected_step_names:
            if name in seen_expected_steps:
                failures.append(f"rendered_manifest step name is duplicated: {name}")
            else:
                seen_expected_steps.add(name)
    expected_artifact_set = set(seen_expected_paths) if isinstance(rendered_manifest, dict) else None
    expected_step_set = set(seen_expected_steps) if isinstance(rendered_manifest, dict) else None
    expected_step_command_map = expected_step_commands if isinstance(rendered_manifest, dict) else None
    steps = trial.get("steps")
    if not isinstance(steps, list) or not steps:
        failures.append("trial has no steps")
    else:
        observed_step_names = []
        for step in steps:
            if isinstance(step, dict) and isinstance(step.get("name"), str) and step["name"].strip():
                observed_step_names.append(step["name"])
                elapsed = step.get("elapsed_seconds")
                if not isinstance(elapsed, (int, float)) or elapsed < 0:
                    failures.append(f"trial step elapsed_seconds is invalid: {step['name']}")
                if not isinstance(step.get("detail"), str):
                    failures.append(f"trial step detail must be a string: {step['name']}")
            else:
                failures.append("trial step name must be a non-empty string")
        duplicated_steps = sorted(
            name for name in set(observed_step_names) if observed_step_names.count(name) > 1
        )
        for name in duplicated_steps:
            failures.append(f"trial step name is duplicated: {name}")
        if expected_step_set is not None:
            observed_step_set = set(observed_step_names)
            for missing_step in sorted(expected_step_set - observed_step_set):
                failures.append(f"trial step missing rendered_manifest action: {missing_step}")
            for unexpected_step in sorted(observed_step_set - expected_step_set):
                failures.append(f"trial step not declared by rendered_manifest: {unexpected_step}")
        if expected_step_command_map is not None:
            for step in steps:
                if not isinstance(step, dict):
                    continue
                name = step.get("name")
                if name in expected_step_command_map and step.get("command") != expected_step_command_map[name]:
                    failures.append(f"trial step command mismatch: {name}")
        failed_steps = [step.get("name", "<unnamed>") for step in steps if step.get("status") != "PASS"]
        if failed_steps:
            failures.append(f"failed trial steps={','.join(failed_steps)}")
    artifacts = trial.get("artifacts")
    provenance_by_path = {}
    artifact_provenance = trial.get("artifact_provenance")
    if not isinstance(artifact_provenance, list) or not artifact_provenance:
        failures.append("trial artifact_provenance must be a non-empty list")
    else:
        for entry in artifact_provenance:
            if not isinstance(entry, dict):
                failures.append("trial artifact_provenance entries must be objects")
                continue
            path = entry.get("path")
            sha256 = entry.get("sha256")
            size_bytes = entry.get("size_bytes")
            if not isinstance(path, str) or not path.strip():
                failures.append("trial artifact_provenance.path must be a non-empty string")
                continue
            if not isinstance(sha256, str) or len(sha256) != 64:
                failures.append(f"trial artifact_provenance sha256 is invalid: {path}")
            if not isinstance(size_bytes, int) or size_bytes <= 0:
                failures.append(f"trial artifact_provenance size_bytes is invalid: {path}")
            if path in provenance_by_path:
                failures.append(f"trial artifact_provenance path is duplicated: {path}")
            else:
                provenance_by_path[path] = entry
    if not isinstance(artifacts, list) or not artifacts:
        failures.append("trial artifacts must be a non-empty list")
    else:
        root = artifact_root or ROOT
        artifact_paths = set()
        for artifact in artifacts:
            if not isinstance(artifact, str) or not artifact.strip():
                failures.append("trial artifacts must be non-empty strings")
                continue
            if artifact in artifact_paths:
                failures.append(f"trial artifact path is duplicated: {artifact}")
                continue
            artifact_paths.add(artifact)
            artifact_path = artifact_resolver(artifact) if artifact_resolver else resolve_artifact_path(artifact, root)
            if not artifact_path.is_file():
                failures.append(f"trial artifact does not exist: {artifact}")
                continue
            actual_size = artifact_path.stat().st_size
            if actual_size == 0:
                failures.append(f"trial artifact is empty: {artifact}")
            provenance = provenance_by_path.get(artifact)
            if provenance is None:
                failures.append(f"trial artifact missing provenance: {artifact}")
                continue
            if provenance.get("size_bytes") != actual_size:
                failures.append(f"trial artifact size mismatch: {artifact}")
            if provenance.get("sha256") != sha256_file(artifact_path):
                failures.append(f"trial artifact sha256 mismatch: {artifact}")
        for extra_path in sorted(set(provenance_by_path) - artifact_paths):
            failures.append(f"trial artifact_provenance has unlisted artifact: {extra_path}")
        if expected_artifact_set is not None:
            for missing_path in sorted(expected_artifact_set - artifact_paths):
                failures.append(f"trial artifact missing rendered_manifest output: {missing_path}")
            for unexpected_path in sorted(artifact_paths - expected_artifact_set):
                failures.append(f"trial artifact not declared by rendered_manifest: {unexpected_path}")
    evidence = trial.get("external_evidence")
    if not isinstance(evidence, dict):
        failures.append("external_evidence must be present")
        return failures
    if isinstance(rendered_manifest, dict) and rendered_manifest.get("external_evidence") != evidence:
        failures.append("rendered_manifest.external_evidence must match external_evidence")
    required_strings = [
        "lab_or_org",
        "workflow_owner",
        "dataset_name",
        "dataset_source",
        "downstream_workflow",
        "execution_environment",
        "reviewer_name_or_role",
        "reviewed_at_utc",
        "signoff_statement",
    ]
    for key in required_strings:
        value = evidence.get(key)
        if not isinstance(value, str) or not value.strip():
            failures.append(f"external_evidence.{key} must be a non-empty string")
        elif has_placeholder(value):
            failures.append(f"external_evidence.{key} must replace template placeholder text")
    reviewed_at = evidence.get("reviewed_at_utc")
    parsed_reviewed_at = None
    if isinstance(reviewed_at, str) and not has_placeholder(reviewed_at):
        try:
            parsed_reviewed_at = datetime.fromisoformat(reviewed_at)
            if parsed_reviewed_at.tzinfo is None:
                failures.append("external_evidence.reviewed_at_utc must include timezone")
            elif not is_utc_datetime(parsed_reviewed_at):
                failures.append("external_evidence.reviewed_at_utc must be UTC")
        except ValueError:
            failures.append(f"external_evidence.reviewed_at_utc is invalid: {reviewed_at}")
    metadata_generated_at = (
        trial.get("metadata", {}).get("generated_at_utc") if isinstance(trial.get("metadata"), dict) else None
    )
    if parsed_reviewed_at is not None and isinstance(metadata_generated_at, str):
        try:
            parsed_generated_at = datetime.fromisoformat(metadata_generated_at)
            if (
                parsed_reviewed_at.tzinfo is not None
                and parsed_generated_at.tzinfo is not None
                and parsed_reviewed_at < parsed_generated_at
            ):
                failures.append("external_evidence.reviewed_at_utc must be at or after metadata.generated_at_utc")
        except ValueError:
            pass
    criteria = evidence.get("acceptance_criteria")
    if not isinstance(criteria, list) or not criteria or not all(
        isinstance(item, str) and item.strip() for item in criteria
    ):
        failures.append("external_evidence.acceptance_criteria must be a non-empty string list")
    else:
        if len(criteria) < MIN_EXTERNAL_ACCEPTANCE_CRITERIA:
            failures.append(
                f"external_evidence.acceptance_criteria must contain at least {MIN_EXTERNAL_ACCEPTANCE_CRITERIA} items"
            )
        for index, criterion in enumerate(criteria):
            if has_placeholder(criterion):
                failures.append(
                    f"external_evidence.acceptance_criteria[{index}] must replace template placeholder text"
                )
    if evidence.get("manual_csv_editing") is not False:
        failures.append("external_evidence.manual_csv_editing must be false")
    return failures


def external_trial_pass_detail(trial: dict) -> str:
    evidence = trial.get("external_evidence") if isinstance(trial.get("external_evidence"), dict) else {}
    metadata = trial.get("metadata") if isinstance(trial.get("metadata"), dict) else {}
    return (
        "External workflow trial PASS: "
        f"trial_id={trial.get('trial_id')}, "
        f"lab_or_org={evidence.get('lab_or_org')}, "
        f"trial_commit={metadata.get('git_commit', '')[:12]}, "
        f"generated_at_utc={metadata.get('generated_at_utc')}, "
        f"steps={len(trial.get('steps') or [])}, "
        f"artifacts={len(trial.get('artifacts') or [])}"
    )


def validate_external_trial_report(path: Path, artifact_root: Path | None) -> Gate:
    started = time.perf_counter()
    try:
        trial = load_json(path)
        readiness_report = trial.get("readiness_report")
        readiness_report_file = (
            Path(readiness_report["path"])
            if isinstance(readiness_report, dict) and isinstance(readiness_report.get("path"), str)
            else None
        )
        failures = external_trial_failures(
            trial,
            artifact_root,
            report_path=path,
            readiness_report_file=readiness_report_file,
        )
        status = "FAIL" if failures else "PASS"
        detail = "; ".join(failures) if failures else external_trial_pass_detail(trial)
    except Exception as exc:  # noqa: BLE001 - report exact release gate failure.
        status = "FAIL"
        detail = f"{type(exc).__name__}: {exc}"
    return Gate(
        name="Validate external L4 workflow trial report",
        command=None,
        status=status,
        elapsed_seconds=time.perf_counter() - started,
        detail=detail,
    )


def package_path_is_safe(package_path: object) -> bool:
    if not isinstance(package_path, str) or not package_path.strip():
        return False
    path = Path(package_path)
    return not path.is_absolute() and ".." not in path.parts and "." not in path.parts


def package_zip_sha256_issues(path: Path, zip_name: str) -> tuple[str | None, list[str]]:
    parts = path.read_text(encoding="utf-8").split()
    if not parts:
        return None, [f"package zip sha256 file is empty: {path.name}"]
    issues = []
    digest = parts[0]
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        issues.append(f"package zip sha256 digest is invalid: {path.name}")
    if len(parts) < 2:
        issues.append(f"package zip sha256 file missing zip name: {path.name}")
    elif Path(parts[1]).name != zip_name:
        issues.append(f"package zip sha256 target mismatch for {zip_name}: {parts[1]}")
    return digest, issues


def external_package_readme_common_required_fields(trial: dict, artifact_manifest: dict) -> dict[str, str]:
    evidence = trial.get("external_evidence") if isinstance(trial.get("external_evidence"), dict) else {}
    metadata = trial.get("metadata") if isinstance(trial.get("metadata"), dict) else {}
    fields = {
        "claim_status": f"- claim_status: `{artifact_manifest.get('claim_status')}`",
        "evidence_scope": f"- evidence_scope: `{artifact_manifest.get('evidence_scope')}`",
        "final_production_signoff": (
            f"- final_production_signoff: `{artifact_manifest.get('final_production_signoff')}`"
        ),
        "trial_id": f"- trial_id: `{trial.get('trial_id')}`",
        "trial_status": f"- trial_status: `{trial.get('status')}`",
        "lab_or_org": f"- lab_or_org: `{evidence.get('lab_or_org')}`",
        "workflow_owner": f"- workflow_owner: `{evidence.get('workflow_owner')}`",
        "dataset_name": f"- dataset_name: `{evidence.get('dataset_name')}`",
        "dataset_source": f"- dataset_source: `{evidence.get('dataset_source')}`",
        "downstream_workflow": f"- downstream_workflow: `{evidence.get('downstream_workflow')}`",
        "execution_environment": f"- execution_environment: `{evidence.get('execution_environment')}`",
        "reviewer_name_or_role": f"- reviewer_name_or_role: `{evidence.get('reviewer_name_or_role')}`",
        "reviewed_at_utc": f"- reviewed_at_utc: `{evidence.get('reviewed_at_utc')}`",
        "signoff_statement": f"- signoff_statement: `{evidence.get('signoff_statement')}`",
        "manual_csv_editing": f"- manual_csv_editing: `{evidence.get('manual_csv_editing')}`",
        "trial_git_commit": f"- trial_git_commit: `{metadata.get('git_commit')}`",
        "trial_generated_at_utc": f"- trial_generated_at_utc: `{metadata.get('generated_at_utc')}`",
        "readiness_status": f"- readiness_status: `{trial.get('readiness_report', {}).get('status')}`",
        "readiness_claim_status": (
            f"- readiness_claim_status: `{trial.get('readiness_report', {}).get('claim_status')}`"
        ),
        "readiness_evidence_scope": (
            f"- readiness_evidence_scope: `{trial.get('readiness_report', {}).get('evidence_scope')}`"
        ),
        "readiness_final_production_signoff": (
            "- readiness_final_production_signoff: "
            f"`{trial.get('readiness_report', {}).get('final_production_signoff')}`"
        ),
        "readiness_generated_at_utc": (
            f"- readiness_generated_at_utc: `{trial.get('readiness_report', {}).get('generated_at_utc')}`"
        ),
        "readiness_sha256": f"- readiness_sha256: `{trial.get('readiness_report', {}).get('sha256')}`",
        "readiness_package_name": (
            f"- readiness_package_name: `{trial.get('readiness_report', {}).get('package_name')}`"
        ),
        "readiness_workspace": f"- readiness_workspace: `{trial.get('readiness_report', {}).get('workspace')}`",
        "readiness_manifest": f"- readiness_manifest: `{trial.get('readiness_report', {}).get('manifest')}`",
        "packaged_at_utc": f"- packaged_at_utc: `{artifact_manifest.get('packaged_at_utc')}`",
        "validation_detail_text": str(artifact_manifest.get("validation_detail")),
    }
    fields.update(external_package_readme_contract_fields(trial.get("rendered_manifest")))
    return fields


def external_package_readme_contract_fields(manifest: object) -> dict[str, str]:
    if not isinstance(manifest, dict):
        return {}
    fields = {
        "manifest_morphojet_objects_csv": (
            f"- morphojet_objects_csv: `{manifest.get('morphojet_objects_csv')}`"
        ),
        "manifest_required_object_metadata_columns": (
            "- required_object_metadata_columns: "
            f"`{format_manifest_list(manifest.get('required_object_metadata_columns', []))}`"
        ),
    }
    top_level_metadata = manifest.get("required_object_metadata_columns", [])
    for index, export in enumerate(manifest.get("exports", [])):
        if not isinstance(export, dict):
            continue
        metadata_columns = export.get("required_object_metadata_columns", top_level_metadata)
        fields[f"manifest_export_{index}_name"] = f"- export[{index}].name: `{export.get('name')}`"
        fields[f"manifest_export_{index}_object_set"] = (
            f"- export[{index}].object_set: `{export.get('object_set')}`"
        )
        fields[f"manifest_export_{index}_channels"] = (
            f"- export[{index}].channels: `{format_manifest_list(export.get('channels', []))}`"
        )
        fields[f"manifest_export_{index}_metadata_columns"] = (
            "- export[{}].required_object_metadata_columns: `{}`".format(
                index,
                format_manifest_list(metadata_columns),
            )
        )
        fields[f"manifest_export_{index}_out_csv"] = f"- export[{index}].out_csv: `{export.get('out_csv')}`"
        for key in ["expected_cellprofiler_csv", "comparison_report", "comparison_json"]:
            if key in export:
                fields[f"manifest_export_{index}_{key}"] = (
                    f"- export[{index}].{key}: `{export.get(key)}`"
                )
    return fields


def format_manifest_list(value: object) -> str:
    if not isinstance(value, list):
        return "none"
    items = [str(item) for item in value if isinstance(item, str) and item.strip()]
    return ", ".join(items) if items else "none"


def external_package_readme_failures(readme: str, trial: dict, artifact_manifest: dict) -> list[str]:
    evidence = trial.get("external_evidence") if isinstance(trial.get("external_evidence"), dict) else {}
    required_fields = {
        **external_package_readme_common_required_fields(trial, artifact_manifest),
        "language_switch": "Language: English | [简体中文](README.zh-CN.md)",
        "validation_detail": "This package was created only after the external trial report passed",
        "not_final_signoff": "not a final production signoff by itself",
        "reviewer_entrypoint": "Chinese-community reviewers can use `README.zh-CN.md` as a first-class review entrypoint",
        "package_verifier": "`verify_external_evidence_package.py`",
        "stable_release_report": "saved stable-release verifier report",
        "revalidation_command": "python3 benchmark/release_gate.py --external-trial-json",
    }
    failures = []
    for name, snippet in required_fields.items():
        if snippet not in readme:
            failures.append(f"package README missing signoff field: {name}")
    criteria = evidence.get("acceptance_criteria")
    if isinstance(criteria, list):
        for index, criterion in enumerate(criteria):
            if isinstance(criterion, str) and criterion.strip() and f"- {criterion}" not in readme:
                failures.append(f"package README missing acceptance criterion: {index}")
    return failures


def external_package_chinese_readme_failures(readme: str, trial: dict, artifact_manifest: dict) -> list[str]:
    evidence = trial.get("external_evidence") if isinstance(trial.get("external_evidence"), dict) else {}
    required_fields = {
        **external_package_readme_common_required_fields(trial, artifact_manifest),
        "title": "# 外部 L4 试验证据包",
        "language_switch": "Language: [English](README.md) | 简体中文",
        "validation_detail": "这个 evidence package 只在外部 trial report 通过",
        "not_final_signoff": "它本身不是最终生产签核",
        "reviewer_entrypoint": "中文社区 reviewer 可以把 `README.zh-CN.md` 作为这个 evidence package 的一等复核入口",
        "package_verifier": "`verify_external_evidence_package.py`",
        "stable_release_report": "saved stable-release verifier report",
        "revalidation_command": "python3 benchmark/release_gate.py --external-trial-json",
    }
    failures = []
    for name, snippet in required_fields.items():
        if snippet not in readme:
            failures.append(f"package Chinese README missing signoff field: {name}")
    criteria = evidence.get("acceptance_criteria")
    if isinstance(criteria, list):
        for index, criterion in enumerate(criteria):
            if isinstance(criterion, str) and criterion.strip() and f"- {criterion}" not in readme:
                failures.append(f"package Chinese README missing acceptance criterion: {index}")
    return failures


def external_package_review_file_failures(package_dir: Path, artifact_manifest: dict) -> list[str]:
    failures = []
    expected_review_files = {
        "handoff_trial.json",
        "readiness.json",
        "rendered_manifest.json",
        "external_evidence.json",
        "README.md",
        "README.zh-CN.md",
    }
    review_files = artifact_manifest.get("review_files")
    if not isinstance(review_files, list) or not review_files:
        return ["package artifact_manifest.review_files must be a non-empty list"]
    entries_by_path = {}
    for entry in review_files:
        if not isinstance(entry, dict):
            failures.append("package artifact_manifest review_file entries must be objects")
            continue
        review_path = entry.get("path")
        if not package_path_is_safe(review_path):
            failures.append(f"package review_file path is unsafe: {review_path}")
            continue
        if review_path in entries_by_path:
            failures.append(f"package review_file path is duplicated: {review_path}")
        entries_by_path[review_path] = entry
        file_path = package_dir / review_path
        if not file_path.is_file():
            failures.append(f"package review_file is missing: {review_path}")
            continue
        if entry.get("size_bytes") != file_path.stat().st_size:
            failures.append(f"package review_file size mismatch: {review_path}")
        if entry.get("sha256") != sha256_file(file_path):
            failures.append(f"package review_file sha256 mismatch: {review_path}")
    observed_paths = set(entries_by_path)
    for missing_path in sorted(expected_review_files - observed_paths):
        failures.append(f"package artifact_manifest.review_files missing required file: {missing_path}")
    for extra_path in sorted(observed_paths - expected_review_files):
        failures.append(f"package artifact_manifest.review_files has unexpected file: {extra_path}")
    return failures


def package_artifact_manifest_argv_failures(
    artifact_manifest: dict,
    package_dir: Path,
    trial_json: Path | None,
) -> list[str]:
    failures = []
    argv = artifact_manifest.get("argv")
    if not isinstance(argv, list) or not argv or not all(isinstance(item, str) and item for item in argv):
        return ["package artifact_manifest.argv must be a non-empty string list"]
    if argv[0] != "benchmark/package_external_trial.py":
        failures.append(f"package artifact_manifest.argv[0]={argv[0]}")
    if argv.count("--overwrite") > 1:
        failures.append("package artifact_manifest.argv has duplicate --overwrite")
    expected_values = [
        ("--trial-json", artifact_manifest.get("trial_json")),
        ("--trial-root", artifact_manifest.get("trial_root")),
        ("--out-dir", str(package_dir.parent)),
        ("--package-name", package_dir.name),
    ]
    if trial_json is not None:
        expected_values[0] = ("--trial-json", str(trial_json.resolve()))
    expected_by_flag = dict(expected_values)
    for flag, expected in expected_values:
        values = argv_values(argv, flag)
        if len(values) > 1:
            failures.append(f"package artifact_manifest.argv has duplicate {flag}")
        if not values:
            failures.append(f"package artifact_manifest.argv missing {flag}")
        for value in values:
            if value is None:
                failures.append(f"package artifact_manifest.argv {flag} must include a value")
            elif flag in {"--trial-json", "--trial-root", "--out-dir"}:
                if not isinstance(expected, str) or normalized_path_key(Path(value)) != normalized_path_key(Path(expected)):
                    failures.append(f"package artifact_manifest.argv {flag} must match artifact_manifest")
            elif value != expected:
                failures.append(f"package artifact_manifest.argv {flag} must match package name")
    canonical_argv = [
        "benchmark/package_external_trial.py",
        "--trial-json",
        normalized_path_key(Path(str(expected_by_flag["--trial-json"]))),
        "--trial-root",
        normalized_path_key(Path(str(expected_by_flag["--trial-root"]))),
        "--out-dir",
        normalized_path_key(Path(str(expected_by_flag["--out-dir"]))),
        "--package-name",
        str(expected_by_flag["--package-name"]),
    ]
    normalized_argv = normalize_package_artifact_manifest_argv(argv)
    if normalized_argv not in [canonical_argv, [*canonical_argv, "--overwrite"]]:
        failures.append("package artifact_manifest.argv must match canonical packager argv")
    return failures


def normalize_package_artifact_manifest_argv(argv: list[str]) -> list[str]:
    normalized = []
    path_flags = {"--trial-json", "--trial-root", "--out-dir"}
    index = 0
    while index < len(argv):
        item = argv[index]
        normalized.append(item)
        if item in path_flags and index + 1 < len(argv) and not argv[index + 1].startswith("--"):
            normalized.append(normalized_path_key(Path(argv[index + 1])))
            index += 2
            continue
        index += 1
    return normalized


def validate_external_evidence_package(package_dir: Path, trial_json: Path | None) -> Gate:
    started = time.perf_counter()
    try:
        package_dir = package_dir.resolve()
        failures = []
        if not package_dir.is_dir():
            failures.append(f"external evidence package dir does not exist: {package_dir}")
            raise ValueError("; ".join(failures))
        trial_path = package_dir / "handoff_trial.json"
        readiness_path = package_dir / "readiness.json"
        rendered_manifest_path = package_dir / "rendered_manifest.json"
        external_evidence_path = package_dir / "external_evidence.json"
        artifact_manifest_path = package_dir / "artifact_manifest.json"
        readme_path = package_dir / "README.md"
        readme_zh_path = package_dir / "README.zh-CN.md"
        for required_path in [
            trial_path,
            readiness_path,
            rendered_manifest_path,
            external_evidence_path,
            artifact_manifest_path,
            readme_path,
            readme_zh_path,
        ]:
            if not required_path.is_file():
                failures.append(f"package missing file: {required_path.name}")
        if failures:
            raise ValueError("; ".join(failures))

        trial = load_json(trial_path)
        rendered_manifest = load_json(rendered_manifest_path)
        external_evidence = load_json(external_evidence_path)
        artifact_manifest = load_json(artifact_manifest_path)
        readme = readme_path.read_text(encoding="utf-8")
        readme_zh = readme_zh_path.read_text(encoding="utf-8")
        if trial_json is not None and sha256_file(trial_path) != sha256_file(trial_json):
            failures.append("package handoff_trial.json does not match --external-trial-json")
        if artifact_manifest.get("schema_version") != 1:
            failures.append(f"package artifact_manifest.schema_version={artifact_manifest.get('schema_version')}")
        if artifact_manifest.get("generator") != "benchmark/package_external_trial.py":
            failures.append(f"package artifact_manifest.generator={artifact_manifest.get('generator')}")
        for field, expected in non_final_claim_scope(EXTERNAL_PACKAGE_EVIDENCE_SCOPE).items():
            if artifact_manifest.get(field) != expected:
                if field == "final_production_signoff":
                    failures.append("package artifact_manifest.final_production_signoff must be false")
                else:
                    failures.append(f"package artifact_manifest.{field}={artifact_manifest.get(field)}")
        failures.extend(package_artifact_manifest_argv_failures(artifact_manifest, package_dir, trial_json))
        packaged_at = artifact_manifest.get("packaged_at_utc")
        if not isinstance(packaged_at, str) or not packaged_at.strip():
            failures.append("package artifact_manifest.packaged_at_utc must be a non-empty string")
        else:
            try:
                parsed_packaged_at = datetime.fromisoformat(packaged_at)
                if parsed_packaged_at.tzinfo is None:
                    failures.append("package artifact_manifest.packaged_at_utc must include timezone")
                elif not is_utc_datetime(parsed_packaged_at):
                    failures.append("package artifact_manifest.packaged_at_utc must be UTC")
            except ValueError:
                failures.append(f"package artifact_manifest.packaged_at_utc is invalid: {packaged_at}")
        if artifact_manifest.get("trial_id") != trial.get("trial_id"):
            failures.append("package artifact_manifest.trial_id must match trial_id")
        if artifact_manifest.get("readiness_report") != trial.get("readiness_report"):
            failures.append("package artifact_manifest.readiness_report must match trial readiness_report")
        if artifact_manifest.get("trial_claim_status") != NON_FINAL_CLAIM_STATUS:
            failures.append(
                f"package artifact_manifest.trial_claim_status={artifact_manifest.get('trial_claim_status')}"
            )
        if artifact_manifest.get("trial_evidence_scope") != EXTERNAL_TRIAL_EVIDENCE_SCOPE:
            failures.append(
                f"package artifact_manifest.trial_evidence_scope={artifact_manifest.get('trial_evidence_scope')}"
            )
        if artifact_manifest.get("trial_final_production_signoff") is not NON_FINAL_PRODUCTION_SIGNOFF:
            failures.append("package artifact_manifest.trial_final_production_signoff must be false")
        if artifact_manifest.get("trial_claim_status") != trial.get("claim_status"):
            failures.append("package artifact_manifest.trial_claim_status must match trial claim_status")
        if artifact_manifest.get("trial_evidence_scope") != trial.get("evidence_scope"):
            failures.append("package artifact_manifest.trial_evidence_scope must match trial evidence_scope")
        if artifact_manifest.get("trial_final_production_signoff") != trial.get("final_production_signoff"):
            failures.append(
                "package artifact_manifest.trial_final_production_signoff must match trial final_production_signoff"
            )
        validation_detail = artifact_manifest.get("validation_detail")
        if not isinstance(validation_detail, str) or not validation_detail.strip():
            failures.append("package artifact_manifest.validation_detail must be a non-empty string")
        elif validation_detail != external_trial_pass_detail(trial):
            failures.append("package artifact_manifest.validation_detail must match external trial PASS detail")
        manifest_trial_json = artifact_manifest.get("trial_json")
        if not isinstance(manifest_trial_json, str) or not Path(manifest_trial_json).is_absolute():
            failures.append("package artifact_manifest.trial_json must be an absolute path")
        elif trial_json is not None and Path(manifest_trial_json) != trial_json.resolve():
            failures.append("package artifact_manifest.trial_json must match --external-trial-json")
        elif Path(manifest_trial_json).name != trial_path.name:
            failures.append("package artifact_manifest.trial_json must match packaged handoff_trial.json")
        manifest_trial_json_size = artifact_manifest.get("trial_json_size_bytes")
        if not isinstance(manifest_trial_json_size, int) or manifest_trial_json_size <= 0:
            failures.append("package artifact_manifest.trial_json_size_bytes must be a positive integer")
        elif manifest_trial_json_size != trial_path.stat().st_size:
            failures.append("package artifact_manifest.trial_json_size_bytes must match packaged handoff_trial.json")
        manifest_trial_json_sha = artifact_manifest.get("trial_json_sha256")
        if not isinstance(manifest_trial_json_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", manifest_trial_json_sha):
            failures.append("package artifact_manifest.trial_json_sha256 must be a SHA-256 digest")
        elif manifest_trial_json_sha != sha256_file(trial_path):
            failures.append("package artifact_manifest.trial_json_sha256 must match packaged handoff_trial.json")
        if trial_json is not None:
            if isinstance(manifest_trial_json_size, int) and manifest_trial_json_size != trial_json.stat().st_size:
                failures.append("package artifact_manifest.trial_json_size_bytes must match --external-trial-json")
            if (
                isinstance(manifest_trial_json_sha, str)
                and re.fullmatch(r"[0-9a-f]{64}", manifest_trial_json_sha)
                and manifest_trial_json_sha != sha256_file(trial_json)
            ):
                failures.append("package artifact_manifest.trial_json_sha256 must match --external-trial-json")
        manifest_trial_root = artifact_manifest.get("trial_root")
        if not isinstance(manifest_trial_root, str) or not Path(manifest_trial_root).is_absolute():
            failures.append("package artifact_manifest.trial_root must be an absolute path")
        else:
            manifest_trial_root_path = Path(manifest_trial_root)
            trial_artifacts_for_root = trial.get("artifacts") if isinstance(trial.get("artifacts"), list) else []
            if trial_artifacts_for_root and not all(
                resolve_artifact_path(artifact, manifest_trial_root_path).is_file()
                for artifact in trial_artifacts_for_root
                if isinstance(artifact, str)
            ):
                failures.append("package artifact_manifest.trial_root does not resolve trial artifacts")
        if rendered_manifest != trial.get("rendered_manifest"):
            failures.append("package rendered_manifest.json must match trial rendered_manifest")
        if external_evidence != trial.get("external_evidence"):
            failures.append("package external_evidence.json must match trial external_evidence")
        failures.extend(external_package_review_file_failures(package_dir, artifact_manifest))
        failures.extend(external_package_readme_failures(readme, trial, artifact_manifest))
        failures.extend(external_package_chinese_readme_failures(readme_zh, trial, artifact_manifest))
        manifest_artifacts = artifact_manifest.get("artifacts")
        if not isinstance(manifest_artifacts, list) or not manifest_artifacts:
            failures.append("package artifact_manifest.artifacts must be a non-empty list")
            manifest_artifacts = []
        entries_by_source = {}
        entries_by_package_path = {}
        for entry in manifest_artifacts:
            if not isinstance(entry, dict):
                failures.append("package artifact_manifest artifact entries must be objects")
                continue
            source_path = entry.get("source_path")
            package_path = entry.get("package_path")
            if not isinstance(source_path, str) or not source_path.strip():
                failures.append("package artifact source_path must be a non-empty string")
                continue
            if source_path in entries_by_source:
                failures.append(f"package artifact source_path is duplicated: {source_path}")
            entries_by_source[source_path] = entry
            if not package_path_is_safe(package_path):
                failures.append(f"package artifact package_path is unsafe: {source_path}")
                continue
            if package_path in entries_by_package_path:
                failures.append(f"package artifact package_path is duplicated: {package_path}")
            entries_by_package_path[package_path] = entry
            packaged_file = (package_dir / package_path).resolve()
            try:
                packaged_file.relative_to(package_dir)
            except ValueError:
                failures.append(f"package artifact escapes package dir: {source_path}")
                continue
            if not packaged_file.is_file():
                failures.append(f"package artifact file is missing: {source_path}")
                continue
            if packaged_file.stat().st_size == 0:
                failures.append(f"package artifact file is empty: {source_path}")
            if entry.get("size_bytes") != packaged_file.stat().st_size:
                failures.append(f"package artifact size mismatch: {source_path}")
            if entry.get("sha256") != sha256_file(packaged_file):
                failures.append(f"package artifact sha256 mismatch: {source_path}")

        def resolve_packaged_artifact(artifact: str) -> Path:
            entry = entries_by_source.get(artifact)
            if not isinstance(entry, dict) or not package_path_is_safe(entry.get("package_path")):
                return package_dir / "__missing_artifact__"
            return package_dir / entry["package_path"]

        failures.extend(
            external_trial_failures(
                trial,
                artifact_resolver=resolve_packaged_artifact,
                readiness_report_file=readiness_path,
            )
        )
        trial_artifacts = trial.get("artifacts") if isinstance(trial.get("artifacts"), list) else []
        for missing_source in sorted(set(trial_artifacts) - set(entries_by_source)):
            failures.append(f"package artifact_manifest missing trial artifact: {missing_source}")
        for extra_source in sorted(set(entries_by_source) - set(trial_artifacts)):
            failures.append(f"package artifact_manifest has unlisted trial artifact: {extra_source}")

        zip_path = package_dir.parent / f"{package_dir.name}.zip"
        sha_path = package_dir.parent / f"{package_dir.name}.zip.sha256"
        if not zip_path.is_file():
            failures.append(f"package zip is missing: {zip_path.name}")
        if not sha_path.is_file():
            failures.append(f"package zip sha256 file is missing: {sha_path.name}")
        if zip_path.is_file() and sha_path.is_file():
            expected_zip_hash, checksum_failures = package_zip_sha256_issues(sha_path, zip_path.name)
            failures.extend(checksum_failures)
            if expected_zip_hash != sha256_file(zip_path):
                failures.append(f"package zip sha256 mismatch: {zip_path.name}")
            try:
                with zipfile.ZipFile(zip_path) as archive:
                    zip_names = archive.namelist()
                    names = set(zip_names)
                required_zip_entries = {
                    f"{package_dir.name}/artifact_manifest.json",
                }
                review_files = artifact_manifest.get("review_files")
                if isinstance(review_files, list):
                    for entry in review_files:
                        if isinstance(entry, dict) and package_path_is_safe(entry.get("path")):
                            required_zip_entries.add(f"{package_dir.name}/{entry['path']}")
                for entry in manifest_artifacts:
                    if isinstance(entry, dict) and package_path_is_safe(entry.get("package_path")):
                        required_zip_entries.add(f"{package_dir.name}/{entry['package_path']}")
                duplicated_zip_entries = sorted(name for name in names if zip_names.count(name) > 1)
                for duplicated_name in duplicated_zip_entries:
                    failures.append(f"package zip entry is duplicated: {duplicated_name}")
                for required_name in sorted(required_zip_entries):
                    if required_name not in names:
                        failures.append(f"package zip missing entry: {required_name}")
                    else:
                        package_file = package_dir.parent / required_name
                        with zipfile.ZipFile(zip_path) as archive:
                            if package_file.is_file() and archive.read(required_name) != package_file.read_bytes():
                                failures.append(f"package zip entry content mismatch: {required_name}")
                for unexpected_name in sorted(names - required_zip_entries):
                    failures.append(f"package zip has unexpected entry: {unexpected_name}")
            except zipfile.BadZipFile:
                failures.append(f"package zip is invalid: {zip_path.name}")

        status = "FAIL" if failures else "PASS"
        detail = "; ".join(failures) if failures else (
            "External L4 evidence package PASS: "
            f"trial_id={trial.get('trial_id')}, "
            f"package={package_dir}, "
            f"artifacts={len(manifest_artifacts)}, "
            f"zip={zip_path.name}"
        )
    except Exception as exc:  # noqa: BLE001 - report exact release gate failure.
        status = "FAIL"
        detail = f"{type(exc).__name__}: {exc}"
    return Gate(
        name="Validate external L4 evidence package",
        command=None,
        status=status,
        elapsed_seconds=time.perf_counter() - started,
        detail=detail,
    )


def local_release_archive_name(version: str) -> str:
    import platform

    system = platform.system().lower()
    release_os = "macos" if system == "darwin" else system
    return f"morphojet-{version}-{release_os}-{platform.machine()}.tar.gz"


def git_commit() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    return completed.stdout.strip()


def git_status_porcelain() -> list[str]:
    completed = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    return [line for line in completed.stdout.splitlines() if line]


def git_changed_paths(old_commit: str, new_commit: str) -> list[str]:
    completed = subprocess.run(
        ["git", "diff", "--name-only", f"{old_commit}..{new_commit}"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    return [line for line in completed.stdout.splitlines() if line]


def is_doc_path(path: str) -> bool:
    return path == "README.md" or (
        "/" not in path and path.startswith("README.") and path.endswith(".md")
    ) or path.startswith("docs/")


def is_l3_provenance_compatible_path(path: str) -> bool:
    return (
        is_doc_path(path)
        or path == ".github/workflows/cellbindb-l3.yml"
        or path == ".github/workflows/external-l4-rehearsal.yml"
        or path.startswith("tests/")
        or path == "benchmark/audit_production_evidence.py"
        or path == "benchmark/check_external_l4_readiness.py"
        or path == "benchmark/inspect_cellbindb_direct_masks.py"
        or path == "benchmark/release_gate.py"
        or path == "benchmark/build_release_archive.py"
        or path == "benchmark/handoff/external_lab_template.json"
        or path == "benchmark/package_external_trial.py"
        or path == "benchmark/prepare_external_l4_trial.py"
        or path == "benchmark/run_handoff_trial.py"
        or path == "benchmark/run_external_l4_rehearsal.py"
        or path == "benchmark/run_production_gate.py"
        or path == "benchmark/triage_oracle_candidates.py"
        or path == "benchmark/validate_claim_language.py"
        or path == "benchmark/validate_handoff_manifest.py"
        or path == "benchmark/verify_github_release.py"
        or path == "benchmark/verify_github_workflows.py"
        or path == "benchmark/verify_external_trial_report.py"
        or path == "benchmark/verify_external_evidence_package.py"
        or path == "benchmark/verify_release_gate_report.py"
        or path == "benchmark/verify_release_archive.py"
    )


def is_external_trial_compatible_path(path: str) -> bool:
    return (
        is_doc_path(path)
        or path == ".github/workflows/cellbindb-l3.yml"
        or path == ".github/workflows/external-l4-rehearsal.yml"
        or path.startswith("tests/")
        or path == "benchmark/audit_production_evidence.py"
        or path == "benchmark/check_external_l4_readiness.py"
        or path == "benchmark/inspect_cellbindb_direct_masks.py"
        or path == "benchmark/release_gate.py"
        or path == "benchmark/handoff/external_lab_template.json"
        or path == "benchmark/package_external_trial.py"
        or path == "benchmark/prepare_external_l4_trial.py"
        or path == "benchmark/run_external_l4_rehearsal.py"
        or path == "benchmark/run_production_gate.py"
        or path == "benchmark/triage_oracle_candidates.py"
        or path == "benchmark/validate_claim_language.py"
        or path == "benchmark/validate_handoff_manifest.py"
        or path == "benchmark/verify_github_release.py"
        or path == "benchmark/verify_github_workflows.py"
        or path == "benchmark/verify_external_trial_report.py"
        or path == "benchmark/verify_external_evidence_package.py"
        or path == "benchmark/verify_release_gate_report.py"
        or path == "benchmark/verify_release_archive.py"
    )


def validate_clean_git_worktree(status_lines: list[str]) -> Gate:
    detail = "git worktree clean"
    status = "PASS"
    if status_lines:
        status = "FAIL"
        detail = "dirty git worktree:\n" + "\n".join(status_lines[:50])
        if len(status_lines) > 50:
            detail += f"\n... {len(status_lines) - 50} more entries"
    return Gate(
        name="Require clean git worktree",
        command=["git", "status", "--porcelain"],
        status=status,
        elapsed_seconds=0.0,
        detail=detail,
    )


def gate_status(gates: list[Gate], name: str) -> str | None:
    for gate in gates:
        if gate.name == name:
            return gate.status
    return None


def production_audit_status(gates: list[Gate], name: str) -> str:
    status = gate_status(gates, name)
    if status is None:
        return PRODUCTION_AUDIT_MISSING_STATUS
    return status


def combined_production_audit_status(gates: list[Gate], names: list[str], enabled: bool) -> str:
    if not enabled:
        return PRODUCTION_AUDIT_MISSING_STATUS
    statuses = [production_audit_status(gates, name) for name in names]
    if all(status == PRODUCTION_AUDIT_PASS_STATUS for status in statuses):
        return PRODUCTION_AUDIT_PASS_STATUS
    if any(status == PRODUCTION_AUDIT_FAIL_STATUS for status in statuses):
        return PRODUCTION_AUDIT_FAIL_STATUS
    return PRODUCTION_AUDIT_MISSING_STATUS


def build_production_claim_audit(args: argparse.Namespace, gates: list[Gate], metadata: dict) -> dict:
    standard_statuses = [production_audit_status(gates, name) for name in PRODUCTION_STANDARD_GATE_NAMES]
    checks = [
        {
            "name": "clean_git_worktree",
            "status": production_audit_status(gates, "Require clean git worktree")
            if args.require_clean_git
            else PRODUCTION_AUDIT_MISSING_STATUS,
            "detail": "Release or production-readiness reports should run with --require-clean-git.",
        },
        {
            "name": "standard_code_and_artifact_gates",
            "status": PRODUCTION_AUDIT_PASS_STATUS
            if all(status == PRODUCTION_AUDIT_PASS_STATUS for status in standard_statuses)
            else PRODUCTION_AUDIT_FAIL_STATUS,
            "detail": "Standard Rust, Python, manifest, direct-mask, L3 artifact, workflow bridge, and handoff gates.",
        },
        {
            "name": "github_actions_workflow_verification",
            "status": production_audit_status(gates, "Verify saved GitHub Actions workflow report")
            if args.github_workflow_verification_report
            else PRODUCTION_AUDIT_MISSING_STATUS,
            "detail": (
                "Requires a saved GitHub Actions workflow verification report for the final commit, "
                "repo, branch, and required workflows."
            ),
        },
        {
            "name": "l3_provenance_hashes",
            "status": production_audit_status(gates, "Validate CellBinDB L3 provenance")
            if args.require_l3_provenance
            else PRODUCTION_AUDIT_MISSING_STATUS,
            "detail": "Production-readiness claims should run with --require-l3-provenance.",
        },
        {
            "name": "external_l4_workflow_trial",
            "status": production_audit_status(gates, "Validate external L4 workflow trial report")
            if args.external_trial_json
            else PRODUCTION_AUDIT_MISSING_STATUS,
            "detail": "Requires --external-trial-json from a real no-manual-CSV-edit workflow trial.",
        },
        {
            "name": "external_l4_evidence_package",
            "status": production_audit_status(gates, "Validate external L4 evidence package")
            if args.external_evidence_package_dir
            else PRODUCTION_AUDIT_MISSING_STATUS,
            "detail": "Requires --external-evidence-package-dir from a validated external L4 trial package.",
        },
        {
            "name": "external_l4_saved_reviewer_reports",
            "status": combined_production_audit_status(
                gates,
                [
                    "Verify saved external L4 trial report",
                    "Verify saved external L4 evidence package report",
                    "Verify saved external L4 reviewer report pair",
                ],
                bool(args.external_trial_verification_report)
                and bool(args.external_evidence_package_verification_report),
            ),
            "detail": (
                "Requires saved external trial and evidence-package reviewer reports to be supplied "
                "and re-checked with file hashing, expected commit binding, and matching "
                "external-evidence identity summaries."
            ),
        },
        {
            "name": "stable_github_release",
            "status": production_audit_status(gates, "Verify GitHub release assets")
            if args.verify_github_release and args.github_release_kind == "stable"
            else PRODUCTION_AUDIT_MISSING_STATUS,
            "detail": "Requires --verify-github-release with --github-release-kind stable.",
        },
        {
            "name": "stable_github_release_saved_report",
            "status": production_audit_status(gates, "Verify saved stable GitHub release report")
            if args.github_release_verification_report
            else PRODUCTION_AUDIT_MISSING_STATUS,
            "detail": "Requires a saved stable GitHub release verifier report bound to the final repo and tag.",
        },
        {
            "name": "production_evidence_readiness_audit",
            "status": production_audit_status(gates, "Verify saved production evidence audit report")
            if args.production_evidence_audit_report
            else PRODUCTION_AUDIT_MISSING_STATUS,
            "detail": "Requires a saved production evidence audit report rechecked with file hashing and readiness enforcement.",
        },
    ]
    if [check["name"] for check in checks] != PRODUCTION_AUDIT_CHECK_NAMES:
        raise AssertionError("production audit check order drifted from PRODUCTION_AUDIT_CHECK_NAMES")
    status = (
        PRODUCTION_AUDIT_PASS_STATUS
        if all(check["status"] == PRODUCTION_AUDIT_PASS_STATUS for check in checks)
        else PRODUCTION_AUDIT_INCOMPLETE_STATUS
    )
    missing_or_failed_checks = [
        check["name"] for check in checks if check["status"] != PRODUCTION_AUDIT_PASS_STATUS
    ]
    return {
        "status": status,
        "git_commit": metadata["git_commit"],
        "missing_or_failed_checks": missing_or_failed_checks,
        "checks": checks,
    }


PRODUCTION_CHECKLIST_GUIDANCE = {
    "clean_git_worktree": {
        "evidence": "Release-gate report generated with --require-clean-git and git_dirty=false.",
        "next_action": "Commit or remove local changes, then rerun the final gate with --require-clean-git.",
    },
    "standard_code_and_artifact_gates": {
        "evidence": "Rust, Python, manifest, L3 artifact, workflow bridge, and handoff gates are PASS.",
        "next_action": "Fix the failing standard gate detail, then regenerate the release-gate report.",
    },
    "github_actions_workflow_verification": {
        "evidence": (
            "A saved GitHub Actions workflow verifier report for the final commit showing ci.yml and "
            "external-l4-rehearsal.yml PASS on main."
        ),
        "next_action": (
            "After pushing the final commit, run verify_github_workflows.py, save the JSON report, "
            "and supply --github-workflow-verification-report."
        ),
    },
    "l3_provenance_hashes": {
        "evidence": "CellBinDB L3 provenance exists, was not generated with --skip-cellprofiler, and hashes match.",
        "next_action": "Rerun with --require-l3-provenance after refreshing L3 artifacts when measurement code changed.",
    },
    "external_l4_workflow_trial": {
        "evidence": "A real external handoff_trial.json PASS report with no manual CSV edits and signed L4 evidence.",
        "next_action": (
            "Prepare the workspace, run readiness, then run benchmark/run_handoff_trial.py "
            "with --require-external-evidence and --readiness-report."
        ),
    },
    "external_l4_evidence_package": {
        "evidence": "A package_external_trial.py evidence package bound to the external trial report.",
        "next_action": "Package the accepted external trial and supply --external-evidence-package-dir.",
    },
    "external_l4_saved_reviewer_reports": {
        "evidence": "Saved external trial and evidence-package verifier reports rechecked with file hashing and expected commit binding.",
        "next_action": (
            "Run verify_external_trial_report.py and verify_external_evidence_package.py, then recheck "
            "both saved reports with --verify-report-files --require-report-pass --expect-commit <final-commit>."
        ),
    },
    "stable_github_release": {
        "evidence": "A live non-prerelease GitHub release for the final tag verified from benngaihk/MorphoJet.",
        "next_action": "After L4 evidence is accepted, publish the stable tag and verify it with --github-release-kind stable.",
    },
    "stable_github_release_saved_report": {
        "evidence": "A saved stable GitHub release verifier report bound to the final tag, repo, commit, and assets.",
        "next_action": (
            "Save verify_github_release.py output outside the download dir, then recheck it with "
            "--verify-report-files --require-stable-report --verify-git-commit "
            "--expect-tag <final-tag> --expect-repo benngaihk/MorphoJet --expect-commit <final-commit>."
        ),
    },
    "production_evidence_readiness_audit": {
        "evidence": "A saved production-evidence-audit report rechecked with --verify-report-files --require-ready.",
        "next_action": (
            "Run audit_production_evidence.py after external L4, workflow, and stable-release verifier reports are saved, "
            "then supply --production-evidence-audit-report and recheck it before final signoff."
        ),
    },
}


def markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def production_checklist_rows(audit: dict) -> list[dict[str, str]]:
    rows = []
    for check in audit["checks"]:
        guidance = PRODUCTION_CHECKLIST_GUIDANCE[check["name"]]
        next_action = (
            "No action needed for this check."
            if check["status"] == PRODUCTION_AUDIT_PASS_STATUS
            else guidance["next_action"]
        )
        rows.append(
            {
                "check": check["name"],
                "status": check["status"],
                "evidence": guidance["evidence"],
                "next_action": next_action,
            }
        )
    return rows


def production_claim_boundary_lines(payload: dict) -> list[str]:
    if payload.get("final_production_signoff") is FINAL_PRODUCTION_SIGNOFF:
        return [
            "## Production Claim Boundary",
            "",
            "This report is a final production signoff candidate because `final_production_signoff=true`; "
            "the saved report verifier must still pass with `--require-production-claim-pass` and "
            "`--expect-missing-checks none` before release signoff is accepted.",
        ]
    missing = ", ".join(payload.get("missing_or_failed_checks") or []) or "none"
    return [
        "## Production Claim Boundary",
        "",
        "This report is not a production signoff. It remains `NOT_PRODUCTION_CLAIM` until "
        "`final_production_signoff=true`, `production_claim_status=PASS`, and "
        "`missing_or_failed_checks=none` are present in the same saved report.",
        "",
        f"Current production blockers: `{missing}`.",
    ]


def render_markdown(payload: dict, out_json: Path) -> str:
    metadata = payload["metadata"]
    audit = payload["production_claim_audit"]
    checklist = payload["production_claim_checklist"]
    lines = [
        "# Release Gate Report",
        "",
        f"- status: `{payload['status']}`",
        f"- claim_status: `{payload['claim_status']}`",
        f"- evidence_scope: `{payload['evidence_scope']}`",
        f"- final_production_signoff: `{payload['final_production_signoff']}`",
        f"- production_claim_status: `{payload['production_claim_status']}`",
        f"- missing_or_failed_checks: `{', '.join(payload['missing_or_failed_checks']) or 'none'}`",
        f"- json: `{out_json}`",
        f"- generated_at_utc: `{metadata['generated_at_utc']}`",
        f"- git_commit: `{metadata['git_commit']}`",
        f"- git_dirty: `{metadata['git_dirty']}`",
        f"- argv: `{' '.join(metadata['argv'])}`",
        "",
        *production_claim_boundary_lines(payload),
        "",
        "| Gate | Status | Seconds |",
        "|---|---:|---:|",
    ]
    for gate in payload["gates"]:
        lines.append(f"| {gate.name} | {gate.status} | {gate.elapsed_seconds:.3f} |")
    lines.extend(
        [
            "",
            "## Production Claim Audit",
            "",
            "| Check | Status | Detail |",
            "|---|---:|---|",
        ]
    )
    for check in audit["checks"]:
        lines.append(f"| {check['name']} | {check['status']} | {check['detail']} |")
    lines.extend(
        [
            "",
            "## Production Claim Checklist",
            "",
            "| Check | Status | Required evidence | Next action |",
            "|---|---:|---|---|",
        ]
    )
    for row in checklist:
        lines.append(
            "| "
            f"{markdown_cell(row['check'])} | "
            f"{markdown_cell(row['status'])} | "
            f"{markdown_cell(row['evidence'])} | "
            f"{markdown_cell(row['next_action'])} |"
        )
    lines.extend(["", "## Details", ""])
    for gate in payload["gates"]:
        lines.append(f"### {gate.name}")
        lines.append("")
        lines.append(f"- status: `{gate.status}`")
        if gate.command:
            lines.append(f"- command: `{' '.join(gate.command)}`")
        if gate.detail:
            lines.append("")
            lines.append("```text")
            lines.append(gate.detail)
            lines.append("```")
        lines.append("")
    return "\n".join(lines)


def canonical_release_gate_argv(argv: list[str]) -> list[str]:
    canonical = ["benchmark/release_gate.py"]
    index = 1
    while index < len(argv):
        item = argv[index]
        canonical.append(item)
        if item in RELEASE_GATE_ARGV_PATH_FLAGS and index + 1 < len(argv) and not argv[index + 1].startswith("--"):
            canonical.append(normalized_path_key(Path(argv[index + 1])))
            index += 2
            continue
        index += 1
    return canonical


def optional_absolute_path(path: Path | None) -> str | None:
    return normalized_path_key(path) if path else None


def build_metadata(args: argparse.Namespace, git_status_lines: list[str]) -> dict:
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_commit(),
        "git_dirty": bool(git_status_lines),
        "git_status": git_status_lines,
        "argv": canonical_release_gate_argv(sys.argv),
        "run_l3": args.run_l3,
        "build_release_artifact": args.build_release_artifact,
        "release_version": args.release_version,
        "verify_github_release": args.verify_github_release,
        "github_release_kind": args.github_release_kind,
        "require_clean_git": args.require_clean_git,
        "require_l3_provenance": args.require_l3_provenance,
        "require_production_claim": args.require_production_claim,
        "external_trial_json": optional_absolute_path(args.external_trial_json),
        "external_trial_root": optional_absolute_path(args.external_trial_root),
        "external_evidence_package_dir": optional_absolute_path(args.external_evidence_package_dir),
        "external_trial_verification_report": optional_absolute_path(args.external_trial_verification_report),
        "external_evidence_package_verification_report": optional_absolute_path(
            args.external_evidence_package_verification_report
        ),
        "github_release_verification_report": optional_absolute_path(args.github_release_verification_report),
        "github_workflow_verification_report": optional_absolute_path(args.github_workflow_verification_report),
        "production_evidence_audit_report": optional_absolute_path(args.production_evidence_audit_report),
    }


def write_report(args: argparse.Namespace, gates: list[Gate], metadata: dict) -> dict:
    audit = build_production_claim_audit(args, gates, metadata)
    gates_pass = all(gate.status == "PASS" for gate in gates)
    production_claim_pass = audit["status"] == PRODUCTION_AUDIT_PASS_STATUS
    final_production_signoff = bool(gates_pass and production_claim_pass and args.require_production_claim)
    payload = {
        "status": "PASS" if gates_pass and (production_claim_pass or not args.require_production_claim) else "FAIL",
        "claim_status": FINAL_CLAIM_STATUS if final_production_signoff else NON_FINAL_CLAIM_STATUS,
        "evidence_scope": FINAL_EVIDENCE_SCOPE if final_production_signoff else NON_FINAL_EVIDENCE_SCOPE,
        "final_production_signoff": final_production_signoff,
        "production_claim_status": audit["status"],
        "missing_or_failed_checks": audit["missing_or_failed_checks"],
        "production_claim_audit": audit,
        "production_claim_checklist": production_checklist_rows(audit),
        "metadata": metadata,
        "gates": [asdict(gate) for gate in gates],
    }
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(payload, indent=2) + "\n")
    args.out_md.parent.mkdir(parents=True, exist_ok=True)
    args.out_md.write_text(render_markdown({**payload, "gates": gates}, args.out_json) + "\n")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-json", type=Path, default=Path("benchmark/results/release-gate/report.json"))
    parser.add_argument("--out-md", type=Path, default=Path("benchmark/results/release-gate/report.md"))
    parser.add_argument("--run-l3", action="store_true", help="Rerun the full CellBinDB L3 benchmark")
    parser.add_argument("--build-release-artifact", action="store_true", help="Build and verify a local release archive")
    parser.add_argument("--release-version", default="local", help="Version label for --build-release-artifact")
    parser.add_argument("--verify-github-release", help="Download and verify an existing GitHub release tag")
    parser.add_argument(
        "--github-release-kind",
        choices=["prerelease", "stable"],
        default="prerelease",
        help="Expected GitHub release kind for --verify-github-release",
    )
    parser.add_argument("--require-clean-git", action="store_true", help="Fail unless git status is clean")
    parser.add_argument(
        "--require-l3-provenance",
        action="store_true",
        help="Fail unless CellBinDB L3 provenance exists and hashes match current artifacts",
    )
    parser.add_argument(
        "--require-production-claim",
        action="store_true",
        help="Fail unless the production-claim audit is complete and passing",
    )
    parser.add_argument(
        "--external-trial-json",
        type=Path,
        help="Validate a real external L4 handoff trial report JSON",
    )
    parser.add_argument(
        "--external-trial-root",
        type=Path,
        help="Root directory for resolving relative external trial artifact paths",
    )
    parser.add_argument(
        "--external-evidence-package-dir",
        type=Path,
        help="Validate an external L4 evidence package created by benchmark/package_external_trial.py",
    )
    parser.add_argument(
        "--external-trial-verification-report",
        type=Path,
        help="Re-check a saved external trial verifier JSON report",
    )
    parser.add_argument(
        "--external-evidence-package-verification-report",
        type=Path,
        help="Re-check a saved external evidence package verifier JSON report",
    )
    parser.add_argument(
        "--github-release-verification-report",
        type=Path,
        help="Re-check a saved stable GitHub release verifier JSON report",
    )
    parser.add_argument(
        "--github-workflow-verification-report",
        type=Path,
        help="Re-check a saved GitHub Actions workflow verifier JSON report for the final commit",
    )
    parser.add_argument(
        "--production-evidence-audit-report",
        type=Path,
        help="Re-check a saved production evidence audit JSON report before final production signoff",
    )
    args = parser.parse_args()
    production_claim_failures = production_claim_contract_failures(args)
    if production_claim_failures:
        parser.error("; ".join(production_claim_failures))
    validate_report_output_paths(args)

    git_status_lines = git_status_porcelain()
    metadata = build_metadata(args, git_status_lines)
    gates = []
    if args.require_clean_git:
        clean_gate = validate_clean_git_worktree(git_status_lines)
        gates.append(clean_gate)
        if clean_gate.status != "PASS":
            payload = write_report(args, gates, metadata)
            print(f"wrote {args.out_json}")
            print(f"wrote {args.out_md}")
            print(f"status={payload['status']}")
            return 1

    cargo = cargo_bin()
    python_files = [
        *sorted(str(path.relative_to(ROOT)) for path in ROOT.glob("benchmark/*.py")),
        "corpus/generate_smoke.py",
        *sorted(str(path.relative_to(ROOT)) for path in ROOT.glob("tests/*.py")),
        *sorted(str(path.relative_to(ROOT)) for path in ROOT.glob("tests/parity/*.py")),
    ]
    gates.extend(
        [
            run_command("Rust formatting", [cargo, "fmt", "--", "--check"]),
            run_command("Rust tests", [cargo, "test"]),
            run_command("Rust clippy", [cargo, "clippy", "--all-targets", "--", "-D", "warnings"]),
            run_command("Python helper compilation", ["python3", "-m", "py_compile", *python_files]),
            run_command("Python helper tests", ["python3", "-m", "unittest", "discover", "-s", "tests"]),
            run_command("Validate claim language", ["python3", "benchmark/validate_claim_language.py"]),
            run_command(
                "Validate handoff manifests",
                [
                    "python3",
                    "benchmark/validate_handoff_manifest.py",
                    "benchmark/handoff/cellbindb_supported_columns.json",
                    "--var",
                    "base_dir=benchmark/results/cellbindb/oracle-full",
                    "--require-downstream-check",
                ],
            ),
            run_command(
                "Validate external lab handoff template",
                [
                    "python3",
                    "benchmark/validate_handoff_manifest.py",
                    "benchmark/handoff/external_lab_template.json",
                    "--var",
                    "base_dir=benchmark/results/external-lab-template",
                    "--require-downstream-check",
                    "--require-external-evidence",
                    "--allow-external-evidence-placeholders",
                ],
            ),
        ]
    )
    if args.build_release_artifact:
        gates.append(
            run_command(
                "Build local release archive",
                [
                    "python3",
                    "benchmark/build_release_archive.py",
                    "--version",
                    args.release_version,
                    "--out-dir",
                    "benchmark/results/release-artifacts",
                ],
            )
        )
        archive = Path("benchmark/results/release-artifacts") / local_release_archive_name(args.release_version)
        expected_commit = git_commit()
        gates.append(
            run_command(
                "Verify local release archive",
                [
                    "python3",
                    "benchmark/verify_release_archive.py",
                    str(archive),
                    "--expect-commit",
                    expected_commit,
                    "--json-out",
                    "benchmark/results/release-artifacts/verification.json",
                ],
            )
        )
    if args.run_l3:
        gates.append(run_command("Run CellBinDB L3 benchmark", ["python3", "benchmark/run_cellbindb_oracle.py", "--threads", "8"]))
    if args.verify_github_release:
        gates.append(
            run_command(
                "Verify GitHub release assets",
                live_github_release_report_command(
                    args.verify_github_release,
                    args.github_release_kind,
                    expected_commit=metadata["git_commit"],
                ),
            )
        )
    gates.append(validate_cellbindb_direct_masks())
    gates.append(validate_l3_artifacts())
    if args.require_l3_provenance:
        gates.append(validate_l3_provenance_artifact())
    gates.append(validate_workflow_bridge_artifacts())
    gates.append(validate_handoff_trial_artifacts())
    if args.external_trial_json:
        gates.append(validate_external_trial_report(args.external_trial_json, args.external_trial_root))
    if args.external_evidence_package_dir:
        gates.append(validate_external_evidence_package(args.external_evidence_package_dir, args.external_trial_json))
    if args.external_trial_verification_report:
        gate = run_command(
            "Verify saved external L4 trial report",
            saved_external_trial_report_command(
                args.external_trial_verification_report,
                expected_commit=metadata["git_commit"],
            ),
        )
        gates.append(
            gate_with_binding_failures(
                gate,
                saved_external_trial_report_binding_failures(args.external_trial_verification_report, args)
                if gate.status == "PASS"
                else [],
            )
        )
    if args.external_evidence_package_verification_report:
        gate = run_command(
            "Verify saved external L4 evidence package report",
            saved_external_package_report_command(
                args.external_evidence_package_verification_report,
                expected_commit=metadata["git_commit"],
            ),
        )
        gates.append(
            gate_with_binding_failures(
                gate,
                saved_external_package_report_binding_failures(
                    args.external_evidence_package_verification_report,
                    args,
                )
                if gate.status == "PASS"
                else [],
            )
        )
    if args.external_trial_verification_report and args.external_evidence_package_verification_report:
        gates.append(
            saved_external_reviewer_pair_gate(
                args.external_trial_verification_report,
                args.external_evidence_package_verification_report,
            )
        )
    if args.github_release_verification_report:
        command = saved_github_release_report_command(
            args.github_release_verification_report,
            expected_tag=args.verify_github_release,
            expected_commit=metadata["git_commit"],
        )
        gates.append(
            run_command(
                "Verify saved stable GitHub release report",
                command,
            )
        )
    if args.github_workflow_verification_report:
        gates.append(
            run_command(
                "Verify saved GitHub Actions workflow report",
                saved_github_workflow_report_command(
                    args.github_workflow_verification_report,
                    expected_commit=metadata["git_commit"],
                ),
            )
        )
    if args.production_evidence_audit_report:
        gates.append(
            run_command(
                "Verify saved production evidence audit report",
                saved_production_evidence_audit_report_command(args.production_evidence_audit_report),
            )
        )

    payload = write_report(args, gates, metadata)
    print(f"wrote {args.out_json}")
    print(f"wrote {args.out_md}")
    print(f"status={payload['status']}")
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
