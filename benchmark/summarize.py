#!/usr/bin/env python3
"""Summarize a MorphoJet benchmark output directory."""

from __future__ import annotations

import csv
import sys
from pathlib import Path


def count_rows(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open(newline="") as handle:
        return sum(1 for _ in csv.DictReader(handle))


def main() -> int:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("benchmark/results/morphojet")
    print(f"output_dir,{out_dir}")
    print(f"image_rows,{count_rows(out_dir / 'Image.csv')}")
    print(f"object_rows,{count_rows(out_dir / 'Objects.csv')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
