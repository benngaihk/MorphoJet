#!/usr/bin/env python3
"""Unit tests for GitHub Actions workflow verification."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmark"))

import release_gate  # noqa: E402
import verify_github_workflows  # noqa: E402


class VerifyGithubWorkflowsTest(unittest.TestCase):
    COMMIT = "a" * 40

    def test_defaults_reuse_release_gate_repo(self) -> None:
        self.assertIs(release_gate.GITHUB_RELEASE_REPO, verify_github_workflows.DEFAULT_REPO)
        self.assertEqual(["ci.yml", "external-l4-rehearsal.yml"], verify_github_workflows.DEFAULT_WORKFLOWS)

    def workflow_payload(self, workflow: str, status: str = "completed", conclusion: str = "success") -> list[dict]:
        return [
            {
                "conclusion": conclusion,
                "createdAt": "2026-07-08T00:00:00Z",
                "databaseId": 123,
                "displayTitle": "Test run",
                "event": "push",
                "headBranch": "main",
                "headSha": self.COMMIT,
                "name": workflow,
                "status": status,
                "updatedAt": "2026-07-08T00:01:00Z",
                "url": f"https://github.com/benngaihk/MorphoJet/actions/runs/{workflow}",
                "workflowName": workflow,
            }
        ]

    def valid_saved_report_payload(self, report: Path) -> dict:
        return {
            "schema_version": 1,
            "verifier": "benchmark/verify_github_workflows.py",
            "generated_at_utc": "2026-07-08T00:00:00+00:00",
            "claim_status": "NOT_PRODUCTION_CLAIM",
            "evidence_scope": "GITHUB_ACTIONS_WORKFLOW_VERIFICATION",
            "final_production_signoff": False,
            "status": "PASS",
            "repo": "benngaihk/MorphoJet",
            "branch": "main",
            "commit": self.COMMIT,
            "workflows": ["ci.yml", "external-l4-rehearsal.yml"],
            "argv": [
                "benchmark/verify_github_workflows.py",
                "--repo",
                "benngaihk/MorphoJet",
                "--branch",
                "main",
                "--commit",
                self.COMMIT,
                "--workflow",
                "ci.yml",
                "--workflow",
                "external-l4-rehearsal.yml",
                "--json-out",
                str(report),
            ],
            "workflow_runs": [
                verify_github_workflows.summarize_workflow("benngaihk/MorphoJet", "main", self.COMMIT, "ci.yml"),
                verify_github_workflows.summarize_workflow(
                    "benngaihk/MorphoJet",
                    "main",
                    self.COMMIT,
                    "external-l4-rehearsal.yml",
                ),
            ],
        }

    def test_writes_pass_report_for_required_workflows(self) -> None:
        def fake_run(command: list[str]) -> str:
            workflow = command[command.index("--workflow") + 1]
            return json.dumps(self.workflow_payload(workflow))

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "workflows.json"
            with patch.object(verify_github_workflows, "run", side_effect=fake_run), contextlib.redirect_stdout(io.StringIO()):
                status = verify_github_workflows.verify_github_workflows(
                    "benngaihk/MorphoJet",
                    "main",
                    self.COMMIT,
                    ["ci.yml", "external-l4-rehearsal.yml"],
                    json_out=out,
                )
            payload = json.loads(out.read_text(encoding="utf-8"))

        self.assertEqual(0, status)
        self.assertEqual("PASS", payload["status"])
        self.assertEqual("NOT_PRODUCTION_CLAIM", payload["claim_status"])
        self.assertEqual("GITHUB_ACTIONS_WORKFLOW_VERIFICATION", payload["evidence_scope"])
        self.assertFalse(payload["final_production_signoff"])
        self.assertEqual(["ci.yml", "external-l4-rehearsal.yml"], payload["workflows"])
        self.assertTrue(all(run["status"] == "PASS" for run in payload["workflow_runs"]))

    def test_marks_failed_workflow_report_fail(self) -> None:
        def fake_run(command: list[str]) -> str:
            workflow = command[command.index("--workflow") + 1]
            conclusion = "failure" if workflow == "ci.yml" else "success"
            return json.dumps(self.workflow_payload(workflow, conclusion=conclusion))

        with patch.object(verify_github_workflows, "run", side_effect=fake_run), contextlib.redirect_stderr(io.StringIO()) as stderr:
            status = verify_github_workflows.verify_github_workflows(
                "benngaihk/MorphoJet",
                "main",
                self.COMMIT,
                ["ci.yml", "external-l4-rehearsal.yml"],
            )

        self.assertEqual(1, status)
        self.assertIn("FAIL: ci.yml", stderr.getvalue())

    def test_marks_missing_workflow_run_fail(self) -> None:
        with patch.object(verify_github_workflows, "run", return_value="[]"), contextlib.redirect_stderr(io.StringIO()) as stderr:
            status = verify_github_workflows.verify_github_workflows(
                "benngaihk/MorphoJet",
                "main",
                self.COMMIT,
                ["ci.yml"],
            )

        self.assertEqual(1, status)
        self.assertIn("no GitHub Actions run found", stderr.getvalue())

    def test_saved_report_requires_pass_and_expected_workflows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "workflows.json"
            with patch.object(verify_github_workflows, "workflow_runs") as workflow_runs:
                workflow_runs.side_effect = lambda _repo, _branch, _commit, workflow: self.workflow_payload(workflow)
                payload = self.valid_saved_report_payload(report)
            report.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                status = verify_github_workflows.verify_saved_report(
                    report,
                    require_report_pass=True,
                    expect_commit=self.COMMIT,
                    expect_workflows=["ci.yml", "external-l4-rehearsal.yml"],
                )

        self.assertEqual(0, status)
        self.assertIn("status=PASS", stdout.getvalue())

    def test_saved_report_live_recheck_accepts_matching_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "workflows.json"
            with patch.object(verify_github_workflows, "workflow_runs") as workflow_runs:
                workflow_runs.side_effect = lambda _repo, _branch, _commit, workflow: self.workflow_payload(workflow)
                payload = self.valid_saved_report_payload(report)
            report.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            with (
                patch.object(verify_github_workflows, "workflow_runs") as workflow_runs,
                contextlib.redirect_stdout(io.StringIO()) as stdout,
            ):
                workflow_runs.side_effect = lambda _repo, _branch, _commit, workflow: self.workflow_payload(workflow)
                status = verify_github_workflows.verify_saved_report(report, require_report_pass=True, verify_live_runs=True)

        self.assertEqual(0, status)
        self.assertIn("verified_live_runs=True", stdout.getvalue())

    def test_saved_report_live_recheck_rejects_changed_run_signature(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "workflows.json"
            with patch.object(verify_github_workflows, "workflow_runs") as workflow_runs:
                workflow_runs.side_effect = lambda _repo, _branch, _commit, workflow: self.workflow_payload(workflow)
                payload = self.valid_saved_report_payload(report)
            report.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            with (
                patch.object(verify_github_workflows, "workflow_runs") as workflow_runs,
                contextlib.redirect_stderr(io.StringIO()) as stderr,
            ):
                workflow_runs.side_effect = lambda _repo, _branch, _commit, workflow: self.workflow_payload(
                    workflow,
                    conclusion="failure" if workflow == "ci.yml" else "success",
                )
                status = verify_github_workflows.verify_saved_report(report, require_report_pass=True, verify_live_runs=True)

        self.assertEqual(1, status)
        self.assertIn("live workflow run signatures changed after report was written", stderr.getvalue())

    def test_saved_report_rejects_tampered_workflow_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "workflows.json"
            payload = {
                "schema_version": 1,
                "verifier": "benchmark/verify_github_workflows.py",
                "generated_at_utc": "2026-07-08T00:00:00+00:00",
                "claim_status": "NOT_PRODUCTION_CLAIM",
                "evidence_scope": "GITHUB_ACTIONS_WORKFLOW_VERIFICATION",
                "final_production_signoff": False,
                "status": "PASS",
                "repo": "benngaihk/MorphoJet",
                "branch": "main",
                "commit": self.COMMIT,
                "workflows": ["ci.yml", "external-l4-rehearsal.yml"],
                "argv": ["benchmark/verify_github_workflows.py"],
                "workflow_runs": [
                    {"workflow": "external-l4-rehearsal.yml", "status": "PASS"},
                    {"workflow": "ci.yml", "status": "PASS"},
                ],
            }
            report.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                status = verify_github_workflows.verify_saved_report(report, require_report_pass=True)

        self.assertEqual(1, status)
        self.assertIn("workflow_runs order must match workflows", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
