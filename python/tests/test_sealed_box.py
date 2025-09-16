import math
import pathlib
import sys
import unittest

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from spl_core import BoxDesign, DriverParameters, SealedBoxSolver


class SealedBoxSolverTest(unittest.TestCase):
    def setUp(self) -> None:
        self.driver = DriverParameters(
            fs_hz=37.2,
            qts=0.38,
            re_ohm=5.6,
            bl_t_m=17.0,
            mms_kg=0.118,
            sd_m2=0.0855,
            le_h=0.0007,
            vas_l=92.0,
            xmax_mm=11.5,
        )
        self.box = BoxDesign(volume_l=50.0)
        self.solver = SealedBoxSolver(self.driver, self.box)

    def test_alignment_estimates(self) -> None:
        fc = self.solver.system_resonance()
        qtc = self.solver.system_qtc()
        self.assertGreater(fc, self.driver.fs_hz)
        self.assertTrue(50.0 < fc < 90.0)
        self.assertTrue(0.5 < qtc < 1.2)

    def test_frequency_response_shape(self) -> None:
        fc = self.solver.system_resonance()
        freqs = [fc / 2, fc, fc * 2]
        response = self.solver.frequency_response(freqs)

        self.assertEqual(len(response.frequency_hz), len(freqs))
        self.assertEqual(len(response.spl_db), len(freqs))
        self.assertEqual(len(response.impedance_ohm), len(freqs))
        self.assertEqual(len(response.cone_displacement_m), len(freqs))

        spl_low, spl_mid, spl_high = response.spl_db
        self.assertGreater(spl_mid, spl_low)
        self.assertGreater(spl_high, spl_mid)

        v_low, v_mid, v_high = response.cone_velocity_ms
        self.assertGreater(v_mid, v_low)
        self.assertLess(v_high, v_mid)

        d_low, d_mid, d_high = response.cone_displacement_m
        self.assertAlmostEqual(d_low, v_low / (2 * math.pi * freqs[0]), places=6)
        self.assertAlmostEqual(d_mid, v_mid / (2 * math.pi * freqs[1]), places=6)
        self.assertAlmostEqual(d_high, v_high / (2 * math.pi * freqs[2]), places=6)

        z_mag = abs(response.impedance_ohm[1])
        self.assertGreater(z_mag, self.driver.re_ohm)

        as_dict = response.to_dict()
        self.assertIn("impedance_real", as_dict)
        self.assertEqual(len(as_dict["impedance_real"]), len(freqs))
        self.assertIn("cone_displacement_m", as_dict)

    def test_alignment_summary_band_edges(self) -> None:
        freqs = [float(f) for f in range(10, 201, 2)]
        response = self.solver.frequency_response(freqs)
        summary = self.solver.alignment_summary(response)

        self.assertIsNotNone(summary.f3_low_hz)
        self.assertIsNotNone(summary.f3_high_hz)
        assert summary.f3_low_hz is not None
        assert summary.f3_high_hz is not None
        self.assertLess(summary.f3_low_hz, summary.fc_hz)
        self.assertGreater(summary.f3_high_hz, summary.fc_hz)
        self.assertGreater(summary.max_spl_db, response.spl_db[0])
        self.assertGreater(summary.max_cone_velocity_ms, 0.0)
        self.assertGreater(summary.max_cone_displacement_m, 0.0)
        self.assertIsNotNone(summary.excursion_ratio)
        assert summary.excursion_ratio is not None
        self.assertGreater(summary.excursion_headroom_db or 0.0, -10.0)
        self.assertIsNotNone(summary.safe_drive_voltage_v)

        summary_dict = summary.to_dict()
        fc_from_dict = summary_dict["fc_hz"]
        assert fc_from_dict is not None
        self.assertAlmostEqual(fc_from_dict, summary.fc_hz, places=6)
        self.assertIn("max_cone_displacement_m", summary_dict)

    def test_safe_drive_voltage_scaling(self) -> None:
        freqs = [float(f) for f in range(15, 201, 5)]
        response = self.solver.frequency_response(freqs)
        summary = self.solver.alignment_summary(response)

        self.assertIsNotNone(summary.safe_drive_voltage_v)
        assert summary.safe_drive_voltage_v is not None

        if summary.excursion_ratio and summary.excursion_ratio > 1.0:
            self.assertLess(summary.safe_drive_voltage_v, self.solver.drive_voltage)
        else:
            self.assertAlmostEqual(
                summary.safe_drive_voltage_v, self.solver.drive_voltage, places=6
            )


if __name__ == "__main__":
    unittest.main()
