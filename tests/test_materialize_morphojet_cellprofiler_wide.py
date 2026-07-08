#!/usr/bin/env python3
"""Unit tests for MorphoJet long-to-wide CellProfiler export."""

from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmark"))

import check_cellprofiler_wide_contract  # noqa: E402
import compare_cellprofiler_wide_subset  # noqa: E402
import materialize_morphojet_cellprofiler_wide  # noqa: E402


def object_row(channel: str, **metadata: str) -> dict[str, str]:
    row = {
        "ImageNumber": "1",
        "ObjectNumber": "1",
        "Channel": channel,
        "ObjectSet": "Cells",
        "AreaShape_Area": "4",
        "AreaShape_Center_X": "1.5",
        "AreaShape_Center_Y": "2.5",
        "AreaShape_BoundingBoxMinimum_X": "0",
        "AreaShape_BoundingBoxMinimum_Y": "1",
        "AreaShape_BoundingBoxMaximum_X": "2",
        "AreaShape_BoundingBoxMaximum_Y": "3",
        "AreaShape_Perimeter": "8",
        "AreaShape_Eccentricity": "0.1",
        "AreaShape_MajorAxisLength": "3",
        "AreaShape_MinorAxisLength": "2",
        "AreaShape_Solidity": "1",
        "Intensity_MinIntensity": "0.1",
        "Intensity_MaxIntensity": "0.9",
        "Intensity_MeanIntensity": "0.5",
        "Intensity_MedianIntensity": "0.5",
        "Intensity_IntegratedIntensity": "2",
        "Intensity_LowerQuartileIntensity": "0.25",
        "Intensity_UpperQuartileIntensity": "0.75",
        "Intensity_StdIntensity": "0.2",
        "Intensity_MADIntensity": "0.1",
        "Location_CenterMassIntensity_X": "1.2",
        "Location_CenterMassIntensity_Y": "2.2",
        "Location_CenterMassIntensity_Z": "0",
        "Location_Center_Z": "0",
        "Location_MaxIntensity_Z": "0",
        "Plate": "P001",
        "Well": "A01",
        "Site": "1",
    }
    row.update(metadata)
    return row


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = list(rows[0])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


class MaterializeMorphoJetWideTest(unittest.TestCase):
    def test_materialize_carries_requested_metadata_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            objects = root / "Objects.csv"
            out = root / "Cells.wide.csv"
            write_csv(objects, [object_row("DNA"), object_row("PH3")])

            row_count = materialize_morphojet_cellprofiler_wide.materialize(
                objects,
                "Cells",
                ["DNA", "PH3"],
                out,
                ["Plate", "Well", "Site"],
            )
            columns, rows = check_cellprofiler_wide_contract.read_rows(out)

        self.assertEqual(1, row_count)
        self.assertIn("Plate", columns)
        self.assertIn("Well", columns)
        self.assertIn("Site", columns)
        self.assertEqual("P001", rows[0]["Plate"])
        self.assertEqual("A01", rows[0]["Well"])
        self.assertEqual("1", rows[0]["Site"])
        self.assertLess(columns.index("Number_Object_Number"), columns.index("Plate"))
        self.assertLess(columns.index("Site"), columns.index("Intensity_MinIntensity_DNA"))

    def test_materialize_rejects_metadata_that_differs_across_channels(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            objects = root / "Objects.csv"
            write_csv(objects, [object_row("DNA", Well="A01"), object_row("PH3", Well="A02")])

            with self.assertRaises(SystemExit) as context:
                materialize_morphojet_cellprofiler_wide.materialize(
                    objects,
                    "Cells",
                    ["DNA", "PH3"],
                    root / "Cells.wide.csv",
                    ["Plate", "Well", "Site"],
                )

        self.assertIn("metadata column Well differs across channels", str(context.exception))

    def test_wide_contract_can_require_metadata_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wide = root / "Cells.wide.csv"
            objects = root / "Objects.csv"
            write_csv(objects, [object_row("DNA"), object_row("PH3")])
            materialize_morphojet_cellprofiler_wide.materialize(
                objects,
                "Cells",
                ["DNA", "PH3"],
                wide,
                ["Plate", "Well", "Site"],
            )

            passed, summary = check_cellprofiler_wide_contract.check(
                wide,
                ["DNA", "PH3"],
                min_rows=1,
                metadata_columns=["Plate", "Well", "Site"],
            )

        self.assertTrue(passed)
        self.assertEqual(["Plate", "Well", "Site"], summary["metadata_columns"])

    def test_compare_allows_declared_metadata_extra_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            objects = root / "Objects.csv"
            actual = root / "Cells.wide.csv"
            expected = root / "CellProfiler_Cells.csv"
            write_csv(objects, [object_row("DNA"), object_row("PH3")])
            materialize_morphojet_cellprofiler_wide.materialize(
                objects,
                "Cells",
                ["DNA", "PH3"],
                actual,
                ["Plate", "Well", "Site"],
            )
            columns, rows = check_cellprofiler_wide_contract.read_rows(actual)
            expected_columns = [column for column in columns if column not in {"Plate", "Well", "Site"}]
            with expected.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=expected_columns)
                writer.writeheader()
                writer.writerow({column: rows[0][column] for column in expected_columns})

            passed, _report, summary = compare_cellprofiler_wide_subset.compare(
                expected,
                actual,
                ["ImageNumber", "ObjectNumber"],
                abs_tol=1e-6,
                rel_tol=1e-5,
                allowed_extra_columns=["Plate", "Well", "Site"],
            )

        self.assertTrue(passed)
        self.assertEqual(["Plate", "Well", "Site"], summary["allowed_actual_extra_columns"])


if __name__ == "__main__":
    unittest.main()
