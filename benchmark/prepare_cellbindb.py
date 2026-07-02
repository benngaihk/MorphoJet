#!/usr/bin/env python3
"""Prepare CellBinDB image tables from the verified Zenodo archive."""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from zipfile import ZipFile


IMG_SUFFIX = "-img.tif"
INSTANCE_SUFFIX = "-instancemask.tif"
SEMANTIC_SUFFIX = "-mask.tif"


@dataclass
class CellBinSample:
    key: str
    image: str
    instance_mask: str
    semantic_mask: str | None
    source_group: str
    stain: str


def sample_key(path: str, suffix: str) -> str:
    return path[: -len(suffix)]


def infer_source_group(path: str) -> str:
    parts = path.split("/")
    return parts[1] if len(parts) > 2 and parts[0] == "CellBinDB" else ""


def infer_stain(source_group: str) -> str:
    if "_" not in source_group:
        return source_group or "Unknown"
    return source_group.rsplit("_", 1)[-1] or "Unknown"


def collect_samples(zip_path: Path) -> list[CellBinSample]:
    grouped: dict[str, dict[str, str]] = {}
    with ZipFile(zip_path) as archive:
        for name in archive.namelist():
            if name.endswith("/") or not name.lower().endswith(".tif"):
                continue
            if name.endswith(INSTANCE_SUFFIX):
                grouped.setdefault(sample_key(name, INSTANCE_SUFFIX), {})["instance_mask"] = name
            elif name.endswith(IMG_SUFFIX):
                grouped.setdefault(sample_key(name, IMG_SUFFIX), {})["image"] = name
            elif name.endswith(SEMANTIC_SUFFIX):
                grouped.setdefault(sample_key(name, SEMANTIC_SUFFIX), {})["semantic_mask"] = name

    samples: list[CellBinSample] = []
    incomplete = []
    for key, files in sorted(grouped.items()):
        if "image" not in files or "instance_mask" not in files:
            incomplete.append(key)
            continue
        source_group = infer_source_group(files["image"])
        samples.append(
            CellBinSample(
                key=key,
                image=files["image"],
                instance_mask=files["instance_mask"],
                semantic_mask=files.get("semantic_mask"),
                source_group=source_group,
                stain=infer_stain(source_group),
            )
        )
    if incomplete:
        raise SystemExit(f"incomplete CellBinDB sample groups: {incomplete[:10]}")
    return samples


def extract_members(zip_path: Path, extract_dir: Path, samples: list[CellBinSample], overwrite: bool) -> None:
    if overwrite and extract_dir.exists():
        shutil.rmtree(extract_dir)
    extract_dir.mkdir(parents=True, exist_ok=True)
    members = []
    for sample in samples:
        members.append(sample.image)
        members.append(sample.instance_mask)
    with ZipFile(zip_path) as archive:
        for member in members:
            target = extract_dir / member
            if target.exists() and not overwrite:
                continue
            archive.extract(member, extract_dir)


def relative(path: Path, base_dir: Path) -> str:
    return os.path.relpath(path.resolve(), base_dir.resolve())


def write_table(samples: list[CellBinSample], extract_dir: Path, out: Path, channel: str, object_set: str) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "ImageNumber",
        "ImagePath",
        "MaskPath",
        "Channel",
        "ObjectSet",
        "Dataset",
        "SourceGroup",
        "Stain",
    ]
    with out.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for image_number, sample in enumerate(samples, start=1):
            writer.writerow(
                {
                    "ImageNumber": image_number,
                    "ImagePath": relative(extract_dir / sample.image, out.parent),
                    "MaskPath": relative(extract_dir / sample.instance_mask, out.parent),
                    "Channel": channel,
                    "ObjectSet": object_set,
                    "Dataset": "CellBinDB",
                    "SourceGroup": sample.source_group,
                    "Stain": sample.stain,
                }
            )


def write_summary(path: Path, samples: list[CellBinSample], zip_path: Path, out: Path) -> None:
    by_stain: dict[str, int] = {}
    by_source_group: dict[str, int] = {}
    for sample in samples:
        by_stain[sample.stain] = by_stain.get(sample.stain, 0) + 1
        by_source_group[sample.source_group] = by_source_group.get(sample.source_group, 0) + 1
    payload = {
        "zip": str(zip_path),
        "image_table": str(out),
        "rows": len(samples),
        "by_stain": dict(sorted(by_stain.items())),
        "by_source_group": dict(sorted(by_source_group.items())),
        "first_samples": [asdict(sample) for sample in samples[:5]],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", type=Path, default=Path("benchmark/data/cellbindb/CellBinDB.zip"))
    parser.add_argument("--extract-dir", type=Path, default=Path("benchmark/data/cellbindb/extracted"))
    parser.add_argument("--out", type=Path, default=Path("benchmark/results/cellbindb/images.csv"))
    parser.add_argument("--summary-json", type=Path)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--extract", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--channel", default="Intensity")
    parser.add_argument("--object-set", default="Cells")
    args = parser.parse_args()

    if not args.zip.is_file():
        raise SystemExit(f"CellBinDB zip not found: {args.zip}")
    if args.limit is not None and args.limit <= 0:
        raise SystemExit("--limit must be positive")

    samples = collect_samples(args.zip)
    selected = samples[: args.limit] if args.limit else samples
    if args.extract:
        extract_members(args.zip, args.extract_dir, selected, args.overwrite)
    write_table(selected, args.extract_dir, args.out, args.channel, args.object_set)
    if args.summary_json:
        write_summary(args.summary_json, selected, args.zip, args.out)
    print(f"available_samples={len(samples)}")
    print(f"wrote_rows={len(selected)}")
    print(f"image_table={args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
