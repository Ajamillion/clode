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
    PortGeometry,
    SealedBoxSolver,
    VentedBoxDesign,
    VentedBoxSolver,
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
        delta, stats, diagnosis = compare_measurement_to_prediction(self.prediction, self.prediction)
        self.assertIsNotNone(stats.spl_rmse_db)
        assert stats.spl_rmse_db is not None
        self.assertLess(stats.spl_rmse_db, 1e-6)
        self.assertIsNotNone(stats.spl_mae_db)
        assert stats.spl_mae_db is not None
        self.assertLess(stats.spl_mae_db, 1e-6)
        self.assertEqual(stats.spl_bias_db, 0.0)
        self.assertIsNotNone(stats.spl_std_dev_db)
        assert stats.spl_std_dev_db is not None
        self.assertLess(stats.spl_std_dev_db, 1e-6)
        self.assertIsNotNone(stats.spl_pearson_r)
        assert stats.spl_pearson_r is not None
        self.assertAlmostEqual(stats.spl_pearson_r, 1.0, places=6)
        self.assertIsNotNone(stats.spl_r_squared)
        assert stats.spl_r_squared is not None
        self.assertAlmostEqual(stats.spl_r_squared, 1.0, places=6)
        self.assertEqual(stats.spl_p95_abs_error_db, 0.0)
        self.assertEqual(stats.spl_highest_delta_db, 0.0)
        self.assertEqual(stats.spl_lowest_delta_db, 0.0)
        self.assertEqual(stats.max_spl_delta_db, 0.0)
        self.assertIsNone(stats.phase_rmse_deg)
        self.assertIsNotNone(delta.spl_delta_db)
        assert delta.spl_delta_db is not None
        self.assertTrue(all(abs(v) < 1e-6 for v in delta.spl_delta_db))
        self.assertIsNotNone(diagnosis.overall_bias_db)
        self.assertAlmostEqual(diagnosis.overall_bias_db or 0.0, 0.0, places=6)
        self.assertEqual(diagnosis.notes, [])

    def test_compare_with_offset_and_interpolation(self) -> None:
        measurement_axis = [22.0, 51.0, 88.0, 140.0]
        resampled = self.prediction.resample(measurement_axis)
        assert resampled.spl_db is not None
        measurement = MeasurementTrace(
            frequency_hz=measurement_axis,
            spl_db=[value + 0.8 for value in resampled.spl_db],
            impedance_ohm=[complex(abs(z) * 1.05, 0.0) for z in resampled.impedance_ohm or []] or None,
        )
        delta, stats, diagnosis = compare_measurement_to_prediction(measurement, self.prediction)
        assert stats.spl_rmse_db is not None
        self.assertAlmostEqual(stats.spl_rmse_db, 0.8, places=2)
        assert stats.spl_mae_db is not None
        self.assertAlmostEqual(stats.spl_mae_db, 0.8, places=2)
        assert stats.spl_bias_db is not None
        self.assertAlmostEqual(stats.spl_bias_db, 0.8, places=2)
        assert stats.spl_std_dev_db is not None
        self.assertLess(stats.spl_std_dev_db, 1e-6)
        self.assertIsNotNone(stats.spl_pearson_r)
        assert stats.spl_pearson_r is not None
        self.assertGreater(stats.spl_pearson_r, 0.99)
        self.assertIsNotNone(stats.spl_r_squared)
        assert stats.spl_r_squared is not None
        self.assertGreater(stats.spl_r_squared, 0.95)
        assert stats.spl_p95_abs_error_db is not None
        self.assertAlmostEqual(stats.spl_p95_abs_error_db, 0.8, places=2)
        assert stats.spl_highest_delta_db is not None
        self.assertAlmostEqual(stats.spl_highest_delta_db, 0.8, places=2)
        assert stats.spl_lowest_delta_db is not None
        self.assertAlmostEqual(stats.spl_lowest_delta_db, 0.8, places=2)
        assert stats.max_spl_delta_db is not None
        self.assertGreater(stats.max_spl_delta_db, 0.7)
        assert delta.spl_delta_db is not None
        self.assertTrue(all(math.isclose(v, 0.8, rel_tol=1e-3) for v in delta.spl_delta_db))
        self.assertIsNotNone(diagnosis.recommended_level_trim_db)
        assert diagnosis.recommended_level_trim_db is not None
        self.assertAlmostEqual(diagnosis.recommended_level_trim_db, -0.8, places=2)
        self.assertIn('level', ' '.join(diagnosis.notes or []).lower())

    def test_compare_diagnosis_suggests_port_and_leakage_adjustments(self) -> None:
        vented_solver = VentedBoxSolver(
            self.driver,
            VentedBoxDesign(
                volume_l=62.0,
                leakage_q=12.0,
                port=PortGeometry(diameter_m=0.11, length_m=0.24, count=1, flare_factor=1.6, loss_q=16.0),
            ),
        )
        frequencies = [18.0 + i * 4.0 for i in range(25)]
        response = vented_solver.frequency_response(frequencies)
        prediction = measurement_from_response(response)
        assert prediction.spl_db is not None
        base_spl = list(prediction.spl_db)
        modified_spl = base_spl[:]
        peak_idx = max(range(len(base_spl)), key=base_spl.__getitem__)
        if peak_idx + 1 < len(modified_spl):
            modified_spl[peak_idx + 1] += 1.8
            modified_spl[peak_idx] -= 0.6
        elif peak_idx > 0:
            modified_spl[peak_idx - 1] += 1.8
            modified_spl[peak_idx] -= 0.6
        for idx, freq in enumerate(prediction.frequency_hz):
            if freq < 35.0:
                modified_spl[idx] -= 2.5
        measurement = MeasurementTrace(
            frequency_hz=list(prediction.frequency_hz),
            spl_db=modified_spl,
            impedance_ohm=prediction.impedance_ohm,
        )
        _, _, diagnosis = compare_measurement_to_prediction(
            measurement,
            prediction,
            port_length_m=vented_solver.box.port.length_m,
        )
        self.assertIsNotNone(diagnosis.tuning_shift_hz)
        assert diagnosis.tuning_shift_hz is not None
        self.assertNotAlmostEqual(diagnosis.tuning_shift_hz, 0.0, places=2)
        self.assertIsNotNone(diagnosis.recommended_port_length_scale)
        assert diagnosis.recommended_port_length_scale is not None
        if diagnosis.tuning_shift_hz > 0:
            self.assertLess(diagnosis.recommended_port_length_scale, 1.0)
        else:
            self.assertGreater(diagnosis.recommended_port_length_scale, 1.0)
        self.assertEqual(diagnosis.leakage_hint, 'lower_q')
        self.assertTrue(diagnosis.notes)

    def test_measurement_bandpass_limits_samples(self) -> None:
        measurement = MeasurementTrace(
            frequency_hz=[15.0, 25.0, 40.0, 80.0, 120.0],
            spl_db=[80.0, 82.0, 85.0, 88.0, 90.0],
        )
        filtered = measurement.bandpass(30.0, 90.0)
        self.assertEqual(filtered.frequency_hz, [40.0, 80.0])
        assert filtered.spl_db is not None
        self.assertEqual(filtered.spl_db, [85.0, 88.0])

        delta, stats, _ = compare_measurement_to_prediction(filtered, self.prediction)
        self.assertEqual(stats.sample_count, 2)
        assert delta.frequency_hz == [40.0, 80.0]

    def test_fractional_octave_smoothing_reduces_peaks(self) -> None:
        base = MeasurementTrace(
            frequency_hz=[20.0 + i * 5.0 for i in range(12)],
            spl_db=[85.0 + math.sin(i * 1.7) * 4.0 for i in range(12)],
        )
        noisy = MeasurementTrace(
            frequency_hz=list(base.frequency_hz),
            spl_db=[value + ((-1) ** i) * 1.5 for i, value in enumerate(base.spl_db or [])],
        )
        smoothed = noisy.fractional_octave_smooth(6.0)
        assert noisy.spl_db is not None
        assert smoothed.spl_db is not None
        original_span = max(noisy.spl_db) - min(noisy.spl_db)
        smoothed_span = max(smoothed.spl_db) - min(smoothed.spl_db)
        self.assertLess(smoothed_span, original_span)
        self.assertEqual(smoothed.frequency_hz, noisy.frequency_hz)

    def test_compare_with_smoothing_reduces_max_delta(self) -> None:
        measurement = MeasurementTrace(
            frequency_hz=list(self.prediction.frequency_hz),
            spl_db=[
                (self.prediction.spl_db or [])[idx] + ((-1) ** idx) * 1.0
                for idx in range(len(self.prediction.frequency_hz))
            ],
        )
        _, unsmoothed_stats, _ = compare_measurement_to_prediction(measurement, self.prediction)
        _, smoothed_stats, _ = compare_measurement_to_prediction(
            measurement,
            self.prediction,
            smoothing_fraction=6.0,
        )
        assert unsmoothed_stats.max_spl_delta_db is not None
        assert smoothed_stats.max_spl_delta_db is not None
        self.assertLess(smoothed_stats.max_spl_delta_db, unsmoothed_stats.max_spl_delta_db)
        assert unsmoothed_stats.spl_p95_abs_error_db is not None
        assert smoothed_stats.spl_p95_abs_error_db is not None
        self.assertLess(
            smoothed_stats.spl_p95_abs_error_db,
            unsmoothed_stats.spl_p95_abs_error_db,
        )
        assert unsmoothed_stats.spl_std_dev_db is not None
        assert smoothed_stats.spl_std_dev_db is not None
        self.assertLess(smoothed_stats.spl_std_dev_db, unsmoothed_stats.spl_std_dev_db)

    def test_bandpass_raises_when_out_of_range(self) -> None:
        measurement = MeasurementTrace(
            frequency_hz=[20.0, 40.0, 80.0],
            spl_db=[82.0, 85.0, 90.0],
        )
        with self.assertRaises(ValueError):
            measurement.bandpass(100.0, 150.0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
