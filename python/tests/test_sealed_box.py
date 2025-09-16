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

        spl_low, spl_mid, spl_high = response.spl_db
        self.assertGreater(spl_mid, spl_low)
        self.assertGreater(spl_high, spl_mid)

        v_low, v_mid, v_high = response.cone_velocity_ms
        self.assertGreater(v_mid, v_low)
        self.assertLess(v_high, v_mid)

        z_mag = abs(response.impedance_ohm[1])
        self.assertGreater(z_mag, self.driver.re_ohm)


if __name__ == "__main__":
    unittest.main()
