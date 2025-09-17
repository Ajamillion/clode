import pathlib
import sys
import unittest

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from spl_core import (
    hybrid_simulation_request_schema,
    hybrid_simulation_response_schema,
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
        self.assertIn("xmax_mm", driver["properties"])
        xmax = driver["properties"]["xmax_mm"]
        self.assertIn("anyOf", xmax)
        number_opts = [opt for opt in xmax["anyOf"] if opt.get("type") == "number"]
        self.assertTrue(number_opts)
        self.assertEqual(number_opts[0]["exclusiveMinimum"], 0.0)
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
        self.assertIn("cone_displacement_m", schema["properties"])
        self.assertIn("cone_displacement_m", schema["required"])

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
        self.assertIn("cone_displacement_m", schema["properties"])

    def test_hybrid_request_schema_includes_alignment_controls(self) -> None:
        schema = hybrid_simulation_request_schema()
        self.assertEqual(schema["type"], "object")
        self.assertIn("grid_resolution", schema["properties"])
        grid = schema["properties"]["grid_resolution"]
        self.assertGreaterEqual(grid["minimum"], 8)
        alignment = schema["properties"]["alignment"]
        self.assertIn("enum", alignment)
        self.assertIn("auto", alignment["enum"])
        port_schema = schema["properties"]["port"]
        self.assertEqual(port_schema["type"], "object")
        self.assertIn("snapshot_stride", schema["properties"])
        stride_schema = schema["properties"]["snapshot_stride"]
        self.assertEqual(stride_schema["minimum"], 1)

    def test_hybrid_response_schema_exposes_plane_metrics(self) -> None:
        schema = hybrid_simulation_response_schema()
        self.assertIn("plane_metrics", schema["properties"])
        plane_metrics = schema["properties"]["plane_metrics"]
        self.assertEqual(plane_metrics["type"], "object")
        metric_props = plane_metrics["additionalProperties"]["properties"]
        self.assertIn("max_pressure_coords_m", metric_props)
        coords_schema = metric_props["max_pressure_coords_m"]
        self.assertEqual(coords_schema["minItems"], 3)
        self.assertEqual(coords_schema["maxItems"], 3)
        self.assertIn("field_snapshots", schema["required"])
        snapshots = schema["properties"]["field_snapshots"]
        self.assertEqual(snapshots["type"], "array")
        summary = schema["properties"]["summary"]
        self.assertEqual(summary["type"], "object")
        self.assertIn("max_pressure_location_m", summary["properties"])
        self.assertIn("plane_max_pressure_location_m", summary["properties"])
        self.assertIn("snapshot_stride", schema["required"])

    def test_solver_catalog_lists_both_solvers(self) -> None:
        catalog = solver_json_schemas()
        self.assertIn("sealed", catalog)
        self.assertIn("vented", catalog)
        self.assertIn("hybrid", catalog)
        self.assertIn("request", catalog["sealed"])
        self.assertEqual(
            catalog["vented"]["response"]["title"],
            "VentedBoxSimulationResponse",
        )


if __name__ == "__main__":
    unittest.main()
