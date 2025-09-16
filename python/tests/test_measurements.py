import io
import json
import math
import pathlib
import sys
import unittest
import zipfile

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from spl_core import (
    BoxDesign,
    DriverParameters,
    MeasurementTrace,
    SealedBoxSolver,
    compare_measurement_to_prediction,
    measurement_from_response,
    parse_klippel_dat,
    parse_rew_mdat,
)


class MeasurementParsingTests(unittest.TestCase):
    def test_parse_klippel_dat_with_impedance(self) -> None:
        payload = """# Klippel export\n20;85.0;-45;5.1;3.2\n40;88.5;-32;5.9;4.1\n"""
        trace = parse_klippel_dat(payload)
        self.assertEqual(trace.frequency_hz, [20.0, 40.0])
        assert trace.spl_db is not None
        self.assertTrue(
            all(math.isclose(v, expected) for v, expected in zip(trace.spl_db, [85.0, 88.5], strict=True))
        )
        assert trace.phase_deg is not None
        self.assertTrue(
            all(
                math.isclose(v, expected)
                for v, expected in zip(trace.phase_deg, [-45.0, -32.0], strict=True)
            )
        )
        assert trace.impedance_ohm is not None
        self.assertTrue(all(isinstance(z, complex) for z in trace.impedance_ohm))

    def test_parse_rew_mdat_json(self) -> None:
        payload = {
            "measurement": {
                "frequency": [25.0, 63.0, 125.0],
                "spl": [81.2, 87.5, 92.0],
                "phase": [-60.0, -35.0, -20.0],
                "impedance_real": [6.1, 5.8, 4.9],
                "impedance_imag": [3.0, 2.6, 1.4],
            }
        }
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, mode="w") as archive:
            archive.writestr("measurement.json", json.dumps(payload))
        trace = parse_rew_mdat(buffer.getvalue())
        self.assertEqual(trace.frequency_hz, [25.0, 63.0, 125.0])
        assert trace.spl_db is not None
        self.assertEqual(len(trace.spl_db), 3)
        assert trace.impedance_ohm is not None
        self.assertAlmostEqual(abs(trace.impedance_ohm[0]), math.hypot(6.1, 3.0))


class MeasurementComparisonTests(unittest.TestCase):
    def setUp(self) -> None:
        self.driver = DriverParameters(
            fs_hz=32.0,
            qts=0.39,
            re_ohm=3.2,
            bl_t_m=15.5,
            mms_kg=0.125,
            sd_m2=0.052,
            vas_l=75.0,
            le_h=0.0007,
            xmax_mm=12.0,
        )
        self.box = BoxDesign(volume_l=55.0, leakage_q=15.0)
        self.solver = SealedBoxSolver(self.driver, self.box)
        frequencies = [18.0 + i * 6.0 for i in range(12)]
        response = self.solver.frequency_response(frequencies)
        self.prediction = measurement_from_response(response)

    def test_compare_identical_trace(self) -> None:
        delta, stats = compare_measurement_to_prediction(self.prediction, self.prediction)
        self.assertIsNotNone(stats.spl_rmse_db)
        assert stats.spl_rmse_db is not None
        self.assertLess(stats.spl_rmse_db, 1e-6)
        self.assertEqual(stats.spl_bias_db, 0.0)
        self.assertEqual(stats.max_spl_delta_db, 0.0)
        self.assertIsNone(stats.phase_rmse_deg)
        self.assertIsNotNone(delta.spl_delta_db)
        assert delta.spl_delta_db is not None
        self.assertTrue(all(abs(v) < 1e-6 for v in delta.spl_delta_db))

    def test_compare_with_offset_and_interpolation(self) -> None:
        measurement_axis = [22.0, 51.0, 88.0, 140.0]
        resampled = self.prediction.resample(measurement_axis)
        assert resampled.spl_db is not None
        measurement = MeasurementTrace(
            frequency_hz=measurement_axis,
            spl_db=[value + 0.8 for value in resampled.spl_db],
            impedance_ohm=[complex(abs(z) * 1.05, 0.0) for z in resampled.impedance_ohm or []] or None,
        )
        delta, stats = compare_measurement_to_prediction(measurement, self.prediction)
        assert stats.spl_rmse_db is not None
        self.assertAlmostEqual(stats.spl_rmse_db, 0.8, places=2)
        assert stats.spl_bias_db is not None
        self.assertAlmostEqual(stats.spl_bias_db, 0.8, places=2)
        assert stats.max_spl_delta_db is not None
        self.assertGreater(stats.max_spl_delta_db, 0.7)
        assert delta.spl_delta_db is not None
        self.assertTrue(all(math.isclose(v, 0.8, rel_tol=1e-3) for v in delta.spl_delta_db))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
