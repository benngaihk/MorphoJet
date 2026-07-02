#!/usr/bin/env python3
"""Run the pinned ExampleHuman oracle parity and L3 smoke metrics path."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CP_IMAGE = "cellprofiler/cellprofiler:4.2.6"
CP_PLATFORM = "linux/amd64"
EXAMPLE_PIPELINE = Path("benchmark/data/cellprofiler/prepared/ExampleHuman/ExampleHuman.cppipe")
EXAMPLE_IMAGES = Path("benchmark/data/cellprofiler/prepared/ExampleHuman/images")


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
    parser.add_argument("--skip-cellprofiler", action="store_true")
    parser.add_argument("--threads", default="8")
    args = parser.parse_args()

    if not EXAMPLE_PIPELINE.is_file():
        raise SystemExit(f"missing ExampleHuman pipeline: {EXAMPLE_PIPELINE}")
    if not EXAMPLE_IMAGES.is_dir():
        raise SystemExit(f"missing ExampleHuman images: {EXAMPLE_IMAGES}")

    cp_dir = Path("benchmark/results/cellprofiler-run-426-npy")
    masks_tiff_dir = Path("benchmark/results/cellprofiler-run-426-labels-tiff")
    mj_dir = Path("benchmark/results/morphojet-run-426-labels-tiff")
    parity_dir = Path("benchmark/results/parity")
    metrics_dir = Path("benchmark/results/metrics-examplehuman")
    impact_dir = Path("benchmark/results/impact-examplehuman")
    patched_pipeline = Path("benchmark/results/cellprofiler/example-human-masks.cppipe")
    bridge_json = Path("benchmark/results/cellprofiler/example-human-masks.json")
    image_table = masks_tiff_dir / "morphojet-images.csv"
    cp_long = cp_dir / "Objects.long.csv"

    run(
        [
            "python3",
            "benchmark/export_cellprofiler_masks.py",
            str(EXAMPLE_PIPELINE),
            "--out",
            str(patched_pipeline),
            "--bridge-json",
            str(bridge_json),
        ]
    )

    if not args.skip_cellprofiler:
        remove(cp_dir)
        run(
            [
                "python3",
                "benchmark/run_docker_metrics.py",
                "--name",
                "cellprofiler-examplehuman",
                "--container-name",
                "morphojet-examplehuman-cellprofiler",
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
                str(patched_pipeline),
                "-i",
                str(EXAMPLE_IMAGES),
                "-o",
                str(cp_dir),
            ]
        )

    remove(masks_tiff_dir)
    run(
        [
            "python3",
            "benchmark/convert_npy_masks_to_tiff.py",
            "--base-dir",
            str(cp_dir),
            "--out-dir",
            str(masks_tiff_dir),
        ]
    )
    run(
        [
            "python3",
            "benchmark/build_oracle_image_table.py",
            "--base-dir",
            ".",
            "--bridge-json",
            str(bridge_json),
            "--channel",
            "DNA",
            "benchmark/data/cellprofiler/prepared/ExampleHuman/images/*d0.tif",
            "(.+)d0\\.tif$",
            "--channel",
            "PH3",
            "benchmark/data/cellprofiler/prepared/ExampleHuman/images/*d1.tif",
            "(.+)d1\\.tif$",
            "--mask-glob-template",
            "benchmark/results/cellprofiler-run-426-labels-tiff/morphojet_masks/{safe_name}/*_MorphoJetMask_{safe_name}.tif",
            "--mask-key-regex-template",
            "(.+)d0_MorphoJetMask_{safe_name}\\.tif$",
            "--out",
            str(image_table),
        ]
    )
    run(
        [
            "python3",
            "benchmark/materialize_cellprofiler_oracle.py",
            "--object",
            f"Cells={cp_dir / 'Cells.csv'}",
            "--object",
            f"Cytoplasm={cp_dir / 'Cytoplasm.csv'}",
            "--object",
            f"Nuclei={cp_dir / 'Nuclei.csv'}",
            "--channels",
            "DNA,PH3",
            "--out",
            str(cp_long),
        ]
    )

    run([cargo_bin(), "build", "--release", "-p", "morphojet"])
    remove(mj_dir)
    run(
        [
            "python3",
            "benchmark/run_command_metrics.py",
            "--name",
            "morphojet-examplehuman",
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
    parity_dir.mkdir(parents=True, exist_ok=True)
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
            str(parity_dir / "example-human-objects-parity.md"),
            "--json-out",
            str(parity_dir / "example-human-objects-parity.json"),
            "--fail-on-gap",
        ]
    )
    run(
        [
            "python3",
            "benchmark/impact_report.py",
            "--image-rows",
            "6",
            "--parity-json",
            str(parity_dir / "example-human-objects-parity.json"),
            "--cellprofiler-metrics-json",
            str(metrics_dir / "cellprofiler-examplehuman.metrics.json"),
            "--morphojet-metrics-json",
            str(metrics_dir / "morphojet-examplehuman.metrics.json"),
            "--out",
            str(impact_dir / "summary.md"),
            "--json-out",
            str(impact_dir / "summary.json"),
        ]
    )
    print("ExampleHuman oracle smoke complete")
    print(f"parity: {parity_dir / 'example-human-objects-parity.md'}")
    print(f"impact: {impact_dir / 'summary.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
