#!/usr/bin/env python3
"""Reject unsupported production and replacement claims in source docs."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def unique_paths(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in paths:
        resolved = path.resolve(strict=False)
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(path)
    return unique


DEFAULT_PATHS = unique_paths(
    [
        *sorted(ROOT.glob("*.md")),
        *sorted((ROOT / "docs").rglob("*.md")),
        *sorted((ROOT / "corpus").rglob("*.md")),
    ]
)
ROOT_README_CONTRACT = [
    {
        "path": ROOT / "README.md",
        "requirements": [
            "Language: English | [简体中文](README.zh-CN.md)",
            "Production-readiness gates are tracked in [docs/PRODUCTION_READINESS.md](docs/PRODUCTION_READINESS.md)",
            "README 中文版维护承诺",
            "README.zh-CN.md",
        ],
    },
    {
        "path": ROOT / "README.zh-CN.md",
        "requirements": [
            "语言：[English](README.md) | 简体中文",
            "## README 中文版维护承诺",
            "`README.zh-CN.md` 是中文社区的一等入口，不是英文 README 的简短摘要",
            "## 外部 L4 试验与生产门禁",
            "## 中文社区验证入口",
            "## 当前里程碑状态",
            "python3 benchmark/prepare_external_l4_trial.py --workspace path/to/external-trial",
            "python3 benchmark/run_production_gate.py",
            "README.md",
            "README.zh-CN.md",
            "真实外部 L4 workflow trial",
            "saved stable-release verifier report",
            "中文社区",
        ],
    },
]
ROOT_README_SHARED_ANCHORS = [
    "claim_status=NOT_PRODUCTION_CLAIM",
    "evidence_scope=RELEASE_GATE_PRECHECK",
    "final_production_signoff=false",
    "production_claim_status=INCOMPLETE",
    "benchmark/prepare_external_l4_trial.py --workspace path/to/external-trial",
    "benchmark/run_production_gate.py",
    "benchmark/verify_release_gate_report.py",
    "--external-trial-verification-report",
    "--external-evidence-package-verification-report",
    "--github-release-verification-report",
    "--github-workflow-verification-report",
    "--production-evidence-audit-report",
    "--require-stable-report",
    "--expect-tag",
    "--expect-repo",
    "--expect-commit",
    "Verify saved external L4 reviewer report pair",
    "README.md",
    "README.zh-CN.md",
]
PRODUCTION_READINESS_CONTRACT = {
    "path": ROOT / "docs" / "PRODUCTION_READINESS.md",
    "requirements": [
        "final_production_gate --external-trial-json",
        "--external-evidence-package-dir",
        "--external-trial-verification-report",
        "--external-evidence-package-verification-report",
        "--github-release-tag",
        "--github-release-verification-report",
        "--github-workflow-verification-report",
        "--production-evidence-audit-report",
        "--require-stable-report",
        "--expect-tag v0.1.0",
        "--expect-repo benngaihk/MorphoJet",
        "--expect-commit <final-commit>",
        "five saved final-input report arguments",
        "reruns that signoff-mode recheck before invoking the release gate",
    ],
}
RISKY_PATTERNS = [
    re.compile(r"\bproduction[- ]ready\b", re.IGNORECASE),
    re.compile(r"\bproduction[- ]grade\b", re.IGNORECASE),
    re.compile(r"\bready for production\b", re.IGNORECASE),
    re.compile(r"\breplaces?\s+CellProfiler\b", re.IGNORECASE),
    re.compile(r"\bCellProfiler[- ]replacement\b", re.IGNORECASE),
    re.compile(r"生产级"),
    re.compile(r"生产就绪"),
    re.compile(r"生产可用"),
    re.compile(r"可用于生产"),
    re.compile(r"达到生产标准"),
    re.compile(r"(?:替代|取代)\s*CellProfiler", re.IGNORECASE),
    re.compile(r"CellProfiler\s*(?:的)?替代品", re.IGNORECASE),
]
SAFE_LINE_MARKERS = [
    "not ",
    "not-",
    "must not",
    "should not",
    "do not",
    "does not",
    "without",
    "until",
    "unproven",
    "unsupported",
    "incomplete",
    "blocking",
    "remain",
    "remains",
    "before",
    "not enough",
    "not allowed",
    "不是",
    "不能",
    "不可",
    "不应",
    "不要",
    "不替代",
    "不取代",
    "不能替代",
    "不能取代",
    "尚未",
    "未完成",
    "未通过",
    "未满足",
    "直到",
    "之前",
    "除非",
    "不足以",
    "不代表",
    "阻塞",
    "保持",
    "仍",
]
SAFE_CONTEXT_MARKERS = [
    "not allowed",
    "not production-grade until",
    "must not",
    "should not",
    "do not",
    "不能",
    "不可",
    "不是",
    "尚未",
    "直到",
    "不替代",
    "不取代",
]


def risky_matches(line: str) -> list[str]:
    return [pattern.pattern for pattern in RISKY_PATTERNS if pattern.search(line)]


def is_guarded_claim(line: str, previous_lines: list[str]) -> bool:
    normalized = line.lower()
    if any(marker in normalized for marker in SAFE_LINE_MARKERS):
        return True
    context = "\n".join(previous_lines[-5:]).lower()
    return any(marker in context for marker in SAFE_CONTEXT_MARKERS)


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def validate_file(path: Path) -> list[str]:
    failures: list[str] = []
    lines = path.read_text(encoding="utf-8").splitlines()
    previous: list[str] = []
    for index, line in enumerate(lines, start=1):
        matches = risky_matches(line)
        if matches and not is_guarded_claim(line, previous):
            failures.append(f"{display_path(path)}:{index}: unsupported production/replacement claim: {line.strip()}")
        previous.append(line)
    return failures


def validate_paths(paths: list[Path]) -> list[str]:
    failures: list[str] = []
    for path in paths:
        if path.is_dir():
            for child in sorted(path.rglob("*.md")):
                failures.extend(validate_file(child))
        else:
            failures.extend(validate_file(path))
    return failures


def validate_root_readme_contract() -> list[str]:
    failures: list[str] = []
    readme_texts: dict[Path, str] = {}
    for contract in ROOT_README_CONTRACT:
        path = contract["path"]
        if not isinstance(path, Path) or not path.is_file():
            failures.append(f"{display_path(path)}: missing required root README")
            continue
        text = path.read_text(encoding="utf-8")
        readme_texts[path] = text
        for required in contract["requirements"]:
            if required not in text:
                failures.append(
                    f"{display_path(path)}: missing required bilingual README contract text: {required}"
                )
    for path, text in readme_texts.items():
        if path.name not in {"README.md", "README.zh-CN.md"}:
            continue
        for required in ROOT_README_SHARED_ANCHORS:
            if required not in text:
                failures.append(f"{display_path(path)}: missing required shared bilingual README anchor: {required}")
    return failures


def validate_production_readiness_contract() -> list[str]:
    failures: list[str] = []
    path = PRODUCTION_READINESS_CONTRACT["path"]
    if not isinstance(path, Path) or not path.is_file():
        failures.append(f"{display_path(path)}: missing production readiness document")
        return failures
    text = path.read_text(encoding="utf-8")
    for required in PRODUCTION_READINESS_CONTRACT["requirements"]:
        if required not in text:
            failures.append(f"{display_path(path)}: missing required production readiness contract text: {required}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", type=Path, help="Markdown files or directories to scan")
    args = parser.parse_args()
    paths = args.paths or DEFAULT_PATHS
    failures = validate_paths(paths)
    if not args.paths:
        failures.extend(validate_root_readme_contract())
        failures.extend(validate_production_readiness_contract())
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print(f"claim language ok: {len(paths)} path(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
