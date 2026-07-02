#!/usr/bin/env python3
"""Run a manifest-driven CellProfiler vs MorphoJet oracle benchmark."""

from __future__ import annotations

import argparse
import json
import csv
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any


def run(command: list[str], cwd: Path) -> None:
    subprocess.run(command, cwd=cwd, check=True)


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


def metric_command(name: str, out_dir: str, command: list[str]) -> list[str]:
    return [
        "python3",
        "benchmark/run_command_metrics.py",
        "--name",
        name,
        "--out",
        out_dir,
        "--fail-on-nonzero",
        "--",
        *command,
    ]


def cellprofiler_command(manifest: dict[str, Any], root: Path) -> list[str]:
    cellprofiler = manifest["cellprofiler"]
    if "command" in cellprofiler and cellprofiler["command"]:
        return ["bash", "-lc", cellprofiler["command"]]

    image = cellprofiler["docker_image"]
    pipeline = cellprofiler["pipeline_path"]
    output_dir = cellprofiler["output_dir"]
    return [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{root}:/work",
        "-w",
        "/work",
        image,
        "cellprofiler",
        "-c",
        "-r",
        "-p",
        pipeline,
        "-o",
        output_dir,
    ]


def morphojet_command(manifest: dict[str, Any]) -> list[str]:
    morphojet = manifest["morphojet"]
    return [
        "target/release/morphojet",
        "measure",
        "--images",
        morphojet["image_table"],
        "--out",
        morphojet["output_dir"],
        "--threads",
        str(morphojet.get("threads", 1)),
        "--cellprofiler-compatible",
        "--overwrite",
    ]


def count_csv_rows(path: Path) -> int:
    with path.open(newline="") as handle:
        return sum(1 for _ in csv.DictReader(handle))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()

    root = Path.cwd()
    manifest = json.loads(args.manifest.read_text())
    run(
        [
            "python3",
            "benchmark/validate_benchmark_manifest.py",
            str(args.manifest),
            "--check-files",
            "--require-m0-ready",
        ],
        root,
    )
    run([cargo_bin(), "build", "--release", "-p", "morphojet"], root)

    metrics_dir = "benchmark/results/metrics"
    run(metric_command("cellprofiler", metrics_dir, cellprofiler_command(manifest, root)), root)
    run(metric_command("morphojet", metrics_dir, morphojet_command(manifest)), root)

    parity = manifest["parity"]
    parity_dir = Path(parity["output_dir"])
    parity_dir.mkdir(parents=True, exist_ok=True)
    cp_normalized = parity_dir / "cellprofiler_objects.normalized.csv"
    mj_normalized = parity_dir / "morphojet_objects.normalized.csv"
    run(
        [
            "python3",
            "tests/parity/normalize_measurements.py",
            manifest["cellprofiler"]["objects_csv"],
            str(cp_normalized),
        ],
        root,
    )
    run(
        [
            "python3",
            "tests/parity/normalize_measurements.py",
            manifest["morphojet"]["objects_csv"],
            str(mj_normalized),
        ],
        root,
    )
    run(
        [
            "python3",
            "tests/parity/compare_measurements.py",
            str(cp_normalized),
            str(mj_normalized),
            "--keys",
            parity["keys"],
            "--abs-tol",
            str(parity["abs_tol"]),
            "--rel-tol",
            str(parity["rel_tol"]),
            "--out",
            str(parity_dir / "objects_parity.md"),
            "--json-out",
            str(parity_dir / "objects_parity.json"),
            "--fail-on-gap",
        ],
        root,
    )
    run(
        [
            "python3",
            "benchmark/impact_report.py",
            "--image-rows",
            str(count_csv_rows(root / manifest["morphojet"]["image_table"])),
            "--parity-json",
            str(parity_dir / "objects_parity.json"),
            "--cellprofiler-metrics-json",
            "benchmark/results/metrics/cellprofiler.metrics.json",
            "--morphojet-metrics-json",
            "benchmark/results/metrics/morphojet.metrics.json",
            "--out",
            "benchmark/results/impact/summary.md",
            "--json-out",
            "benchmark/results/impact/summary.json",
            "--fail-on-gap",
        ],
        root,
    )
    print(f"oracle benchmark complete: {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
