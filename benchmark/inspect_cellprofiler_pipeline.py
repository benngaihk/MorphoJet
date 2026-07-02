#!/usr/bin/env python3
"""Inspect a CellProfiler .cppipe for MorphoJet oracle-readiness."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path


MODULE_RE = re.compile(r"^([A-Za-z0-9_]+):\[module_num:(\d+)\|")


@dataclass
class Module:
    kind: str
    module_num: int
    settings: dict[str, list[str]]


def parse_pipeline(path: Path) -> list[Module]:
    modules: list[Module] = []
    current: Module | None = None
    for line in path.read_text(errors="replace").splitlines():
        match = MODULE_RE.match(line)
        if match:
            current = Module(kind=match.group(1), module_num=int(match.group(2)), settings={})
            modules.append(current)
            continue
        if current and line.startswith("    ") and ":" in line:
            key, value = line.strip().split(":", 1)
            current.settings.setdefault(key, []).append(value.strip())
    return modules


def split_names(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def collect_summary(modules: list[Module]) -> dict:
    object_outputs: dict[str, list[str]] = {}
    measured_objects: set[str] = set()
    measured_images: set[str] = set()
    saved_images: list[dict[str, str]] = []
    export_modules: list[int] = []
    convert_modules: list[dict[str, object]] = []

    for module in modules:
        settings = module.settings
        if module.kind == "IdentifyPrimaryObjects":
            for name in settings.get("Name the primary objects to be identified", []):
                object_outputs.setdefault(name, []).append(module.kind)
        elif module.kind == "IdentifySecondaryObjects":
            for name in settings.get("Name the objects to be identified", []):
                object_outputs.setdefault(name, []).append(module.kind)
        elif module.kind == "IdentifyTertiaryObjects":
            for name in settings.get("Name the tertiary objects to be identified", []):
                object_outputs.setdefault(name, []).append(module.kind)
        elif module.kind == "MeasureObjectIntensity":
            for value in settings.get("Select objects to measure", []):
                measured_objects.update(split_names(value))
            for value in settings.get("Select images to measure", []):
                measured_images.update(split_names(value))
        elif module.kind == "MeasureObjectSizeShape":
            for value in settings.get("Select object sets to measure", []):
                measured_objects.update(split_names(value))
        elif module.kind == "SaveImages":
            saved_images.append(
                {
                    "module_num": str(module.module_num),
                    "type": first(settings, "Select the type of image to save"),
                    "image": first(settings, "Select the image to save"),
                    "format": first(settings, "Saved file format"),
                }
            )
        elif module.kind == "ExportToSpreadsheet":
            export_modules.append(module.module_num)
        elif module.kind == "ConvertObjectsToImage":
            convert_modules.append(
                {
                    "module_num": module.module_num,
                    "input_objects": first(settings, "Select the input objects"),
                    "output_image": first(settings, "Name the output image"),
                }
            )

    measured_object_list = sorted(measured_objects)
    missing_label_exports = [
        name
        for name in measured_object_list
        if not any(item.get("input_objects") == name for item in convert_modules)
    ]

    return {
        "object_outputs": object_outputs,
        "measured_objects": measured_object_list,
        "measured_images": sorted(measured_images),
        "saved_images": saved_images,
        "export_modules": export_modules,
        "convert_objects_to_image_modules": convert_modules,
        "missing_label_exports": missing_label_exports,
        "m0_ready": not missing_label_exports and bool(measured_object_list),
        "modules": [asdict(module) for module in modules],
    }


def first(settings: dict[str, list[str]], key: str) -> str:
    values = settings.get(key, [])
    return values[0] if values else ""


def render_markdown(path: Path, summary: dict) -> str:
    lines = [
        "# CellProfiler Pipeline Inspection",
        "",
        f"- pipeline: `{path}`",
        f"- m0_ready: `{'true' if summary['m0_ready'] else 'false'}`",
        "",
        "## Object Outputs",
        "",
        "| Object | Producer Modules | Measured | Missing Label Export |",
        "|---|---|---:|---:|",
    ]
    measured = set(summary["measured_objects"])
    missing = set(summary["missing_label_exports"])
    for name, producers in summary["object_outputs"].items():
        lines.append(
            f"| {name} | {', '.join(producers)} | {'yes' if name in measured else 'no'} | {'yes' if name in missing else 'no'} |"
        )
    lines.extend(
        [
            "",
            "## Measured Images",
            "",
            ", ".join(summary["measured_images"]) or "None found.",
            "",
            "## SaveImages Modules",
            "",
            "| Module | Type | Image | Format |",
            "|---:|---|---|---|",
        ]
    )
    for item in summary["saved_images"]:
        lines.append(f"| {item['module_num']} | {item['type']} | {item['image']} | {item['format']} |")
    lines.extend(
        [
            "",
            "## Required Bridge Work",
            "",
        ]
    )
    if summary["missing_label_exports"]:
        lines.append(
            "Add object-to-label-image export for: "
            + ", ".join(f"`{name}`" for name in summary["missing_label_exports"])
            + "."
        )
    else:
        lines.append("No missing label exports detected.")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pipeline", type=Path)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--md-out", type=Path)
    parser.add_argument("--fail-if-not-m0-ready", action="store_true")
    args = parser.parse_args()

    modules = parse_pipeline(args.pipeline)
    summary = collect_summary(modules)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(summary, indent=2) + "\n")
    if args.md_out:
        args.md_out.parent.mkdir(parents=True, exist_ok=True)
        args.md_out.write_text(render_markdown(args.pipeline, summary))
    if not args.json_out and not args.md_out:
        print(json.dumps(summary, indent=2))
    if args.fail_if_not_m0_ready and not summary["m0_ready"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
