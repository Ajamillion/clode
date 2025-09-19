"""CLI helper that writes solver JSON schemas to disk for downstream tooling."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve()
PYTHON_ROOT = SCRIPT_PATH.parent.parent
PROJECT_ROOT = PYTHON_ROOT.parent

for candidate in (PROJECT_ROOT, PYTHON_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from spl_core import solver_json_schemas  # noqa: E402 - path adjusted above


def export_solver_schemas(output_dir: Path, *, pretty: bool = False) -> list[Path]:
    """Write the solver schema catalog to *output_dir* and return generated paths."""

    output_dir.mkdir(parents=True, exist_ok=True)
    indent = 2 if pretty else None
    catalog = solver_json_schemas()
    exported: list[Path] = []

    catalog_path = output_dir / "catalog.json"
    catalog_path.write_text(json.dumps(catalog, indent=indent), encoding="utf-8")
    exported.append(catalog_path)

    for alignment, schemas in catalog.items():
        for schema_type, schema in schemas.items():
            filename = f"{alignment}-{schema_type}.schema.json"
            path = output_dir / filename
            path.write_text(json.dumps(schema, indent=indent), encoding="utf-8")
            exported.append(path)

    return exported


def _format_file_list(paths: Iterable[Path]) -> str:
    return ", ".join(path.name for path in paths)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export solver request/response JSON schemas.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("schema-exports"),
        help="Directory to write the generated schema files into.",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output with two-space indentation.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    output_dir = args.output.expanduser()
    files = export_solver_schemas(output_dir, pretty=args.pretty)
    file_list = _format_file_list(files)
    print(f"Wrote {len(files)} schema files to {output_dir.resolve()} ({file_list})")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
