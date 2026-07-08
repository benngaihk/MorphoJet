#!/usr/bin/env python3
"""Unit tests for oracle candidate triage."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmark"))

import triage_oracle_candidates  # noqa: E402


CELLPROFILER_CANDIDATES = ROOT / "benchmark/cellprofiler/candidates.json"
PUBLIC_CORPORA = ROOT / "benchmark/cellprofiler/public_corpora.json"


class OracleCandidateTriageTest(unittest.TestCase):
    def test_catalog_triage_keeps_examples_blocked_and_cellbindb_inspection_only(self) -> None:
        payload = triage_oracle_candidates.build_payload(
            CELLPROFILER_CANDIDATES,
            PUBLIC_CORPORA,
            ["benchmark/triage_oracle_candidates.py"],
        )

        self.assertEqual("NOT_PRODUCTION_CLAIM", payload["claim_status"])
        self.assertEqual("ORACLE_CANDIDATE_TRIAGE", payload["evidence_scope"])
        self.assertFalse(payload["final_production_signoff"])
        self.assertEqual("INSPECTION_REQUIRED", payload["summary"]["status"])
        self.assertEqual(5, payload["summary"]["candidate_count"])
        self.assertEqual([], payload["summary"]["ready_candidates"])
        self.assertIn("cellbindb", payload["summary"]["needs_inspection_candidates"])
        self.assertIn("bbbc039-via-cellbindb", payload["summary"]["needs_inspection_candidates"])
        self.assertIn("example-human", payload["summary"]["blocked_candidates"])

        by_id = {candidate["id"]: candidate for candidate in payload["candidates"]}
        self.assertFalse(by_id["example-human"]["has_preexisting_label_masks"])
        self.assertEqual("BLOCKED", by_id["example-human"]["m0_contract_status"])
        self.assertIn("mask-export bridge", by_id["example-human"]["next_step"])
        self.assertTrue(by_id["cellbindb"]["has_preexisting_label_masks"])
        self.assertEqual("NEEDS_INSPECTION", by_id["cellbindb"]["m0_contract_status"])
        self.assertIn("background 0", by_id["cellbindb"]["label_mask_contract"])

    def test_markdown_renders_non_final_scope_and_candidate_table(self) -> None:
        payload = triage_oracle_candidates.build_payload(
            CELLPROFILER_CANDIDATES,
            PUBLIC_CORPORA,
            ["benchmark/triage_oracle_candidates.py"],
        )

        markdown = triage_oracle_candidates.render_markdown(payload)

        self.assertIn("claim_status: `NOT_PRODUCTION_CLAIM`", markdown)
        self.assertIn("evidence_scope: `ORACLE_CANDIDATE_TRIAGE`", markdown)
        self.assertIn("does not prove production readiness", markdown)
        self.assertIn("| example-human | cellprofiler_examples | BLOCKED |", markdown)
        self.assertIn("| cellbindb | public_corpora | NEEDS_INSPECTION |", markdown)

    def test_cli_writes_json_and_markdown_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            json_out = Path(tmp) / "triage.json"
            md_out = Path(tmp) / "triage.md"

            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "benchmark/triage_oracle_candidates.py"),
                    "--json-out",
                    str(json_out),
                    "--md-out",
                    str(md_out),
                ],
                cwd=ROOT,
                check=True,
            )

            payload = json.loads(json_out.read_text(encoding="utf-8"))
            markdown = md_out.read_text(encoding="utf-8")

        self.assertEqual("ORACLE_CANDIDATE_TRIAGE", payload["evidence_scope"])
        self.assertEqual("INSPECTION_REQUIRED", payload["summary"]["status"])
        self.assertIn("Oracle Candidate Triage", markdown)


if __name__ == "__main__":
    unittest.main()
