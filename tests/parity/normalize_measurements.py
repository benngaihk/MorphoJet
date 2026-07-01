#!/usr/bin/env python3
"""Normalize measurement CSVs before parity diffs.

This starter keeps the operation deliberately small: sort rows by stable keys
and round numeric values. Dataset-specific column aliases should be added only
after comparing against pinned CellProfiler oracle outputs.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


def normalize_value(value: str, digits: int) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except ValueError:
        return value


def normalize_csv(input_path: Path, output_path: Path, digits: int) -> None:
    with input_path.open(newline="") as source:
        reader = csv.DictReader(source)
        fieldnames = reader.fieldnames or []
        rows = [
            {field: normalize_value(row.get(field, ""), digits) for field in fieldnames}
            for row in reader
        ]

    sort_keys = [key for key in ("ImageNumber", "ObjectNumber", "Channel") if key in fieldnames]
    if sort_keys:
        rows.sort(key=lambda row: tuple(row.get(key, "") for key in sort_keys))

    with output_path.open("w", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--digits", type=int, default=6)
    args = parser.parse_args()
    normalize_csv(args.input, args.output, args.digits)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
