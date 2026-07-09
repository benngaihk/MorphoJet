#!/usr/bin/env python3
"""Unit tests for production-claim language guard."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmark"))

import validate_claim_language  # noqa: E402


class ValidateClaimLanguageTest(unittest.TestCase):
    def test_default_paths_include_chinese_readme(self) -> None:
        default_paths = {path.relative_to(ROOT).as_posix() for path in validate_claim_language.DEFAULT_PATHS}

        self.assertIn("README.md", default_paths)
        self.assertIn("README.zh-CN.md", default_paths)
        self.assertIn("MORPHOJET-FEASIBILITY.md", default_paths)
        self.assertIn("corpus/README.md", default_paths)
        self.assertIn("docs/PRODUCTION_READINESS.md", default_paths)

    def test_root_readme_contract_requires_chinese_community_coverage(self) -> None:
        failures = validate_claim_language.validate_root_readme_contract()

        self.assertEqual([], failures)
        self.assertIn(
            "Verify saved external L4 reviewer report pair",
            validate_claim_language.ROOT_README_SHARED_ANCHORS,
        )
        for anchor in ["--require-stable-report", "--expect-tag", "--expect-repo", "--expect-commit"]:
            self.assertIn(anchor, validate_claim_language.ROOT_README_SHARED_ANCHORS)

    def test_root_readme_contract_rejects_missing_chinese_l4_guidance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            readme = root / "README.md"
            readme_zh = root / "README.zh-CN.md"
            readme.write_text(
                "Language: English | [简体中文](README.zh-CN.md)\n"
                "Production-readiness gates are tracked in [docs/PRODUCTION_READINESS.md](docs/PRODUCTION_READINESS.md).\n"
                "README 中文版维护承诺\n"
                "README.zh-CN.md\n",
                encoding="utf-8",
            )
            readme_zh.write_text(
                "语言：[English](README.md) | 简体中文\n"
                "## README 中文版维护承诺\n"
                "`README.zh-CN.md` 是中文社区的一等入口，不是英文 README 的简短摘要\n"
                "## 当前里程碑状态\n"
                "中文社区\n",
                encoding="utf-8",
            )
            original_contract = validate_claim_language.ROOT_README_CONTRACT
            original_shared_anchors = validate_claim_language.ROOT_README_SHARED_ANCHORS
            validate_claim_language.ROOT_README_CONTRACT = [
                {
                    "path": readme,
                    "requirements": [
                        "Language: English | [简体中文](README.zh-CN.md)",
                        "Production-readiness gates are tracked in [docs/PRODUCTION_READINESS.md](docs/PRODUCTION_READINESS.md)",
                        "README 中文版维护承诺",
                        "README.zh-CN.md",
                    ],
                },
                {
                    "path": readme_zh,
                    "requirements": [
                        "语言：[English](README.md) | 简体中文",
                        "## README 中文版维护承诺",
                        "`README.zh-CN.md` 是中文社区的一等入口，不是英文 README 的简短摘要",
                        "## 外部 L4 试验与生产门禁",
                        "python3 benchmark/run_production_gate.py",
                        "中文社区",
                    ],
                },
            ]
            validate_claim_language.ROOT_README_SHARED_ANCHORS = []
            try:
                failures = validate_claim_language.validate_root_readme_contract()
            finally:
                validate_claim_language.ROOT_README_CONTRACT = original_contract
                validate_claim_language.ROOT_README_SHARED_ANCHORS = original_shared_anchors

        self.assertEqual(2, len(failures))
        self.assertIn("README.zh-CN.md", failures[0])
        self.assertIn("## 外部 L4 试验与生产门禁", failures[0])
        self.assertIn("python3 benchmark/run_production_gate.py", failures[1])

    def test_root_readme_contract_rejects_missing_shared_bilingual_anchor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            readme = root / "README.md"
            readme_zh = root / "README.zh-CN.md"
            readme.write_text(
                "Language: English | [简体中文](README.zh-CN.md)\n"
                "--github-release-verification-report\n",
                encoding="utf-8",
            )
            readme_zh.write_text("语言：[English](README.md) | 简体中文\n", encoding="utf-8")
            original_contract = validate_claim_language.ROOT_README_CONTRACT
            original_shared_anchors = validate_claim_language.ROOT_README_SHARED_ANCHORS
            validate_claim_language.ROOT_README_CONTRACT = [
                {"path": readme, "requirements": []},
                {"path": readme_zh, "requirements": []},
            ]
            validate_claim_language.ROOT_README_SHARED_ANCHORS = ["--github-release-verification-report"]
            try:
                failures = validate_claim_language.validate_root_readme_contract()
            finally:
                validate_claim_language.ROOT_README_CONTRACT = original_contract
                validate_claim_language.ROOT_README_SHARED_ANCHORS = original_shared_anchors

        self.assertEqual(1, len(failures))
        self.assertIn("README.zh-CN.md", failures[0])
        self.assertIn("missing required shared bilingual README anchor", failures[0])
        self.assertIn("--github-release-verification-report", failures[0])

    def test_production_readiness_contract_requires_final_wrapper_audit_binding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "PRODUCTION_READINESS.md"
            path.write_text(
                "final_production_gate --external-trial-json\n"
                "--external-evidence-package-dir\n"
                "--external-trial-verification-report\n"
                "--external-evidence-package-verification-report\n"
                "--github-release-tag\n"
                "--github-release-verification-report\n"
                "--github-workflow-verification-report\n"
                "--require-stable-report\n"
                "--expect-tag v0.1.0\n"
                "--expect-repo benngaihk/MorphoJet\n"
                "--expect-commit <final-commit>\n"
                "schema_version=2\n"
                "input_artifacts\n"
                "external_trial_root\n"
                "external_evidence_package_dir\n"
                "five saved final-input report arguments\n"
                "reruns that signoff-mode recheck before invoking the release gate\n",
                encoding="utf-8",
            )
            original_contract = validate_claim_language.PRODUCTION_READINESS_CONTRACT
            validate_claim_language.PRODUCTION_READINESS_CONTRACT = {
                "path": path,
                "requirements": original_contract["requirements"],
            }
            try:
                failures = validate_claim_language.validate_production_readiness_contract()
            finally:
                validate_claim_language.PRODUCTION_READINESS_CONTRACT = original_contract

        self.assertEqual(1, len(failures))
        self.assertIn("PRODUCTION_READINESS.md", failures[0])
        self.assertIn("--production-evidence-audit-report", failures[0])

    def test_accepts_guarded_claim_language(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "README.md"
            path.write_text(
                "MorphoJet is not production-ready yet.\n"
                "Do not claim broad CellProfiler replacement before L4.\n"
                "Not allowed before L4:\n"
                "> MorphoJet replaces CellProfiler.\n",
                encoding="utf-8",
            )

            failures = validate_claim_language.validate_paths([path])

        self.assertEqual([], failures)

    def test_rejects_unguarded_production_ready_claim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "README.md"
            path.write_text("MorphoJet is production-ready for labs.\n", encoding="utf-8")

            failures = validate_claim_language.validate_paths([path])

        self.assertEqual(1, len(failures))
        self.assertIn("unsupported production/replacement claim", failures[0])

    def test_rejects_unguarded_cellprofiler_replacement_claim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "README.md"
            path.write_text("MorphoJet replaces CellProfiler.\n", encoding="utf-8")

            failures = validate_claim_language.validate_paths([path])

        self.assertEqual(1, len(failures))
        self.assertIn("MorphoJet replaces CellProfiler", failures[0])

    def test_accepts_guarded_chinese_claim_language(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "README.zh-CN.md"
            path.write_text(
                "MorphoJet 目前不是 CellProfiler 的替代品。\n"
                "在外部 L4 和稳定 release 通过之前，不能宣称生产级。\n",
                encoding="utf-8",
            )

            failures = validate_claim_language.validate_paths([path])

        self.assertEqual([], failures)

    def test_accepts_guarded_chinese_substitution_heading(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "MORPHOJET-FEASIBILITY.md"
            path.write_text("## 为什么不替代 CellProfiler：尊重 oracle\n", encoding="utf-8")

            failures = validate_claim_language.validate_paths([path])

        self.assertEqual([], failures)

    def test_rejects_unguarded_chinese_production_claim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "README.zh-CN.md"
            path.write_text("MorphoJet 已达到生产级，可直接用于实验室。\n", encoding="utf-8")

            failures = validate_claim_language.validate_paths([path])

        self.assertEqual(1, len(failures))
        self.assertIn("unsupported production/replacement claim", failures[0])

    def test_rejects_unguarded_chinese_cellprofiler_replacement_claim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "README.zh-CN.md"
            path.write_text("MorphoJet 可以替代 CellProfiler。\n", encoding="utf-8")

            failures = validate_claim_language.validate_paths([path])

        self.assertEqual(1, len(failures))
        self.assertIn("MorphoJet 可以替代 CellProfiler", failures[0])

    def test_directory_scan_is_recursive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nested = root / "nested" / "README.md"
            nested.parent.mkdir(parents=True)
            nested.write_text("MorphoJet is production-ready for labs.\n", encoding="utf-8")

            failures = validate_claim_language.validate_paths([root])

        self.assertEqual(1, len(failures))
        self.assertIn("nested/README.md", failures[0])


if __name__ == "__main__":
    unittest.main()
