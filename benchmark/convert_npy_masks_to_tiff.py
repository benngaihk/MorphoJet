#!/usr/bin/env python3
"""Convert CellProfiler-exported NPY label matrices to uint16 TIFF masks."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image


def convert_one(path: Path, base_dir: Path, out_dir: Path) -> Path:
    array = np.load(path)
    if array.ndim != 2:
        raise SystemExit(f"expected 2D label matrix: {path} has shape {array.shape}")
    if array.min() < 0 or array.max() > np.iinfo(np.uint16).max:
        raise SystemExit(f"label values out of uint16 range: {path}")
    relative = path.relative_to(base_dir).with_suffix(".tif")
    out_path = out_dir / relative
    out_path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(array.astype(np.uint16, copy=False)).save(out_path)
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-dir", type=Path, required=True)
    parser.add_argument("--glob", default="morphojet_masks/*/*.npy")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    paths = sorted(args.base_dir.glob(args.glob))
    if not paths:
        raise SystemExit(f"no npy masks matched {args.glob}")

    outputs = [convert_one(path, args.base_dir, args.out_dir) for path in paths]
    print(f"converted {len(outputs)} masks to {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
