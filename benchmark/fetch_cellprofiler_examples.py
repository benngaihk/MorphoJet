#!/usr/bin/env python3
"""Fetch pinned CellProfiler example candidates for oracle preparation."""

from __future__ import annotations

import argparse
import fnmatch
import json
import shutil
import subprocess
from pathlib import Path


def run(command: list[str], cwd: Path | None = None) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def load_catalog(path: Path) -> dict:
    return json.loads(path.read_text())


def select_candidate(catalog: dict, candidate_id: str) -> dict:
    for candidate in catalog["candidates"]:
        if candidate["id"] == candidate_id:
            return candidate
    raise SystemExit(f"unknown candidate: {candidate_id}")


def fetch_repo(catalog: dict, repo_dir: Path) -> None:
    source = catalog["source"]
    if repo_dir.exists():
        shutil.rmtree(repo_dir)
    run(["git", "clone", "--depth", "1", source["repo"], str(repo_dir)])
    current = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_dir, text=True).strip()
    expected = source["pinned_head"]
    if current != expected:
        raise SystemExit(f"CellProfiler examples HEAD mismatch: expected {expected}, got {current}")


def materialize_candidate(repo_dir: Path, candidate: dict, out_dir: Path) -> None:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    source_dir = repo_dir / candidate["path"]
    if not source_dir.is_dir():
        raise SystemExit(f"candidate source directory missing: {source_dir}")

    shutil.copytree(source_dir, out_dir / candidate["path"])


def write_manifest_stub(catalog: dict, candidate: dict, out_dir: Path, manifest_out: Path) -> None:
    image_paths = sorted(
        path
        for path in (out_dir / candidate["path"] / "images").iterdir()
        if fnmatch.fnmatch(str(path.relative_to(out_dir)), candidate["images_glob"])
    )
    manifest = {
        "benchmark_id": f"cellprofiler-{candidate['id']}",
        "description": f"Prepared from {catalog['source']['name']} at {catalog['source']['pinned_head']}",
        "dataset": {
            "name": candidate["id"],
            "source_url": catalog["source"]["repo"],
            "source_commit": catalog["source"]["pinned_head"],
            "license": candidate["license"],
            "download_instructions": f"python3 benchmark/fetch_cellprofiler_examples.py --candidate {candidate['id']}",
            "image_count": len(image_paths),
            "m0_status": candidate["m0_status"],
            "m0_gap": candidate["m0_gap"],
        },
        "cellprofiler": {
            "version": "pin exact CellProfiler version before running",
            "docker_image": "cellprofiler/cellprofiler:latest",
            "pipeline_path": str(out_dir / candidate["pipeline"]),
            "output_dir": "benchmark/results/cellprofiler",
            "objects_csv": "benchmark/results/cellprofiler/Objects.csv",
        },
        "morphojet": {
            "image_table": "benchmark/cellprofiler/images.csv",
            "output_dir": "benchmark/results/morphojet",
            "objects_csv": "benchmark/results/morphojet/Objects.csv",
            "threads": 8,
        },
        "parity": {
            "keys": "ImageNumber,ObjectNumber,Channel",
            "abs_tol": 1e-6,
            "rel_tol": 1e-5,
            "output_dir": "benchmark/results/parity",
        },
        "impact": {
            "minimum_image_rows": 1000,
            "minimum_object_count_parity": 1.0,
            "minimum_numeric_parity": 0.99,
            "minimum_speedup": 10.0,
            "maximum_rss_ratio": 0.5,
        },
    }
    manifest_out.parent.mkdir(parents=True, exist_ok=True)
    manifest_out.write_text(json.dumps(manifest, indent=2) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", default="example-human")
    parser.add_argument("--catalog", type=Path, default=Path("benchmark/cellprofiler/candidates.json"))
    parser.add_argument("--work-dir", type=Path, default=Path("benchmark/data/cellprofiler/examples-repo"))
    parser.add_argument("--out-dir", type=Path, default=Path("benchmark/data/cellprofiler/prepared"))
    parser.add_argument("--manifest-out", type=Path, default=Path("benchmark/cellprofiler/manifest.candidate.json"))
    args = parser.parse_args()

    catalog = load_catalog(args.catalog)
    candidate = select_candidate(catalog, args.candidate)
    fetch_repo(catalog, args.work_dir)
    materialize_candidate(args.work_dir, candidate, args.out_dir)
    write_manifest_stub(catalog, candidate, args.out_dir, args.manifest_out)
    print(f"prepared candidate: {candidate['id']}")
    print(f"manifest: {args.manifest_out}")
    print(f"m0_status: {candidate['m0_status']}")
    print(f"m0_gap: {candidate['m0_gap']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
