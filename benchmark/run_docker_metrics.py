#!/usr/bin/env python3
"""Run a Docker container and capture elapsed time plus sampled container RSS."""

from __future__ import annotations

import argparse
import json
import platform
import re
import subprocess
import sys
import threading
import time
from pathlib import Path


MEMORY_RE = re.compile(r"^\s*([0-9.]+)\s*([KMGT]i?B|B)")
UNIT_TO_MB = {
    "B": 1 / (1024 * 1024),
    "KB": 1 / 1024,
    "KIB": 1 / 1024,
    "MB": 1,
    "MIB": 1,
    "GB": 1024,
    "GIB": 1024,
    "TB": 1024 * 1024,
    "TIB": 1024 * 1024,
}


def parse_memory_mb(value: str) -> float:
    current = value.split("/", 1)[0].strip()
    match = MEMORY_RE.match(current)
    if not match:
        raise ValueError(f"could not parse Docker memory value: {value!r}")
    amount = float(match.group(1))
    unit = match.group(2).upper()
    return amount * UNIT_TO_MB[unit]


def build_docker_command(args: argparse.Namespace, command: list[str]) -> list[str]:
    docker_command = ["docker", "run", "--rm", "--name", args.container_name]
    if args.platform:
        docker_command.extend(["--platform", args.platform])
    if args.user:
        docker_command.extend(["--user", args.user])
    for environment in args.env:
        docker_command.extend(["--env", environment])
    for volume in args.volume:
        docker_command.extend(["-v", volume])
    if args.workdir:
        docker_command.extend(["-w", args.workdir])
    docker_command.append(args.image)
    docker_command.extend(command)
    return docker_command


def sample_stats(container_name: str, interval: float, samples: list[dict[str, float]], stop: threading.Event) -> None:
    while not stop.is_set():
        completed = subprocess.run(
            [
                "docker",
                "stats",
                "--no-stream",
                "--format",
                "{{json .}}",
                container_name,
            ],
            text=True,
            capture_output=True,
        )
        if completed.returncode == 0 and completed.stdout.strip():
            try:
                payload = json.loads(completed.stdout.strip().splitlines()[-1])
                samples.append(
                    {
                        "timestamp": time.time(),
                        "memory_mb": parse_memory_mb(payload["MemUsage"]),
                    }
                )
            except (KeyError, ValueError, json.JSONDecodeError):
                pass
        stop.wait(interval)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--container-name", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--platform")
    parser.add_argument("--user")
    parser.add_argument("--env", action="append", default=[])
    parser.add_argument("--volume", action="append", default=[])
    parser.add_argument("--workdir")
    parser.add_argument("--sample-interval", type=float, default=0.25)
    parser.add_argument("--fail-on-nonzero", action="store_true")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("missing container command after --")

    args.out.mkdir(parents=True, exist_ok=True)
    subprocess.run(["docker", "rm", "-f", args.container_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    docker_command = build_docker_command(args, command)

    samples: list[dict[str, float]] = []
    stop = threading.Event()
    sampler = threading.Thread(target=sample_stats, args=(args.container_name, args.sample_interval, samples, stop))
    sampler.start()
    started = time.perf_counter()
    completed = subprocess.run(docker_command, text=True, capture_output=True)
    elapsed = time.perf_counter() - started
    stop.set()
    sampler.join()

    stdout_path = args.out / f"{args.name}.stdout.log"
    stderr_path = args.out / f"{args.name}.stderr.log"
    metrics_path = args.out / f"{args.name}.metrics.json"
    stdout_path.write_text(completed.stdout)
    stderr_path.write_text(completed.stderr)
    peak_rss_mb = max((sample["memory_mb"] for sample in samples), default=0.0)
    metrics = {
        "name": args.name,
        "command": docker_command,
        "exit_code": completed.returncode,
        "elapsed_seconds": elapsed,
        "peak_rss_mb": peak_rss_mb,
        "rss_source": "docker stats MemUsage sampled during container run",
        "rss_samples": len(samples),
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
    print(f"peak_rss_mb={peak_rss_mb:.3f}")

    if args.fail_on_nonzero and completed.returncode != 0:
        return completed.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
