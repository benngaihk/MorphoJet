#!/usr/bin/env python3
"""Run MorphoJet release-readiness gates and write an auditable report."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


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
    for export in manifest.get("exports", []):
        if not isinstance(export, dict):
            continue
        name = export.get("name")
        if isinstance(name, str) and name.strip():
            channels = export.get("channels")
            channel_arg = ",".join(channels) if isinstance(channels, list) else ""
            out_csv = export.get("out_csv")
            object_set = export.get("object_set")
            step_commands.append(
                (
                    f"Materialize {name} wide CSV",
                    [
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
                    ],
                )
            )
            if "expected_cellprofiler_csv" in export:
                step_commands.append(
                    (
                        f"Compare {name} supported columns",
                        [
                            "python3",
                            "benchmark/compare_cellprofiler_wide_subset.py",
                            export.get("expected_cellprofiler_csv"),
                            out_csv,
                            "--out",
                            export.get("comparison_report"),
                            "--json-out",
                            export.get("comparison_json"),
                            "--fail-on-gap",
                        ],
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


def external_trial_metadata_failures(metadata: object) -> list[str]:
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
    argv = metadata.get("argv")
    if not isinstance(argv, list) or not argv or not all(isinstance(item, str) and item for item in argv):
        failures.append("metadata.argv must be a non-empty string list")
    elif argv[0] != "benchmark/run_handoff_trial.py":
        failures.append(f"metadata.argv[0]={argv[0]}")
    return failures


def external_trial_failures(trial: dict, artifact_root: Path | None = None) -> list[str]:
    failures = []
    if trial.get("status") != "PASS":
        failures.append(f"trial status is {trial.get('status')}")
    failures.extend(external_trial_metadata_failures(trial.get("metadata")))
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
            artifact_path = resolve_artifact_path(artifact, root)
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
    ]
    for key in required_strings:
        value = evidence.get(key)
        if not isinstance(value, str) or not value.strip():
            failures.append(f"external_evidence.{key} must be a non-empty string")
        elif has_placeholder(value):
            failures.append(f"external_evidence.{key} must replace template placeholder text")
    criteria = evidence.get("acceptance_criteria")
    if not isinstance(criteria, list) or not criteria or not all(
        isinstance(item, str) and item.strip() for item in criteria
    ):
        failures.append("external_evidence.acceptance_criteria must be a non-empty string list")
    if evidence.get("manual_csv_editing") is not False:
        failures.append("external_evidence.manual_csv_editing must be false")
    return failures


def validate_external_trial_report(path: Path, artifact_root: Path | None) -> Gate:
    started = time.perf_counter()
    try:
        trial = load_json(path)
        failures = external_trial_failures(trial, artifact_root)
        status = "FAIL" if failures else "PASS"
        evidence = trial.get("external_evidence") if isinstance(trial.get("external_evidence"), dict) else {}
        metadata = trial.get("metadata") if isinstance(trial.get("metadata"), dict) else {}
        detail = "; ".join(failures) if failures else (
            "External workflow trial PASS: "
            f"trial_id={trial.get('trial_id')}, "
            f"lab_or_org={evidence.get('lab_or_org')}, "
            f"trial_commit={metadata.get('git_commit', '')[:12]}, "
            f"generated_at_utc={metadata.get('generated_at_utc')}, "
            f"steps={len(trial.get('steps') or [])}, "
            f"artifacts={len(trial.get('artifacts') or [])}"
        )
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
    return path == "README.md" or path.startswith("docs/")


def is_l3_provenance_compatible_path(path: str) -> bool:
    return is_doc_path(path) or path.startswith("tests/") or path == "benchmark/release_gate.py"


def is_external_trial_compatible_path(path: str) -> bool:
    return is_doc_path(path) or path.startswith("tests/") or path == "benchmark/release_gate.py"


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
        return "MISSING"
    return status


def build_production_claim_audit(args: argparse.Namespace, gates: list[Gate], metadata: dict) -> dict:
    standard_gate_names = [
        "Rust formatting",
        "Rust tests",
        "Rust clippy",
        "Python helper compilation",
        "Python helper tests",
        "Validate handoff manifests",
        "Validate external lab handoff template",
        "Validate existing CellBinDB L3 artifacts",
        "Validate CellBinDB workflow bridge artifacts",
        "Validate CellBinDB handoff trial artifacts",
    ]
    standard_statuses = [production_audit_status(gates, name) for name in standard_gate_names]
    checks = [
        {
            "name": "clean_git_worktree",
            "status": production_audit_status(gates, "Require clean git worktree")
            if args.require_clean_git
            else "MISSING",
            "detail": "Release or production-readiness reports should run with --require-clean-git.",
        },
        {
            "name": "standard_code_and_artifact_gates",
            "status": "PASS" if all(status == "PASS" for status in standard_statuses) else "FAIL",
            "detail": "Standard Rust, Python, manifest, L3 artifact, workflow bridge, and handoff gates.",
        },
        {
            "name": "l3_provenance_hashes",
            "status": production_audit_status(gates, "Validate CellBinDB L3 provenance")
            if args.require_l3_provenance
            else "MISSING",
            "detail": "Production-readiness claims should run with --require-l3-provenance.",
        },
        {
            "name": "external_l4_workflow_trial",
            "status": production_audit_status(gates, "Validate external L4 workflow trial report")
            if args.external_trial_json
            else "MISSING",
            "detail": "Requires --external-trial-json from a real no-manual-CSV-edit workflow trial.",
        },
        {
            "name": "stable_github_release",
            "status": production_audit_status(gates, "Verify GitHub release assets")
            if args.verify_github_release and args.github_release_kind == "stable"
            else "MISSING",
            "detail": "Requires --verify-github-release with --github-release-kind stable.",
        },
    ]
    status = "PASS" if all(check["status"] == "PASS" for check in checks) else "INCOMPLETE"
    return {
        "status": status,
        "git_commit": metadata["git_commit"],
        "checks": checks,
    }


def render_markdown(payload: dict, out_json: Path) -> str:
    metadata = payload["metadata"]
    audit = payload["production_claim_audit"]
    lines = [
        "# Release Gate Report",
        "",
        f"- status: `{payload['status']}`",
        f"- production_claim_status: `{audit['status']}`",
        f"- json: `{out_json}`",
        f"- generated_at_utc: `{metadata['generated_at_utc']}`",
        f"- git_commit: `{metadata['git_commit']}`",
        f"- git_dirty: `{metadata['git_dirty']}`",
        f"- argv: `{' '.join(metadata['argv'])}`",
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


def build_metadata(args: argparse.Namespace, git_status_lines: list[str]) -> dict:
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_commit(),
        "git_dirty": bool(git_status_lines),
        "git_status": git_status_lines,
        "argv": ["benchmark/release_gate.py", *sys.argv[1:]],
        "run_l3": args.run_l3,
        "build_release_artifact": args.build_release_artifact,
        "release_version": args.release_version,
        "verify_github_release": args.verify_github_release,
        "github_release_kind": args.github_release_kind,
        "require_clean_git": args.require_clean_git,
        "require_l3_provenance": args.require_l3_provenance,
        "external_trial_json": str(args.external_trial_json) if args.external_trial_json else None,
        "external_trial_root": str(args.external_trial_root) if args.external_trial_root else None,
    }


def write_report(args: argparse.Namespace, gates: list[Gate], metadata: dict) -> dict:
    audit = build_production_claim_audit(args, gates, metadata)
    payload = {
        "status": "PASS" if all(gate.status == "PASS" for gate in gates) else "FAIL",
        "production_claim_audit": audit,
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
        "--external-trial-json",
        type=Path,
        help="Validate a real external L4 handoff trial report JSON",
    )
    parser.add_argument(
        "--external-trial-root",
        type=Path,
        help="Root directory for resolving relative external trial artifact paths",
    )
    args = parser.parse_args()

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
        release_kind_flag = "--expect-stable" if args.github_release_kind == "stable" else "--expect-prerelease"
        gates.append(
            run_command(
                "Verify GitHub release assets",
                [
                    "python3",
                    "benchmark/verify_github_release.py",
                    args.verify_github_release,
                    release_kind_flag,
                    "--json-out",
                    f"benchmark/results/github-release/{args.verify_github_release}/verification.json",
                ],
            )
        )
    gates.append(validate_l3_artifacts())
    if args.require_l3_provenance:
        gates.append(validate_l3_provenance_artifact())
    gates.append(validate_workflow_bridge_artifacts())
    gates.append(validate_handoff_trial_artifacts())
    if args.external_trial_json:
        gates.append(validate_external_trial_report(args.external_trial_json, args.external_trial_root))

    payload = write_report(args, gates, metadata)
    print(f"wrote {args.out_json}")
    print(f"wrote {args.out_md}")
    print(f"status={payload['status']}")
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
