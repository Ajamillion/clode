from __future__ import annotations

import unittest

from services.gateway.app.main import _build_optimisation_result


class OptimisationResultTests(unittest.TestCase):
    def test_default_alignment_is_sealed(self) -> None:
        result = _build_optimisation_result({})
        self.assertEqual(result["alignment"], "sealed")
        self.assertIn("history", result)
        self.assertGreater(len(result["history"]), 0)
        solution = result["convergence"]["solution"]
        self.assertIn("fc_hz", solution)
        self.assertIn("alignment", solution)
        self.assertEqual(solution["alignment"], "sealed")

    def test_vented_alignment_includes_port_metrics(self) -> None:
        params = {"preferAlignment": "vented", "maxVolume": 70.0, "targetSpl": 120.0}
        result = _build_optimisation_result(params)
        self.assertEqual(result["alignment"], "vented")
        solution = result["convergence"]["solution"]
        self.assertIn("fb_hz", solution)
        metrics = result["metrics"]
        self.assertIn("max_port_velocity_ms", metrics)
        summary = result["summary"]
        self.assertIn("max_port_velocity_ms", summary)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
