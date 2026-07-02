#!/usr/bin/env python3
"""Build a multi-channel, multi-object-set MorphoJet image table."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from build_image_table import collect, compile_pattern, parse_metadata, relative


def parse_channel_specs(values: list[list[str]], base_dir: Path) -> list[dict[str, object]]:
    specs = []
    for channel, glob, key_regex in values:
        paths = [Path(path) for path in sorted(base_dir.glob(glob))]
        if not paths:
            raise SystemExit(f"no images matched {glob} for channel {channel}")
        specs.append(
            {
                "channel": channel,
                "glob": glob,
                "paths": collect(paths, compile_pattern(key_regex), f"{channel} image"),
            }
        )
    return specs


def parse_bridge_objects(path: Path) -> list[dict[str, str]]:
    bridge = json.loads(path.read_text())
    objects = bridge.get("objects", [])
    if not objects:
        raise SystemExit(f"bridge manifest has no objects: {path}")
    return objects


def render_template(template: str, object_item: dict[str, str]) -> str:
    return template.format(
        object=object_item["name"],
        safe_name=object_item.get("safe_name", object_item["name"]),
    )


def collect_masks(
    objects: list[dict[str, str]],
    base_dir: Path,
    mask_glob_template: str,
    mask_key_regex_template: str,
) -> dict[str, dict[str, Path]]:
    masks = {}
    for object_item in objects:
        object_name = object_item["name"]
        mask_glob = render_template(mask_glob_template, object_item)
        key_regex = render_template(mask_key_regex_template, object_item)
        paths = [Path(path) for path in sorted(base_dir.glob(mask_glob))]
        if not paths:
            raise SystemExit(f"no masks matched {mask_glob} for object set {object_name}")
        masks[object_name] = collect(paths, compile_pattern(key_regex), f"{object_name} mask")
    return masks


def ensure_same_keys(label: str, expected: set[str], actual: set[str]) -> None:
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        raise SystemExit(f"{label} key mismatch: missing={missing[:10]} extra={extra[:10]}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bridge-json", type=Path, required=True)
    parser.add_argument("--channel", nargs=3, action="append", metavar=("NAME", "GLOB", "KEY_REGEX"), required=True)
    parser.add_argument("--mask-glob-template", required=True)
    parser.add_argument("--mask-key-regex-template", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--base-dir", type=Path, default=Path.cwd())
    parser.add_argument("--metadata", action="append", default=[])
    args = parser.parse_args()

    try:
        channel_specs = parse_channel_specs(args.channel, args.base_dir)
        objects = parse_bridge_objects(args.bridge_json)
        masks_by_object = collect_masks(
            objects,
            args.base_dir,
            args.mask_glob_template,
            args.mask_key_regex_template,
        )
    except ValueError as err:
        raise SystemExit(str(err)) from err

    sample_keys = set(channel_specs[0]["paths"].keys())
    for spec in channel_specs[1:]:
        ensure_same_keys(f"{spec['channel']} image", sample_keys, set(spec["paths"].keys()))
    for object_name, masks in masks_by_object.items():
        ensure_same_keys(f"{object_name} mask", sample_keys, set(masks))

    metadata = parse_metadata(args.metadata)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["ImageNumber", "ImagePath", "MaskPath", "Channel", "ObjectSet", *metadata.keys()]
    with args.out.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for image_number, sample_key in enumerate(sorted(sample_keys), start=1):
            for object_item in objects:
                object_name = object_item["name"]
                mask_path = masks_by_object[object_name][sample_key]
                for spec in channel_specs:
                    row = {
                        "ImageNumber": image_number,
                        "ImagePath": relative(spec["paths"][sample_key], args.out.parent),
                        "MaskPath": relative(mask_path, args.out.parent),
                        "Channel": spec["channel"],
                        "ObjectSet": object_name,
                    }
                    row.update(metadata)
                    writer.writerow(row)

    row_count = len(sample_keys) * len(objects) * len(channel_specs)
    print(f"wrote {row_count} rows to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
