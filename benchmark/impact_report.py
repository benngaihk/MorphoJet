#!/usr/bin/env python3
"""Create a PASS/FAIL impact report from oracle benchmark metrics."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Gate:
    name: str
    required: str
    observed: str
    passed: bool


def pass_fail(value: bool) -> str:
    return "PASS" if value else "FAIL"


def render_report(gates: list[Gate], output: Path) -> None:
    status = "PASS" if all(gate.passed for gate in gates) else "FAIL"
    lines = [
        "# Industry Impact Gate Report",
        "",
        f"- status: `{status}`",
        "",
        "| Gate | Required | Observed | Status |",
        "|---|---:|---:|---:|",
    ]
    for gate in gates:
        lines.append(f"| {gate.name} | {gate.required} | {gate.observed} | {pass_fail(gate.passed)} |")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "A PASS means this benchmark dataset supports the narrow claim being tested. It does not prove full CellProfiler replacement or broad image-analysis superiority.",
            "A FAIL means the claim must be narrowed before public use.",
        ]
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image-rows", type=int, required=True)
    parser.add_argument("--object-count-parity", type=float, required=True)
    parser.add_argument("--numeric-parity", type=float, required=True)
    parser.add_argument("--cellprofiler-seconds", type=float, required=True)
    parser.add_argument("--morphojet-seconds", type=float, required=True)
    parser.add_argument("--cellprofiler-rss-mb", type=float, required=True)
    parser.add_argument("--morphojet-rss-mb", type=float, required=True)
    parser.add_argument("--out", type=Path, default=Path("benchmark/results/impact/summary.md"))
    parser.add_argument("--json-out", type=Path, default=Path("benchmark/results/impact/summary.json"))
    parser.add_argument("--fail-on-gap", action="store_true")
    args = parser.parse_args()

    speedup = args.cellprofiler_seconds / args.morphojet_seconds if args.morphojet_seconds else 0.0
    rss_ratio = args.morphojet_rss_mb / args.cellprofiler_rss_mb if args.cellprofiler_rss_mb else 1.0
    gates = [
        Gate("Scale", ">=1000 image rows", str(args.image_rows), args.image_rows >= 1000),
        Gate("Object count parity", "100%", f"{args.object_count_parity:.4%}", args.object_count_parity >= 1.0),
        Gate("Core numeric parity", ">=99%", f"{args.numeric_parity:.4%}", args.numeric_parity >= 0.99),
        Gate("Wall-clock speedup", ">=10x", f"{speedup:.2f}x", speedup >= 10.0),
        Gate("Peak RSS ratio", "<=50%", f"{rss_ratio:.2%}", rss_ratio <= 0.50),
    ]
    render_report(gates, args.out)
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(
        json.dumps(
            {
                "status": "PASS" if all(gate.passed for gate in gates) else "FAIL",
                "speedup": speedup,
                "rss_ratio": rss_ratio,
                "gates": [gate.__dict__ for gate in gates],
            },
            indent=2,
        )
        + "\n"
    )
    print(f"wrote {args.out}")
    print(f"wrote {args.json_out}")
    return 1 if args.fail_on_gap and not all(gate.passed for gate in gates) else 0


if __name__ == "__main__":
    raise SystemExit(main())
