#!/usr/bin/env python3
"""Materialize MorphoJet's long object CSV into a CellProfiler-style wide object CSV."""

from __future__ import annotations

import argparse
import csv
import math
from collections import OrderedDict
from pathlib import Path


KEY_COLUMNS = ["ImageNumber", "ObjectNumber"]

BASE_COLUMNS = [
    "ImageNumber",
    "ObjectNumber",
    "AreaShape_Area",
    "AreaShape_BoundingBoxArea",
    "AreaShape_BoundingBoxMaximum_X",
    "AreaShape_BoundingBoxMaximum_Y",
    "AreaShape_BoundingBoxMinimum_X",
    "AreaShape_BoundingBoxMinimum_Y",
    "AreaShape_Center_X",
    "AreaShape_Center_Y",
    "AreaShape_ConvexArea",
    "AreaShape_Eccentricity",
    "AreaShape_EquivalentDiameter",
    "AreaShape_Extent",
    "AreaShape_MajorAxisLength",
    "AreaShape_MinorAxisLength",
    "AreaShape_Perimeter",
    "AreaShape_Solidity",
    "Location_Center_X",
    "Location_Center_Y",
    "Location_Center_Z",
    "Number_Object_Number",
]

SHAPE_COLUMNS = [
    "AreaShape_Area",
    "AreaShape_BoundingBoxMaximum_X",
    "AreaShape_BoundingBoxMaximum_Y",
    "AreaShape_BoundingBoxMinimum_X",
    "AreaShape_BoundingBoxMinimum_Y",
    "AreaShape_Center_X",
    "AreaShape_Center_Y",
    "AreaShape_Eccentricity",
    "AreaShape_MajorAxisLength",
    "AreaShape_MinorAxisLength",
    "AreaShape_Perimeter",
    "AreaShape_Solidity",
]

INTENSITY_COLUMNS = [
    "Intensity_MinIntensity",
    "Intensity_MaxIntensity",
    "Intensity_MeanIntensity",
    "Intensity_MedianIntensity",
    "Intensity_IntegratedIntensity",
    "Intensity_LowerQuartileIntensity",
    "Intensity_UpperQuartileIntensity",
    "Intensity_StdIntensity",
    "Intensity_MADIntensity",
    "Location_CenterMassIntensity_X",
    "Location_CenterMassIntensity_Y",
    "Location_CenterMassIntensity_Z",
    "Location_MaxIntensity_Z",
]


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def require(row: dict[str, str], column: str, source: Path) -> str:
    if column not in row:
        raise SystemExit(f"missing column {column} in {source}")
    return row[column]


def parse_channels(value: str | None, rows: list[dict[str, str]], object_set: str, source: Path) -> list[str]:
    if value:
        channels = [channel.strip() for channel in value.split(",") if channel.strip()]
        if not channels:
            raise SystemExit("--channels must contain at least one channel")
        return channels

    channels: OrderedDict[str, None] = OrderedDict()
    for row in rows:
        if require(row, "ObjectSet", source) != object_set:
            continue
        channels[require(row, "Channel", source)] = None
    if not channels:
        raise SystemExit(f"no channels found for ObjectSet={object_set} in {source}")
    return list(channels)


def format_int(value: int) -> str:
    return str(value)


def format_float(value: float) -> str:
    return f"{value:.10}"


def parse_float(row: dict[str, str], column: str, source: Path) -> float:
    try:
        return float(require(row, column, source))
    except ValueError as exc:
        raise SystemExit(f"invalid numeric value for {column} in {source}: {exc}") from exc


def bounding_box_dimensions(row: dict[str, str], source: Path) -> tuple[int, int]:
    try:
        min_x = int(float(require(row, "AreaShape_BoundingBoxMinimum_X", source)))
        min_y = int(float(require(row, "AreaShape_BoundingBoxMinimum_Y", source)))
        max_x = int(float(require(row, "AreaShape_BoundingBoxMaximum_X", source)))
        max_y = int(float(require(row, "AreaShape_BoundingBoxMaximum_Y", source)))
    except ValueError as exc:
        raise SystemExit(f"invalid bounding box value in {source}: {exc}") from exc
    return max_x - min_x, max_y - min_y


def bounding_box_area(row: dict[str, str], source: Path) -> str:
    width, height = bounding_box_dimensions(row, source)
    return format_int(width * height)


def equivalent_diameter(row: dict[str, str], source: Path) -> str:
    area = parse_float(row, "AreaShape_Area", source)
    return format_float(math.sqrt(4.0 * area / math.pi))


def extent(row: dict[str, str], source: Path) -> str:
    area = parse_float(row, "AreaShape_Area", source)
    bbox_area = float(bounding_box_area(row, source))
    return format_float(area / bbox_area if bbox_area else 0.0)


def convex_area(row: dict[str, str], source: Path) -> str:
    area = parse_float(row, "AreaShape_Area", source)
    solidity = parse_float(row, "AreaShape_Solidity", source)
    return format_float(area / solidity if solidity else 0.0)


def materialize(objects_csv: Path, object_set: str, channels: list[str], out: Path) -> int:
    rows = read_rows(objects_csv)
    by_key: OrderedDict[tuple[str, str], dict[str, str]] = OrderedDict()
    seen_channels: dict[tuple[str, str], set[str]] = {}

    for row in rows:
        if require(row, "ObjectSet", objects_csv) != object_set:
            continue

        key = (require(row, "ImageNumber", objects_csv), require(row, "ObjectNumber", objects_csv))
        channel = require(row, "Channel", objects_csv)
        if channel not in channels:
            continue

        target = by_key.setdefault(
            key,
            {
                "ImageNumber": key[0],
                "ObjectNumber": key[1],
                "AreaShape_BoundingBoxArea": bounding_box_area(row, objects_csv),
                "AreaShape_ConvexArea": convex_area(row, objects_csv),
                "AreaShape_EquivalentDiameter": equivalent_diameter(row, objects_csv),
                "AreaShape_Extent": extent(row, objects_csv),
                "Location_Center_X": require(row, "AreaShape_Center_X", objects_csv),
                "Location_Center_Y": require(row, "AreaShape_Center_Y", objects_csv),
                "Location_Center_Z": require(row, "Location_Center_Z", objects_csv),
                "Number_Object_Number": key[1],
            },
        )
        seen_channels.setdefault(key, set()).add(channel)

        for column in SHAPE_COLUMNS:
            value = require(row, column, objects_csv)
            existing = target.get(column)
            if existing is not None and existing != value:
                raise SystemExit(f"shape column {column} differs across channels for key {key}")
            target[column] = value

        for column in INTENSITY_COLUMNS:
            target[f"{column}_{channel}"] = require(row, column, objects_csv)

    missing = {
        key: sorted(set(channels) - key_channels)
        for key, key_channels in seen_channels.items()
        if set(channels) - key_channels
    }
    if missing:
        first_key, first_missing = next(iter(missing.items()))
        raise SystemExit(f"missing channels for key {first_key}: {', '.join(first_missing)}")

    if not by_key:
        raise SystemExit(f"no rows for ObjectSet={object_set} and channels={','.join(channels)}")

    fieldnames = BASE_COLUMNS + [f"{column}_{channel}" for channel in channels for column in INTENSITY_COLUMNS]
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in by_key.values():
            writer.writerow(row)
    return len(by_key)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--objects", type=Path, required=True, help="MorphoJet Objects.csv")
    parser.add_argument("--object-set", required=True, help="ObjectSet to materialize, for example Cells")
    parser.add_argument("--channels", help="Comma-separated channel order; defaults to discovery order")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    source_rows = read_rows(args.objects)
    channels = parse_channels(args.channels, source_rows, args.object_set, args.objects)
    row_count = materialize(args.objects, args.object_set, channels, args.out)
    print(f"wrote {row_count} {args.object_set} rows to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
