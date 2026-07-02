#!/usr/bin/env python3
"""Run the CellBinDB direct-mask CellProfiler oracle path."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CP_IMAGE = "cellprofiler/cellprofiler:4.2.6"
CP_PLATFORM = "linux/amd64"


def run(command: list[str]) -> None:
    subprocess.run(command, cwd=ROOT, check=True)


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


def remove(path: Path) -> None:
    if path.exists():
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", type=Path, default=Path("benchmark/data/cellbindb/CellBinDB.zip"))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--threads", default="8")
    parser.add_argument("--run-name")
    parser.add_argument("--skip-cellprofiler", action="store_true")
    args = parser.parse_args()

    run_name = args.run_name or ("full" if args.limit is None else f"n{args.limit}")
    base_dir = Path("benchmark/results/cellbindb") / f"oracle-{run_name}"
    extract_dir = Path("benchmark/data/cellbindb") / f"extracted-{run_name}"
    image_table = base_dir / "images.csv"
    summary_json = base_dir / "summary.json"
    pipeline = base_dir / "cellbindb-direct-mask.cppipe"
    cp_dir = base_dir / "cellprofiler"
    mj_dir = base_dir / "morphojet"
    metrics_dir = base_dir / "metrics"
    parity_md = base_dir / "parity.md"
    parity_json = base_dir / "parity.json"
    workflow_bridge_md = base_dir / "workflow_bridge.md"
    workflow_bridge_json = base_dir / "workflow_bridge.json"
    handoff_trial_md = base_dir / "handoff_trial.md"
    handoff_trial_json = base_dir / "handoff_trial.json"
    impact_md = base_dir / "impact.md"
    impact_json = base_dir / "impact.json"
    cp_long = cp_dir / "Objects.long.csv"

    prepare_command = [
        "python3",
        "benchmark/prepare_cellbindb.py",
        "--zip",
        str(args.zip),
        "--extract-dir",
        str(extract_dir),
        "--out",
        str(image_table),
        "--summary-json",
        str(summary_json),
        "--extract",
        "--overwrite",
    ]
    if args.limit is not None:
        prepare_command.extend(["--limit", str(args.limit)])
    run(prepare_command)
    run(["python3", "benchmark/build_cellbindb_cellprofiler_pipeline.py", "--out", str(pipeline)])

    if not args.skip_cellprofiler:
        remove(cp_dir)
        run(
            [
                "python3",
                "benchmark/run_docker_metrics.py",
                "--name",
                f"cellprofiler-cellbindb-{run_name}",
                "--container-name",
                f"morphojet-cellbindb-{run_name}-cellprofiler",
                "--image",
                CP_IMAGE,
                "--platform",
                CP_PLATFORM,
                "--volume",
                f"{ROOT}:/work",
                "--workdir",
                "/work",
                "--out",
                str(metrics_dir),
                "--fail-on-nonzero",
                "--",
                "cellprofiler",
                "-c",
                "-r",
                "-p",
                str(pipeline),
                "-i",
                str(extract_dir),
                "-o",
                str(cp_dir),
            ]
        )

    run([cargo_bin(), "build", "--release", "-p", "morphojet"])
    remove(mj_dir)
    run(
        [
            "python3",
            "benchmark/run_command_metrics.py",
            "--name",
            f"morphojet-cellbindb-{run_name}",
            "--out",
            str(metrics_dir),
            "--fail-on-nonzero",
            "--",
            "target/release/morphojet",
            "measure",
            "--images",
            str(image_table),
            "--out",
            str(mj_dir),
            "--threads",
            args.threads,
            "--cellprofiler-compatible",
            "--overwrite",
        ]
    )
    run(
        [
            "python3",
            "benchmark/materialize_cellprofiler_oracle.py",
            "--object",
            f"Cells={cp_dir / 'Cells.csv'}",
            "--channels",
            "Intensity",
            "--out",
            str(cp_long),
        ]
    )
    run(
        [
            "python3",
            "tests/parity/compare_measurements.py",
            str(cp_long),
            str(mj_dir / "Objects.csv"),
            "--keys",
            "ImageNumber,ObjectSet,ObjectNumber,Channel",
            "--abs-tol",
            "1e-6",
            "--rel-tol",
            "1e-5",
            "--out",
            str(parity_md),
            "--json-out",
            str(parity_json),
            "--fail-on-gap",
        ]
    )
    run(
        [
            "python3",
            "benchmark/run_handoff_trial.py",
            "benchmark/handoff/cellbindb_supported_columns.json",
            "--var",
            f"base_dir={base_dir}",
            "--out-json",
            str(handoff_trial_json),
            "--out-md",
            str(handoff_trial_md),
        ]
    )
    rows = args.limit if args.limit is not None else 1044
    run(
        [
            "python3",
            "benchmark/impact_report.py",
            "--image-rows",
            str(rows),
            "--parity-json",
            str(parity_json),
            "--cellprofiler-metrics-json",
            str(metrics_dir / f"cellprofiler-cellbindb-{run_name}.metrics.json"),
            "--morphojet-metrics-json",
            str(metrics_dir / f"morphojet-cellbindb-{run_name}.metrics.json"),
            "--out",
            str(impact_md),
            "--json-out",
            str(impact_json),
        ]
    )
    print("CellBinDB oracle run complete")
    print(f"summary: {summary_json}")
    print(f"parity: {parity_md}")
    print(f"workflow_bridge: {workflow_bridge_md}")
    print(f"handoff_trial: {handoff_trial_md}")
    print(f"impact: {impact_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
