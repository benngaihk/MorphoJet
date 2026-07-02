#!/usr/bin/env python3
"""Build a MorphoJet image table from paired image and label-mask files."""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path


def compile_pattern(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern)


def key_for(path: Path, pattern: re.Pattern[str]) -> str:
    match = pattern.search(path.name)
    if not match:
        raise ValueError(f"path does not match key pattern: {path}")
    if match.groupdict():
        return "|".join(f"{key}={value}" for key, value in sorted(match.groupdict().items()))
    if match.groups():
        return "|".join(match.groups())
    return match.group(0)


def collect(paths: list[Path], pattern: re.Pattern[str], kind: str) -> dict[str, Path]:
    collected: dict[str, Path] = {}
    for path in sorted(paths):
        key = key_for(path, pattern)
        if key in collected:
            raise SystemExit(f"duplicate {kind} key {key}: {collected[key]} and {path}")
        collected[key] = path
    return collected


def parse_metadata(values: list[str]) -> dict[str, str]:
    metadata = {}
    for value in values:
        if "=" not in value:
            raise SystemExit(f"metadata must be KEY=VALUE: {value}")
        key, item = value.split("=", 1)
        metadata[key] = item
    return metadata


def relative(path: Path, base_dir: Path) -> str:
    try:
        return str(path.relative_to(base_dir))
    except ValueError:
        return str(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--images-glob", required=True)
    parser.add_argument("--masks-glob", required=True)
    parser.add_argument("--image-key-regex", required=True)
    parser.add_argument("--mask-key-regex", required=True)
    parser.add_argument("--channel", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--base-dir", type=Path, default=Path.cwd())
    parser.add_argument("--metadata", action="append", default=[])
    args = parser.parse_args()

    image_paths = [Path(path) for path in sorted(args.base_dir.glob(args.images_glob))]
    mask_paths = [Path(path) for path in sorted(args.base_dir.glob(args.masks_glob))]
    if not image_paths:
        raise SystemExit(f"no images matched {args.images_glob}")
    if not mask_paths:
        raise SystemExit(f"no masks matched {args.masks_glob}")

    images = collect(image_paths, compile_pattern(args.image_key_regex), "image")
    masks = collect(mask_paths, compile_pattern(args.mask_key_regex), "mask")
    missing_masks = sorted(set(images) - set(masks))
    extra_masks = sorted(set(masks) - set(images))
    if missing_masks or extra_masks:
        raise SystemExit(
            "image/mask key mismatch: "
            f"missing_masks={missing_masks[:10]} extra_masks={extra_masks[:10]}"
        )

    metadata = parse_metadata(args.metadata)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["ImageNumber", "ImagePath", "MaskPath", "Channel", *metadata.keys()]
    with args.out.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for image_number, key in enumerate(sorted(images), start=1):
            row = {
                "ImageNumber": image_number,
                "ImagePath": relative(images[key], args.out.parent),
                "MaskPath": relative(masks[key], args.out.parent),
                "Channel": args.channel,
            }
            row.update(metadata)
            writer.writerow(row)

    print(f"wrote {len(images)} rows to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
