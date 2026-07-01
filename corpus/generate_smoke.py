#!/usr/bin/env python3
"""Generate a deterministic tiny MorphoJet smoke corpus.

The PNG writer is intentionally standard-library only so the first benchmark
path has no Python imaging dependency.
"""

from __future__ import annotations

import argparse
import csv
import struct
import zlib
from pathlib import Path


def png_chunk(kind: bytes, payload: bytes) -> bytes:
    checksum = zlib.crc32(kind)
    checksum = zlib.crc32(payload, checksum)
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", checksum)


def write_gray_png(path: Path, width: int, height: int, pixels: list[int]) -> None:
    if len(pixels) != width * height:
        raise ValueError("pixel count does not match dimensions")
    rows = bytearray()
    for y in range(height):
        rows.append(0)
        start = y * width
        rows.extend(pixels[start : start + width])

    header = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    data = b"".join(
        [
            b"\x89PNG\r\n\x1a\n",
            png_chunk(b"IHDR", header),
            png_chunk(b"IDAT", zlib.compress(bytes(rows), level=9)),
            png_chunk(b"IEND", b""),
        ]
    )
    path.write_bytes(data)


def make_image(width: int, height: int, index: int) -> list[int]:
    return [((x * 7 + y * 11 + index * 13) % 251) + 1 for y in range(height) for x in range(width)]


def make_mask(width: int, height: int, index: int) -> list[int]:
    pixels = [0 for _ in range(width * height)]
    objects = [
        (1, 4 + index % 3, 5, 9, 8),
        (2, 18, 7 + index % 4, 26, 14),
        (3, 8, 21, 16 + index % 5, 29),
        (4, 30, 22, 40, 34),
    ]
    for label, x0, y0, x1, y1 in objects:
        for y in range(y0, y1):
            for x in range(x0, x1):
                pixels[y * width + x] = label
    return pixels


def generate(output: Path, images: int, width: int, height: int) -> None:
    image_dir = output / "images"
    mask_dir = output / "masks"
    image_dir.mkdir(parents=True, exist_ok=True)
    mask_dir.mkdir(parents=True, exist_ok=True)

    table_path = output / "images.csv"
    with table_path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["ImageNumber", "ImagePath", "MaskPath", "Channel", "Plate", "Well", "Site"],
        )
        writer.writeheader()
        for idx in range(1, images + 1):
            image_path = image_dir / f"img_{idx:04d}.png"
            mask_path = mask_dir / f"mask_{idx:04d}.png"
            write_gray_png(image_path, width, height, make_image(width, height, idx))
            write_gray_png(mask_path, width, height, make_mask(width, height, idx))
            writer.writerow(
                {
                    "ImageNumber": idx,
                    "ImagePath": image_path.relative_to(output),
                    "MaskPath": mask_path.relative_to(output),
                    "Channel": "DAPI",
                    "Plate": "P001",
                    "Well": f"A{idx:02d}",
                    "Site": "1",
                }
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("benchmark/data/smoke"))
    parser.add_argument("--images", type=int, default=16)
    parser.add_argument("--width", type=int, default=48)
    parser.add_argument("--height", type=int, default=40)
    args = parser.parse_args()
    generate(args.output, args.images, args.width, args.height)
    print(f"wrote {args.images} image rows to {args.output / 'images.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
