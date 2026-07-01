#!/usr/bin/env python3
"""Compare two normalized measurement CSV files and write a parity report."""

from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class ColumnDiff:
    column: str
    compared: int = 0
    failures: int = 0
    max_abs: float = 0.0
    max_rel: float = 0.0


def read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        return reader.fieldnames or [], list(reader)


def parse_number(value: str) -> float | None:
    try:
        number = float(value)
    except ValueError:
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def row_key(row: dict[str, str], keys: list[str]) -> tuple[str, ...]:
    return tuple(row.get(key, "") for key in keys)


def compare_values(left: float, right: float, abs_tol: float, rel_tol: float) -> tuple[bool, float, float]:
    abs_diff = abs(left - right)
    scale = max(abs(left), abs(right), 1.0)
    rel_diff = abs_diff / scale
    return abs_diff <= abs_tol or rel_diff <= rel_tol, abs_diff, rel_diff


def compare(
    expected_path: Path,
    actual_path: Path,
    keys: list[str],
    abs_tol: float,
    rel_tol: float,
) -> tuple[bool, str, dict[str, object]]:
    expected_columns, expected_rows = read_rows(expected_path)
    actual_columns, actual_rows = read_rows(actual_path)

    common_columns = [column for column in expected_columns if column in actual_columns and column not in keys]
    missing_actual_columns = [column for column in expected_columns if column not in actual_columns]
    extra_actual_columns = [column for column in actual_columns if column not in expected_columns]

    expected_by_key = {row_key(row, keys): row for row in expected_rows}
    actual_by_key = {row_key(row, keys): row for row in actual_rows}
    missing_rows = sorted(set(expected_by_key) - set(actual_by_key))
    extra_rows = sorted(set(actual_by_key) - set(expected_by_key))
    shared_keys = sorted(set(expected_by_key) & set(actual_by_key))

    column_diffs = {column: ColumnDiff(column) for column in common_columns}
    string_failures: list[str] = []

    for key in shared_keys:
        expected = expected_by_key[key]
        actual = actual_by_key[key]
        for column in common_columns:
            expected_number = parse_number(expected.get(column, ""))
            actual_number = parse_number(actual.get(column, ""))
            if expected_number is None or actual_number is None:
                if expected.get(column, "") != actual.get(column, ""):
                    string_failures.append(f"{key} {column}: {expected.get(column, '')!r} != {actual.get(column, '')!r}")
                continue

            ok, abs_diff, rel_diff = compare_values(expected_number, actual_number, abs_tol, rel_tol)
            diff = column_diffs[column]
            diff.compared += 1
            diff.max_abs = max(diff.max_abs, abs_diff)
            diff.max_rel = max(diff.max_rel, rel_diff)
            if not ok:
                diff.failures += 1

    failed_columns = [diff for diff in column_diffs.values() if diff.failures]
    passed = not (missing_actual_columns or missing_rows or extra_rows or failed_columns or string_failures)

    lines = [
        "# Measurement Parity Report",
        "",
        f"- expected: `{expected_path}`",
        f"- actual: `{actual_path}`",
        f"- keys: `{', '.join(keys)}`",
        f"- abs_tol: `{abs_tol}`",
        f"- rel_tol: `{rel_tol}`",
        f"- expected_rows: `{len(expected_rows)}`",
        f"- actual_rows: `{len(actual_rows)}`",
        f"- status: `{'PASS' if passed else 'FAIL'}`",
        "",
        "## Schema",
        "",
        f"- missing_actual_columns: `{len(missing_actual_columns)}`",
        f"- extra_actual_columns: `{len(extra_actual_columns)}`",
    ]

    if missing_actual_columns:
        lines.append(f"- missing: `{', '.join(missing_actual_columns)}`")
    if extra_actual_columns:
        lines.append(f"- extra: `{', '.join(extra_actual_columns)}`")

    lines.extend(
        [
            "",
            "## Rows",
            "",
            f"- missing_rows: `{len(missing_rows)}`",
            f"- extra_rows: `{len(extra_rows)}`",
            "",
            "## Numeric Columns",
            "",
            "| Column | Compared | Failures | Max Abs | Max Rel |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for diff in column_diffs.values():
        if diff.compared:
            lines.append(
                f"| {diff.column} | {diff.compared} | {diff.failures} | {diff.max_abs:.10g} | {diff.max_rel:.10g} |"
            )

    if string_failures:
        lines.extend(["", "## String Failures", ""])
        for failure in string_failures[:20]:
            lines.append(f"- {failure}")
        if len(string_failures) > 20:
            lines.append(f"- ... {len(string_failures) - 20} more")

    summary = {
        "status": "PASS" if passed else "FAIL",
        "expected_rows": len(expected_rows),
        "actual_rows": len(actual_rows),
        "shared_rows": len(shared_keys),
        "missing_actual_columns": missing_actual_columns,
        "extra_actual_columns": extra_actual_columns,
        "missing_rows": len(missing_rows),
        "extra_rows": len(extra_rows),
        "string_failures": len(string_failures),
        "numeric_compared": sum(diff.compared for diff in column_diffs.values()),
        "numeric_failures": sum(diff.failures for diff in column_diffs.values()),
        "columns": [asdict(diff) for diff in column_diffs.values()],
    }

    return passed, "\n".join(lines) + "\n", summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("expected", type=Path)
    parser.add_argument("actual", type=Path)
    parser.add_argument("--keys", default="ImageNumber,ObjectNumber,Channel")
    parser.add_argument("--abs-tol", type=float, default=1e-6)
    parser.add_argument("--rel-tol", type=float, default=1e-5)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--fail-on-gap", action="store_true")
    args = parser.parse_args()

    keys = [key.strip() for key in args.keys.split(",") if key.strip()]
    passed, report, summary = compare(args.expected, args.actual, keys, args.abs_tol, args.rel_tol)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report)
    else:
        print(report, end="")
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(summary, indent=2) + "\n")
    return 1 if args.fail_on_gap and not passed else 0


if __name__ == "__main__":
    raise SystemExit(main())
