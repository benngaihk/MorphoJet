#!/usr/bin/env python3
"""Check that a wide object CSV satisfies MorphoJet's CellProfiler-style contract."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


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


def read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        return reader.fieldnames or [], list(reader)


def required_columns(channels: list[str]) -> list[str]:
    columns = list(BASE_COLUMNS)
    for channel in channels:
        columns.extend(f"{column}_{channel}" for column in INTENSITY_COLUMNS)
    return columns


def check(path: Path, channels: list[str], min_rows: int) -> tuple[bool, dict[str, object]]:
    columns, rows = read_rows(path)
    required = required_columns(channels)
    missing_columns = [column for column in required if column not in columns]
    extra_columns = [column for column in columns if column not in required]
    duplicate_keys = 0
    empty_keys = 0
    seen = set()
    for row in rows:
        key = (row.get("ImageNumber", ""), row.get("ObjectNumber", ""))
        if not key[0] or not key[1]:
            empty_keys += 1
            continue
        if key in seen:
            duplicate_keys += 1
        seen.add(key)

    issues = []
    if len(rows) < min_rows:
        issues.append(f"row_count {len(rows)} < min_rows {min_rows}")
    if missing_columns:
        issues.append(f"missing_columns={','.join(missing_columns)}")
    if duplicate_keys:
        issues.append(f"duplicate_keys={duplicate_keys}")
    if empty_keys:
        issues.append(f"empty_keys={empty_keys}")

    summary = {
        "status": "PASS" if not issues else "FAIL",
        "csv": str(path),
        "rows": len(rows),
        "columns": len(columns),
        "required_columns": required,
        "missing_columns": missing_columns,
        "extra_columns": extra_columns,
        "duplicate_keys": duplicate_keys,
        "empty_keys": empty_keys,
        "issues": issues,
    }
    return not issues, summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv", type=Path)
    parser.add_argument("--channels", required=True, help="Comma-separated channel suffixes")
    parser.add_argument("--min-rows", type=int, default=1)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()

    channels = [channel.strip() for channel in args.channels.split(",") if channel.strip()]
    if not channels:
        raise SystemExit("--channels must contain at least one channel")
    if args.min_rows < 0:
        raise SystemExit("--min-rows must be >= 0")

    passed, summary = check(args.csv, channels, args.min_rows)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(summary, indent=2) + "\n")
    print(f"status={summary['status']}")
    print(f"rows={summary['rows']}")
    print(f"columns={summary['columns']}")
    if summary["issues"]:
        for issue in summary["issues"]:
            print(f"ERROR: {issue}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
