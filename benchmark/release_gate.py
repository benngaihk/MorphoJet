#!/usr/bin/env python3
"""Run MorphoJet release-readiness gates and write an auditable report."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Gate:
    name: str
    command: list[str] | None
    status: str
    elapsed_seconds: float
    detail: str


def run_command(name: str, command: list[str]) -> Gate:
    started = time.perf_counter()
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    elapsed = time.perf_counter() - started
    detail = completed.stdout[-4000:]
    if completed.stderr:
        detail = (detail + "\n" + completed.stderr[-4000:]).strip()
    return Gate(
        name=name,
        command=command,
        status="PASS" if completed.returncode == 0 else "FAIL",
        elapsed_seconds=elapsed,
        detail=detail,
    )


def cargo_bin() -> str:
    env_cargo = os.environ.get("CARGO")
    if env_cargo:
        return env_cargo
    cargo = shutil.which("cargo")
    if cargo:
        return cargo
    home_cargo = Path.home() / ".cargo" / "bin" / "cargo"
    if home_cargo.exists():
        return str(home_cargo)
    return "cargo"


def load_json(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(path)
    return json.loads(path.read_text())


def validate_l3_artifacts() -> Gate:
    started = time.perf_counter()
    try:
        parity = load_json(ROOT / "benchmark/results/cellbindb/oracle-full/parity.json")
        impact = load_json(ROOT / "benchmark/results/cellbindb/oracle-full/impact.json")
        failures = []
        if parity.get("status") != "PASS":
            failures.append(f"parity status is {parity.get('status')}")
        if parity.get("expected_rows") != 107936 or parity.get("actual_rows") != 107936:
            failures.append(
                f"unexpected row counts expected={parity.get('expected_rows')} actual={parity.get('actual_rows')}"
            )
        if parity.get("numeric_failures") != 0:
            failures.append(f"numeric_failures={parity.get('numeric_failures')}")
        if impact.get("status") != "PASS":
            failures.append(f"impact status is {impact.get('status')}")
        if not impact.get("gates") or not all(gate.get("passed") for gate in impact["gates"]):
            failures.append("one or more impact gates did not pass")
        status = "FAIL" if failures else "PASS"
        detail = "; ".join(failures) if failures else (
            "CellBinDB L3 artifacts PASS: "
            f"rows={parity.get('actual_rows')}, "
            f"speedup={impact.get('speedup'):.2f}x, "
            f"rss_ratio={impact.get('rss_ratio'):.2%}"
        )
    except Exception as exc:  # noqa: BLE001 - report exact release gate failure.
        status = "FAIL"
        detail = f"{type(exc).__name__}: {exc}"
    return Gate(
        name="Validate existing CellBinDB L3 artifacts",
        command=None,
        status=status,
        elapsed_seconds=time.perf_counter() - started,
        detail=detail,
    )


def render_markdown(gates: list[Gate], out_json: Path) -> str:
    status = "PASS" if all(gate.status == "PASS" for gate in gates) else "FAIL"
    lines = [
        "# Release Gate Report",
        "",
        f"- status: `{status}`",
        f"- json: `{out_json}`",
        "",
        "| Gate | Status | Seconds |",
        "|---|---:|---:|",
    ]
    for gate in gates:
        lines.append(f"| {gate.name} | {gate.status} | {gate.elapsed_seconds:.3f} |")
    lines.extend(["", "## Details", ""])
    for gate in gates:
        lines.append(f"### {gate.name}")
        lines.append("")
        lines.append(f"- status: `{gate.status}`")
        if gate.command:
            lines.append(f"- command: `{' '.join(gate.command)}`")
        if gate.detail:
            lines.append("")
            lines.append("```text")
            lines.append(gate.detail)
            lines.append("```")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-json", type=Path, default=Path("benchmark/results/release-gate/report.json"))
    parser.add_argument("--out-md", type=Path, default=Path("benchmark/results/release-gate/report.md"))
    parser.add_argument("--run-l3", action="store_true", help="Rerun the full CellBinDB L3 benchmark")
    args = parser.parse_args()

    cargo = cargo_bin()
    python_files = [
        *sorted(str(path.relative_to(ROOT)) for path in ROOT.glob("benchmark/*.py")),
        "corpus/generate_smoke.py",
        *sorted(str(path.relative_to(ROOT)) for path in ROOT.glob("tests/parity/*.py")),
    ]
    gates = [
        run_command("Rust formatting", [cargo, "fmt", "--", "--check"]),
        run_command("Rust tests", [cargo, "test"]),
        run_command("Rust clippy", [cargo, "clippy", "--all-targets", "--", "-D", "warnings"]),
        run_command("Python helper compilation", ["python3", "-m", "py_compile", *python_files]),
    ]
    if args.run_l3:
        gates.append(run_command("Run CellBinDB L3 benchmark", ["python3", "benchmark/run_cellbindb_oracle.py", "--threads", "8"]))
    gates.append(validate_l3_artifacts())

    payload = {
        "status": "PASS" if all(gate.status == "PASS" for gate in gates) else "FAIL",
        "gates": [asdict(gate) for gate in gates],
    }
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(payload, indent=2) + "\n")
    args.out_md.parent.mkdir(parents=True, exist_ok=True)
    args.out_md.write_text(render_markdown(gates, args.out_json) + "\n")
    print(f"wrote {args.out_json}")
    print(f"wrote {args.out_md}")
    print(f"status={payload['status']}")
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
