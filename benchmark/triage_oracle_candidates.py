#!/usr/bin/env python3
"""Triage public oracle candidates against MorphoJet's M0 direct-mask contract."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CLAIM_STATUS = "NOT_PRODUCTION_CLAIM"
EVIDENCE_SCOPE = "ORACLE_CANDIDATE_TRIAGE"
FINAL_PRODUCTION_SIGNOFF = False


@dataclass(frozen=True)
class CandidateTriage:
    id: str
    name: str
    source_catalog: str
    source_url: str | None
    license: str | None
    m0_status: str
    m0_contract_status: str
    has_intensity_images: bool
    has_preexisting_label_masks: bool
    label_mask_contract: str
    object_table_status: str
    download_source_recorded: bool
    license_recorded: bool
    reason: str
    next_step: str


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def m0_contract_status(m0_status: str) -> str:
    if m0_status == "direct":
        return "READY"
    if m0_status == "candidate_direct_masks":
        return "NEEDS_INSPECTION"
    if m0_status == "not_direct":
        return "BLOCKED"
    return "UNKNOWN"


def label_mask_contract(m0_status: str) -> str:
    if m0_status == "direct":
        return "pre-existing label masks declared direct"
    if m0_status == "candidate_direct_masks":
        return "candidate says semantic and instance masks exist; inspect files for background 0 and positive integer labels"
    if m0_status == "not_direct":
        return "no pre-existing label masks declared for MorphoJet M0"
    return "not declared"


def object_table_status(m0_status: str, catalog_kind: str) -> str:
    if m0_status == "direct":
        return "ready after manifest validation"
    if m0_status == "candidate_direct_masks":
        return "requires CellProfiler measurement-only oracle materialization"
    if catalog_kind == "cellprofiler_examples":
        return "available only after CellProfiler segmentation or mask-export bridge"
    return "unknown"


def triage_cellprofiler_examples(catalog: dict[str, Any]) -> list[CandidateTriage]:
    source = catalog.get("source", {})
    items: list[CandidateTriage] = []
    for candidate in catalog.get("candidates", []):
        m0_status = str(candidate.get("m0_status", "unknown"))
        source_url = source.get("repo") or source.get("examples_page")
        gap = candidate.get("m0_gap") or "M0 readiness is not declared."
        items.append(
            CandidateTriage(
                id=str(candidate.get("id", "")),
                name=str(candidate.get("path") or candidate.get("id", "")),
                source_catalog="cellprofiler_examples",
                source_url=str(source_url) if source_url else None,
                license=candidate.get("license"),
                m0_status=m0_status,
                m0_contract_status=m0_contract_status(m0_status),
                has_intensity_images=bool(candidate.get("images_glob")),
                has_preexisting_label_masks=m0_status == "direct",
                label_mask_contract=label_mask_contract(m0_status),
                object_table_status=object_table_status(m0_status, "cellprofiler_examples"),
                download_source_recorded=bool(source_url and source.get("pinned_head")),
                license_recorded=bool(candidate.get("license")),
                reason=str(gap),
                next_step="Add the mask-export bridge or select a public direct-mask corpus before using this as an M0 oracle.",
            )
        )
    return items


def triage_public_corpora(catalog: dict[str, Any]) -> list[CandidateTriage]:
    items: list[CandidateTriage] = []
    for candidate in catalog.get("candidates", []):
        m0_status = str(candidate.get("m0_status", "unknown"))
        source_url = candidate.get("source_url")
        next_step = candidate.get("next_step") or "Inspect image/mask layout and license before oracle use."
        items.append(
            CandidateTriage(
                id=str(candidate.get("id", "")),
                name=str(candidate.get("name") or candidate.get("id", "")),
                source_catalog="public_corpora",
                source_url=str(source_url) if source_url else None,
                license=candidate.get("license"),
                m0_status=m0_status,
                m0_contract_status=m0_contract_status(m0_status),
                has_intensity_images=bool(candidate.get("primary_file")),
                has_preexisting_label_masks=m0_status in {"direct", "candidate_direct_masks"},
                label_mask_contract=label_mask_contract(m0_status),
                object_table_status=object_table_status(m0_status, "public_corpora"),
                download_source_recorded=bool(source_url and candidate.get("primary_file")),
                license_recorded=bool(candidate.get("license")),
                reason=str(candidate.get("why") or "No rationale recorded."),
                next_step=str(next_step),
            )
        )
    return items


def summarize(candidates: list[CandidateTriage]) -> dict[str, Any]:
    by_status: dict[str, int] = {}
    for candidate in candidates:
        by_status[candidate.m0_contract_status] = by_status.get(candidate.m0_contract_status, 0) + 1
    ready = [candidate for candidate in candidates if candidate.m0_contract_status == "READY"]
    needs_inspection = [candidate for candidate in candidates if candidate.m0_contract_status == "NEEDS_INSPECTION"]
    blocked = [candidate for candidate in candidates if candidate.m0_contract_status == "BLOCKED"]
    if ready:
        status = "READY_CANDIDATES_PRESENT"
    elif needs_inspection:
        status = "INSPECTION_REQUIRED"
    else:
        status = "NO_M0_DIRECT_CANDIDATE"
    return {
        "status": status,
        "candidate_count": len(candidates),
        "by_m0_contract_status": by_status,
        "ready_candidates": [candidate.id for candidate in ready],
        "needs_inspection_candidates": [candidate.id for candidate in needs_inspection],
        "blocked_candidates": [candidate.id for candidate in blocked],
    }


def build_payload(
    cellprofiler_catalog_path: Path,
    public_corpora_path: Path,
    argv: list[str],
) -> dict[str, Any]:
    candidates = [
        *triage_cellprofiler_examples(load_json(cellprofiler_catalog_path)),
        *triage_public_corpora(load_json(public_corpora_path)),
    ]
    return {
        "schema_version": 1,
        "claim_status": CLAIM_STATUS,
        "evidence_scope": EVIDENCE_SCOPE,
        "final_production_signoff": FINAL_PRODUCTION_SIGNOFF,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "argv": argv,
        "input_catalogs": {
            "cellprofiler_examples": str(cellprofiler_catalog_path),
            "public_corpora": str(public_corpora_path),
        },
        "summary": summarize(candidates),
        "candidates": [asdict(candidate) for candidate in candidates],
    }


def render_markdown(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "# Oracle Candidate Triage",
        "",
        f"- claim_status: `{payload['claim_status']}`",
        f"- evidence_scope: `{payload['evidence_scope']}`",
        f"- final_production_signoff: `{payload['final_production_signoff']}`",
        f"- status: `{summary['status']}`",
        f"- candidate_count: {summary['candidate_count']}",
        f"- ready_candidates: {', '.join(summary['ready_candidates']) or '-'}",
        f"- needs_inspection_candidates: {', '.join(summary['needs_inspection_candidates']) or '-'}",
        f"- blocked_candidates: {', '.join(summary['blocked_candidates']) or '-'}",
        "",
        "This report is a triage aid only. It does not prove production readiness or a final CellProfiler replacement claim.",
        "",
        "## Candidates",
        "",
        "| ID | Catalog | M0 Contract | Images | Pre-existing Masks | Object Table | License | Reason |",
        "|---|---|---|---:|---:|---|---:|---|",
    ]
    for candidate in payload["candidates"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    candidate["id"],
                    candidate["source_catalog"],
                    candidate["m0_contract_status"],
                    "yes" if candidate["has_intensity_images"] else "no",
                    "yes" if candidate["has_preexisting_label_masks"] else "no",
                    candidate["object_table_status"],
                    "yes" if candidate["license_recorded"] else "no",
                    candidate["reason"].replace("\n", " "),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Next Steps",
            "",
            "1. Inspect `NEEDS_INSPECTION` direct-mask candidates for background value 0, positive integer instance labels, matching image/mask dimensions, and license terms.",
            "2. Keep `BLOCKED` CellProfiler examples in L2 smoke scope until label masks are exported or separately sourced.",
            "3. Promote a candidate into the manifest-driven oracle path only after the direct-mask contract is satisfied and recorded in a real benchmark manifest.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cellprofiler-candidates", type=Path, default=Path("benchmark/cellprofiler/candidates.json"))
    parser.add_argument("--public-corpora", type=Path, default=Path("benchmark/cellprofiler/public_corpora.json"))
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--md-out", type=Path)
    args = parser.parse_args()

    payload = build_payload(
        args.cellprofiler_candidates,
        args.public_corpora,
        ["benchmark/triage_oracle_candidates.py", *sys.argv[1:]],
    )
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if args.md_out:
        args.md_out.parent.mkdir(parents=True, exist_ok=True)
        args.md_out.write_text(render_markdown(payload), encoding="utf-8")
    if not args.json_out and not args.md_out:
        print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
