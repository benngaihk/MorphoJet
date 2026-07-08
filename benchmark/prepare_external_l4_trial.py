#!/usr/bin/env python3
"""Prepare a workspace for a real external L4 handoff trial."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import release_gate
import validate_handoff_manifest


ROOT = Path(__file__).resolve().parents[1]
GENERATOR = "benchmark/prepare_external_l4_trial.py"
DEFAULT_TEMPLATE = Path("benchmark/handoff/external_lab_template.json")
DEFAULT_TEMPLATE_ABS = (ROOT / DEFAULT_TEMPLATE).resolve()
MANIFEST_NAME = "external_manifest.json"
PLAN_NAME = "trial_plan.json"
README_NAME = "README.md"
README_ZH_NAME = "README.zh-CN.md"
CLAIM_STATUS = release_gate.NON_FINAL_CLAIM_STATUS
EVIDENCE_SCOPE = release_gate.EXTERNAL_TRIAL_PLAN_EVIDENCE_SCOPE
FINAL_PRODUCTION_SIGNOFF = release_gate.NON_FINAL_PRODUCTION_SIGNOFF
STABLE_RELEASE_TAG = release_gate.DEFAULT_STABLE_RELEASE_TAG
STABLE_RELEASE_REPO = release_gate.GITHUB_RELEASE_REPO
STABLE_RELEASE_URL = release_gate.stable_release_url(STABLE_RELEASE_TAG, STABLE_RELEASE_REPO)
EXTERNAL_EVIDENCE_REQUIRED_FIELDS = [
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
EXTERNAL_EVIDENCE_MIN_ACCEPTANCE_CRITERIA = 3
EXTERNAL_WORKSPACE_README_SHARED_ANCHORS = [
    "claim_status=NOT_PRODUCTION_CLAIM",
    "final_production_signoff=false",
    "README.zh-CN.md",
    "README.md",
    "--require-report-pass",
    "--verify-report-files",
    "--require-local-evidence-preflight-pass",
    "--external-trial-verification-report",
    "--external-evidence-package-verification-report",
    "--github-release-verification-report",
    "--github-workflow-verification-report",
    "--production-evidence-audit-report",
    "audit_production_evidence.py",
    "PRODUCTION_EVIDENCE_READINESS_AUDIT",
    "--require-production-claim-pass",
    "--expect-missing-checks",
]


class PrepareError(Exception):
    """Raised when an external L4 trial workspace cannot be prepared safely."""


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise PrepareError(f"{path} must contain a JSON object")
    return data


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_commit(rev: str = "HEAD") -> str:
    completed = subprocess.run(
        ["git", "rev-parse", f"{rev}^{{commit}}"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    return completed.stdout.strip()


def is_utc_datetime(value: datetime) -> bool:
    return value.utcoffset() == timezone.utc.utcoffset(value)


def slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-")
    return slug or "external-l4-trial"


def command_line(command: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in command)


def generator_argv(template_path: Path, workspace: Path, package_name: str | None, overwrite: bool) -> list[str]:
    argv = [GENERATOR, "--workspace", str(workspace)]
    if template_path.resolve() != DEFAULT_TEMPLATE_ABS:
        argv.extend(["--template", str(template_path)])
    if package_name is not None:
        argv.extend(["--package-name", package_name])
    if overwrite:
        argv.append("--overwrite")
    return argv


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


def external_evidence_requirements() -> dict[str, Any]:
    return {
        "required_fields": list(EXTERNAL_EVIDENCE_REQUIRED_FIELDS),
        "reviewed_at_utc": "required_utc_timestamp",
        "signoff_statement": "required_non_placeholder",
        "manual_csv_editing": False,
        "acceptance_criteria_min_count": EXTERNAL_EVIDENCE_MIN_ACCEPTANCE_CRITERIA,
        "acceptance_criteria_policy": "non_empty_non_placeholder",
        "placeholder_policy": "all_REPLACE_WITH_values_must_be_replaced_before_trial",
        "enforced_by": ["validate_manifest", "run_trial"],
    }


def validate_external_evidence_requirements(payload: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    requirements = payload.get("external_evidence_requirements")
    expected = external_evidence_requirements()
    if requirements != expected:
        failures.append("external_evidence_requirements changed after plan was written")
    if not isinstance(requirements, dict):
        return failures
    if requirements.get("required_fields") != EXTERNAL_EVIDENCE_REQUIRED_FIELDS:
        failures.append("external_evidence_requirements.required_fields must match the external signoff contract")
    if requirements.get("manual_csv_editing") is not False:
        failures.append("external_evidence_requirements.manual_csv_editing must be false")
    if requirements.get("acceptance_criteria_min_count") != EXTERNAL_EVIDENCE_MIN_ACCEPTANCE_CRITERIA:
        failures.append(
            "external_evidence_requirements.acceptance_criteria_min_count must be "
            f"{EXTERNAL_EVIDENCE_MIN_ACCEPTANCE_CRITERIA}"
        )
    if requirements.get("reviewed_at_utc") != "required_utc_timestamp":
        failures.append("external_evidence_requirements.reviewed_at_utc must require a UTC timestamp")
    if requirements.get("placeholder_policy") != "all_REPLACE_WITH_values_must_be_replaced_before_trial":
        failures.append("external_evidence_requirements.placeholder_policy must require replacing template placeholders")
    if requirements.get("enforced_by") != ["validate_manifest", "run_trial"]:
        failures.append("external_evidence_requirements.enforced_by must bind validate_manifest and run_trial")
    return failures


def validate_production_claim_blockers(payload: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    workspace = payload.get("workspace")
    package_name = payload.get("package_name")
    if not isinstance(workspace, str) or not workspace.strip():
        return failures
    if not isinstance(package_name, str) or not package_name.strip():
        return failures
    expected = production_claim_blockers(Path(workspace), package_name)
    if payload.get("production_claim_blockers") != expected:
        failures.append("production_claim_blockers changed after plan was written")
    blockers = payload.get("production_claim_blockers")
    if not isinstance(blockers, list):
        failures.append("production_claim_blockers must be a list")
        return failures
    expected_names = [blocker["name"] for blocker in expected]
    actual_names = [blocker.get("name") for blocker in blockers if isinstance(blocker, dict)]
    if actual_names != expected_names:
        failures.append("production_claim_blockers must preserve the release-gate blocker order")
    for blocker in blockers:
        if not isinstance(blocker, dict):
            failures.append("production_claim_blockers entries must be objects")
            continue
        name = blocker.get("name")
        if name not in expected_names:
            failures.append(f"production_claim_blockers contains unexpected blocker: {name}")
        if blocker.get("status") not in {
            "PENDING_FINAL_GATE",
            "PENDING_EXTERNAL_EVIDENCE",
            "PENDING_EXTERNAL_REVIEW",
            "PENDING_STABLE_RELEASE",
            "PENDING_REMOTE_CI_VERIFICATION",
        }:
            failures.append(f"production_claim_blockers.{name} has invalid status")
        if not isinstance(blocker.get("required_evidence"), str) or not blocker["required_evidence"].strip():
            failures.append(f"production_claim_blockers.{name} required_evidence must be a non-empty string")
        if not isinstance(blocker.get("next_action"), str) or not blocker["next_action"].strip():
            failures.append(f"production_claim_blockers.{name} next_action must be a non-empty string")
        planned_paths = blocker.get("planned_paths")
        if not isinstance(planned_paths, list) or not planned_paths or not all(
            isinstance(path, str) and path.strip() for path in planned_paths
        ):
            failures.append(f"production_claim_blockers.{name} planned_paths must be a non-empty string list")
        final_gate_bindings = blocker.get("final_gate_bindings")
        if not isinstance(final_gate_bindings, list) or not final_gate_bindings or not all(
            isinstance(binding, str) and binding.strip() for binding in final_gate_bindings
        ):
            failures.append(f"production_claim_blockers.{name} final_gate_bindings must be a non-empty string list")
    return failures


def validate_final_signoff_command_bindings(payload: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    commands = payload.get("commands")
    requirements = payload.get("final_signoff_requirements")
    if not isinstance(commands, dict) or not isinstance(requirements, list):
        return failures
    workspace = payload.get("workspace")
    package_name = payload.get("package_name")
    if not isinstance(workspace, str) or not workspace.strip():
        return failures
    if not isinstance(package_name, str) or not package_name.strip():
        return failures
    final_gate = commands.get("final_production_gate")
    if not isinstance(final_gate, list) or not all(isinstance(item, str) and item for item in final_gate):
        return failures
    requirement_by_name: dict[str, dict[str, Any]] = {}
    for requirement in requirements:
        if not isinstance(requirement, dict):
            continue
        name = requirement.get("name")
        if isinstance(name, str):
            requirement_by_name[name] = requirement

    for binding in final_gate_requirement_bindings(Path(workspace), package_name):
        requirement_name = binding["name"]
        flag = binding["final_gate_flag"]
        verification_step = binding["verification_step"]
        requirement = requirement_by_name.get(requirement_name)
        if requirement is None:
            failures.append(f"final_signoff_requirements missing {requirement_name}")
            continue
        expected_required_for = f"final_production_gate {flag}"
        if requirement.get("required_for") != expected_required_for:
            failures.append(f"final_signoff_requirements.{requirement_name} required_for must be {expected_required_for}")
        if requirement.get("verification_step") != verification_step:
            failures.append(f"final_signoff_requirements.{requirement_name} verification_step must be {verification_step}")
        elif verification_step not in commands:
            failures.append(f"final_signoff_requirements.{requirement_name} verification_step missing commands.{verification_step}")
        flag_values = argv_values(final_gate, flag)
        if len(flag_values) != 1 or flag_values[0] is None:
            failures.append(f"commands.final_production_gate must include exactly one {flag} value")
        elif binding["final_gate_value"] != flag_values[0]:
            failures.append(f"commands.final_production_gate {flag} must be {binding['final_gate_value']}")
        elif flag != "--github-release-tag" and requirement.get("planned_path") != flag_values[0]:
            failures.append(f"final_signoff_requirements.{requirement_name} planned_path must match final_production_gate {flag}")
        if requirement.get("planned_path") != binding["planned_path"]:
            failures.append(f"final_signoff_requirements.{requirement_name} planned_path must be {binding['planned_path']}")

    final_report_requirement = requirement_by_name.get("final_production_claim_report")
    if final_report_requirement is None:
        failures.append("final_signoff_requirements missing final_production_claim_report")
    else:
        if final_report_requirement.get("required_for") != "production_signoff":
            failures.append("final_signoff_requirements.final_production_claim_report required_for must be production_signoff")
        if final_report_requirement.get("verification_step") != "verify_final_production_report":
            failures.append(
                "final_signoff_requirements.final_production_claim_report verification_step must be "
                "verify_final_production_report"
            )
        elif "verify_final_production_report" not in commands:
            failures.append(
                "final_signoff_requirements.final_production_claim_report verification_step missing "
                "commands.verify_final_production_report"
            )
        out_values = argv_values(final_gate, "--out-json")
        if len(out_values) != 1 or out_values[0] is None:
            failures.append("commands.final_production_gate must include exactly one --out-json value")
        elif final_report_requirement.get("planned_path") != out_values[0]:
            failures.append(
                "final_signoff_requirements.final_production_claim_report planned_path must match "
                "final_production_gate --out-json"
            )
    return failures


def validate_pre_signoff_command_bindings(payload: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    commands = payload.get("commands")
    requirements = payload.get("pre_signoff_requirements")
    if not isinstance(commands, dict) or not isinstance(requirements, list):
        return failures
    requirement_by_name: dict[str, dict[str, Any]] = {}
    for requirement in requirements:
        if not isinstance(requirement, dict):
            continue
        name = requirement.get("name")
        if isinstance(name, str):
            requirement_by_name[name] = requirement

    def command_values(command_name: str, flag: str) -> list[str | None]:
        command = commands.get(command_name)
        if not isinstance(command, list) or not all(isinstance(item, str) and item for item in command):
            failures.append(f"commands.{command_name} must be a non-empty string list before binding {flag}")
            return []
        return argv_values(command, flag)

    readiness_requirement = requirement_by_name.get("external_l4_readiness_precheck")
    if readiness_requirement is None:
        failures.append("pre_signoff_requirements missing external_l4_readiness_precheck")
    else:
        if readiness_requirement.get("verification_step") != "verify_readiness":
            failures.append("pre_signoff_requirements.external_l4_readiness_precheck verification_step must be verify_readiness")
        elif "verify_readiness" not in commands:
            failures.append(
                "pre_signoff_requirements.external_l4_readiness_precheck verification_step missing "
                "commands.verify_readiness"
            )
        if readiness_requirement.get("required_before") != "run_trial":
            failures.append("pre_signoff_requirements.external_l4_readiness_precheck required_before must be run_trial")
        elif "run_trial" not in commands:
            failures.append("pre_signoff_requirements.external_l4_readiness_precheck required_before missing commands.run_trial")
        planned_path = readiness_requirement.get("planned_path")
        for command_name, flag in [
            ("check_readiness", "--json-out"),
            ("verify_readiness", "--verify-report"),
            ("run_trial", "--readiness-report"),
        ]:
            values = command_values(command_name, flag)
            if len(values) != 1 or values[0] is None:
                failures.append(f"commands.{command_name} must include exactly one {flag} value")
            elif planned_path != values[0]:
                failures.append(
                    "pre_signoff_requirements.external_l4_readiness_precheck planned_path must match "
                    f"{command_name} {flag}"
                )

    preflight_requirement = requirement_by_name.get("local_evidence_preflight_report")
    if preflight_requirement is None:
        failures.append("pre_signoff_requirements missing local_evidence_preflight_report")
    else:
        if preflight_requirement.get("verification_step") != "verify_local_evidence_preflight":
            failures.append(
                "pre_signoff_requirements.local_evidence_preflight_report verification_step must be "
                "verify_local_evidence_preflight"
            )
        elif "verify_local_evidence_preflight" not in commands:
            failures.append(
                "pre_signoff_requirements.local_evidence_preflight_report verification_step missing "
                "commands.verify_local_evidence_preflight"
            )
        if preflight_requirement.get("required_before") != "verify_stable_release":
            failures.append("pre_signoff_requirements.local_evidence_preflight_report required_before must be verify_stable_release")
        elif "verify_stable_release" not in commands:
            failures.append(
                "pre_signoff_requirements.local_evidence_preflight_report required_before missing "
                "commands.verify_stable_release"
            )
        planned_path = preflight_requirement.get("planned_path")
        for command_name, flag in [
            ("local_evidence_preflight", "--local-evidence-preflight-json"),
            ("verify_local_evidence_preflight", "--verify-local-evidence-preflight-report"),
        ]:
            values = command_values(command_name, flag)
            if len(values) != 1 or values[0] is None:
                failures.append(f"commands.{command_name} must include exactly one {flag} value")
            elif planned_path != values[0]:
                failures.append(
                    "pre_signoff_requirements.local_evidence_preflight_report planned_path must match "
                    f"{command_name} {flag}"
                )
    saved_reviewer_bindings = [
        (
            "external_l4_trial_saved_reviewer_report",
            "verify_trial_report",
            "--external-trial-verification-report",
        ),
        (
            "external_l4_package_saved_reviewer_report",
            "verify_package_report",
            "--external-evidence-package-verification-report",
        ),
    ]
    for requirement_name, verification_step, preflight_flag in saved_reviewer_bindings:
        requirement = requirement_by_name.get(requirement_name)
        if requirement is None:
            failures.append(f"pre_signoff_requirements missing {requirement_name}")
            continue
        if requirement.get("verification_step") != verification_step:
            failures.append(f"pre_signoff_requirements.{requirement_name} verification_step must be {verification_step}")
        elif verification_step not in commands:
            failures.append(f"pre_signoff_requirements.{requirement_name} verification_step missing commands.{verification_step}")
        if requirement.get("required_before") != "local_evidence_preflight":
            failures.append(f"pre_signoff_requirements.{requirement_name} required_before must be local_evidence_preflight")
        elif "local_evidence_preflight" not in commands:
            failures.append(f"pre_signoff_requirements.{requirement_name} required_before missing commands.local_evidence_preflight")
        planned_path = requirement.get("planned_path")
        for command_name, flag in [
            (verification_step, "--verify-report"),
            ("local_evidence_preflight", preflight_flag),
        ]:
            values = command_values(command_name, flag)
            if len(values) != 1 or values[0] is None:
                failures.append(f"commands.{command_name} must include exactly one {flag} value")
            elif planned_path != values[0]:
                failures.append(
                    f"pre_signoff_requirements.{requirement_name} planned_path must match "
                    f"{command_name} {flag}"
                )
    audit_requirement = requirement_by_name.get("production_evidence_readiness_audit")
    if audit_requirement is None:
        failures.append("pre_signoff_requirements missing production_evidence_readiness_audit")
    else:
        if audit_requirement.get("verification_step") != "verify_production_evidence_audit":
            failures.append(
                "pre_signoff_requirements.production_evidence_readiness_audit verification_step must be "
                "verify_production_evidence_audit"
            )
        elif "verify_production_evidence_audit" not in commands:
            failures.append(
                "pre_signoff_requirements.production_evidence_readiness_audit verification_step missing "
                "commands.verify_production_evidence_audit"
            )
        if audit_requirement.get("required_before") != "final_production_gate":
            failures.append(
                "pre_signoff_requirements.production_evidence_readiness_audit required_before must be "
                "final_production_gate"
            )
        elif "final_production_gate" not in commands:
            failures.append(
                "pre_signoff_requirements.production_evidence_readiness_audit required_before missing "
                "commands.final_production_gate"
            )
        planned_path = audit_requirement.get("planned_path")
        for command_name, flag in [
            ("audit_production_evidence", "--out-json"),
            ("verify_production_evidence_audit", "--verify-report"),
        ]:
            values = command_values(command_name, flag)
            if len(values) != 1 or values[0] is None:
                failures.append(f"commands.{command_name} must include exactly one {flag} value")
            elif planned_path != values[0]:
                failures.append(
                    "pre_signoff_requirements.production_evidence_readiness_audit planned_path must match "
                    f"{command_name} {flag}"
                )
    return failures


def validate_external_evidence_command_bindings(payload: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    commands = payload.get("commands")
    workspace = payload.get("workspace")
    package_name = payload.get("package_name")
    if not isinstance(commands, dict):
        return failures
    if not isinstance(workspace, str) or not workspace.strip():
        return failures
    if not isinstance(package_name, str) or not package_name.strip():
        return failures
    workspace_path = Path(workspace)
    trial_json = str(workspace_path / "handoff_trial.json")
    trial_verification = str(workspace_path / "handoff_trial-verification.json")
    package_out = str(workspace_path / "evidence-package")
    package_dir = str(workspace_path / "evidence-package" / package_name)
    package_verification = str(workspace_path / "evidence-package-verification.json")
    readiness_json = str(workspace_path / "readiness.json")
    preflight_json = str(workspace_path / "local-evidence-preflight.json")
    github_release_verification = str(workspace_path / "github-release-verification.json")
    production_claim_json = str(workspace_path / "production-claim.json")
    production_evidence_audit_json = str(workspace_path / "production-evidence-audit.json")

    def command(command_name: str) -> list[str]:
        value = commands.get(command_name)
        if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
            failures.append(f"commands.{command_name} must be a non-empty string list before evidence binding")
            return []
        return value

    def expect_flag(command_name: str, flag: str, expected: str, label: str) -> None:
        values = argv_values(command(command_name), flag)
        if len(values) != 1 or values[0] is None:
            failures.append(f"commands.{command_name} must include exactly one {flag} value for {label}")
        elif values[0] != expected:
            failures.append(f"commands.{command_name} {flag} must match {label}")

    def expect_positional(command_name: str, index: int, expected: str, label: str) -> None:
        cmd = command(command_name)
        if len(cmd) <= index:
            failures.append(f"commands.{command_name} missing positional {label}")
        elif cmd[index] != expected:
            failures.append(f"commands.{command_name} positional {label} must match {expected}")

    for command_name, flag in [
        ("run_trial", "--out-json"),
        ("package_evidence", "--trial-json"),
        ("verify_package", "--trial-json"),
        ("local_evidence_preflight", "--external-trial-json"),
        ("final_production_gate", "--external-trial-json"),
    ]:
        expect_flag(command_name, flag, trial_json, "handoff_trial.json")
    expect_positional("verify_trial", 2, trial_json, "handoff_trial.json")

    for command_name, flag in [
        ("verify_trial", "--trial-root"),
        ("package_evidence", "--trial-root"),
        ("local_evidence_preflight", "--external-trial-root"),
        ("final_production_gate", "--external-trial-root"),
    ]:
        expect_flag(command_name, flag, workspace, "external trial root")
    expect_flag("check_readiness", "--json-out", readiness_json, "readiness.json")
    expect_flag("verify_readiness", "--verify-report", readiness_json, "readiness.json")
    expect_flag("run_trial", "--readiness-report", readiness_json, "readiness.json")

    expect_flag("package_evidence", "--out-dir", package_out, "evidence package output directory")
    expect_flag("package_evidence", "--package-name", package_name, "evidence package name")
    expect_positional("verify_package", 2, package_dir, "evidence package directory")
    expect_flag("local_evidence_preflight", "--external-evidence-package-dir", package_dir, "evidence package directory")
    expect_flag("final_production_gate", "--external-evidence-package-dir", package_dir, "evidence package directory")

    expect_flag("verify_trial", "--json-out", trial_verification, "trial reviewer report")
    expect_flag("verify_trial_report", "--verify-report", trial_verification, "trial reviewer report")
    expect_flag("local_evidence_preflight", "--external-trial-verification-report", trial_verification, "trial reviewer report")
    expect_flag("final_production_gate", "--external-trial-verification-report", trial_verification, "trial reviewer report")

    expect_flag("verify_package", "--json-out", package_verification, "package reviewer report")
    expect_flag("verify_package_report", "--verify-report", package_verification, "package reviewer report")
    expect_flag(
        "local_evidence_preflight",
        "--external-evidence-package-verification-report",
        package_verification,
        "package reviewer report",
    )
    expect_flag(
        "final_production_gate",
        "--external-evidence-package-verification-report",
        package_verification,
        "package reviewer report",
    )

    expect_flag("local_evidence_preflight", "--local-evidence-preflight-json", preflight_json, "local preflight report")
    expect_flag(
        "verify_local_evidence_preflight",
        "--verify-local-evidence-preflight-report",
        preflight_json,
        "local preflight report",
    )
    expect_flag("verify_stable_release", "--json-out", github_release_verification, "GitHub release verifier report")
    github_workflow_verification = str(Path(workspace) / "github-workflow-verification.json")
    expect_flag(
        "verify_github_workflows",
        "--json-out",
        github_workflow_verification,
        "GitHub workflow verifier report",
    )
    expect_flag(
        "verify_github_workflows_report",
        "--verify-report",
        github_workflow_verification,
        "GitHub workflow verifier report",
    )
    expect_flag(
        "verify_stable_release_report",
        "--verify-report",
        github_release_verification,
        "GitHub release verifier report",
    )
    expect_flag(
        "final_production_gate",
        "--github-release-verification-report",
        github_release_verification,
        "GitHub release verifier report",
    )
    expect_flag(
        "final_production_gate",
        "--github-workflow-verification-report",
        github_workflow_verification,
        "GitHub workflow verifier report",
    )
    for command_name in ["audit_production_evidence", "final_production_gate"]:
        expect_flag(command_name, "--external-trial-json", trial_json, "handoff_trial.json")
        expect_flag(command_name, "--external-trial-root", workspace, "external trial root")
        expect_flag(command_name, "--external-evidence-package-dir", package_dir, "evidence package directory")
        expect_flag(command_name, "--external-trial-verification-report", trial_verification, "trial reviewer report")
        expect_flag(
            command_name,
            "--external-evidence-package-verification-report",
            package_verification,
            "package reviewer report",
        )
        expect_flag(
            command_name,
            "--github-release-verification-report",
            github_release_verification,
            "GitHub release verifier report",
        )
        expect_flag(
            command_name,
            "--github-workflow-verification-report",
            github_workflow_verification,
            "GitHub workflow verifier report",
        )
        expect_flag(command_name, "--github-release-tag", STABLE_RELEASE_TAG, "stable release tag")
    expect_flag("audit_production_evidence", "--out-json", production_evidence_audit_json, "production evidence audit")
    expect_flag(
        "verify_production_evidence_audit",
        "--verify-report",
        production_evidence_audit_json,
        "production evidence audit",
    )
    expect_flag(
        "final_production_gate",
        "--production-evidence-audit-report",
        production_evidence_audit_json,
        "production evidence audit",
    )
    expect_flag("final_production_gate", "--out-json", production_claim_json, "final production claim report")
    expect_positional("verify_final_production_report", 2, production_claim_json, "final production claim report")
    return failures


def validate_stable_release_command_bindings(payload: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    commands = payload.get("commands")
    workspace = payload.get("workspace")
    plan_git_commit = payload.get("git_commit")
    if not isinstance(commands, dict):
        return failures
    if not isinstance(workspace, str) or not workspace.strip():
        return failures
    if not isinstance(plan_git_commit, str) or not re.fullmatch(r"[0-9a-f]{40}", plan_git_commit):
        return failures
    github_release_verification = str(Path(workspace) / "github-release-verification.json")
    github_workflow_verification = str(Path(workspace) / "github-workflow-verification.json")
    production_evidence_audit = str(Path(workspace) / "production-evidence-audit.json")

    def command(command_name: str) -> list[str]:
        value = commands.get(command_name)
        if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
            failures.append(f"commands.{command_name} must be a non-empty string list before stable-release binding")
            return []
        return value

    def expect_flag(command_name: str, flag: str, expected: str, label: str) -> None:
        values = argv_values(command(command_name), flag)
        if len(values) != 1 or values[0] is None:
            failures.append(f"commands.{command_name} must include exactly one {flag} value for {label}")
        elif values[0] != expected:
            failures.append(f"commands.{command_name} {flag} must be {expected} for {label}")

    def expect_present(command_name: str, flag: str, label: str) -> None:
        count = command(command_name).count(flag)
        if count != 1:
            failures.append(f"commands.{command_name} must include exactly one {flag} for {label}")

    verify_release = command("verify_stable_release")
    if len(verify_release) <= 2:
        failures.append("commands.verify_stable_release missing stable release tag argument")
    elif verify_release[2] != STABLE_RELEASE_TAG:
        failures.append(f"commands.verify_stable_release tag must be {STABLE_RELEASE_TAG}")
    expect_flag("verify_stable_release", "--repo", STABLE_RELEASE_REPO, "stable release repo")
    expect_flag("verify_stable_release", "--expect-commit", plan_git_commit, "stable release commit")
    expect_flag("verify_stable_release", "--json-out", github_release_verification, "GitHub release verifier report")
    expect_present("verify_stable_release", "--expect-stable", "stable release verification")

    expect_flag("verify_github_workflows", "--repo", STABLE_RELEASE_REPO, "GitHub workflow repo")
    expect_flag("verify_github_workflows", "--branch", "main", "GitHub workflow branch")
    expect_flag("verify_github_workflows", "--commit", plan_git_commit, "GitHub workflow commit")
    expect_flag("verify_github_workflows", "--json-out", github_workflow_verification, "GitHub workflow report")

    expect_flag("verify_stable_release_report", "--verify-report", github_release_verification, "GitHub release verifier report")
    expect_flag("verify_stable_release_report", "--expect-tag", STABLE_RELEASE_TAG, "stable release tag")
    expect_flag("verify_stable_release_report", "--expect-repo", STABLE_RELEASE_REPO, "stable release repo")
    expect_flag("verify_stable_release_report", "--expect-commit", plan_git_commit, "stable release commit")
    for flag, label in [
        ("--verify-report-files", "saved stable release file recheck"),
        ("--require-report-pass", "saved stable release PASS enforcement"),
        ("--require-stable-report", "saved stable report type"),
        ("--verify-git-commit", "saved stable release git commit binding"),
    ]:
        expect_present("verify_stable_release_report", flag, label)

    expect_flag(
        "verify_github_workflows_report",
        "--verify-report",
        github_workflow_verification,
        "GitHub workflow verifier report",
    )
    expect_flag("verify_github_workflows_report", "--expect-repo", STABLE_RELEASE_REPO, "GitHub workflow repo")
    expect_flag("verify_github_workflows_report", "--expect-branch", "main", "GitHub workflow branch")
    expect_flag(
        "verify_github_workflows_report",
        "--expect-commit",
        plan_git_commit,
        "GitHub workflow commit",
    )
    for workflow in ["ci.yml", "external-l4-rehearsal.yml"]:
        values = argv_values(command("verify_github_workflows_report"), "--expect-workflow")
        if workflow not in values:
            failures.append(f"commands.verify_github_workflows_report missing --expect-workflow {workflow}")
    expect_present("verify_github_workflows_report", "--require-report-pass", "saved GitHub workflow PASS enforcement")

    expect_flag(
        "audit_production_evidence",
        "--github-release-verification-report",
        github_release_verification,
        "GitHub release verifier report",
    )
    expect_flag(
        "audit_production_evidence",
        "--github-workflow-verification-report",
        github_workflow_verification,
        "GitHub workflow verifier report",
    )
    expect_flag("audit_production_evidence", "--github-release-tag", STABLE_RELEASE_TAG, "stable release tag")
    expect_present("audit_production_evidence", "--verify-live-github-release", "live stable release audit")
    expect_flag(
        "verify_production_evidence_audit",
        "--verify-report",
        production_evidence_audit,
        "production evidence audit",
    )
    expect_present("verify_production_evidence_audit", "--verify-report-files", "production evidence audit file recheck")
    expect_present("verify_production_evidence_audit", "--require-ready", "production evidence audit readiness")

    expect_flag("final_production_gate", "--github-release-tag", STABLE_RELEASE_TAG, "final stable release tag")
    expect_flag(
        "final_production_gate",
        "--github-release-verification-report",
        github_release_verification,
        "GitHub release verifier report",
    )
    expect_flag(
        "final_production_gate",
        "--github-workflow-verification-report",
        github_workflow_verification,
        "GitHub workflow verifier report",
    )
    return failures


def validate_saved_reviewer_report_command_bindings(payload: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    commands = payload.get("commands")
    workspace = payload.get("workspace")
    package_name = payload.get("package_name")
    if not isinstance(commands, dict):
        return failures
    if not isinstance(workspace, str) or not workspace.strip():
        return failures
    if not isinstance(package_name, str) or not package_name.strip():
        return failures
    workspace_path = Path(workspace)
    trial_json = str(workspace_path / "handoff_trial.json")
    trial_verification = str(workspace_path / "handoff_trial-verification.json")
    package_verification = str(workspace_path / "evidence-package-verification.json")

    def command(command_name: str) -> list[str]:
        value = commands.get(command_name)
        if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
            failures.append(f"commands.{command_name} must be a non-empty string list before saved-reviewer binding")
            return []
        return value

    def expect_flag(command_name: str, flag: str, expected: str, label: str) -> None:
        values = argv_values(command(command_name), flag)
        if len(values) != 1 or values[0] is None:
            failures.append(f"commands.{command_name} must include exactly one {flag} value for {label}")
        elif values[0] != expected:
            failures.append(f"commands.{command_name} {flag} must match {label}")

    def expect_present(command_name: str, flag: str, label: str) -> None:
        count = command(command_name).count(flag)
        if count != 1:
            failures.append(f"commands.{command_name} must include exactly one {flag} for {label}")

    expect_flag("verify_trial_report", "--verify-report", trial_verification, "trial reviewer report")
    for flag, label in [
        ("--verify-report-files", "trial saved reviewer file recheck"),
        ("--require-report-pass", "trial saved reviewer PASS enforcement"),
    ]:
        expect_present("verify_trial_report", flag, label)

    expect_flag("verify_package_report", "--verify-report", package_verification, "package reviewer report")
    for flag, label in [
        ("--verify-report-files", "package saved reviewer file recheck"),
        ("--require-report-pass", "package saved reviewer PASS enforcement"),
        ("--require-trial-json", "package saved reviewer source trial binding"),
    ]:
        expect_present("verify_package_report", flag, label)
    expect_flag("verify_package", "--trial-json", trial_json, "source trial JSON")
    return failures


def validate_generator_argv(payload: dict[str, Any], argv: list[str]) -> list[str]:
    failures = []
    if argv[0] != GENERATOR:
        failures.append(f"argv[0]={argv[0]}")
    if "--verify-plan" in argv:
        failures.append("argv must not include --verify-plan for a generated trial plan")
    workspace = payload.get("workspace")
    template = payload.get("template")
    package_name = payload.get("package_name")
    workspace_values = argv_values(argv, "--workspace")
    if len(workspace_values) > 1:
        failures.append("argv has duplicate --workspace")
    if not workspace_values:
        failures.append("argv missing --workspace")
    for value in workspace_values:
        if value is None:
            failures.append("argv --workspace must include a value")
        elif not Path(value).is_absolute():
            failures.append("argv --workspace must be an absolute path")
        elif isinstance(workspace, str) and value != workspace:
            failures.append(f"workspace must match argv --workspace {value}")
    template_values = argv_values(argv, "--template")
    if len(template_values) > 1:
        failures.append("argv has duplicate --template")
    if not template_values and template not in {str(DEFAULT_TEMPLATE), str(DEFAULT_TEMPLATE_ABS)}:
        failures.append("argv missing --template for non-default template")
    for value in template_values:
        if value is None:
            failures.append("argv --template must include a value")
        elif not Path(value).is_absolute():
            failures.append("argv --template must be an absolute path")
        elif isinstance(template, str) and value != template:
            failures.append(f"template must match argv --template {value}")
    package_values = argv_values(argv, "--package-name")
    if len(package_values) > 1:
        failures.append("argv has duplicate --package-name")
    for value in package_values:
        if value is None:
            failures.append("argv --package-name must include a value")
        elif isinstance(package_name, str) and slugify(value) != package_name:
            failures.append(f"package_name must match argv --package-name {value}")
    if argv.count("--overwrite") > 1:
        failures.append("argv has duplicate --overwrite")
    return failures


def validate_plan_payload(payload: Any, verify_files: bool = False) -> list[str]:
    failures: list[str] = []
    if not isinstance(payload, dict):
        return ["trial plan must be a JSON object"]
    if payload.get("schema_version") != 1:
        failures.append(f"schema_version={payload.get('schema_version')}")
    if payload.get("generator") != GENERATOR:
        failures.append(f"generator={payload.get('generator')}")
    generated_at = payload.get("generated_at_utc")
    if not isinstance(generated_at, str) or not generated_at.strip():
        failures.append("generated_at_utc must be a non-empty string")
    else:
        try:
            parsed = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                failures.append("generated_at_utc must include timezone")
            elif not is_utc_datetime(parsed):
                failures.append("generated_at_utc must be UTC")
        except ValueError:
            failures.append(f"generated_at_utc is invalid: {generated_at}")
    argv = payload.get("argv")
    if not isinstance(argv, list) or not argv or not all(isinstance(item, str) and item for item in argv):
        failures.append("argv must be a non-empty string list")
    else:
        failures.extend(validate_generator_argv(payload, argv))
    for key in ["template", "workspace", "manifest", "package_name"]:
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            failures.append(f"{key} must be a non-empty string")
        elif key != "package_name" and not Path(value).is_absolute():
            failures.append(f"{key} must be an absolute path")
    plan_git_commit = payload.get("git_commit")
    if not isinstance(plan_git_commit, str) or not re.fullmatch(r"[0-9a-f]{40}", plan_git_commit):
        failures.append(f"git_commit={plan_git_commit}")
    template_size = payload.get("template_size_bytes")
    if not isinstance(template_size, int) or template_size <= 0:
        failures.append(f"template_size_bytes={template_size}")
    template_sha = payload.get("template_sha256")
    if not isinstance(template_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", template_sha):
        failures.append(f"template_sha256={template_sha}")
    if payload.get("claim_status") != CLAIM_STATUS:
        failures.append(f"claim_status={payload.get('claim_status')}")
    if payload.get("evidence_scope") != EVIDENCE_SCOPE:
        failures.append(f"evidence_scope={payload.get('evidence_scope')}")
    if payload.get("final_production_signoff") is not FINAL_PRODUCTION_SIGNOFF:
        failures.append("final_production_signoff must be false")
    commands = payload.get("commands")
    expected_command_names = [
        "verify_plan",
        "validate_manifest",
        "check_readiness",
        "verify_readiness",
        "run_trial",
        "verify_trial",
        "verify_trial_report",
        "package_evidence",
        "verify_package",
        "verify_package_report",
        "local_evidence_preflight",
        "verify_local_evidence_preflight",
        "verify_stable_release",
        "verify_stable_release_report",
        "verify_github_workflows",
        "verify_github_workflows_report",
        "audit_production_evidence",
        "verify_production_evidence_audit",
        "final_production_gate",
        "verify_final_production_report",
    ]
    if not isinstance(commands, dict):
        failures.append("commands must be an object")
    else:
        if sorted(commands) != sorted(expected_command_names):
            failures.append("commands must contain exactly the expected external L4 plan steps")
        for name in expected_command_names:
            command = commands.get(name)
            if not isinstance(command, list) or not command or not all(isinstance(item, str) and item for item in command):
                failures.append(f"commands.{name} must be a non-empty string list")
        manifest = payload.get("manifest")
        workspace = payload.get("workspace")
        package_name = payload.get("package_name")
        if all(
            isinstance(value, str) and value.strip()
            for value in [manifest, workspace, package_name, plan_git_commit]
        ):
            expected_commands = plan_commands(Path(manifest), Path(workspace), package_name, plan_git_commit)
            if commands != expected_commands:
                failures.append("commands changed after plan was written")
            expected_requirements = final_signoff_requirements(Path(workspace), package_name)
            if payload.get("final_signoff_requirements") != expected_requirements:
                failures.append("final_signoff_requirements changed after plan was written")
            expected_pre_signoff = pre_signoff_requirements(Path(workspace))
            if payload.get("pre_signoff_requirements") != expected_pre_signoff:
                failures.append("pre_signoff_requirements changed after plan was written")
            failures.extend(validate_pre_signoff_command_bindings(payload))
            failures.extend(validate_final_signoff_command_bindings(payload))
            failures.extend(validate_external_evidence_command_bindings(payload))
            failures.extend(validate_stable_release_command_bindings(payload))
            failures.extend(validate_saved_reviewer_report_command_bindings(payload))
            failures.extend(validate_external_evidence_requirements(payload))
            failures.extend(validate_production_claim_blockers(payload))
    if verify_files:
        failures.extend(validate_plan_files(payload))
    return failures


def validate_plan_files(payload: dict[str, Any]) -> list[str]:
    failures = []
    if not all(isinstance(payload.get(key), str) and payload.get(key).strip() for key in ["template", "workspace", "manifest", "package_name"]):
        return failures
    template_path = Path(payload["template"])
    workspace = Path(payload["workspace"])
    manifest_path = Path(payload["manifest"])
    if not template_path.is_file():
        failures.append(f"template file does not exist: {template_path}")
    else:
        if payload.get("template_size_bytes") != template_path.stat().st_size:
            failures.append("template_size_bytes changed after plan was written")
        if payload.get("template_sha256") != sha256(template_path):
            failures.append("template_sha256 changed after plan was written")
    if not manifest_path.is_file():
        failures.append(f"manifest file does not exist: {manifest_path}")
    readme_path = workspace / README_NAME
    if not readme_path.is_file():
        failures.append(f"README file does not exist: {readme_path}")
    else:
        readme_text = readme_path.read_text(encoding="utf-8")
        if readme_text != render_readme(payload):
            failures.append("README changed after plan was written")
        failures.extend(validate_external_workspace_readme_shared_anchors(README_NAME, readme_text))
    readme_zh_path = workspace / README_ZH_NAME
    if not readme_zh_path.is_file():
        failures.append(f"Chinese README file does not exist: {readme_zh_path}")
    else:
        readme_zh_text = readme_zh_path.read_text(encoding="utf-8")
        if readme_zh_text != render_readme_zh(payload):
            failures.append("Chinese README changed after plan was written")
        failures.extend(validate_external_workspace_readme_shared_anchors(README_ZH_NAME, readme_zh_text))
    return failures


def validate_external_workspace_readme_shared_anchors(readme_name: str, text: str) -> list[str]:
    failures = []
    for anchor in EXTERNAL_WORKSPACE_README_SHARED_ANCHORS:
        if anchor not in text:
            failures.append(f"{readme_name} missing external L4 shared README anchor: {anchor}")
    return failures


def verify_saved_plan(plan_path: Path, verify_files: bool = False) -> int:
    try:
        payload = json.loads(plan_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - exact plan verification failure.
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    failures = validate_plan_payload(payload, verify_files=verify_files)
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print(f"trial plan ok: {plan_path}")
    print(f"claim_status={payload['claim_status']}")
    print(f"evidence_scope={payload['evidence_scope']}")
    print(f"final_production_signoff={payload['final_production_signoff']}")
    return 0


def verify_saved_plan_with_options(
    plan_path: Path,
    verify_files: bool = False,
    require_plan_files: bool = False,
) -> int:
    if require_plan_files and not verify_files:
        print("FAIL: --require-plan-files requires --verify-plan-files", file=sys.stderr)
        return 1
    return verify_saved_plan(plan_path, verify_files=verify_files)


def validate_template(template: dict[str, Any]) -> None:
    issues = validate_handoff_manifest.validate_schema(
        template,
        require_downstream_check=True,
        require_external_evidence=True,
        allow_external_evidence_placeholders=True,
    )
    if issues:
        raise PrepareError("\n".join(issues))


def plan_commands(
    manifest_path: Path,
    workspace: Path,
    package_name: str,
    github_workflow_commit: str,
) -> dict[str, list[str]]:
    plan_path = workspace / PLAN_NAME
    trial_json = workspace / "handoff_trial.json"
    trial_md = workspace / "handoff_trial.md"
    trial_verification = workspace / "handoff_trial-verification.json"
    package_out = workspace / "evidence-package"
    package_dir = package_out / package_name
    package_verification = workspace / "evidence-package-verification.json"
    preflight_json = workspace / "local-evidence-preflight.json"
    preflight_md = workspace / "local-evidence-preflight.md"
    github_release_dir = workspace / "github-release"
    github_release_verification = workspace / "github-release-verification.json"
    github_workflow_verification = workspace / "github-workflow-verification.json"
    production_evidence_audit_json = workspace / "production-evidence-audit.json"
    production_evidence_audit_md = workspace / "production-evidence-audit.md"
    production_claim_json = workspace / "production-claim.json"
    production_claim_md = workspace / "production-claim.md"
    readiness_json = workspace / "readiness.json"
    base_var = f"base_dir={workspace}"
    return {
        "verify_plan": [
            "python3",
            "benchmark/prepare_external_l4_trial.py",
            "--verify-plan",
            str(plan_path),
            "--verify-plan-files",
            "--require-plan-files",
        ],
        "validate_manifest": [
            "python3",
            "benchmark/validate_handoff_manifest.py",
            str(manifest_path),
            "--var",
            base_var,
            "--check-files",
            "--require-downstream-check",
            "--require-external-evidence",
        ],
        "check_readiness": [
            "python3",
            "benchmark/check_external_l4_readiness.py",
            "--workspace",
            str(workspace),
            "--package-name",
            package_name,
            "--json-out",
            str(readiness_json),
        ],
        "verify_readiness": [
            "python3",
            "benchmark/check_external_l4_readiness.py",
            "--verify-report",
            str(readiness_json),
            "--verify-report-files",
            "--require-ready",
        ],
        "run_trial": [
            "python3",
            "benchmark/run_handoff_trial.py",
            str(manifest_path),
            "--var",
            base_var,
            "--readiness-report",
            str(readiness_json),
            "--out-json",
            str(trial_json),
            "--out-md",
            str(trial_md),
            "--require-external-evidence",
        ],
        "verify_trial": [
            "python3",
            "benchmark/verify_external_trial_report.py",
            str(trial_json),
            "--trial-root",
            str(workspace),
            "--json-out",
            str(trial_verification),
        ],
        "verify_trial_report": [
            "python3",
            "benchmark/verify_external_trial_report.py",
            "--verify-report",
            str(trial_verification),
            "--verify-report-files",
            "--require-report-pass",
        ],
        "package_evidence": [
            "python3",
            "benchmark/package_external_trial.py",
            "--trial-json",
            str(trial_json),
            "--trial-root",
            str(workspace),
            "--out-dir",
            str(package_out),
            "--package-name",
            package_name,
        ],
        "verify_package": [
            "python3",
            "benchmark/verify_external_evidence_package.py",
            str(package_dir),
            "--trial-json",
            str(trial_json),
            "--json-out",
            str(package_verification),
        ],
        "verify_package_report": [
            "python3",
            "benchmark/verify_external_evidence_package.py",
            "--verify-report",
            str(package_verification),
            "--verify-report-files",
            "--require-report-pass",
            "--require-trial-json",
        ],
        "local_evidence_preflight": [
            "python3",
            "benchmark/run_production_gate.py",
            "--local-evidence-preflight-only",
            "--external-trial-json",
            str(trial_json),
            "--external-trial-root",
            str(workspace),
            "--external-evidence-package-dir",
            str(package_dir),
            "--external-trial-verification-report",
            str(trial_verification),
            "--external-evidence-package-verification-report",
            str(package_verification),
            "--github-release-tag",
            STABLE_RELEASE_TAG,
            "--local-evidence-preflight-json",
            str(preflight_json),
            "--local-evidence-preflight-md",
            str(preflight_md),
        ],
        "verify_local_evidence_preflight": [
            "python3",
            "benchmark/run_production_gate.py",
            "--verify-local-evidence-preflight-report",
            str(preflight_json),
            "--verify-local-evidence-preflight-files",
            "--verify-local-evidence-preflight-gates",
            "--require-local-evidence-preflight-pass",
        ],
        "verify_stable_release": [
            "python3",
            "benchmark/verify_github_release.py",
            STABLE_RELEASE_TAG,
            "--repo",
            STABLE_RELEASE_REPO,
            "--out-dir",
            str(github_release_dir),
            "--expect-commit",
            github_workflow_commit,
            "--expect-stable",
            "--json-out",
            str(github_release_verification),
        ],
        "verify_stable_release_report": [
            "python3",
            "benchmark/verify_github_release.py",
            "--verify-report",
            str(github_release_verification),
            "--verify-report-files",
            "--require-report-pass",
            "--require-stable-report",
            "--verify-git-commit",
            "--expect-tag",
            STABLE_RELEASE_TAG,
            "--expect-repo",
            STABLE_RELEASE_REPO,
            "--expect-commit",
            github_workflow_commit,
        ],
        "verify_github_workflows": [
            "python3",
            "benchmark/verify_github_workflows.py",
            "--repo",
            STABLE_RELEASE_REPO,
            "--branch",
            "main",
            "--commit",
            github_workflow_commit,
            "--json-out",
            str(github_workflow_verification),
        ],
        "verify_github_workflows_report": [
            "python3",
            "benchmark/verify_github_workflows.py",
            "--verify-report",
            str(github_workflow_verification),
            "--require-report-pass",
            "--expect-repo",
            STABLE_RELEASE_REPO,
            "--expect-branch",
            "main",
            "--expect-commit",
            github_workflow_commit,
            "--expect-workflow",
            "ci.yml",
            "--expect-workflow",
            "external-l4-rehearsal.yml",
        ],
        "audit_production_evidence": [
            "python3",
            "benchmark/audit_production_evidence.py",
            "--external-trial-json",
            str(trial_json),
            "--external-trial-root",
            str(workspace),
            "--external-evidence-package-dir",
            str(package_dir),
            "--external-trial-verification-report",
            str(trial_verification),
            "--external-evidence-package-verification-report",
            str(package_verification),
            "--github-release-verification-report",
            str(github_release_verification),
            "--github-workflow-verification-report",
            str(github_workflow_verification),
            "--github-release-tag",
            STABLE_RELEASE_TAG,
            "--verify-live-github-release",
            "--out-json",
            str(production_evidence_audit_json),
            "--out-md",
            str(production_evidence_audit_md),
        ],
        "verify_production_evidence_audit": [
            "python3",
            "benchmark/audit_production_evidence.py",
            "--verify-report",
            str(production_evidence_audit_json),
            "--verify-report-files",
            "--require-ready",
        ],
        "final_production_gate": [
            "python3",
            "benchmark/run_production_gate.py",
            "--external-trial-json",
            str(trial_json),
            "--external-trial-root",
            str(workspace),
            "--external-evidence-package-dir",
            str(package_dir),
            "--external-trial-verification-report",
            str(trial_verification),
            "--external-evidence-package-verification-report",
            str(package_verification),
            "--github-release-verification-report",
            str(github_release_verification),
            "--github-workflow-verification-report",
            str(github_workflow_verification),
            "--production-evidence-audit-report",
            str(production_evidence_audit_json),
            "--github-release-tag",
            STABLE_RELEASE_TAG,
            "--out-json",
            str(production_claim_json),
            "--out-md",
            str(production_claim_md),
        ],
        "verify_final_production_report": [
            "python3",
            "benchmark/verify_release_gate_report.py",
            str(production_claim_json),
            "--require-report-pass",
            "--require-clean-git-metadata",
            "--verify-git-commit",
            "--require-production-claim-pass",
            "--expect-missing-checks",
            "none",
        ],
    }


def final_gate_requirement_bindings(workspace: Path, package_name: str) -> list[dict[str, str]]:
    package_dir = workspace / "evidence-package" / package_name
    return [
        {
            "name": "external_l4_workflow_trial",
            "status": "PENDING_EXTERNAL_EVIDENCE",
            "planned_path": str(workspace / "handoff_trial.json"),
            "verification_step": "verify_trial",
            "final_gate_flag": "--external-trial-json",
            "final_gate_value": str(workspace / "handoff_trial.json"),
        },
        {
            "name": "external_l4_evidence_package",
            "status": "PENDING_EXTERNAL_EVIDENCE",
            "planned_path": str(package_dir),
            "verification_step": "verify_package",
            "final_gate_flag": "--external-evidence-package-dir",
            "final_gate_value": str(package_dir),
        },
        {
            "name": "external_l4_trial_saved_reviewer_report",
            "status": "PENDING_EXTERNAL_REVIEW",
            "planned_path": str(workspace / "handoff_trial-verification.json"),
            "verification_step": "verify_trial_report",
            "final_gate_flag": "--external-trial-verification-report",
            "final_gate_value": str(workspace / "handoff_trial-verification.json"),
        },
        {
            "name": "external_l4_package_saved_reviewer_report",
            "status": "PENDING_EXTERNAL_REVIEW",
            "planned_path": str(workspace / "evidence-package-verification.json"),
            "verification_step": "verify_package_report",
            "final_gate_flag": "--external-evidence-package-verification-report",
            "final_gate_value": str(workspace / "evidence-package-verification.json"),
        },
        {
            "name": "stable_github_release",
            "status": "PENDING_STABLE_RELEASE",
            "planned_path": STABLE_RELEASE_URL,
            "verification_step": "verify_stable_release",
            "final_gate_flag": "--github-release-tag",
            "final_gate_value": STABLE_RELEASE_TAG,
        },
        {
            "name": "stable_github_release_saved_report",
            "status": "PENDING_STABLE_RELEASE",
            "planned_path": str(workspace / "github-release-verification.json"),
            "verification_step": "verify_stable_release_report",
            "final_gate_flag": "--github-release-verification-report",
            "final_gate_value": str(workspace / "github-release-verification.json"),
        },
        {
            "name": "github_actions_workflow_verification",
            "status": "PENDING_REMOTE_CI_VERIFICATION",
            "planned_path": str(workspace / "github-workflow-verification.json"),
            "verification_step": "verify_github_workflows_report",
            "final_gate_flag": "--github-workflow-verification-report",
            "final_gate_value": str(workspace / "github-workflow-verification.json"),
        },
        {
            "name": "production_evidence_readiness_audit",
            "status": "PENDING_FINAL_GATE",
            "planned_path": str(workspace / "production-evidence-audit.json"),
            "verification_step": "verify_production_evidence_audit",
            "final_gate_flag": "--production-evidence-audit-report",
            "final_gate_value": str(workspace / "production-evidence-audit.json"),
        },
    ]


def final_signoff_requirements(workspace: Path, package_name: str) -> list[dict[str, str]]:
    requirements = [
        {
            "name": binding["name"],
            "status": binding["status"],
            "planned_path": binding["planned_path"],
            "verification_step": binding["verification_step"],
            "required_for": f"final_production_gate {binding['final_gate_flag']}",
        }
        for binding in final_gate_requirement_bindings(workspace, package_name)
    ]
    requirements.append(
        {
            "name": "final_production_claim_report",
            "status": "PENDING_FINAL_GATE",
            "planned_path": str(workspace / "production-claim.json"),
            "verification_step": "verify_final_production_report",
            "required_for": "production_signoff",
        }
    )
    return requirements


def pre_signoff_requirements(workspace: Path) -> list[dict[str, str]]:
    return [
        {
            "name": "external_l4_readiness_precheck",
            "status": "PENDING_EXTERNAL_EVIDENCE",
            "planned_path": str(workspace / "readiness.json"),
            "verification_step": "verify_readiness",
            "required_before": "run_trial",
        },
        {
            "name": "local_evidence_preflight_report",
            "status": "PENDING_EXTERNAL_EVIDENCE",
            "planned_path": str(workspace / "local-evidence-preflight.json"),
            "verification_step": "verify_local_evidence_preflight",
            "required_before": "verify_stable_release",
        },
        {
            "name": "external_l4_trial_saved_reviewer_report",
            "status": "PENDING_EXTERNAL_REVIEW",
            "planned_path": str(workspace / "handoff_trial-verification.json"),
            "verification_step": "verify_trial_report",
            "required_before": "local_evidence_preflight",
        },
        {
            "name": "external_l4_package_saved_reviewer_report",
            "status": "PENDING_EXTERNAL_REVIEW",
            "planned_path": str(workspace / "evidence-package-verification.json"),
            "verification_step": "verify_package_report",
            "required_before": "local_evidence_preflight",
        },
        {
            "name": "production_evidence_readiness_audit",
            "status": "PENDING_FINAL_GATE",
            "planned_path": str(workspace / "production-evidence-audit.json"),
            "verification_step": "verify_production_evidence_audit",
            "required_before": "final_production_gate",
        },
    ]


def production_claim_blockers(workspace: Path, package_name: str) -> list[dict[str, Any]]:
    final_requirement_bindings = {
        binding["name"]: binding for binding in final_gate_requirement_bindings(workspace, package_name)
    }
    blocker_requirement_groups = {
        "external_l4_workflow_trial": ["external_l4_workflow_trial"],
        "external_l4_evidence_package": ["external_l4_evidence_package"],
        "external_l4_saved_reviewer_reports": [
            "external_l4_trial_saved_reviewer_report",
            "external_l4_package_saved_reviewer_report",
        ],
        "stable_github_release": ["stable_github_release"],
        "stable_github_release_saved_report": ["stable_github_release_saved_report"],
        "github_actions_workflow_verification": ["github_actions_workflow_verification"],
    }
    blocker_bindings: dict[str, dict[str, Any]] = {
        "clean_git_worktree": {
            "status": "PENDING_FINAL_GATE",
            "planned_paths": [str(workspace / "production-claim.json")],
            "final_gate_bindings": ["run_production_gate.py --require-clean-git"],
        },
        "l3_provenance_hashes": {
            "status": "PENDING_FINAL_GATE",
            "planned_paths": [str(workspace / "production-claim.json")],
            "final_gate_bindings": ["run_production_gate.py --require-l3-provenance"],
        },
    }
    for blocker_name, requirement_names in blocker_requirement_groups.items():
        requirements = [final_requirement_bindings[name] for name in requirement_names]
        blocker_bindings[blocker_name] = {
            "status": requirements[0]["status"],
            "planned_paths": [requirement["planned_path"] for requirement in requirements],
            "final_gate_bindings": [
                f"final_production_gate {requirement['final_gate_flag']}"
                for requirement in requirements
            ],
        }
    blockers: list[dict[str, Any]] = []
    for name in release_gate.PRODUCTION_FINAL_BLOCKER_NAMES:
        guidance = release_gate.PRODUCTION_CHECKLIST_GUIDANCE[name]
        binding = blocker_bindings[name]
        blockers.append(
            {
                "name": name,
                "status": binding["status"],
                "required_evidence": guidance["evidence"],
                "next_action": guidance["next_action"],
                "planned_paths": binding["planned_paths"],
                "final_gate_bindings": binding["final_gate_bindings"],
            }
        )
    return blockers


def render_readme(plan: dict[str, Any]) -> str:
    commands = plan["commands"]
    lines = [
        "# External L4 Trial Workspace",
        "",
        "Language: English | [简体中文](README.zh-CN.md)",
        "",
        "This workspace is a preparation scaffold, not external L4 evidence.",
        f"trial_plan.json claim_status: `{plan['claim_status']}`",
        f"trial_plan.json evidence_scope: `{plan['evidence_scope']}`",
        f"trial_plan.json final_production_signoff: `{plan['final_production_signoff']}`",
        f"trial_plan.json git_commit: `{plan['git_commit']}`",
        "The saved package verifier report produced by `verify_package` is also not final production signoff: `claim_status=NOT_PRODUCTION_CLAIM`, `evidence_scope=EXTERNAL_L4_EVIDENCE_PACKAGE_REVIEW`, `final_production_signoff=false`.",
        "The saved local preflight report produced by `local_evidence_preflight` is also not final production signoff: it must remain `claim_status=NOT_PRODUCTION_CLAIM`, `evidence_scope=LOCAL_EXTERNAL_L4_PREFLIGHT`, and `final_evidence_acceptable=false`.",
        "The saved production evidence audit produced by `audit_production_evidence` is also not final production signoff: it must remain `claim_status=NOT_PRODUCTION_CLAIM`, `evidence_scope=PRODUCTION_EVIDENCE_READINESS_AUDIT`, and `final_production_signoff=false`. It must be rechecked with `--verify-report-files --require-ready` before `final_production_gate` runs.",
        "The saved GitHub Actions workflow verifier report must be generated with `--commit` and rechecked with `--expect-commit` for the `trial_plan.json git_commit`, so branch movement cannot replace the final remote-CI evidence.",
        "The live stable release verifier command must also use `--expect-commit` for the same `trial_plan.json git_commit`, so the release tag, downloaded archives, `morphojet doctor` commit prefix, and final workflow evidence all point to the same planned commit before signoff.",
        "The saved stable release verifier report must also be rechecked with `--expect-commit` for the same `trial_plan.json git_commit`, so an older saved release report cannot satisfy the final report slot.",
        "Chinese-community reviewers can use `README.zh-CN.md` as a first-class review entrypoint. It must preserve the same command order, non-final claim labels, pre-signoff requirements, final blockers, and package README evidence path as this English README.",
        "The saved trial-plan signoff command must pair `--require-plan-files` with `--verify-plan-files`, so a structurally valid `trial_plan.json` cannot be accepted before rechecking the template, manifest, and English plus Chinese README files.",
        "`check_readiness` also verifies the saved `trial_plan.json`, template hash, manifest presence, and both English and Chinese README files before returning READY, so readiness fails if the execution instructions or plan are weakened after workspace preparation. The saved readiness signoff command must pair `--require-ready` with `--verify-report-files`; otherwise the saved READY JSON is rejected instead of being treated as reviewer-ready evidence.",
        "`check_readiness` also enforces any `required_object_metadata_columns` declared in the manifest. If the template keeps `Plate`, `Well`, and `Site`, generate MorphoJet `Objects.csv` with `measure --include-object-metadata` so those columns are present before the external trial runs.",
        "`run_trial` re-verifies the saved READY report and refuses to execute if its manifest or workspace does not match the current trial manifest and `base_dir`. It also passes declared object metadata columns through to the wide CSV and allows those same columns during supported-subset comparison.",
        "`verify_trial_report` and `verify_package_report` re-check the saved reviewer reports with file hashing and PASS enforcement before local preflight or final signoff can treat those reports as reviewer evidence. Their saved-report signoff commands must pair `--require-report-pass` with `--verify-report-files`; otherwise the saved reviewer JSON is rejected instead of being treated as signed evidence.",
        "`verify_local_evidence_preflight` rejects non-stable saved `github_release_tag` values, requires clean saved git metadata when `--require-local-evidence-preflight-pass` is used, rehashes the source trial JSON, packaged trial JSON, package `artifact_manifest.json`, package `readiness.json`, package `README.md`, package `README.zh-CN.md`, zip, checksum, and reviewer reports; it also requires required input-artifact summaries to remain `exists=true`, only treats saved reviewer reports as validated when both saved reviewer verifier gates pass, requires metadata-bound saved reviewer reports to keep matching gate entries and hash summaries, and recomputes the source/package trial claim-scope labels, package-manifest package/source-trial scope labels, packaged readiness READY status, `claim_status=NOT_PRODUCTION_CLAIM`, `evidence_scope=EXTERNAL_L4_READINESS_PRECHECK`, `final_production_signoff=false`, UTC generation time, `package_name`, workspace, manifest, package README-rendered readiness scope, package README-rendered handoff contract binding to `rendered_manifest.json`, and package README `review_entrypoint_present` values for both `README.md` and `README.zh-CN.md` before PASS can be accepted. The saved local preflight Markdown also renders those values in the `Review Entrypoint` input-artifact column.",
        "Replace all `REPLACE_WITH` values in the manifest and place the real input files before running the trial.",
        "",
        "Expected input files:",
        "",
        f"- `{plan['workspace']}/morphojet/Objects.csv`",
        f"- `{plan['workspace']}/cellprofiler/Cells.csv`",
        "",
        "External evidence requirements recorded in `trial_plan.json`:",
        "",
        "| Field | Requirement |",
        "|---|---|",
    ]
    for field in plan["external_evidence_requirements"]["required_fields"]:
        lines.append(f"| `{field}` | required, non-placeholder value |")
    lines.extend(
        [
            f"| `manual_csv_editing` | must be `{plan['external_evidence_requirements']['manual_csv_editing']}` |",
            "| `reviewed_at_utc` | must include a UTC timezone offset |",
            "| `acceptance_criteria` | at least "
            f"{plan['external_evidence_requirements']['acceptance_criteria_min_count']} non-placeholder items |",
            "",
            "`validate_manifest` and `run_trial` both enforce these requirements with `--require-external-evidence`, and `verify_plan` rejects a saved plan whose external evidence contract has been removed or weakened.",
            "",
        ]
    )
    lines.extend(
        [
            "Run these commands from the MorphoJet repository root:",
            "",
        ]
    )
    for name in [
        "verify_plan",
        "validate_manifest",
        "check_readiness",
        "verify_readiness",
        "run_trial",
        "verify_trial",
        "verify_trial_report",
        "package_evidence",
        "verify_package",
        "verify_package_report",
        "local_evidence_preflight",
        "verify_local_evidence_preflight",
        "verify_stable_release",
        "verify_stable_release_report",
        "verify_github_workflows",
        "verify_github_workflows_report",
        "audit_production_evidence",
        "verify_production_evidence_audit",
        "final_production_gate",
        "verify_final_production_report",
    ]:
        lines.extend(
            [
                f"## {name}",
                "",
                "```bash",
                command_line(commands[name]),
                "```",
                "",
            ]
        )
    lines.extend(
        [
            "## pre_signoff_requirements",
            "",
            "| Requirement | Status | Planned Path | Verification Step | Required Before |",
            "|---|---:|---|---|---|",
        ]
    )
    for requirement in plan.get("pre_signoff_requirements", []):
        lines.append(
            "| "
            f"{requirement['name']} | "
            f"{requirement['status']} | "
            f"{requirement['planned_path']} | "
            f"{requirement['verification_step']} | "
            f"{requirement['required_before']} |"
        )
    lines.extend(
        [
            "",
            "## final_signoff_requirements",
            "",
            "| Requirement | Status | Planned Path | Verification Step | Required For |",
            "|---|---:|---|---|---|",
        ]
    )
    for requirement in plan.get("final_signoff_requirements", []):
        lines.append(
            "| "
            f"{requirement['name']} | "
            f"{requirement['status']} | "
            f"{requirement['planned_path']} | "
            f"{requirement['verification_step']} | "
            f"{requirement['required_for']} |"
        )
    lines.extend(
        [
            "",
            "The final production gate still requires the completed external trial, evidence package, saved reviewer reports, a live stable release verification, a saved stable release verifier report, and a saved GitHub Actions workflow verifier report in one passing report.",
            "The final verification command re-checks that saved production-claim report before signoff.",
            "",
            "## production_claim_blockers",
            "",
            "| Blocker | Status | Required Evidence | Next Action | Planned Paths | Final Gate Binding |",
            "|---|---:|---|---|---|---|",
        ]
    )
    for blocker in plan.get("production_claim_blockers", []):
        lines.append(
            "| "
            f"{blocker['name']} | "
            f"{blocker['status']} | "
            f"{blocker['required_evidence']} | "
            f"{blocker['next_action']} | "
            f"{', '.join(blocker['planned_paths'])} | "
            f"{', '.join(blocker['final_gate_bindings'])} |"
        )
    lines.extend(
        [
            "",
        ]
    )
    return "\n".join(lines)


def render_readme_zh(plan: dict[str, Any]) -> str:
    commands = plan["commands"]
    lines = [
        "# 外部 L4 试验工作区",
        "",
        "Language: [English](README.md) | 简体中文",
        "",
        "这个工作区只是准备脚手架，不是外部 L4 证据。",
        f"trial_plan.json claim_status：`{plan['claim_status']}`",
        f"trial_plan.json evidence_scope：`{plan['evidence_scope']}`",
        f"trial_plan.json final_production_signoff：`{plan['final_production_signoff']}`",
        f"trial_plan.json git_commit：`{plan['git_commit']}`",
        "`verify_package` 生成的 saved package verifier report 也不是最终生产签核：`claim_status=NOT_PRODUCTION_CLAIM`、`evidence_scope=EXTERNAL_L4_EVIDENCE_PACKAGE_REVIEW`、`final_production_signoff=false`。",
        "`local_evidence_preflight` 生成的 saved local preflight report 也不是最终生产签核：它必须保持 `claim_status=NOT_PRODUCTION_CLAIM`、`evidence_scope=LOCAL_EXTERNAL_L4_PREFLIGHT`、`final_evidence_acceptable=false`。",
        "`audit_production_evidence` 生成的 saved production evidence audit 也不是最终生产签核：它必须保持 `claim_status=NOT_PRODUCTION_CLAIM`、`evidence_scope=PRODUCTION_EVIDENCE_READINESS_AUDIT`、`final_production_signoff=false`。它必须在 `final_production_gate` 运行前用 `--verify-report-files --require-ready` 重新复核。",
        "Saved GitHub Actions workflow verifier report 必须用 `--commit` 生成，并用 `--expect-commit` 复核到 `trial_plan.json git_commit`，避免 main 分支移动后替换最终远端 CI 证据。",
        "Live stable release verifier command 也必须用 `--expect-commit` 绑定同一个 `trial_plan.json git_commit`，确保 release tag、下载 archive、`morphojet doctor` commit prefix 和最终 workflow evidence 在签核前都指向同一个计划 commit。",
        "Saved stable release verifier report 也必须用 `--expect-commit` 复核到同一个 `trial_plan.json git_commit`，防止旧 commit 的 saved release report 填进最终报告槽位。",
        "中文社区 reviewer 可以把 `README.zh-CN.md` 作为一等复核入口。它必须保留与英文 README 相同的命令顺序、非最终 claim labels、pre-signoff requirements、最终阻塞项和 package README evidence path。",
        "Saved trial-plan 签核命令必须把 `--require-plan-files` 和 `--verify-plan-files` 配对使用；这样结构正确的 `trial_plan.json` 也必须重新复核 template、manifest、英文 README 和中文 README 文件后才可被接受。",
        "`check_readiness` 在返回 READY 前也会复核 saved `trial_plan.json`、template hash、manifest 是否存在，以及英文和中文 README 文件；如果 workspace 准备后执行说明或计划被改弱，readiness 会失败。Saved readiness 签核命令必须把 `--require-ready` 和 `--verify-report-files` 配对使用；否则 saved READY JSON 会被拒绝，不能当作 reviewer-ready evidence。",
        "`check_readiness` 也会强制检查 manifest 里的 `required_object_metadata_columns`。如果模板保留 `Plate`、`Well`、`Site`，请用 `measure --include-object-metadata` 生成 MorphoJet `Objects.csv`，确保外部 trial 运行前这些列已经存在。",
        "`run_trial` 会重新复核 saved READY report，并且在 report 的 manifest 或 workspace 与当前 trial manifest 和 `base_dir` 不一致时拒绝执行。它也会把声明过的 object metadata columns 带进宽表，并在 supported-subset comparison 中允许这些同一批列。",
        "`verify_trial_report` 和 `verify_package_report` 会用 file hashing 和 PASS enforcement 重新复核 saved reviewer reports；local preflight 或最终签核只有在这些复核通过后，才可把它们当成 reviewer evidence。它们的 saved-report 签核命令必须把 `--require-report-pass` 和 `--verify-report-files` 配对使用；否则 saved reviewer JSON 会被拒绝，不能当作已签核证据。",
        "`verify_local_evidence_preflight` 会拒绝非稳定版 saved `github_release_tag`，并在使用 `--require-local-evidence-preflight-pass` 时要求 saved git metadata 干净，然后重新 hash source trial JSON、package 内 trial JSON、package `artifact_manifest.json`、package `readiness.json`、package `README.md`、package `README.zh-CN.md`、zip、checksum 和 reviewer reports；它还要求必需的 input-artifact summaries 保持 `exists=true`；只有两条 saved reviewer verifier gates 都 PASS 时，它才会把 saved reviewer reports 当作 validated，并且仍要求 metadata 绑定的 saved reviewer reports 保留对应 gate entries 和 hash summaries，再重新计算 source/package trial claim-scope labels、package manifest 的 package/source-trial scope labels、packaged readiness 的 READY 状态、`claim_status=NOT_PRODUCTION_CLAIM`、`evidence_scope=EXTERNAL_L4_READINESS_PRECHECK`、`final_production_signoff=false`、UTC 生成时间、`package_name`、workspace、manifest、package README 渲染出的 readiness scope、package README 渲染出的 handoff contract 与 `rendered_manifest.json` 的绑定，以及 `README.md` 和 `README.zh-CN.md` 的 package README `review_entrypoint_present` 值，全部通过后才可接受 PASS。Saved local preflight Markdown 也会在 `Review Entrypoint` input-artifact 列渲染这些值。",
        "运行 trial 前，请替换 manifest 中所有 `REPLACE_WITH` 值，并放入真实输入文件。",
        "",
        "预期输入文件：",
        "",
        f"- `{plan['workspace']}/morphojet/Objects.csv`",
        f"- `{plan['workspace']}/cellprofiler/Cells.csv`",
        "",
        "`trial_plan.json` 记录的外部证据要求：",
        "",
        "| 字段 | 要求 |",
        "|---|---|",
    ]
    for field in plan["external_evidence_requirements"]["required_fields"]:
        lines.append(f"| `{field}` | 必填，且不能保留 placeholder |")
    lines.extend(
        [
            f"| `manual_csv_editing` | 必须是 `{plan['external_evidence_requirements']['manual_csv_editing']}` |",
            "| `reviewed_at_utc` | 必须包含 UTC 时区偏移 |",
            "| `acceptance_criteria` | 至少 "
            f"{plan['external_evidence_requirements']['acceptance_criteria_min_count']} 条非 placeholder 项 |",
            "",
            "`validate_manifest` 和 `run_trial` 都会通过 `--require-external-evidence` 强制这些要求；如果 saved plan 里的外部证据合同被删除或改弱，`verify_plan` 会拒绝通过。",
            "",
        ]
    )
    lines.extend(
        [
            "请在 MorphoJet 仓库根目录按顺序运行这些命令：",
            "",
        ]
    )
    for name in [
        "verify_plan",
        "validate_manifest",
        "check_readiness",
        "verify_readiness",
        "run_trial",
        "verify_trial",
        "verify_trial_report",
        "package_evidence",
        "verify_package",
        "verify_package_report",
        "local_evidence_preflight",
        "verify_local_evidence_preflight",
        "verify_stable_release",
        "verify_stable_release_report",
        "verify_github_workflows",
        "verify_github_workflows_report",
        "audit_production_evidence",
        "verify_production_evidence_audit",
        "final_production_gate",
        "verify_final_production_report",
    ]:
        lines.extend(
            [
                f"## {name}",
                "",
                "```bash",
                command_line(commands[name]),
                "```",
                "",
            ]
        )
    lines.extend(
        [
            "## pre_signoff_requirements",
            "",
            "| 要求 | 状态 | 计划路径 | 验证步骤 | 前置于 |",
            "|---|---:|---|---|---|",
        ]
    )
    for requirement in plan.get("pre_signoff_requirements", []):
        lines.append(
            "| "
            f"{requirement['name']} | "
            f"{requirement['status']} | "
            f"{requirement['planned_path']} | "
            f"{requirement['verification_step']} | "
            f"{requirement['required_before']} |"
        )
    lines.extend(
        [
            "",
            "## final_signoff_requirements",
            "",
            "| 要求 | 状态 | 计划路径 | 验证步骤 | 用于 |",
            "|---|---:|---|---|---|",
        ]
    )
    for requirement in plan.get("final_signoff_requirements", []):
        lines.append(
            "| "
            f"{requirement['name']} | "
            f"{requirement['status']} | "
            f"{requirement['planned_path']} | "
            f"{requirement['verification_step']} | "
            f"{requirement['required_for']} |"
        )
    lines.extend(
        [
            "",
            "最终生产门禁仍然要求同一份通过报告里同时包含已完成的外部 trial、evidence package、saved reviewer reports、live stable release verification、saved stable release verifier report，以及 saved GitHub Actions workflow verifier report。",
            "最终报告复核命令会在签核前重新检查保存的 production-claim report。",
            "",
            "## production_claim_blockers",
            "",
            "| 阻塞项 | 状态 | 必需证据 | 下一步 | 计划路径 | Final gate binding |",
            "|---|---:|---|---|---|---|",
        ]
    )
    for blocker in plan.get("production_claim_blockers", []):
        lines.append(
            "| "
            f"{blocker['name']} | "
            f"{blocker['status']} | "
            f"{blocker['required_evidence']} | "
            f"{blocker['next_action']} | "
            f"{', '.join(blocker['planned_paths'])} | "
            f"{', '.join(blocker['final_gate_bindings'])} |"
        )
    lines.extend(
        [
            "",
        ]
    )
    return "\n".join(lines)


def generated_paths(workspace: Path) -> list[Path]:
    return [
        workspace / MANIFEST_NAME,
        workspace / PLAN_NAME,
        workspace / README_NAME,
        workspace / README_ZH_NAME,
    ]


def planned_execution_outputs(workspace: Path, package_slug: str) -> list[Path]:
    package_out = workspace / "evidence-package"
    return [
        workspace / "readiness.json",
        workspace / "handoff_trial.json",
        workspace / "handoff_trial.md",
        workspace / "handoff_trial-verification.json",
        workspace / "evidence-package-verification.json",
        workspace / "local-evidence-preflight.json",
        workspace / "local-evidence-preflight.md",
        workspace / "github-release-verification.json",
        workspace / "github-workflow-verification.json",
        workspace / "production-evidence-audit.json",
        workspace / "production-evidence-audit.md",
        workspace / "github-release",
        workspace / "production-claim.json",
        workspace / "production-claim.md",
        package_out / package_slug,
        package_out / f"{package_slug}.zip",
        package_out / f"{package_slug}.zip.sha256",
    ]


def prepare_workspace(
    template_path: Path,
    workspace: Path,
    package_name: str | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    template_path = template_path.resolve()
    workspace = workspace.resolve()
    template = load_json(template_path)
    validate_template(template)
    trial_id = template.get("trial_id")
    if not isinstance(trial_id, str) or not trial_id.strip():
        raise PrepareError("template.trial_id must be a non-empty string")
    package_slug = slugify(package_name or f"external-l4-{trial_id}")
    existing = [path for path in generated_paths(workspace) if path.exists()]
    if existing and not overwrite:
        names = ", ".join(str(path) for path in existing)
        raise PrepareError(f"generated workspace files already exist; pass --overwrite: {names}")
    stale_outputs = [path for path in planned_execution_outputs(workspace, package_slug) if path.exists()]
    if stale_outputs:
        names = ", ".join(str(path) for path in stale_outputs)
        raise PrepareError(f"stale external L4 execution outputs already exist; move or remove them first: {names}")

    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "morphojet").mkdir(exist_ok=True)
    (workspace / "cellprofiler").mkdir(exist_ok=True)
    (workspace / "evidence-package").mkdir(exist_ok=True)

    manifest_path = workspace / MANIFEST_NAME
    write_json(manifest_path, template)
    current_git_commit = git_commit()
    commands = plan_commands(manifest_path, workspace, package_slug, current_git_commit)
    plan = {
        "schema_version": 1,
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": current_git_commit,
        "argv": generator_argv(template_path, workspace, package_name, overwrite),
        "template": str(template_path),
        "template_size_bytes": template_path.stat().st_size,
        "template_sha256": sha256(template_path),
        "workspace": str(workspace),
        "manifest": str(manifest_path),
        "package_name": package_slug,
        "claim_status": CLAIM_STATUS,
        "evidence_scope": EVIDENCE_SCOPE,
        "final_production_signoff": FINAL_PRODUCTION_SIGNOFF,
        "commands": commands,
        "external_evidence_requirements": external_evidence_requirements(),
        "pre_signoff_requirements": pre_signoff_requirements(workspace),
        "final_signoff_requirements": final_signoff_requirements(workspace, package_slug),
        "production_claim_blockers": production_claim_blockers(workspace, package_slug),
    }
    write_json(workspace / PLAN_NAME, plan)
    (workspace / README_NAME).write_text(render_readme(plan), encoding="utf-8")
    (workspace / README_ZH_NAME).write_text(render_readme_zh(plan), encoding="utf-8")
    return plan


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--package-name")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--verify-plan", type=Path, help="Validate a saved external L4 trial_plan.json")
    parser.add_argument("--verify-plan-files", action="store_true", help="Recompute template and command data for a saved trial plan")
    parser.add_argument(
        "--require-plan-files",
        action="store_true",
        help="Reject saved trial plans unless template, manifest, and README files are rechecked",
    )
    args = parser.parse_args()
    if args.verify_plan:
        return verify_saved_plan_with_options(
            args.verify_plan,
            verify_files=args.verify_plan_files,
            require_plan_files=args.require_plan_files,
        )
    if args.workspace is None:
        parser.error("--workspace is required unless --verify-plan is used")

    try:
        template = args.template
        if template == DEFAULT_TEMPLATE and not template.is_absolute():
            template = DEFAULT_TEMPLATE_ABS
        plan = prepare_workspace(
            template,
            args.workspace,
            package_name=args.package_name,
            overwrite=args.overwrite,
        )
    except PrepareError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(plan, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
