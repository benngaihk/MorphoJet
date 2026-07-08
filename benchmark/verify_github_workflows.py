#!/usr/bin/env python3
"""Verify required GitHub Actions workflows for a MorphoJet commit."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import release_gate


VERIFIER = "benchmark/verify_github_workflows.py"
DEFAULT_REPO = release_gate.GITHUB_RELEASE_REPO
DEFAULT_BRANCH = "main"
DEFAULT_WORKFLOWS = ["ci.yml", "external-l4-rehearsal.yml"]
CLAIM_STATUS = release_gate.NON_FINAL_CLAIM_STATUS
EVIDENCE_SCOPE = "GITHUB_ACTIONS_WORKFLOW_VERIFICATION"
FINAL_PRODUCTION_SIGNOFF = release_gate.NON_FINAL_PRODUCTION_SIGNOFF


def is_utc_datetime(value: datetime) -> bool:
    return value.utcoffset() == timezone.utc.utcoffset(value)


def run(command: list[str]) -> str:
    completed = subprocess.run(command, text=True, capture_output=True, check=True)
    return completed.stdout


def git_commit(rev: str = "HEAD") -> str:
    return run(["git", "rev-parse", f"{rev}^{{commit}}"]).strip()


def verifier_argv(
    repo: str,
    branch: str,
    commit: str,
    workflows: list[str],
    json_out: Path | None,
) -> list[str]:
    argv = [
        VERIFIER,
        "--repo",
        repo,
        "--branch",
        branch,
        "--commit",
        commit,
    ]
    for workflow in workflows:
        argv.extend(["--workflow", workflow])
    if json_out is not None:
        argv.extend(["--json-out", str(json_out)])
    return argv


def workflow_runs(repo: str, branch: str, commit: str, workflow: str) -> list[dict[str, Any]]:
    fields = [
        "conclusion",
        "createdAt",
        "databaseId",
        "displayTitle",
        "event",
        "headBranch",
        "headSha",
        "name",
        "status",
        "updatedAt",
        "url",
        "workflowName",
    ]
    output = run(
        [
            "gh",
            "run",
            "list",
            "--repo",
            repo,
            "--workflow",
            workflow,
            "--branch",
            branch,
            "--commit",
            commit,
            "--json",
            ",".join(fields),
            "--limit",
            "10",
        ]
    )
    payload = json.loads(output)
    if not isinstance(payload, list):
        raise ValueError(f"gh run list returned non-list payload for {workflow}")
    return [run for run in payload if isinstance(run, dict)]


def summarize_workflow(repo: str, branch: str, commit: str, workflow: str) -> dict[str, Any]:
    runs = [run for run in workflow_runs(repo, branch, commit, workflow) if run.get("headSha") == commit]
    if not runs:
        return {
            "workflow": workflow,
            "status": "MISSING",
            "conclusion": None,
            "head_sha": commit,
            "run_id": None,
            "url": None,
            "detail": f"no GitHub Actions run found for {workflow} at {commit}",
        }
    latest = runs[0]
    status = latest.get("status")
    conclusion = latest.get("conclusion")
    passed = status == "completed" and conclusion == "success"
    return {
        "workflow": workflow,
        "status": "PASS" if passed else "FAIL",
        "conclusion": conclusion,
        "run_status": status,
        "head_sha": latest.get("headSha"),
        "head_branch": latest.get("headBranch"),
        "run_id": latest.get("databaseId"),
        "url": latest.get("url"),
        "event": latest.get("event"),
        "display_title": latest.get("displayTitle"),
        "created_at": latest.get("createdAt"),
        "updated_at": latest.get("updatedAt"),
        "detail": "workflow completed successfully" if passed else f"workflow status={status} conclusion={conclusion}",
    }


def verify_github_workflows(
    repo: str,
    branch: str,
    commit: str,
    workflows: list[str],
    json_out: Path | None = None,
) -> int:
    summaries = [summarize_workflow(repo, branch, commit, workflow) for workflow in workflows]
    payload = {
        "schema_version": 1,
        "verifier": VERIFIER,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "claim_status": CLAIM_STATUS,
        "evidence_scope": EVIDENCE_SCOPE,
        "final_production_signoff": FINAL_PRODUCTION_SIGNOFF,
        "status": "PASS" if all(summary["status"] == "PASS" for summary in summaries) else "FAIL",
        "repo": repo,
        "branch": branch,
        "commit": commit,
        "workflows": workflows,
        "argv": verifier_argv(repo, branch, commit, workflows, json_out.resolve() if json_out else None),
        "workflow_runs": summaries,
    }
    if json_out is not None:
        json_out = json_out.resolve()
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if payload["status"] == "PASS":
        if json_out:
            print(f"wrote {json_out}")
        print("status=PASS")
        return 0
    for summary in summaries:
        if summary["status"] != "PASS":
            print(f"FAIL: {summary['workflow']}: {summary['detail']}", file=sys.stderr)
    if json_out:
        print(f"wrote {json_out}", file=sys.stderr)
    return 1


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


def validate_report_payload(
    payload: Any,
    report_path: Path | None = None,
    require_report_pass: bool = False,
    expect_commit: str | None = None,
    expect_workflows: list[str] | None = None,
) -> list[str]:
    failures: list[str] = []
    if not isinstance(payload, dict):
        return ["GitHub workflow verification report must be a JSON object"]
    if payload.get("schema_version") != 1:
        failures.append(f"schema_version={payload.get('schema_version')}")
    if payload.get("verifier") != VERIFIER:
        failures.append(f"verifier={payload.get('verifier')}")
    if payload.get("claim_status") != CLAIM_STATUS:
        failures.append(f"claim_status={payload.get('claim_status')}")
    if payload.get("evidence_scope") != EVIDENCE_SCOPE:
        failures.append(f"evidence_scope={payload.get('evidence_scope')}")
    if payload.get("final_production_signoff") is not FINAL_PRODUCTION_SIGNOFF:
        failures.append("final_production_signoff must be false")
    status = payload.get("status")
    if status not in {"PASS", "FAIL"}:
        failures.append(f"status={status}")
    if require_report_pass and status != "PASS":
        failures.append(f"GitHub workflow verification status is not PASS: {status}")
    generated_at = payload.get("generated_at_utc")
    if isinstance(generated_at, str):
        try:
            parsed = datetime.fromisoformat(generated_at)
            if parsed.tzinfo is None:
                failures.append("generated_at_utc must include timezone")
            elif not is_utc_datetime(parsed):
                failures.append("generated_at_utc must be UTC")
        except ValueError:
            failures.append(f"generated_at_utc is invalid: {generated_at}")
    else:
        failures.append("generated_at_utc must be a string")
    repo = payload.get("repo")
    branch = payload.get("branch")
    commit = payload.get("commit")
    workflows = payload.get("workflows")
    if not isinstance(repo, str) or not repo.strip():
        failures.append("repo must be a non-empty string")
    if not isinstance(branch, str) or not branch.strip():
        failures.append("branch must be a non-empty string")
    if not isinstance(commit, str) or not commit.strip():
        failures.append("commit must be a non-empty string")
    if expect_commit is not None and commit != expect_commit:
        failures.append(f"commit does not match expected commit: {commit} != {expect_commit}")
    if not isinstance(workflows, list) or not workflows or not all(isinstance(item, str) and item for item in workflows):
        failures.append("workflows must be a non-empty string list")
    if expect_workflows is not None and workflows != expect_workflows:
        failures.append(f"workflows do not match expected workflows: {workflows} != {expect_workflows}")
    workflow_runs_payload = payload.get("workflow_runs")
    if not isinstance(workflow_runs_payload, list):
        failures.append("workflow_runs must be a list")
    elif isinstance(workflows, list):
        run_names = [run.get("workflow") for run in workflow_runs_payload if isinstance(run, dict)]
        if run_names != workflows:
            failures.append("workflow_runs order must match workflows")
        for run_summary in workflow_runs_payload:
            if not isinstance(run_summary, dict):
                failures.append("workflow_runs entries must be objects")
                continue
            workflow = run_summary.get("workflow")
            run_status = run_summary.get("status")
            if workflow not in workflows:
                failures.append(f"unexpected workflow run entry: {workflow}")
            if run_status not in {"PASS", "FAIL", "MISSING"}:
                failures.append(f"workflow_runs.{workflow}.status={run_status}")
            if require_report_pass and run_status != "PASS":
                failures.append(f"workflow {workflow} is not PASS: {run_status}")
            if run_status == "PASS":
                if run_summary.get("run_status") != "completed":
                    failures.append(f"workflow {workflow} run_status must be completed")
                if run_summary.get("conclusion") != "success":
                    failures.append(f"workflow {workflow} conclusion must be success")
                if run_summary.get("head_sha") != commit:
                    failures.append(f"workflow {workflow} head_sha does not match report commit")
    argv = payload.get("argv")
    if not isinstance(argv, list) or not argv or not all(isinstance(item, str) and item for item in argv):
        failures.append("argv must be a non-empty string list")
    else:
        if argv[0] != VERIFIER:
            failures.append(f"argv[0]={argv[0]}")
        for flag, value in [("--repo", repo), ("--branch", branch), ("--commit", commit)]:
            values = argv_values(argv, flag)
            if len(values) != 1 or values[0] != value:
                failures.append(f"argv must include {flag} {value}")
        if isinstance(workflows, list):
            workflow_values = argv_values(argv, "--workflow")
            if workflow_values != workflows:
                failures.append("argv workflow values must match workflows")
        if report_path is not None:
            json_out_values = argv_values(argv, "--json-out")
            if len(json_out_values) != 1 or json_out_values[0] is None:
                failures.append("argv must include --json-out for saved report")
            elif str(Path(json_out_values[0]).resolve()) != str(report_path.resolve()):
                failures.append("argv --json-out must match saved report path")
    return failures


def verify_saved_report(
    report: Path,
    require_report_pass: bool = False,
    expect_commit: str | None = None,
    expect_workflows: list[str] | None = None,
) -> int:
    try:
        payload = json.loads(report.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - exact report verifier failure.
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    failures = validate_report_payload(
        payload,
        report_path=report,
        require_report_pass=require_report_pass,
        expect_commit=expect_commit,
        expect_workflows=expect_workflows,
    )
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print(f"GitHub workflow verification report ok: {report}")
    print(f"status={payload['status']}")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--branch", default=DEFAULT_BRANCH)
    parser.add_argument("--commit")
    parser.add_argument("--workflow", action="append", dest="workflows")
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--verify-report", type=Path)
    parser.add_argument("--require-report-pass", action="store_true")
    parser.add_argument("--expect-commit")
    parser.add_argument("--expect-workflow", action="append", dest="expect_workflows")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.verify_report:
        return verify_saved_report(
            args.verify_report,
            require_report_pass=args.require_report_pass,
            expect_commit=args.expect_commit,
            expect_workflows=args.expect_workflows,
        )
    commit = args.commit or git_commit()
    workflows = args.workflows or list(DEFAULT_WORKFLOWS)
    try:
        return verify_github_workflows(
            args.repo,
            args.branch,
            commit,
            workflows,
            json_out=args.json_out,
        )
    except Exception as exc:  # noqa: BLE001 - command-line audit should report exact failure.
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
