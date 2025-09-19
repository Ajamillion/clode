#!/usr/bin/env python3
"""Generate sealed and vented Monte Carlo tolerance reports as JSON artefacts."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from random import Random
from typing import Any

SCRIPT_PATH = Path(__file__).resolve()
PYTHON_ROOT = SCRIPT_PATH.parent.parent
PROJECT_ROOT = PYTHON_ROOT.parent

for candidate in (PROJECT_ROOT, PYTHON_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from spl_core import (  # noqa: E402 - added after sys.path tweaks for local execution
    BoxDesign,
    DriverParameters,
    PortGeometry,
    VentedBoxDesign,
    run_tolerance_analysis,
)

DEFAULT_FREQUENCIES = [float(freq) for freq in range(20, 201, 5)]


def _driver_for_sealed() -> DriverParameters:
    return DriverParameters(
        fs_hz=32.5,
        qts=0.37,
        re_ohm=3.4,
        bl_t_m=15.6,
        mms_kg=0.118,
        sd_m2=0.054,
        le_h=0.0007,
        vas_l=72.0,
        xmax_mm=5.0,
    )


def _driver_for_vented() -> DriverParameters:
    return DriverParameters(
        fs_hz=27.5,
        qts=0.33,
        re_ohm=3.3,
        bl_t_m=16.4,
        mms_kg=0.132,
        sd_m2=0.056,
        le_h=0.0006,
        vas_l=88.0,
        xmax_mm=5.5,
    )


def _sealed_design() -> BoxDesign:
    return BoxDesign(volume_l=48.0, leakage_q=13.0)


def _vented_design() -> VentedBoxDesign:
    return VentedBoxDesign(
        volume_l=62.0,
        port=PortGeometry(diameter_m=0.058, length_m=0.19, count=1, loss_q=20.0),
        leakage_q=9.0,
    )


def _serialise(report: Any, *, metadata: dict[str, Any]) -> dict[str, Any]:
    data = report.to_dict()
    payload: dict[str, Any] = {
        "metadata": metadata,
        "report": data,
    }
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("tolerance-snapshots"),
        help="Directory where JSON artefacts will be written.",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=128,
        help="Monte Carlo iterations for each alignment (default: 128)",
    )
    parser.add_argument(
        "--vented-iterations",
        type=int,
        default=None,
        help="Override iteration count for vented analysis.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=1337,
        help="Random seed used for deterministic sampling.",
    )
    parser.add_argument(
        "--mic-distance",
        type=float,
        default=1.0,
        help="Microphone distance in metres used for SPL sampling.",
    )
    parser.add_argument(
        "--sealed-voltage",
        type=float,
        default=2.83,
        help="Drive voltage for sealed alignment sweeps.",
    )
    parser.add_argument(
        "--vented-voltage",
        type=float,
        default=2.83,
        help="Drive voltage for vented alignment sweeps.",
    )
    parser.add_argument(
        "--excursion-limit",
        type=float,
        default=1.0,
        help="Excursion ratio threshold that marks a sealed run as exceeding limits.",
    )
    parser.add_argument(
        "--port-velocity-limit",
        type=float,
        default=17.0,
        help="Port velocity limit (m/s) used for vented tolerance analysis.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = args.output
    output_dir.mkdir(parents=True, exist_ok=True)

    sealed_driver = _driver_for_sealed()
    sealed_design = _sealed_design()
    sealed_report = run_tolerance_analysis(
        "sealed",
        sealed_driver,
        sealed_design,
        DEFAULT_FREQUENCIES,
        max(1, args.iterations),
        rng=Random(args.seed),
        drive_voltage=args.sealed_voltage,
        mic_distance_m=args.mic_distance,
        excursion_limit_ratio=args.excursion_limit,
    )
    sealed_payload = _serialise(
        sealed_report,
        metadata={
            "iterations": max(1, args.iterations),
            "seed": args.seed,
            "drive_voltage_v": args.sealed_voltage,
            "mic_distance_m": args.mic_distance,
            "excursion_limit_ratio": args.excursion_limit,
            "driver": asdict(sealed_driver),
            "box": asdict(sealed_design),
            "frequencies_hz": DEFAULT_FREQUENCIES,
        },
    )
    _write_json(output_dir / "sealed_tolerance.json", sealed_payload)

    vented_iterations = args.vented_iterations or args.iterations
    vented_driver = _driver_for_vented()
    vented_design = _vented_design()
    vented_report = run_tolerance_analysis(
        "vented",
        vented_driver,
        vented_design,
        DEFAULT_FREQUENCIES,
        max(1, vented_iterations),
        rng=Random(args.seed + 1),
        drive_voltage=args.vented_voltage,
        mic_distance_m=args.mic_distance,
        excursion_limit_ratio=args.excursion_limit,
        port_velocity_limit_ms=args.port_velocity_limit,
    )
    vented_payload = _serialise(
        vented_report,
        metadata={
            "iterations": max(1, vented_iterations),
            "seed": args.seed + 1,
            "drive_voltage_v": args.vented_voltage,
            "mic_distance_m": args.mic_distance,
            "excursion_limit_ratio": args.excursion_limit,
            "port_velocity_limit_ms": args.port_velocity_limit,
            "driver": asdict(vented_driver),
            "box": {
                "volume_l": vented_design.volume_l,
                "leakage_q": vented_design.leakage_q,
                "port": asdict(vented_design.port),
            },
            "frequencies_hz": DEFAULT_FREQUENCIES,
        },
    )
    _write_json(output_dir / "vented_tolerance.json", vented_payload)

    manifest = {
        "sealed": sealed_payload["metadata"],
        "vented": vented_payload["metadata"],
        "output_dir": str(output_dir.resolve()),
    }
    _write_json(output_dir / "manifest.json", manifest)

    print(f"Generated tolerance snapshots in {output_dir.resolve()}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
