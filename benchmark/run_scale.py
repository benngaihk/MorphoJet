#!/usr/bin/env python3
"""Run a reproducible synthetic MorphoJet scale benchmark."""

from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import shutil
import subprocess
import time
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass
class ScaleResult:
    image_rows: int
    object_rows: int
    width: int
    height: int
    threads: int
    elapsed_seconds: float
    images_per_second: float
    objects_per_second: float
    output_dir: str


def cargo_bin() -> str:
    env_cargo = os.environ.get("CARGO")
    if env_cargo:
        return env_cargo
    cargo = shutil.which("cargo")
    if cargo:
        return cargo
    home_cargo = Path.home() / ".cargo" / "bin" / "cargo"
    if home_cargo.exists():
        return str(home_cargo)
    raise SystemExit("cargo not found; install Rust or set CARGO=/path/to/cargo")


def run(command: list[str], cwd: Path) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def count_csv_rows(path: Path) -> int:
    with path.open(newline="") as handle:
        return sum(1 for _ in csv.DictReader(handle))


def run_case(root: Path, images: int, width: int, height: int, threads: int, release_binary: Path) -> ScaleResult:
    data_dir = root / "benchmark" / "data" / "scale" / f"n{images}_w{width}_h{height}"
    out_dir = root / "benchmark" / "results" / "scale" / f"n{images}_w{width}_h{height}"
    run(
        [
            "python3",
            "corpus/generate_smoke.py",
            "--output",
            str(data_dir),
            "--images",
            str(images),
            "--width",
            str(width),
            "--height",
            str(height),
        ],
        root,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    run(
        [
            str(release_binary),
            "measure",
            "--images",
            str(data_dir / "images.csv"),
            "--out",
            str(out_dir),
            "--threads",
            str(threads),
            "--cellprofiler-compatible",
        ],
        root,
    )
    elapsed = time.perf_counter() - started
    object_rows = count_csv_rows(out_dir / "Objects.csv")
    return ScaleResult(
        image_rows=images,
        object_rows=object_rows,
        width=width,
        height=height,
        threads=threads,
        elapsed_seconds=elapsed,
        images_per_second=images / elapsed if elapsed else 0.0,
        objects_per_second=object_rows / elapsed if elapsed else 0.0,
        output_dir=str(out_dir),
    )


def write_csv(path: Path, results: list[ScaleResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(results[0]).keys()))
        writer.writeheader()
        for result in results:
            writer.writerow(asdict(result))


def write_summary(path: Path, results: list[ScaleResult]) -> None:
    best = max(results, key=lambda result: result.images_per_second)
    lines = [
        "# Synthetic Scale Benchmark",
        "",
        "This is an L1 engineering benchmark. It does not prove CellProfiler parity or industry impact by itself.",
        "",
        "## Environment",
        "",
        f"- system: `{platform.platform()}`",
        f"- machine: `{platform.machine()}`",
        f"- processor: `{platform.processor()}`",
        f"- python: `{platform.python_version()}`",
        "",
        "## Results",
        "",
        "| Images | Objects | Size | Threads | Seconds | Images/s | Objects/s |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for result in results:
        lines.append(
            "| "
            f"{result.image_rows} | "
            f"{result.object_rows} | "
            f"{result.width}x{result.height} | "
            f"{result.threads} | "
            f"{result.elapsed_seconds:.6f} | "
            f"{result.images_per_second:.2f} | "
            f"{result.objects_per_second:.2f} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            f"- Best synthetic throughput: `{best.images_per_second:.2f}` images/s and `{best.objects_per_second:.2f}` objects/s.",
            "- This validates the local benchmark harness and release CLI path.",
            "- It does not satisfy the L2-L4 industry-impact gates without CellProfiler oracle parity, real/public data, and RSS comparison.",
        ]
    )
    path.write_text("\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", default="16,256,1024")
    parser.add_argument("--width", type=int, default=96)
    parser.add_argument("--height", type=int, default=96)
    parser.add_argument("--threads", type=int, default=os.cpu_count() or 4)
    parser.add_argument("--out", type=Path, default=Path("benchmark/results/scale"))
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    cargo = cargo_bin()
    run([cargo, "build", "--release", "-p", "morphojet"], root)
    release_binary = root / "target" / "release" / "morphojet"

    image_counts = [int(value.strip()) for value in args.cases.split(",") if value.strip()]
    results = [
        run_case(root, image_count, args.width, args.height, args.threads, release_binary)
        for image_count in image_counts
    ]
    args.out.mkdir(parents=True, exist_ok=True)
    write_csv(args.out / "scale.csv", results)
    write_summary(args.out / "summary.md", results)
    (args.out / "metadata.json").write_text(
        json.dumps(
            {
                "cases": image_counts,
                "width": args.width,
                "height": args.height,
                "threads": args.threads,
                "platform": platform.platform(),
                "machine": platform.machine(),
                "processor": platform.processor(),
            },
            indent=2,
        )
        + "\n"
    )
    print(f"wrote {args.out / 'scale.csv'}")
    print(f"wrote {args.out / 'summary.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
