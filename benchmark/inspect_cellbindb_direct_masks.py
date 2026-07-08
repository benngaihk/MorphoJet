#!/usr/bin/env python3
"""Inspect CellBinDB direct-mask suitability for MorphoJet M0 oracle use."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zipfile import ZipFile

import numpy as np
from PIL import Image

from prepare_cellbindb import CellBinSample, collect_samples


CLAIM_STATUS = "NOT_PRODUCTION_CLAIM"
EVIDENCE_SCOPE = "CELLBINDB_DIRECT_MASK_INSPECTION"
FINAL_PRODUCTION_SIGNOFF = False


@dataclass(frozen=True)
class SampleInspection:
    key: str
    image_path: str
    instance_mask_path: str
    semantic_mask_path: str | None
    image_width: int
    image_height: int
    mask_width: int
    mask_height: int
    image_dtype: str
    mask_dtype: str
    mask_min: int
    mask_max: int
    positive_label_count: int
    background_zero_present: bool
    passed: bool
    issues: list[str]


def load_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def md5_file(path: Path) -> str:
    digest = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def select_evenly(samples: list[CellBinSample], limit: int | None) -> list[CellBinSample]:
    if limit is None or limit >= len(samples):
        return samples
    if limit <= 0:
        raise ValueError("limit must be positive")
    if limit == 1:
        return [samples[0]]
    indexes = sorted({round(index * (len(samples) - 1) / (limit - 1)) for index in range(limit)})
    return [samples[index] for index in indexes]


def read_tiff_array(archive: ZipFile, name: str) -> np.ndarray:
    with archive.open(name) as handle:
        image = Image.open(handle)
        image.load()
        return np.array(image)


def inspect_sample(archive: ZipFile, sample: CellBinSample) -> SampleInspection:
    issues: list[str] = []
    image_array = read_tiff_array(archive, sample.image)
    mask_array = read_tiff_array(archive, sample.instance_mask)
    if image_array.ndim < 2:
        issues.append("image is not at least 2D")
    if mask_array.ndim != 2:
        issues.append(f"instance mask must be 2D, got shape={mask_array.shape}")
    image_height, image_width = image_array.shape[:2]
    mask_height, mask_width = mask_array.shape[:2]
    if (image_width, image_height) != (mask_width, mask_height):
        issues.append(
            f"image/mask dimensions differ: image={image_width}x{image_height} mask={mask_width}x{mask_height}"
        )
    if np.issubdtype(mask_array.dtype, np.floating):
        issues.append(f"instance mask dtype must be integer, got {mask_array.dtype}")
    mask_min = int(mask_array.min()) if mask_array.size else 0
    mask_max = int(mask_array.max()) if mask_array.size else 0
    if mask_min < 0:
        issues.append(f"instance mask has negative labels: min={mask_min}")
    background_zero_present = bool(np.any(mask_array == 0))
    if not background_zero_present:
        issues.append("instance mask does not contain background label 0")
    positive_labels = np.unique(mask_array[mask_array > 0])
    if positive_labels.size == 0:
        issues.append("instance mask has no positive object labels")
    return SampleInspection(
        key=sample.key,
        image_path=sample.image,
        instance_mask_path=sample.instance_mask,
        semantic_mask_path=sample.semantic_mask,
        image_width=image_width,
        image_height=image_height,
        mask_width=mask_width,
        mask_height=mask_height,
        image_dtype=str(image_array.dtype),
        mask_dtype=str(mask_array.dtype),
        mask_min=mask_min,
        mask_max=mask_max,
        positive_label_count=int(positive_labels.size),
        background_zero_present=background_zero_present,
        passed=not issues,
        issues=issues,
    )


def candidate_from_public_corpora(public_corpora: dict[str, Any], candidate_id: str) -> dict[str, Any]:
    for candidate in public_corpora.get("candidates", []):
        if candidate.get("id") == candidate_id:
            return candidate
    return {}


def build_payload(
    zip_path: Path,
    metadata_path: Path,
    public_corpora_path: Path,
    candidate_id: str,
    sample_limit: int | None,
    minimum_samples: int,
    verify_md5: bool,
    argv: list[str],
) -> dict[str, Any]:
    metadata = load_json_if_exists(metadata_path)
    public_corpora = load_json_if_exists(public_corpora_path)
    candidate = candidate_from_public_corpora(public_corpora, candidate_id)
    samples = collect_samples(zip_path)
    inspected_samples = select_evenly(samples, sample_limit)
    zip_size = zip_path.stat().st_size
    expected_size = metadata.get("size") or candidate.get("primary_file_size_bytes")
    expected_md5 = str(metadata.get("verified_md5") or metadata.get("checksum") or candidate.get("primary_file_md5") or "")
    expected_md5 = expected_md5.removeprefix("md5:")
    observed_md5 = md5_file(zip_path) if verify_md5 else None

    inspections: list[SampleInspection] = []
    with ZipFile(zip_path) as archive:
        for sample in inspected_samples:
            inspections.append(inspect_sample(archive, sample))

    issues: list[str] = []
    if expected_size is not None and int(expected_size) != zip_size:
        issues.append(f"zip size mismatch: expected={expected_size} observed={zip_size}")
    if verify_md5 and expected_md5 and observed_md5 != expected_md5:
        issues.append(f"zip md5 mismatch: expected={expected_md5} observed={observed_md5}")
    if candidate.get("m0_status") != "candidate_direct_masks":
        issues.append(f"candidate m0_status is not candidate_direct_masks: {candidate.get('m0_status')}")
    if not candidate.get("license"):
        issues.append("candidate license is missing")
    if not metadata.get("record_url") and not candidate.get("source_url"):
        issues.append("record/source URL is missing")
    if len(samples) < minimum_samples:
        issues.append(f"CellBinDB sample count is below required threshold: {len(samples)} < {minimum_samples}")
    failed_samples = [item for item in inspections if not item.passed]
    issues.extend(f"{item.key}: {'; '.join(item.issues)}" for item in failed_samples)
    status = "PASS" if not issues else "FAIL"
    return {
        "schema_version": 1,
        "status": status,
        "claim_status": CLAIM_STATUS,
        "evidence_scope": EVIDENCE_SCOPE,
        "final_production_signoff": FINAL_PRODUCTION_SIGNOFF,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "argv": argv,
        "candidate_id": candidate_id,
        "inspection_scope": "FULL" if len(inspected_samples) == len(samples) else "SAMPLED",
        "zip": {
            "path": str(zip_path),
            "size_bytes": zip_size,
            "expected_size_bytes": expected_size,
            "md5_verified": verify_md5,
            "expected_md5": expected_md5 or None,
            "observed_md5": observed_md5,
        },
        "metadata": {
            "path": str(metadata_path),
            "record": metadata.get("record"),
            "record_url": metadata.get("record_url") or candidate.get("source_url"),
            "license": candidate.get("license"),
            "metadata_source": metadata.get("metadata_source"),
        },
        "summary": {
            "total_sample_groups": len(samples),
            "minimum_sample_groups": minimum_samples,
            "inspected_sample_groups": len(inspected_samples),
            "samples_with_semantic_masks": sum(1 for sample in samples if sample.semantic_mask),
            "inspected_positive_label_count": sum(item.positive_label_count for item in inspections),
            "failed_sample_groups": len(failed_samples),
            "issues": issues,
        },
        "inspected_samples": [asdict(item) for item in inspections],
    }


def render_markdown(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "# CellBinDB Direct-Mask Inspection",
        "",
        f"- status: `{payload['status']}`",
        f"- claim_status: `{payload['claim_status']}`",
        f"- evidence_scope: `{payload['evidence_scope']}`",
        f"- final_production_signoff: `{payload['final_production_signoff']}`",
        f"- inspection_scope: `{payload['inspection_scope']}`",
        f"- total_sample_groups: {summary['total_sample_groups']}",
        f"- minimum_sample_groups: {summary['minimum_sample_groups']}",
        f"- inspected_sample_groups: {summary['inspected_sample_groups']}",
        f"- samples_with_semantic_masks: {summary['samples_with_semantic_masks']}",
        f"- inspected_positive_label_count: {summary['inspected_positive_label_count']}",
        f"- failed_sample_groups: {summary['failed_sample_groups']}",
        "",
        "This report verifies CellBinDB's direct-mask input contract for MorphoJet oracle preparation. It is not final production signoff.",
        "",
        "## Archive",
        "",
        f"- path: `{payload['zip']['path']}`",
        f"- size_bytes: {payload['zip']['size_bytes']}",
        f"- expected_size_bytes: {payload['zip']['expected_size_bytes']}",
        f"- md5_verified: `{payload['zip']['md5_verified']}`",
        "",
        "## Issues",
        "",
    ]
    issues = summary["issues"]
    if issues:
        lines.extend(f"- {issue}" for issue in issues)
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Inspected Samples",
            "",
            "| Key | Image Size | Mask Size | Mask DType | Min | Max | Positive Labels | Background 0 | Status |",
            "|---|---:|---:|---|---:|---:|---:|---:|---:|",
        ]
    )
    for sample in payload["inspected_samples"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    sample["key"],
                    f"{sample['image_width']}x{sample['image_height']}",
                    f"{sample['mask_width']}x{sample['mask_height']}",
                    sample["mask_dtype"],
                    str(sample["mask_min"]),
                    str(sample["mask_max"]),
                    str(sample["positive_label_count"]),
                    "yes" if sample["background_zero_present"] else "no",
                    "PASS" if sample["passed"] else "FAIL",
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", type=Path, default=Path("benchmark/data/cellbindb/CellBinDB.zip"))
    parser.add_argument("--metadata-json", type=Path, default=Path("benchmark/data/cellbindb/zenodo_metadata.json"))
    parser.add_argument("--public-corpora", type=Path, default=Path("benchmark/cellprofiler/public_corpora.json"))
    parser.add_argument("--candidate-id", default="cellbindb")
    parser.add_argument("--sample-limit", type=int, default=32)
    parser.add_argument("--minimum-samples", type=int, default=1000)
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--verify-md5", action="store_true")
    parser.add_argument("--require-pass", action="store_true")
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--md-out", type=Path)
    args = parser.parse_args()

    if args.full:
        sample_limit = None
    else:
        sample_limit = args.sample_limit
        if sample_limit <= 0:
            raise SystemExit("--sample-limit must be positive")
    if not args.zip.is_file():
        raise SystemExit(f"CellBinDB zip not found: {args.zip}")
    if args.minimum_samples <= 0:
        raise SystemExit("--minimum-samples must be positive")

    payload = build_payload(
        args.zip,
        args.metadata_json,
        args.public_corpora,
        args.candidate_id,
        sample_limit,
        args.minimum_samples,
        args.verify_md5,
        ["benchmark/inspect_cellbindb_direct_masks.py", *sys.argv[1:]],
    )
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if args.md_out:
        args.md_out.parent.mkdir(parents=True, exist_ok=True)
        args.md_out.write_text(render_markdown(payload), encoding="utf-8")
    if not args.json_out and not args.md_out:
        print(json.dumps(payload, indent=2))
    if args.require_pass and payload["status"] != "PASS":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
