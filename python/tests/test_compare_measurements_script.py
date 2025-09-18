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
            calibration_path = pathlib.Path(tmpdir) / "calibration.json"
            overrides_path = pathlib.Path(tmpdir) / "overrides.json"

            calibrated_stats_path = pathlib.Path(tmpdir) / "stats_calibrated.json"
            calibrated_delta_path = pathlib.Path(tmpdir) / "delta_calibrated.json"
            calibrated_diagnosis_path = pathlib.Path(tmpdir) / "diagnosis_calibrated.json"

            completed = subprocess.run(
                [
                    sys.executable,
                    str(script_path),
                    str(measurement_path),
                    "--alignment",
                    "sealed",
                    "--json",
                    "--pretty",
                    "--apply-overrides",
                    "--stats-output",
                    str(stats_path),
                    "--delta-output",
                    str(delta_path),
                    "--diagnosis-output",
                    str(diagnosis_path),
                    "--calibration-output",
                    str(calibration_path),
                    "--overrides-output",
                    str(overrides_path),
                    "--calibrated-stats-output",
                    str(calibrated_stats_path),
                    "--calibrated-delta-output",
                    str(calibrated_delta_path),
                    "--calibrated-diagnosis-output",
                    str(calibrated_diagnosis_path),
                    "--smoothing-fraction",
                    "6",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            payload = json.loads(completed.stdout)
            self.assertEqual(payload["alignment"], "sealed")
            band = payload["frequency_band"]
            self.assertAlmostEqual(band["min_hz"], min(frequencies))
            self.assertAlmostEqual(band["max_hz"], max(frequencies))
            self.assertEqual(payload["smoothing_fraction"], 6)
            stats = payload["stats"]
            self.assertEqual(stats["sample_count"], len(frequencies))
            self.assertLess(stats["spl_rmse_db"], 1e-6)
            self.assertLess(stats["spl_mae_db"], 1e-6)
            self.assertAlmostEqual(stats["spl_pearson_r"], 1.0, places=6)
            self.assertAlmostEqual(stats["spl_r_squared"], 1.0, places=6)
            self.assertLess(stats["spl_p95_abs_error_db"], 1e-6)
            self.assertLess(stats["spl_std_dev_db"], 1e-6)
            self.assertLess(abs(stats["spl_highest_delta_db"]), 1e-6)
            self.assertLess(abs(stats["spl_lowest_delta_db"]), 1e-6)
            diagnosis = payload["diagnosis"]
            self.assertAlmostEqual(diagnosis["overall_bias_db"], 0.0, places=6)
            calibration = payload["calibration"]
            self.assertIn("level_trim_db", calibration)
            self.assertIsInstance(calibration["level_trim_db"], dict)
            self.assertAlmostEqual(calibration["level_trim_db"]["mean"], 0.0, places=6)
            overrides = payload["calibration_overrides"]
            self.assertIn("drive_voltage_scale", overrides)
            self.assertAlmostEqual(overrides["drive_voltage_scale"], 1.0, places=6)
            calibrated = payload["calibrated"]
            self.assertAlmostEqual(calibrated["drive_voltage_v"], solver.drive_voltage, places=6)
            self.assertIn("stats", calibrated)
            self.assertEqual(calibrated["stats"]["sample_count"], len(frequencies))

            stats_file = json.loads(stats_path.read_text(encoding="utf-8"))
            self.assertEqual(stats_file["sample_count"], len(frequencies))
            self.assertAlmostEqual(stats_file["spl_pearson_r"], 1.0, places=6)
            self.assertAlmostEqual(stats_file["spl_r_squared"], 1.0, places=6)
            self.assertLess(stats_file["spl_mae_db"], 1e-6)
            self.assertLess(stats_file["spl_p95_abs_error_db"], 1e-6)
            self.assertLess(stats_file["spl_std_dev_db"], 1e-6)
            self.assertLess(abs(stats_file["spl_highest_delta_db"]), 1e-6)
            self.assertLess(abs(stats_file["spl_lowest_delta_db"]), 1e-6)

            calibrated_stats_file = json.loads(calibrated_stats_path.read_text(encoding="utf-8"))
            self.assertEqual(calibrated_stats_file["sample_count"], len(frequencies))
            self.assertAlmostEqual(calibrated_stats_file["spl_pearson_r"], 1.0, places=6)
            self.assertAlmostEqual(calibrated_stats_file["spl_r_squared"], 1.0, places=6)
            self.assertLess(calibrated_stats_file["spl_mae_db"], 1e-6)
            self.assertLess(calibrated_stats_file["spl_p95_abs_error_db"], 1e-6)
            self.assertLess(calibrated_stats_file["spl_std_dev_db"], 1e-6)
            self.assertLess(abs(calibrated_stats_file["spl_highest_delta_db"]), 1e-6)
            self.assertLess(abs(calibrated_stats_file["spl_lowest_delta_db"]), 1e-6)

            delta_file = json.loads(delta_path.read_text(encoding="utf-8"))
            self.assertEqual(len(delta_file["frequency_hz"]), len(frequencies))
            for value in delta_file["spl_delta_db"]:
                self.assertAlmostEqual(value, 0.0, places=7)

            calibrated_delta_file = json.loads(calibrated_delta_path.read_text(encoding="utf-8"))
            self.assertEqual(len(calibrated_delta_file["frequency_hz"]), len(frequencies))
            for value in calibrated_delta_file["spl_delta_db"]:
                self.assertAlmostEqual(value, 0.0, places=7)

            diagnosis_file = json.loads(diagnosis_path.read_text(encoding="utf-8"))
            self.assertIn("notes", diagnosis_file)
            self.assertIn("recommended_level_trim_db", diagnosis_file)

            calibrated_diagnosis_file = json.loads(calibrated_diagnosis_path.read_text(encoding="utf-8"))
            self.assertIn("notes", calibrated_diagnosis_file)

            calibration_file = json.loads(calibration_path.read_text(encoding="utf-8"))
            self.assertIn("level_trim_db", calibration_file)
            self.assertEqual(calibration_file["port_length_scale"], None)

            overrides_file = json.loads(overrides_path.read_text(encoding="utf-8"))
            self.assertIn("drive_voltage_v", overrides_file)
            self.assertEqual(overrides_file["port_length_m"], None)

    def test_cli_respects_frequency_band(self) -> None:
        project_root = pathlib.Path(__file__).resolve().parents[1]
        script_path = project_root / "scripts" / "compare_measurements.py"

        solver = SealedBoxSolver(DEFAULT_DRIVER, BoxDesign(volume_l=55.0))
        frequencies = [20.0, 40.0, 80.0, 160.0]
        response = solver.frequency_response(frequencies, 1.0)
        measurement = measurement_from_response(response)

        with tempfile.TemporaryDirectory() as tmpdir:
            measurement_path = pathlib.Path(tmpdir) / "measurement.dat"
            measurement_path.write_text(
                "".join(f"{f};{spl}\n" for f, spl in zip(measurement.frequency_hz, measurement.spl_db, strict=True)),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    str(script_path),
                    str(measurement_path),
                    "--alignment",
                    "sealed",
                    "--json",
                    "--min-frequency",
                    "30",
                    "--max-frequency",
                    "120",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            payload = json.loads(completed.stdout)
            band = payload["frequency_band"]
            self.assertAlmostEqual(band["min_hz"], 40.0)
            self.assertAlmostEqual(band["max_hz"], 80.0)
            self.assertIsNone(payload.get("smoothing_fraction"))
            stats = payload["stats"]
            self.assertEqual(stats["sample_count"], 2)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
