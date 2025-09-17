import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from spl_core import DEFAULT_DRIVER, BoxDesign, SealedBoxSolver, measurement_from_response


class CompareMeasurementsScriptTests(unittest.TestCase):
    def test_cli_outputs_json_and_writes_files(self) -> None:
        project_root = pathlib.Path(__file__).resolve().parents[1]
        script_path = project_root / "scripts" / "compare_measurements.py"

        solver = SealedBoxSolver(DEFAULT_DRIVER, BoxDesign(volume_l=55.0))
        frequencies = [20.0, 30.0, 40.0, 60.0, 80.0, 120.0]
        response = solver.frequency_response(frequencies, 1.0)
        measurement = measurement_from_response(response)

        with tempfile.TemporaryDirectory() as tmpdir:
            measurement_path = pathlib.Path(tmpdir) / "measurement.dat"
            lines = [f"{f};{spl}\n" for f, spl in zip(measurement.frequency_hz, measurement.spl_db, strict=True)]
            measurement_path.write_text("".join(lines), encoding="utf-8")

            stats_path = pathlib.Path(tmpdir) / "stats.json"
            delta_path = pathlib.Path(tmpdir) / "delta.json"
            diagnosis_path = pathlib.Path(tmpdir) / "diagnosis.json"

            completed = subprocess.run(
                [
                    sys.executable,
                    str(script_path),
                    str(measurement_path),
                    "--alignment",
                    "sealed",
                    "--json",
                    "--pretty",
                    "--stats-output",
                    str(stats_path),
                    "--delta-output",
                    str(delta_path),
                    "--diagnosis-output",
                    str(diagnosis_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            payload = json.loads(completed.stdout)
            self.assertEqual(payload["alignment"], "sealed")
            stats = payload["stats"]
            self.assertEqual(stats["sample_count"], len(frequencies))
            self.assertLess(stats["spl_rmse_db"], 1e-6)
            diagnosis = payload["diagnosis"]
            self.assertAlmostEqual(diagnosis["overall_bias_db"], 0.0, places=6)

            stats_file = json.loads(stats_path.read_text(encoding="utf-8"))
            self.assertEqual(stats_file["sample_count"], len(frequencies))

            delta_file = json.loads(delta_path.read_text(encoding="utf-8"))
            self.assertEqual(len(delta_file["frequency_hz"]), len(frequencies))
            for value in delta_file["spl_delta_db"]:
                self.assertAlmostEqual(value, 0.0, places=7)

            diagnosis_file = json.loads(diagnosis_path.read_text(encoding="utf-8"))
            self.assertIn("notes", diagnosis_file)
            self.assertIn("recommended_level_trim_db", diagnosis_file)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
