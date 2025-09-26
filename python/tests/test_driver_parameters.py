import pathlib
import sys
import unittest

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from spl_core import DEFAULT_DRIVER, DriverParameters, recommended_vented_alignment


class DriverParameterUtilitiesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.driver = DriverParameters(
            fs_hz=32.0,
            qts=0.35,
            re_ohm=5.4,
            bl_t_m=16.2,
            mms_kg=0.104,
            sd_m2=0.082,
            vas_l=95.0,
            xmax_mm=12.0,
        )

    def test_compliance_curve_symmetry(self) -> None:
        offsets = [-12.0, -6.0, 0.0, 6.0, 12.0]
        curve = self.driver.compliance_curve(offsets)
        self.assertEqual(len(curve), len(offsets))

        midpoint = len(curve) // 2
        for i in range(midpoint):
            left = curve[i][1]
            right = curve[-(i + 1)][1]
            self.assertAlmostEqual(left, right, places=12)

        cms_at_center = curve[midpoint][1]
        cms_at_edge = curve[0][1]
        self.assertGreater(cms_at_edge, cms_at_center)

    def test_compliance_curve_without_xmax(self) -> None:
        driver = DriverParameters(
            fs_hz=29.5,
            qts=0.41,
            re_ohm=6.0,
            bl_t_m=15.0,
            mms_kg=0.12,
            sd_m2=0.09,
            vas_l=110.0,
        )
        curve = driver.compliance_curve([-5.0, 0.0, 5.0])
        self.assertEqual(len(curve), 3)
        self.assertGreater(curve[0][1], curve[1][1])

    def test_xmax_conversion(self) -> None:
        self.assertAlmostEqual(self.driver.xmax_m(), 0.012, places=6)

    def test_default_driver_matches_expected(self) -> None:
        self.assertAlmostEqual(DEFAULT_DRIVER.fs_hz, 32.0)
        self.assertAlmostEqual(DEFAULT_DRIVER.qts, 0.39)
        self.assertAlmostEqual(DEFAULT_DRIVER.re_ohm, 3.2)
        self.assertAlmostEqual(DEFAULT_DRIVER.bl_t_m, 15.5)
        self.assertAlmostEqual(DEFAULT_DRIVER.mms_kg, 0.125)
        self.assertAlmostEqual(DEFAULT_DRIVER.sd_m2, 0.052)
        self.assertIsNotNone(DEFAULT_DRIVER.vas_l)
        if DEFAULT_DRIVER.vas_l is not None:
            self.assertAlmostEqual(DEFAULT_DRIVER.vas_l, 75.0)

    def test_recommended_vented_alignment_scales_with_volume(self) -> None:
        small = recommended_vented_alignment(30.0)
        large = recommended_vented_alignment(120.0)

        self.assertGreaterEqual(small.port.diameter_m, 0.06)
        self.assertGreaterEqual(large.port.area_m2(), small.port.area_m2())
        self.assertGreaterEqual(large.port.count, small.port.count)
        self.assertAlmostEqual(small.port.flare_factor, 1.6)
        self.assertAlmostEqual(large.port.flare_factor, 1.6)


if __name__ == "__main__":
    unittest.main()
