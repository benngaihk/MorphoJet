#!/usr/bin/env python3
"""Run a command and capture elapsed time, logs, and peak RSS metadata."""

from __future__ import annotations

import argparse
import json
import platform
import resource
import subprocess
import sys
import time
from pathlib import Path


def maxrss_to_mb(value: int) -> float:
    if sys.platform == "darwin":
        return value / (1024 * 1024)
    return value / 1024


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--fail-on-nonzero", action="store_true")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("missing command after --")

    args.out.mkdir(parents=True, exist_ok=True)
    started_usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    started = time.perf_counter()
    completed = subprocess.run(command, text=True, capture_output=True)
    elapsed = time.perf_counter() - started
    ended_usage = resource.getrusage(resource.RUSAGE_CHILDREN)

    stdout_path = args.out / f"{args.name}.stdout.log"
    stderr_path = args.out / f"{args.name}.stderr.log"
    metrics_path = args.out / f"{args.name}.metrics.json"
    stdout_path.write_text(completed.stdout)
    stderr_path.write_text(completed.stderr)

    peak_rss_raw = max(ended_usage.ru_maxrss, started_usage.ru_maxrss)
    metrics = {
        "name": args.name,
        "command": command,
        "exit_code": completed.returncode,
        "elapsed_seconds": elapsed,
        "peak_rss_mb": maxrss_to_mb(peak_rss_raw),
        "peak_rss_raw": peak_rss_raw,
        "peak_rss_unit": "bytes" if sys.platform == "darwin" else "kilobytes",
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python": platform.python_version(),
        "stdout_log": str(stdout_path),
        "stderr_log": str(stderr_path),
    }
    metrics_path.write_text(json.dumps(metrics, indent=2) + "\n")
    print(f"wrote {metrics_path}")
    print(f"elapsed_seconds={elapsed:.6f}")
    print(f"peak_rss_mb={metrics['peak_rss_mb']:.3f}")

    if args.fail_on_nonzero and completed.returncode != 0:
        return completed.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
