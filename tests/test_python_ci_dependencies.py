#!/usr/bin/env python3
"""Ensure GitHub workflows install dependencies before running image tests."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALL_COMMAND = "python3 -m pip install --disable-pip-version-check --requirement requirements-l3.txt"
SETUP_PYTHON = "actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1"


class PythonCiDependenciesTest(unittest.TestCase):
    def test_python_test_workflows_install_image_dependencies(self) -> None:
        workflow_paths = [
            ROOT / ".github/workflows/cellbindb-l3.yml",
            ROOT / ".github/workflows/ci.yml",
            ROOT / ".github/workflows/release.yml",
        ]

        for workflow_path in workflow_paths:
            workflow_text = workflow_path.read_text(encoding="utf-8")
            with self.subTest(workflow=workflow_path.name):
                self.assertIn(SETUP_PYTHON, workflow_text)
                self.assertIn('python-version: "3.12"', workflow_text)
                self.assertIn("cache-dependency-path: requirements-l3.txt", workflow_text)
                self.assertIn(INSTALL_COMMAND, workflow_text)


if __name__ == "__main__":
    unittest.main()
