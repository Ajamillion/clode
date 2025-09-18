import json
import pathlib
import subprocess
import sys
import tempfile
import unittest


class SchemaExportScriptTests(unittest.TestCase):
    def test_cli_writes_catalog_and_solver_files(self) -> None:
        project_root = pathlib.Path(__file__).resolve().parents[1]
        script_path = project_root / "scripts" / "export_solver_schemas.py"

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = pathlib.Path(tmpdir)
            completed = subprocess.run(
                [sys.executable, str(script_path), "--output", tmpdir, "--pretty"],
                check=True,
                capture_output=True,
                text=True,
            )

            self.assertIn("schema files", completed.stdout)

            catalog_path = output_dir / "catalog.json"
            self.assertTrue(catalog_path.exists())
            catalog = json.loads(catalog_path.read_text())
            self.assertIn("sealed", catalog)
            self.assertIn("vented", catalog)
            self.assertIn("hybrid", catalog)

            sealed_request = output_dir / "sealed-request.schema.json"
            self.assertTrue(sealed_request.exists())
            sealed_schema = json.loads(sealed_request.read_text())
            self.assertEqual(sealed_schema["title"], "SealedBoxSimulationRequest")

            vented_response = output_dir / "vented-response.schema.json"
            self.assertTrue(vented_response.exists())
            response_schema = json.loads(vented_response.read_text())
            self.assertEqual(response_schema["title"], "VentedBoxSimulationResponse")

            hybrid_response = output_dir / "hybrid-response.schema.json"
            self.assertTrue(hybrid_response.exists())
            hybrid_schema = json.loads(hybrid_response.read_text())
            self.assertEqual(hybrid_schema["title"], "HybridBoxSimulationResponse")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
