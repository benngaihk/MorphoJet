#!/usr/bin/env python3
"""Prepare a workspace for a real external L4 handoff trial."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import validate_handoff_manifest


ROOT = Path(__file__).resolve().parents[1]
GENERATOR = "benchmark/prepare_external_l4_trial.py"
DEFAULT_TEMPLATE = Path("benchmark/handoff/external_lab_template.json")
DEFAULT_TEMPLATE_ABS = (ROOT / DEFAULT_TEMPLATE).resolve()
MANIFEST_NAME = "external_manifest.json"
PLAN_NAME = "trial_plan.json"
README_NAME = "README.md"


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
    template_size = payload.get("template_size_bytes")
    if not isinstance(template_size, int) or template_size <= 0:
        failures.append(f"template_size_bytes={template_size}")
    template_sha = payload.get("template_sha256")
    if not isinstance(template_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", template_sha):
        failures.append(f"template_sha256={template_sha}")
    if payload.get("claim_status") != "NOT_PRODUCTION_CLAIM":
        failures.append(f"claim_status={payload.get('claim_status')}")
    commands = payload.get("commands")
    expected_command_names = [
        "verify_plan",
        "validate_manifest",
        "check_readiness",
        "verify_readiness",
        "run_trial",
        "verify_trial",
        "package_evidence",
        "verify_package",
        "local_evidence_preflight",
        "verify_local_evidence_preflight",
        "verify_stable_release",
        "final_production_gate",
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
        if all(isinstance(value, str) and value.strip() for value in [manifest, workspace, package_name]):
            expected_commands = plan_commands(Path(manifest), Path(workspace), package_name)
            if commands != expected_commands:
                failures.append("commands changed after plan was written")
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
    elif readme_path.read_text(encoding="utf-8") != render_readme(payload):
        failures.append("README changed after plan was written")
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
    return 0


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
            "v0.1.0",
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
            "v0.1.0",
            "--repo",
            "benngaihk/MorphoJet",
            "--out-dir",
            str(github_release_dir),
            "--expect-stable",
            "--json-out",
            str(github_release_verification),
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
            "--github-release-tag",
            "v0.1.0",
            "--out-json",
            str(production_claim_json),
            "--out-md",
            str(production_claim_md),
        ],
    }


def render_readme(plan: dict[str, Any]) -> str:
    commands = plan["commands"]
    lines = [
        "# External L4 Trial Workspace",
        "",
        "This workspace is a preparation scaffold, not external L4 evidence.",
        "Replace all `REPLACE_WITH` values in the manifest and place the real input files before running the trial.",
        "",
        "Expected input files:",
        "",
        f"- `{plan['workspace']}/morphojet/Objects.csv`",
        f"- `{plan['workspace']}/cellprofiler/Cells.csv`",
        "",
        "Run these commands from the MorphoJet repository root:",
        "",
    ]
    for name in [
        "verify_plan",
        "validate_manifest",
        "check_readiness",
        "verify_readiness",
        "run_trial",
        "verify_trial",
        "package_evidence",
        "verify_package",
        "local_evidence_preflight",
        "verify_local_evidence_preflight",
        "verify_stable_release",
        "final_production_gate",
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
            "The final production gate still requires the completed external trial, evidence package, and a live stable release verification in one passing report.",
            "",
        ]
    )
    return "\n".join(lines)


def generated_paths(workspace: Path) -> list[Path]:
    return [
        workspace / MANIFEST_NAME,
        workspace / PLAN_NAME,
        workspace / README_NAME,
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
    commands = plan_commands(manifest_path, workspace, package_slug)
    plan = {
        "schema_version": 1,
        "generator": GENERATOR,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "argv": generator_argv(template_path, workspace, package_name, overwrite),
        "template": str(template_path),
        "template_size_bytes": template_path.stat().st_size,
        "template_sha256": sha256(template_path),
        "workspace": str(workspace),
        "manifest": str(manifest_path),
        "package_name": package_slug,
        "claim_status": "NOT_PRODUCTION_CLAIM",
        "commands": commands,
    }
    write_json(workspace / PLAN_NAME, plan)
    (workspace / README_NAME).write_text(render_readme(plan), encoding="utf-8")
    return plan


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--package-name")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--verify-plan", type=Path, help="Validate a saved external L4 trial_plan.json")
    parser.add_argument("--verify-plan-files", action="store_true", help="Recompute template and command data for a saved trial plan")
    args = parser.parse_args()
    if args.verify_plan:
        return verify_saved_plan(args.verify_plan, verify_files=args.verify_plan_files)
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
