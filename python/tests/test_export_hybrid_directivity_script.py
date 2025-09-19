"""Regression tests for the hybrid directivity export CLI."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "export_hybrid_directivity.py"


class ExportHybridDirectivityCLITests(unittest.TestCase):
    def test_csv_export_contains_directivity_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "directivity.csv"
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--output",
                    str(output),
                    "--format",
                    "csv",
                    "--mode",
                    "sealed",
                    "--volume-l",
                    "55",
                    "--freq-start",
                    "40",
                    "--freq-stop",
                    "80",
                    "--freq-count",
                    "4",
                    "--spacing",
                    "linear",
                    "--grid-resolution",
                    "12",
                    "--snapshot-stride",
                    "16",
                    "--quiet",
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertEqual(result.returncode, 0)
            self.assertTrue(output.exists())

            with output.open(encoding="utf-8") as handle:
                reader = csv.reader(handle)
                rows = list(reader)

            self.assertGreater(len(rows), 1)
            header = rows[0]
            self.assertIn("frequency_hz", header)
            self.assertIn("directivity_index_db", header)
            self.assertIn("beamwidth_6db_deg", header)
            self.assertGreater(len(header), 2)

            data_rows = rows[1:]
            self.assertEqual(len(data_rows), 4)
            first_row = data_rows[0]
            self.assertGreater(len(first_row), 3)

            # Ensure numeric values parse cleanly for frequency and DI columns.
            freq = float(first_row[0])
            di_db = float(first_row[1])
            beamwidth = float(first_row[2])
            self.assertGreater(freq, 0.0)
            self.assertEqual(di_db, di_db)  # guard against NaN
            self.assertGreater(beamwidth, 0.0)

    def test_json_export_reports_metadata_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "directivity.json"
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--output",
                    str(output),
                    "--format",
                    "json",
                    "--mode",
                    "sealed",
                    "--volume-l",
                    "60",
                    "--freq-start",
                    "30",
                    "--freq-stop",
                    "90",
                    "--freq-count",
                    "5",
                    "--spacing",
                    "linear",
                    "--grid-resolution",
                    "12",
                    "--snapshot-stride",
                    "18",
                    "--pretty",
                    "--quiet",
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertEqual(result.returncode, 0)
            self.assertTrue(output.exists())

            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["metadata"]["mode"], "sealed")
            self.assertIn("volume_l", payload["metadata"])
            self.assertEqual(len(payload["frequencies_hz"]), 5)
            self.assertEqual(len(payload["directivity_index_db"]), 5)
            self.assertEqual(len(payload["beamwidth_6db_deg"]), 5)
            self.assertTrue(payload["directivity"])
            first_angle = payload["directivity"][0]
            self.assertIn("angle_deg", first_angle)
            self.assertEqual(len(first_angle["relative_spl_db"]), 5)

            summary = payload["summary"]
            self.assertIn("max_directivity_index_db", summary)
            self.assertIn("mean_directivity_index_db", summary)
            self.assertIn("beamwidth_6db_deg", summary)
            self.assertIn("mean_beamwidth_6db_deg", summary)
            self.assertIsNotNone(summary["max_directivity_index_db"])
            self.assertIsNotNone(summary["mean_beamwidth_6db_deg"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
