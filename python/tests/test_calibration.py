import pathlib
import sys
import unittest

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from spl_core.calibration import (
    CalibrationOverrides,
    CalibrationPrior,
    derive_calibration_overrides,
    derive_calibration_update,
)
from spl_core.measurements import MeasurementDiagnosis


class CalibrationUpdateTests(unittest.TestCase):
    def test_level_trim_update(self) -> None:
        prior = CalibrationPrior.default()
        diagnosis = MeasurementDiagnosis(
            overall_bias_db=1.5,
            recommended_level_trim_db=-1.5,
            low_band_bias_db=None,
            mid_band_bias_db=None,
            high_band_bias_db=None,
            tuning_shift_hz=None,
            recommended_port_length_m=None,
            recommended_port_length_scale=None,
            leakage_hint=None,
            notes=[],
        )

        update = derive_calibration_update(diagnosis, prior)
        level = update.level_trim_db
        self.assertIsNotNone(level)
        prior_var = prior.level_trim_db.variance
        obs_var = 0.75 ** 2
        expected_variance = 1.0 / (1.0 / prior_var + 1.0 / obs_var)
        expected_mean = expected_variance * (
            prior.level_trim_db.mean / prior_var + diagnosis.recommended_level_trim_db / obs_var
        )
        assert level is not None
        self.assertAlmostEqual(level.mean, expected_mean, places=6)
        self.assertAlmostEqual(level.variance, expected_variance, places=6)
        self.assertGreater(level.update_weight, 0.5)
        self.assertIsNotNone(level.credible_interval)
        self.assertTrue(any("Level trim" in note for note in update.notes))

    def test_port_length_scale_update(self) -> None:
        prior = CalibrationPrior.default()
        diagnosis = MeasurementDiagnosis(
            overall_bias_db=None,
            recommended_level_trim_db=None,
            low_band_bias_db=None,
            mid_band_bias_db=None,
            high_band_bias_db=None,
            tuning_shift_hz=None,
            recommended_port_length_m=0.24,
            recommended_port_length_scale=1.08,
            leakage_hint=None,
            notes=[],
        )

        update = derive_calibration_update(diagnosis, prior)
        port = update.port_length_scale
        self.assertIsNotNone(port)
        assert port is not None
        prior_var = prior.port_length_scale.variance
        obs_var = 0.08 ** 2
        expected_variance = 1.0 / (1.0 / prior_var + 1.0 / obs_var)
        expected_mean = expected_variance * (
            prior.port_length_scale.mean / prior_var + diagnosis.recommended_port_length_scale / obs_var
        )
        self.assertAlmostEqual(port.mean, expected_mean, places=6)
        self.assertAlmostEqual(port.variance, expected_variance, places=6)
        self.assertGreater(port.update_weight, 0.5)

    def test_leakage_hint_updates_scale(self) -> None:
        prior = CalibrationPrior.default()
        diagnosis = MeasurementDiagnosis(
            overall_bias_db=None,
            recommended_level_trim_db=None,
            low_band_bias_db=-2.0,
            mid_band_bias_db=-0.2,
            high_band_bias_db=None,
            tuning_shift_hz=None,
            recommended_port_length_m=None,
            recommended_port_length_scale=None,
            leakage_hint="lower_q",
            notes=[],
        )

        update = derive_calibration_update(diagnosis, prior)
        leakage = update.leakage_q_scale
        self.assertIsNotNone(leakage)
        assert leakage is not None
        self.assertGreater(leakage.mean, prior.leakage_q_scale.mean)
        self.assertGreater(leakage.update_weight, 0.4)
        interval = leakage.credible_interval
        self.assertIsNotNone(interval)
        assert interval is not None
        self.assertLess(interval[0], interval[1])

    def test_missing_observations_return_none(self) -> None:
        prior = CalibrationPrior.default()
        diagnosis = MeasurementDiagnosis(
            overall_bias_db=None,
            recommended_level_trim_db=None,
            low_band_bias_db=None,
            mid_band_bias_db=None,
            high_band_bias_db=None,
            tuning_shift_hz=None,
            recommended_port_length_m=None,
            recommended_port_length_scale=None,
            leakage_hint=None,
            notes=[],
        )

        update = derive_calibration_update(diagnosis, prior)
        self.assertIsNone(update.level_trim_db)
        self.assertIsNone(update.port_length_scale)
        self.assertIsNone(update.leakage_q_scale)
        self.assertEqual(update.notes, [])

    def test_overrides_project_parameters(self) -> None:
        diagnosis = MeasurementDiagnosis(
            overall_bias_db=-1.2,
            recommended_level_trim_db=1.2,
            low_band_bias_db=None,
            mid_band_bias_db=None,
            high_band_bias_db=None,
            tuning_shift_hz=None,
            recommended_port_length_m=0.24,
            recommended_port_length_scale=1.05,
            leakage_hint="raise_q",
            notes=[],
        )
        update = derive_calibration_update(diagnosis)
        overrides = derive_calibration_overrides(
            update,
            drive_voltage_v=2.83,
            port_length_m=0.23,
            leakage_q=15.0,
        )
        self.assertIsInstance(overrides, CalibrationOverrides)
        assert overrides.drive_voltage_scale is not None
        expected_scale = 10 ** (-update.level_trim_db.mean / 20.0) if update.level_trim_db else None
        if expected_scale is not None:
            self.assertAlmostEqual(overrides.drive_voltage_scale, expected_scale, places=6)
            assert overrides.drive_voltage_v is not None
            self.assertAlmostEqual(overrides.drive_voltage_v, 2.83 * expected_scale, places=6)
        assert overrides.port_length_scale is not None
        self.assertAlmostEqual(overrides.port_length_scale, update.port_length_scale.mean, places=6)
        assert overrides.port_length_m is not None
        self.assertAlmostEqual(overrides.port_length_m, 0.23 * overrides.port_length_scale, places=6)
        assert overrides.leakage_q_scale is not None
        self.assertGreater(overrides.leakage_q_scale, 0)
        assert overrides.leakage_q is not None
        self.assertAlmostEqual(overrides.leakage_q, 15.0 * overrides.leakage_q_scale, places=6)

    def test_overrides_skip_missing_values(self) -> None:
        diagnosis = MeasurementDiagnosis(
            overall_bias_db=None,
            recommended_level_trim_db=None,
            low_band_bias_db=None,
            mid_band_bias_db=None,
            high_band_bias_db=None,
            tuning_shift_hz=None,
            recommended_port_length_m=None,
            recommended_port_length_scale=None,
            leakage_hint=None,
            notes=[],
        )
        update = derive_calibration_update(diagnosis)
        overrides = derive_calibration_overrides(update, drive_voltage_v=-1.0)
        self.assertIsNone(overrides.drive_voltage_scale)
        self.assertIsNone(overrides.drive_voltage_v)
        self.assertIsNone(overrides.port_length_scale)
        self.assertIsNone(overrides.port_length_m)
        self.assertIsNone(overrides.leakage_q_scale)
        self.assertIsNone(overrides.leakage_q)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
