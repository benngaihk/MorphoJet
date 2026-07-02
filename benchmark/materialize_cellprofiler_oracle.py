#!/usr/bin/env python3
"""Materialize CellProfiler object CSVs into MorphoJet's long oracle format."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


SHAPE_COLUMNS = [
    "AreaShape_Area",
    "AreaShape_Center_X",
    "AreaShape_Center_Y",
    "AreaShape_BoundingBoxMinimum_X",
    "AreaShape_BoundingBoxMinimum_Y",
    "AreaShape_BoundingBoxMaximum_X",
    "AreaShape_BoundingBoxMaximum_Y",
    "AreaShape_Perimeter",
    "AreaShape_Eccentricity",
    "AreaShape_MajorAxisLength",
    "AreaShape_MinorAxisLength",
    "AreaShape_Solidity",
    "Location_Center_Z",
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

OUTPUT_COLUMNS = [
    "ImageNumber",
    "ObjectNumber",
    "Channel",
    "ObjectSet",
    "AreaShape_Area",
    "AreaShape_Center_X",
    "AreaShape_Center_Y",
    "AreaShape_BoundingBoxMinimum_X",
    "AreaShape_BoundingBoxMinimum_Y",
    "AreaShape_BoundingBoxMaximum_X",
    "AreaShape_BoundingBoxMaximum_Y",
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
    "Location_Center_Z",
    "Location_MaxIntensity_Z",
    "AreaShape_Perimeter",
    "AreaShape_Eccentricity",
    "AreaShape_MajorAxisLength",
    "AreaShape_MinorAxisLength",
    "AreaShape_Solidity",
]


def parse_object_spec(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise SystemExit(f"--object must be ObjectSet=CSV: {value}")
    name, path = value.split("=", 1)
    if not name:
        raise SystemExit(f"empty ObjectSet in --object: {value}")
    return name, Path(path)


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def require(row: dict[str, str], column: str, source: Path) -> str:
    if column not in row:
        raise SystemExit(f"missing column {column} in {source}")
    return row[column]


def materialize(objects: list[tuple[str, Path]], channels: list[str], out: Path) -> int:
    out.parent.mkdir(parents=True, exist_ok=True)
    row_count = 0
    with out.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        for object_set, path in objects:
            for source_row in read_rows(path):
                shape_values = {
                    column: require(source_row, column, path)
                    for column in SHAPE_COLUMNS
                }
                for channel in channels:
                    row = {
                        "ImageNumber": require(source_row, "ImageNumber", path),
                        "ObjectNumber": require(source_row, "ObjectNumber", path),
                        "Channel": channel,
                        "ObjectSet": object_set,
                    }
                    row.update(shape_values)
                    for column in INTENSITY_COLUMNS:
                        row[column] = require(source_row, f"{column}_{channel}", path)
                    writer.writerow(row)
                    row_count += 1
    return row_count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--object", action="append", required=True, help="ObjectSet=CSV")
    parser.add_argument("--channels", default="DNA,PH3")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    objects = [parse_object_spec(value) for value in args.object]
    channels = [channel.strip() for channel in args.channels.split(",") if channel.strip()]
    if not channels:
        raise SystemExit("--channels must contain at least one channel")

    row_count = materialize(objects, channels, args.out)
    print(f"wrote {row_count} rows to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
