import pathlib
import sys
import unittest

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from spl_core import (
    sealed_simulation_request_schema,
    sealed_simulation_response_schema,
    solver_json_schemas,
    vented_simulation_request_schema,
    vented_simulation_response_schema,
)


class SchemaExportTests(unittest.TestCase):
    def test_sealed_request_schema_structure(self) -> None:
        schema = sealed_simulation_request_schema()
        self.assertEqual(schema["type"], "object")
        self.assertIn("driver", schema["required"])
        driver = schema["properties"]["driver"]
        self.assertEqual(driver["type"], "object")
        self.assertIn("fs_hz", driver["properties"])
        self.assertEqual(driver["properties"]["fs_hz"]["exclusiveMinimum"], 0.0)
        freq_schema = schema["properties"]["frequencies_hz"]
        self.assertEqual(freq_schema["type"], "array")
        self.assertEqual(freq_schema["items"]["type"], "number")
        self.assertGreaterEqual(freq_schema["minItems"], 1)
        self.assertNotIn("mic_distance_m", schema["required"])
        self.assertNotIn("drive_voltage", schema["required"])

    def test_sealed_response_schema_summary(self) -> None:
        schema = sealed_simulation_response_schema()
        self.assertIn("summary", schema["required"])
        summary = schema["properties"]["summary"]
        self.assertEqual(summary["type"], "object")
        f3_low = summary["properties"]["f3_low_hz"]
        self.assertIn("anyOf", f3_low)
        self.assertTrue(any(option.get("type") == "null" for option in f3_low["anyOf"]))
        self.assertIn("fc_hz", schema["required"])
        self.assertIn("qtc", schema["required"])

    def test_vented_request_schema_includes_port(self) -> None:
        schema = vented_simulation_request_schema()
        box = schema["properties"]["box"]
        self.assertIn("port", box["properties"])
        port = box["properties"]["port"]
        self.assertEqual(port["type"], "object")
        self.assertEqual(port["properties"]["count"]["minimum"], 1)
        self.assertEqual(port["properties"]["diameter_m"]["exclusiveMinimum"], 0.0)

    def test_vented_response_schema_contains_port_velocity(self) -> None:
        schema = vented_simulation_response_schema()
        self.assertIn("port_velocity_ms", schema["properties"])
        port_velocity = schema["properties"]["port_velocity_ms"]
        self.assertEqual(port_velocity["type"], "array")
        self.assertIn("fb_hz", schema["required"])
        self.assertIn("max_port_velocity_ms", schema["required"])

    def test_solver_catalog_lists_both_solvers(self) -> None:
        catalog = solver_json_schemas()
        self.assertIn("sealed", catalog)
        self.assertIn("vented", catalog)
        self.assertIn("request", catalog["sealed"])
        self.assertEqual(
            catalog["vented"]["response"]["title"],
            "VentedBoxSimulationResponse",
        )


if __name__ == "__main__":
    unittest.main()
