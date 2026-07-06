#!/usr/bin/env python3
"""Prepare a workspace for a real external L4 handoff trial."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import sys
from pathlib import Path
from typing import Any

import validate_handoff_manifest


ROOT = Path(__file__).resolve().parents[1]
GENERATOR = "benchmark/prepare_external_l4_trial.py"
DEFAULT_TEMPLATE = Path("benchmark/handoff/external_lab_template.json")
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


def slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-")
    return slug or "external-l4-trial"


def command_line(command: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in command)


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
    trial_json = workspace / "handoff_trial.json"
    trial_md = workspace / "handoff_trial.md"
    trial_verification = workspace / "handoff_trial-verification.json"
    package_out = workspace / "evidence-package"
    package_dir = package_out / package_name
    package_verification = workspace / "evidence-package-verification.json"
    preflight_json = workspace / "local-evidence-preflight.json"
    preflight_md = workspace / "local-evidence-preflight.md"
    base_var = f"base_dir={workspace}"
    return {
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
            str(workspace / "readiness.json"),
        ],
        "run_trial": [
            "python3",
            "benchmark/run_handoff_trial.py",
            str(manifest_path),
            "--var",
            base_var,
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
        "validate_manifest",
        "check_readiness",
        "run_trial",
        "verify_trial",
        "package_evidence",
        "verify_package",
        "local_evidence_preflight",
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


def prepare_workspace(
    template_path: Path,
    workspace: Path,
    package_name: str | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
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
        "template": str(template_path),
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
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--package-name")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    try:
        plan = prepare_workspace(
            args.template,
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
