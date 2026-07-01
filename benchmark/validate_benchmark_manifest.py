#!/usr/bin/env python3
"""Validate a MorphoJet oracle benchmark manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REQUIRED_PATHS = [
    ("benchmark_id",),
    ("dataset", "name"),
    ("dataset", "source_url"),
    ("dataset", "license"),
    ("cellprofiler", "version"),
    ("cellprofiler", "pipeline_path"),
    ("cellprofiler", "output_dir"),
    ("cellprofiler", "objects_csv"),
    ("morphojet", "image_table"),
    ("morphojet", "output_dir"),
    ("morphojet", "objects_csv"),
    ("parity", "keys"),
    ("parity", "abs_tol"),
    ("parity", "rel_tol"),
    ("parity", "output_dir"),
]


def get_nested(data: dict[str, Any], path: tuple[str, ...]) -> Any:
    value: Any = data
    for part in path:
        if not isinstance(value, dict) or part not in value:
            raise KeyError(".".join(path))
        value = value[part]
    return value


def validate_schema(data: dict[str, Any]) -> list[str]:
    issues = []
    for path in REQUIRED_PATHS:
        try:
            value = get_nested(data, path)
        except KeyError:
            issues.append(f"missing required field: {'.'.join(path)}")
            continue
        if isinstance(value, str) and not value.strip():
            issues.append(f"empty required field: {'.'.join(path)}")

    cellprofiler = data.get("cellprofiler", {})
    if not (cellprofiler.get("docker_image") or cellprofiler.get("command")):
        issues.append("cellprofiler.docker_image or cellprofiler.command is required")

    morphojet_threads = data.get("morphojet", {}).get("threads")
    if morphojet_threads is not None and int(morphojet_threads) <= 0:
        issues.append("morphojet.threads must be greater than 0")

    return issues


def validate_files(data: dict[str, Any], root: Path) -> list[str]:
    issues = []
    for path in [
        get_nested(data, ("cellprofiler", "pipeline_path")),
        get_nested(data, ("morphojet", "image_table")),
    ]:
        resolved = root / path
        if not resolved.is_file():
            issues.append(f"required file does not exist: {path}")
    return issues


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--check-files", action="store_true")
    args = parser.parse_args()

    data = json.loads(args.manifest.read_text())
    root = Path.cwd()
    issues = validate_schema(data)
    if args.check_files and not issues:
        issues.extend(validate_files(data, root))

    if issues:
        for issue in issues:
            print(f"ERROR: {issue}")
        return 1

    print(f"manifest ok: {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
