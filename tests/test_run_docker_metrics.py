#!/usr/bin/env python3
"""Unit tests for Docker metric command ownership controls."""

from __future__ import annotations

import argparse
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmark"))

import run_docker_metrics  # noqa: E402


class RunDockerMetricsTest(unittest.TestCase):
    def test_build_command_propagates_user_and_environment(self) -> None:
        args = argparse.Namespace(
            container_name="cellprofiler-test",
            platform="linux/amd64",
            user="1001:121",
            env=["HOME=/tmp"],
            volume=["/repo:/work"],
            workdir="/work",
            image="cellprofiler/cellprofiler:4.2.6",
        )

        command = run_docker_metrics.build_docker_command(args, ["cellprofiler", "--version"])

        self.assertEqual(
            [
                "docker",
                "run",
                "--rm",
                "--name",
                "cellprofiler-test",
                "--platform",
                "linux/amd64",
                "--user",
                "1001:121",
                "--env",
                "HOME=/tmp",
                "-v",
                "/repo:/work",
                "-w",
                "/work",
                "cellprofiler/cellprofiler:4.2.6",
                "cellprofiler",
                "--version",
            ],
            command,
        )

    def test_cellprofiler_oracle_runners_request_host_ownership(self) -> None:
        for relative_path in ["benchmark/run_cellbindb_oracle.py", "benchmark/run_examplehuman_oracle.py"]:
            source = (ROOT / relative_path).read_text(encoding="utf-8")
            with self.subTest(path=relative_path):
                self.assertIn('f"{os.getuid()}:{os.getgid()}"', source)
                self.assertIn('"HOME=/tmp"', source)


if __name__ == "__main__":
    unittest.main()
