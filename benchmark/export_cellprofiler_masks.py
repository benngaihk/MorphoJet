#!/usr/bin/env python3
"""Add CellProfiler object label exports to a copied pipeline."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from inspect_cellprofiler_pipeline import collect_summary, parse_pipeline


def sanitize(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "Objects"


def save_objects_module(module_num: int, object_name: str, base_image: str, mask_subdir: str) -> str:
    safe_name = sanitize(object_name)
    return "\n".join(
        [
            (
                "SaveImages:"
                f"[module_num:{module_num}|svn_version:'Unknown'|variable_revision_number:15|"
                "show_window:False|notes:['MorphoJet bridge: save object labels.']|"
                "batch_state:array([], dtype=uint8)|enabled:True|wants_pause:False]"
            ),
            "    Select the type of image to save:Objects",
            "    Select the image to save:None",
            f"    Select the objects to save:{object_name}",
            "    Select the module display window to save:Do not use",
            "    Select method for constructing file names:From image filename",
            f"    Select image name for file prefix:{base_image}",
            f"    Enter single file name:{safe_name}_MorphoJetMask",
            "    Number of digits:4",
            "    Append a suffix to the image file name?:Yes",
            f"    Text to append to the image name:_MorphoJetMask_{safe_name}",
            "    Saved file format:tif",
            f"    Output file location:Default Output Folder sub-folder|{mask_subdir}/{safe_name}",
            "    Image bit depth:16-bit integer",
            "    Overwrite existing files without warning?:Yes",
            "    When to save:Every cycle",
            "    Rescale the images?:No",
            "    Save as grayscale or color image?:Grayscale",
            "    Select colormap:gray",
            "    Record the file and path information to the saved image?:Yes",
            "    Create subfolders in the output folder?:No",
            "    Base image folder:Default Input Folder|",
            "    How to save the series:T (Time)",
        ]
    )


def write_bridge_manifest(
    path: Path,
    source_pipeline: Path,
    patched_pipeline: Path,
    objects: list[str],
    base_image: str,
    mask_subdir: str,
) -> None:
    payload = {
        "source_pipeline": str(source_pipeline),
        "patched_pipeline": str(patched_pipeline),
        "base_image_for_filenames": base_image,
        "mask_output_subdir": mask_subdir,
        "objects": [
            {
                "name": object_name,
                "safe_name": sanitize(object_name),
                "suffix": f"_MorphoJetMask_{sanitize(object_name)}",
                "expected_mask_glob": f"{mask_subdir}/{sanitize(object_name)}/*_MorphoJetMask_{sanitize(object_name)}.tif",
            }
            for object_name in objects
        ],
        "next_step": "Run CellProfiler with patched_pipeline, then build MorphoJet image tables from the emitted TIFF label masks.",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pipeline", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--bridge-json", type=Path)
    parser.add_argument("--base-image")
    parser.add_argument("--mask-subdir", default="morphojet_masks")
    parser.add_argument("--force-all-measured", action="store_true")
    args = parser.parse_args()

    modules = parse_pipeline(args.pipeline)
    summary = collect_summary(modules)
    objects = summary["measured_objects"] if args.force_all_measured else summary["missing_label_exports"]
    if not objects:
        raise SystemExit("no missing measured object label exports found")

    base_image = args.base_image
    if not base_image:
        measured_images = summary.get("measured_images", [])
        if not measured_images:
            raise SystemExit("--base-image is required when the pipeline has no measured images")
        base_image = measured_images[0]

    max_module_num = max((module.module_num for module in modules), default=0)
    additions = [
        save_objects_module(max_module_num + index, object_name, base_image, args.mask_subdir)
        for index, object_name in enumerate(objects, start=1)
    ]

    source_text = args.pipeline.read_text(errors="replace").rstrip()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(source_text + "\n\n" + "\n\n".join(additions) + "\n")

    bridge_json = args.bridge_json or args.out.with_suffix(".masks.json")
    write_bridge_manifest(bridge_json, args.pipeline, args.out, objects, base_image, args.mask_subdir)
    print(f"patched pipeline: {args.out}")
    print(f"bridge manifest: {bridge_json}")
    print("objects: " + ", ".join(objects))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
