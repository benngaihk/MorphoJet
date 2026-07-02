#!/usr/bin/env python3
"""Scan local CellProfiler examples for MorphoJet oracle benchmark candidates."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from inspect_cellprofiler_pipeline import collect_summary, parse_pipeline


IMAGE_SUFFIXES = {".tif", ".tiff", ".png", ".jpg", ".jpeg"}


@dataclass
class ExampleScan:
    example: str
    pipeline: str
    raw_image_files: int
    measured_object_sets: list[str]
    measured_image_channels: list[str]
    missing_label_exports: list[str]
    m0_ready: bool
    rough_image_row_upper_bound: int


def count_images(example_dir: Path) -> int:
    image_dir = example_dir / "images"
    if not image_dir.is_dir():
        return 0
    return sum(1 for path in image_dir.rglob("*") if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES)


def iter_pipelines(repo_dir: Path) -> list[Path]:
    pipelines = []
    for path in sorted(repo_dir.glob("Example*/**/*.cppipe")):
        if "CellProfiler3Pipelines" in path.parts:
            continue
        pipelines.append(path)
    return pipelines


def scan(repo_dir: Path) -> list[ExampleScan]:
    scans: list[ExampleScan] = []
    for pipeline in iter_pipelines(repo_dir):
        example = pipeline.relative_to(repo_dir).parts[0]
        image_count = count_images(repo_dir / example)
        summary = collect_summary(parse_pipeline(pipeline))
        objects = summary["measured_objects"]
        channels = summary["measured_images"]
        rough_upper_bound = image_count * max(1, len(objects)) * max(1, len(channels)) if objects else 0
        scans.append(
            ExampleScan(
                example=example,
                pipeline=str(pipeline.relative_to(repo_dir)),
                raw_image_files=image_count,
                measured_object_sets=objects,
                measured_image_channels=channels,
                missing_label_exports=summary["missing_label_exports"],
                m0_ready=summary["m0_ready"],
                rough_image_row_upper_bound=rough_upper_bound,
            )
        )
    scans.sort(key=lambda item: (item.rough_image_row_upper_bound, item.raw_image_files, item.example), reverse=True)
    return scans


def render_markdown(repo_dir: Path, scans: list[ExampleScan]) -> str:
    total_raw = sum(item.raw_image_files for item in scans)
    best = scans[0].rough_image_row_upper_bound if scans else 0
    lines = [
        "# CellProfiler Examples Candidate Scan",
        "",
        f"- repo_dir: `{repo_dir}`",
        f"- pipelines_scanned: {len(scans)}",
        f"- total_raw_image_files: {total_raw}",
        f"- best_rough_image_row_upper_bound: {best}",
        "",
        "## Candidates",
        "",
        "| Example | Pipeline | Raw Images | Objects | Channels | Missing Labels | M0 Ready | Rough Row Upper Bound |",
        "|---|---|---:|---|---|---|---:|---:|",
    ]
    for item in scans:
        lines.append(
            "| "
            + " | ".join(
                [
                    item.example,
                    f"`{item.pipeline}`",
                    str(item.raw_image_files),
                    ", ".join(item.measured_object_sets) or "-",
                    ", ".join(item.measured_image_channels) or "-",
                    ", ".join(item.missing_label_exports) or "-",
                    "yes" if item.m0_ready else "no",
                    str(item.rough_image_row_upper_bound),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "The rough row upper bound is only for triage. It multiplies raw image files by measured object sets and measured image channels, so it can overestimate real MorphoJet image-table rows. A value below 1,000 means the official examples alone are unlikely to satisfy the L3 scale gate.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-dir", type=Path, default=Path("benchmark/data/cellprofiler/examples-repo"))
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--md-out", type=Path)
    args = parser.parse_args()

    if not args.repo_dir.is_dir():
        raise SystemExit(f"CellProfiler examples repo not found: {args.repo_dir}")

    scans = scan(args.repo_dir)
    payload = {
        "repo_dir": str(args.repo_dir),
        "pipelines_scanned": len(scans),
        "total_raw_image_files": sum(item.raw_image_files for item in scans),
        "best_rough_image_row_upper_bound": scans[0].rough_image_row_upper_bound if scans else 0,
        "candidates": [asdict(item) for item in scans],
    }
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(payload, indent=2) + "\n")
    if args.md_out:
        args.md_out.parent.mkdir(parents=True, exist_ok=True)
        args.md_out.write_text(render_markdown(args.repo_dir, scans))
    if not args.json_out and not args.md_out:
        print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
