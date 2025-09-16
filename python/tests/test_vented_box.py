import pathlib
import sys
import unittest

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from spl_core import (
    DriverParameters,
    PortGeometry,
    VentedBoxDesign,
    VentedBoxSolver,
)


class VentedBoxSolverTest(unittest.TestCase):
    def setUp(self) -> None:
        self.driver = DriverParameters(
            fs_hz=28.5,
            qts=0.36,
            re_ohm=3.4,
            bl_t_m=15.5,
            mms_kg=0.142,
            sd_m2=0.089,
            le_h=0.0008,
            vas_l=140.0,
            xmax_mm=13.0,
        )

        port = PortGeometry(diameter_m=0.1, length_m=0.22, count=1, loss_q=16.0)
        self.box = VentedBoxDesign(volume_l=70.0, port=port, leakage_q=12.0)
        self.solver = VentedBoxSolver(self.driver, self.box)

    def test_tuning_frequency(self) -> None:
        fb = self.solver.tuning_frequency()
        self.assertTrue(28.0 < fb < 42.0)

    def test_frequency_response_characteristics(self) -> None:
        fb = self.solver.tuning_frequency()
        freqs = [fb * 0.5, fb, fb * 2.0]
        response = self.solver.frequency_response(freqs)

        self.assertEqual(len(response.frequency_hz), 3)
        self.assertEqual(len(response.port_air_velocity_ms), 3)
        self.assertEqual(len(response.cone_displacement_m), 3)

        # Port velocity should peak near tuning while cone velocity dips
        port_low, port_fb, port_high = response.port_air_velocity_ms
        cone_low, cone_fb, cone_high = response.cone_velocity_ms

        self.assertGreater(port_fb, port_low)
        self.assertGreater(port_fb, port_high)
        self.assertLess(cone_fb, cone_low)
        self.assertLess(response.cone_displacement_m[1], response.cone_displacement_m[0])

        # SPL should rise meaningfully as we move above tuning
        spl_low, spl_mid, spl_high = response.spl_db
        self.assertLess(spl_low, spl_high)
        self.assertLess(abs(spl_mid - spl_low), 12.0)

        self.assertIn("port_velocity_ms", response.to_dict())
        self.assertIn("cone_displacement_m", response.to_dict())

    def test_impedance_double_peak(self) -> None:
        freqs = [float(f) for f in range(20, 151, 5)]
        response = self.solver.frequency_response(freqs)
        mags = [abs(z) for z in response.impedance_ohm]

        threshold = self.driver.re_ohm * 1.2
        peak_count = 0
        for i, mag in enumerate(mags):
            if mag <= threshold:
                continue
            left = mags[i - 1] if i > 0 else mags[i + 1]
            right = mags[i + 1] if i < len(mags) - 1 else mags[i - 1]
            if mag >= left and mag >= right:
                peak_count += 1

        self.assertGreaterEqual(peak_count, 2)

    def test_alignment_summary_port_metrics(self) -> None:
        freqs = [float(f) for f in range(18, 181, 2)]
        response = self.solver.frequency_response(freqs)
        summary = self.solver.alignment_summary(response)

        self.assertAlmostEqual(summary.fb_hz, self.solver.tuning_frequency(), places=6)
        self.assertIsNotNone(summary.f3_low_hz)
        self.assertIsNotNone(summary.f3_high_hz)
        self.assertGreater(summary.max_port_velocity_ms, 0.0)
        self.assertGreater(summary.max_cone_velocity_ms, 0.0)
        self.assertGreater(summary.max_cone_displacement_m, 0.0)
        self.assertGreater(summary.max_spl_db, response.spl_db[0])
        self.assertIsNotNone(summary.excursion_ratio)
        self.assertIsNotNone(summary.safe_drive_voltage_v)

        summary_dict = summary.to_dict()
        self.assertIn("max_port_velocity_ms", summary_dict)
        self.assertIn("max_cone_displacement_m", summary_dict)


if __name__ == "__main__":
    unittest.main()
