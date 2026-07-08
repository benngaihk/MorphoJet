#!/usr/bin/env python3
"""Unit tests for CellBinDB direct-mask inspection."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmark"))

import inspect_cellbindb_direct_masks  # noqa: E402


def write_tiff(path: Path, array: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(array).save(path)


def add_sample_to_zip(
    zip_path: Path,
    tmp_root: Path,
    sample_name: str,
    image: np.ndarray,
    mask: np.ndarray,
    semantic: np.ndarray | None = None,
) -> None:
    base = Path("CellBinDB/Test_DAPI") / sample_name
    image_rel = base / f"{sample_name}-img.tif"
    mask_rel = base / f"{sample_name}-instancemask.tif"
    semantic_rel = base / f"{sample_name}-mask.tif"
    image_path = tmp_root / image_rel
    mask_path = tmp_root / mask_rel
    semantic_path = tmp_root / semantic_rel
    write_tiff(image_path, image)
    write_tiff(mask_path, mask)
    if semantic is not None:
        write_tiff(semantic_path, semantic)
    with ZipFile(zip_path, "a") as archive:
        archive.write(image_path, image_rel.as_posix())
        archive.write(mask_path, mask_rel.as_posix())
        if semantic is not None:
            archive.write(semantic_path, semantic_rel.as_posix())


def write_catalogs(root: Path, zip_path: Path) -> tuple[Path, Path]:
    metadata_path = root / "zenodo_metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "record": "15370205",
                "record_url": "https://zenodo.org/records/15370205",
                "file": zip_path.name,
                "size": zip_path.stat().st_size,
                "checksum": "md5:placeholder",
                "metadata_source": "fixture",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    public_corpora_path = root / "public_corpora.json"
    public_corpora_path.write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "id": "cellbindb",
                        "name": "CellBinDB",
                        "source_url": "https://zenodo.org/records/15370205",
                        "primary_file": zip_path.name,
                        "primary_file_size_bytes": zip_path.stat().st_size,
                        "primary_file_md5": "placeholder",
                        "license": "fixture license",
                        "m0_status": "candidate_direct_masks",
                    }
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return metadata_path, public_corpora_path


class CellBinDBDirectMaskInspectionTest(unittest.TestCase):
    def test_fixture_direct_masks_pass_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            zip_path = root / "CellBinDB.zip"
            image = np.arange(16, dtype=np.uint16).reshape(4, 4)
            mask = np.array(
                [
                    [0, 0, 1, 1],
                    [0, 2, 2, 1],
                    [0, 2, 0, 0],
                    [3, 3, 0, 0],
                ],
                dtype=np.uint16,
            )
            add_sample_to_zip(zip_path, root / "files", "sample_001", image, mask, mask)
            metadata_path, public_corpora_path = write_catalogs(root, zip_path)

            payload = inspect_cellbindb_direct_masks.build_payload(
                zip_path,
                metadata_path,
                public_corpora_path,
                "cellbindb",
                sample_limit=None,
                minimum_samples=1,
                verify_md5=False,
                argv=["benchmark/inspect_cellbindb_direct_masks.py"],
            )

        self.assertEqual("PASS", payload["status"])
        self.assertEqual("NOT_PRODUCTION_CLAIM", payload["claim_status"])
        self.assertEqual("CELLBINDB_DIRECT_MASK_INSPECTION", payload["evidence_scope"])
        self.assertFalse(payload["final_production_signoff"])
        self.assertEqual("FULL", payload["inspection_scope"])
        self.assertEqual(1, payload["summary"]["total_sample_groups"])
        self.assertEqual(1, payload["summary"]["samples_with_semantic_masks"])
        self.assertEqual(3, payload["summary"]["inspected_positive_label_count"])
        self.assertEqual([], payload["summary"]["issues"])
        self.assertTrue(payload["inspected_samples"][0]["background_zero_present"])

    def test_rejects_bad_mask_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            zip_path = root / "CellBinDB.zip"
            image = np.arange(16, dtype=np.uint16).reshape(4, 4)
            mask = np.ones((3, 4), dtype=np.uint16)
            add_sample_to_zip(zip_path, root / "files", "sample_001", image, mask, mask)
            metadata_path, public_corpora_path = write_catalogs(root, zip_path)

            payload = inspect_cellbindb_direct_masks.build_payload(
                zip_path,
                metadata_path,
                public_corpora_path,
                "cellbindb",
                sample_limit=None,
                minimum_samples=1,
                verify_md5=False,
                argv=["benchmark/inspect_cellbindb_direct_masks.py"],
            )

        self.assertEqual("FAIL", payload["status"])
        joined = "\n".join(payload["summary"]["issues"])
        self.assertIn("image/mask dimensions differ", joined)
        self.assertIn("background label 0", joined)

    def test_cli_writes_reports_and_enforces_require_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            zip_path = root / "CellBinDB.zip"
            image = np.arange(16, dtype=np.uint16).reshape(4, 4)
            mask = np.zeros((4, 4), dtype=np.uint16)
            mask[1:3, 1:3] = 1
            add_sample_to_zip(zip_path, root / "files", "sample_001", image, mask, mask)
            metadata_path, public_corpora_path = write_catalogs(root, zip_path)
            json_out = root / "inspection.json"
            md_out = root / "inspection.md"

            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "benchmark/inspect_cellbindb_direct_masks.py"),
                    "--zip",
                    str(zip_path),
                    "--metadata-json",
                    str(metadata_path),
                    "--public-corpora",
                    str(public_corpora_path),
                    "--full",
                    "--minimum-samples",
                    "1",
                    "--require-pass",
                    "--json-out",
                    str(json_out),
                    "--md-out",
                    str(md_out),
                ],
                cwd=ROOT,
                check=True,
            )

            payload = json.loads(json_out.read_text(encoding="utf-8"))
            markdown = md_out.read_text(encoding="utf-8")

        self.assertEqual("PASS", payload["status"])
        self.assertIn("CellBinDB Direct-Mask Inspection", markdown)
        self.assertIn("not final production signoff", markdown)


if __name__ == "__main__":
    unittest.main()
