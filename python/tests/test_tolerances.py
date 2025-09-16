from __future__ import annotations

import random
import unittest

from spl_core import (
    BoxDesign,
    DriverParameters,
    PortGeometry,
    VentedBoxDesign,
    run_tolerance_analysis,
)


class ToleranceAnalysisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.frequencies = [float(f) for f in range(20, 201, 10)]

    def test_sealed_tolerance_analysis_reports_excursion_rate(self) -> None:
        driver = DriverParameters(
            fs_hz=33.0,
            qts=0.38,
            re_ohm=3.2,
            bl_t_m=15.0,
            mms_kg=0.118,
            sd_m2=0.053,
            le_h=0.0008,
            vas_l=70.0,
            xmax_mm=4.0,
        )
        box = BoxDesign(volume_l=45.0, leakage_q=12.0)
        report = run_tolerance_analysis(
            "sealed",
            driver,
            box,
            self.frequencies,
            30,
            rng=random.Random(42),
            drive_voltage=8.0,
            excursion_limit_ratio=0.05,
        )

        self.assertEqual(report.alignment, "sealed")
        self.assertEqual(report.runs, 30)
        self.assertIn("max_spl_db", report.metrics)
        self.assertGreater(report.metrics["max_spl_db"].stddev, 0.0)
        self.assertGreater(report.excursion_exceedance_rate, 0.0)
        self.assertIsNone(report.port_velocity_limit_ms)
        self.assertIsNone(report.port_velocity_exceedance_rate)
        self.assertIsNotNone(report.worst_case_spl_delta_db)

    def test_vented_tolerance_analysis_flags_port_velocity(self) -> None:
        driver = DriverParameters(
            fs_hz=28.0,
            qts=0.34,
            re_ohm=3.4,
            bl_t_m=16.5,
            mms_kg=0.130,
            sd_m2=0.056,
            le_h=0.0006,
            vas_l=85.0,
            xmax_mm=5.0,
        )
        vented = VentedBoxDesign(
            volume_l=60.0,
            port=PortGeometry(diameter_m=0.055, length_m=0.18, count=1),
            leakage_q=8.0,
        )
        report = run_tolerance_analysis(
            "vented",
            driver,
            vented,
            self.frequencies,
            25,
            rng=random.Random(123),
            drive_voltage=7.0,
            port_velocity_limit_ms=9.0,
        )

        self.assertEqual(report.alignment, "vented")
        self.assertEqual(report.runs, 25)
        self.assertIn("max_port_velocity_ms", report.metrics)
        self.assertIsNotNone(report.port_velocity_limit_ms)
        self.assertIsNotNone(report.port_velocity_exceedance_rate)
        self.assertGreater(report.port_velocity_exceedance_rate or 0.0, 0.0)
        self.assertGreater(report.metrics["max_port_velocity_ms"].maximum, 0.0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
