from __future__ import annotations

import unittest

from services.gateway.app.main import _measurement_comparison_payload
from spl_core import (
    BoxDesign,
    DriverParameters,
    MeasurementTrace,
    PortGeometry,
    SealedBoxSolver,
    VentedBoxDesign,
    VentedBoxSolver,
    measurement_from_response,
)


class MeasurementComparisonPayloadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.driver = DriverParameters(
            fs_hz=32.0,
            qts=0.39,
            re_ohm=3.2,
            bl_t_m=15.5,
            mms_kg=0.125,
            sd_m2=0.052,
            le_h=0.0007,
            vas_l=75.0,
            xmax_mm=12.0,
        )

    def test_sealed_payload_includes_calibrated_rerun(self) -> None:
        box = BoxDesign(volume_l=55.0, leakage_q=15.0)
        solver = SealedBoxSolver(self.driver, box, drive_voltage=2.83)
        frequencies = [18.0 + i * 6.0 for i in range(12)]
        response = solver.frequency_response(frequencies)
        baseline = measurement_from_response(response)
        assert baseline.spl_db is not None
        biased = MeasurementTrace(
            frequency_hz=list(baseline.frequency_hz),
            spl_db=[value + 1.5 for value in baseline.spl_db],
            impedance_ohm=baseline.impedance_ohm,
        )

        payload = _measurement_comparison_payload(
            alignment="sealed",
            driver=self.driver,
            box=box,
            measurement=biased,
            mic_distance_m=1.0,
            drive_voltage=2.83,
            apply_overrides=True,
        )

        stats = payload["stats"]
        calibrated = payload.get("calibrated")
        self.assertIsInstance(stats, dict)
        self.assertIsNotNone(calibrated)
        assert isinstance(calibrated, dict)
        rerun_stats = calibrated.get("stats")
        self.assertIsInstance(rerun_stats, dict)

        spl_bias = stats.get("spl_bias_db")
        rerun_bias = rerun_stats.get("spl_bias_db") if isinstance(rerun_stats, dict) else None
        self.assertIsInstance(spl_bias, int | float)
        self.assertIsInstance(rerun_bias, int | float)
        assert isinstance(rerun_bias, int | float)
        assert isinstance(spl_bias, int | float)
        self.assertLess(abs(rerun_bias), abs(spl_bias))

        inputs = calibrated.get("inputs")
        self.assertIsInstance(inputs, dict)
        if isinstance(inputs, dict):
            drive_value = inputs.get("drive_voltage_v")
            self.assertIsInstance(drive_value, int | float)
            assert isinstance(drive_value, int | float)
            self.assertNotAlmostEqual(drive_value, 2.83, places=6)

    def test_vented_payload_reports_calibrated_port_length(self) -> None:
        box = VentedBoxDesign(
            volume_l=62.0,
            leakage_q=12.0,
            port=PortGeometry(diameter_m=0.11, length_m=0.24, count=1, flare_factor=1.6, loss_q=16.0),
        )
        solver = VentedBoxSolver(self.driver, box, drive_voltage=2.83)
        frequencies = [18.0 + i * 4.0 for i in range(25)]
        response = solver.frequency_response(frequencies)
        baseline = measurement_from_response(response)
        assert baseline.spl_db is not None
        modified_spl = list(baseline.spl_db)
        peak_idx = max(range(len(modified_spl)), key=modified_spl.__getitem__)
        if peak_idx + 1 < len(modified_spl):
            modified_spl[peak_idx + 1] += 1.8
            modified_spl[peak_idx] -= 0.6
        elif peak_idx > 0:
            modified_spl[peak_idx - 1] += 1.8
            modified_spl[peak_idx] -= 0.6
        for idx, freq in enumerate(baseline.frequency_hz):
            if freq < 35.0:
                modified_spl[idx] -= 2.5
        measurement = MeasurementTrace(
            frequency_hz=list(baseline.frequency_hz),
            spl_db=modified_spl,
            impedance_ohm=baseline.impedance_ohm,
        )

        payload = _measurement_comparison_payload(
            alignment="vented",
            driver=self.driver,
            box=box,
            measurement=measurement,
            mic_distance_m=1.0,
            drive_voltage=2.83,
            apply_overrides=True,
        )

        overrides = payload.get("calibration_overrides")
        self.assertIsInstance(overrides, dict)
        if isinstance(overrides, dict):
            self.assertIsNotNone(overrides.get("port_length_m"))

        calibrated = payload.get("calibrated")
        self.assertIsInstance(calibrated, dict)
        assert isinstance(calibrated, dict)
        inputs = calibrated.get("inputs")
        self.assertIsInstance(inputs, dict)
        if isinstance(inputs, dict):
            port_value = inputs.get("port_length_m")
            self.assertIsInstance(port_value, int | float)
            assert isinstance(port_value, int | float)
            self.assertNotAlmostEqual(port_value, box.port.length_m, places=4)

        stats = payload.get("stats")
        rerun_stats = calibrated.get("stats") if isinstance(calibrated, dict) else None
        self.assertIsInstance(stats, dict)
        self.assertIsInstance(rerun_stats, dict)
        if isinstance(stats, dict) and isinstance(rerun_stats, dict):
            bias = stats.get("spl_bias_db")
            rerun_bias = rerun_stats.get("spl_bias_db")
            if isinstance(bias, int | float) and isinstance(rerun_bias, int | float):
                self.assertLess(abs(rerun_bias), abs(bias) + 1e-6)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
