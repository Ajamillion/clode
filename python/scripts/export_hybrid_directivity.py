"""Export hybrid solver directivity traces to CSV or JSON."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections.abc import Iterable, Mapping, Sequence
from math import log10
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve()
PYTHON_ROOT = SCRIPT_PATH.parent.parent
PROJECT_ROOT = PYTHON_ROOT.parent

for candidate in (PROJECT_ROOT, PYTHON_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from spl_core import (  # noqa: E402
    DEFAULT_DRIVER,
    BoxDesign,
    HybridBoxSolver,
    PortGeometry,
    VentedBoxDesign,
)


def _positive_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:  # pragma: no cover - argparse formats message
        raise argparse.ArgumentTypeError(str(exc)) from exc
    if parsed <= 0:
        msg = f"expected a positive value, got {value!r}"
        raise argparse.ArgumentTypeError(msg)
    return parsed


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:  # pragma: no cover - argparse formats message
        raise argparse.ArgumentTypeError(str(exc)) from exc
    if parsed <= 0:
        msg = f"expected a positive integer, got {value!r}"
        raise argparse.ArgumentTypeError(msg)
    return parsed


def _build_frequency_axis(
    start_hz: float,
    stop_hz: float,
    count: int,
    spacing: str,
) -> list[float]:
    if stop_hz <= start_hz:
        msg = "stop frequency must be greater than start frequency"
        raise argparse.ArgumentTypeError(msg)
    if spacing not in {"linear", "log"}:
        msg = f"unsupported spacing '{spacing}'"
        raise argparse.ArgumentTypeError(msg)

    if count <= 1:
        return [start_hz]

    if spacing == "linear":
        step = (stop_hz - start_hz) / (count - 1)
        return [start_hz + step * i for i in range(count)]

    if start_hz <= 0.0:
        raise argparse.ArgumentTypeError("log spacing requires positive start frequency")
    start_log = log10(start_hz)
    stop_log = log10(stop_hz)
    step_log = (stop_log - start_log) / (count - 1)
    return [10 ** (start_log + step_log * i) for i in range(count)]


def _transpose(samples: Sequence[Sequence[float]]) -> list[list[float]]:
    if not samples:
        return []
    column_count = len(samples[0])
    return [
        [angle_samples[row] for angle_samples in samples]
        for row in range(column_count)
    ]


def _clamp(value: float, *, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _beamwidth_for_column(
    angles: Sequence[float],
    responses_db: Sequence[float],
    drop_db: float = 6.0,
) -> float | None:
    if not angles or not responses_db:
        return None

    on_axis = responses_db[0]
    threshold = on_axis - drop_db

    beam_angle = angles[0]
    prev_angle = angles[0]
    prev_value = responses_db[0]

    for angle, value in zip(angles[1:], responses_db[1:], strict=True):
        if value >= threshold:
            beam_angle = angle
            prev_angle = angle
            prev_value = value
            continue

        if value == prev_value:
            crossing = angle
        else:
            ratio = (threshold - prev_value) / (value - prev_value)
            ratio = _clamp(ratio, lower=0.0, upper=1.0)
            crossing = prev_angle + (angle - prev_angle) * ratio

        beam_angle = crossing
        break

    return max(0.0, beam_angle * 2.0)


def _compute_beamwidths(
    angles: Sequence[float],
    directivity_db: Sequence[Sequence[float]],
) -> list[float | None]:
    if not angles or not directivity_db:
        return []

    frequency_count = len(directivity_db[0])
    beamwidths: list[float | None] = []
    for index in range(frequency_count):
        column = [samples[index] for samples in directivity_db]
        beamwidths.append(_beamwidth_for_column(angles, column))
    return beamwidths


def _mean(values: Sequence[float | None]) -> float | None:
    total = 0.0
    count = 0
    for value in values:
        if value is None:
            continue
        total += value
        count += 1
    if count == 0:
        return None
    return total / count


def _export_csv(
    path: Path,
    frequencies: Sequence[float],
    directivity_index: Sequence[float],
    beamwidths: Sequence[float | None],
    directivity_db: Sequence[Sequence[float]],
    angles: Sequence[float],
) -> None:
    rows = _transpose(directivity_db)
    header = ["frequency_hz", "directivity_index_db", "beamwidth_6db_deg"] + [
        f"off_axis_{angle:g}_deg_db" for angle in angles
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        for freq, di_db, beamwidth, sample in zip(
            frequencies,
            directivity_index,
            beamwidths,
            rows,
            strict=True,
        ):
            beamwidth_value = "" if beamwidth is None else beamwidth
            writer.writerow([freq, di_db, beamwidth_value, *sample])


def _export_json(
    path: Path,
    *,
    metadata: Mapping[str, object],
    frequencies: Sequence[float],
    directivity_index: Sequence[float],
    beamwidths: Sequence[float | None],
    directivity_db: Sequence[Sequence[float]],
    angles: Sequence[float],
    summary: Mapping[str, object],
    peak_frequency: float | None,
    peak_index: float | None,
    pretty: bool,
) -> None:
    payload = {
        "metadata": metadata,
        "frequencies_hz": list(frequencies),
        "directivity_index_db": list(directivity_index),
        "beamwidth_6db_deg": [bw for bw in beamwidths],
        "directivity": [
            {
                "angle_deg": angle,
                "relative_spl_db": list(samples),
            }
            for angle, samples in zip(angles, directivity_db, strict=True)
        ],
        "peak": {
            "frequency_hz": peak_frequency,
            "directivity_index_db": peak_index,
        }
        if peak_frequency is not None and peak_index is not None
        else None,
        "summary": summary,
    }
    indent = 2 if pretty else None
    path.write_text(json.dumps(payload, indent=indent), encoding="utf-8")


def _build_solver(args: argparse.Namespace) -> HybridBoxSolver:
    if args.mode == "vented":
        HybridBoxSolver._mode = "vented"
        port = PortGeometry(
            diameter_m=args.port_diameter_m,
            length_m=args.port_length_m,
            count=args.port_count,
            flare_factor=args.port_flare_factor,
            loss_q=args.port_loss_q,
        )
        box: BoxDesign | VentedBoxDesign = VentedBoxDesign(
            volume_l=args.volume_l,
            port=port,
            leakage_q=args.leakage_q,
        )
    else:
        HybridBoxSolver._mode = "sealed"
        box = BoxDesign(
            volume_l=args.volume_l,
            leakage_q=args.leakage_q,
        )

    return HybridBoxSolver(
        DEFAULT_DRIVER,
        box,
        drive_voltage=args.drive_voltage,
        grid_resolution=args.grid_resolution,
        suspension_creep=not args.disable_creep,
    )


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export hybrid solver directivity traces for sealed or vented boxes.",
    )
    parser.add_argument("--output", type=Path, required=True, help="Destination file path.")
    parser.add_argument(
        "--format",
        choices=("csv", "json"),
        default="csv",
        help="Output format (default: %(default)s).",
    )
    parser.add_argument(
        "--mode",
        choices=("sealed", "vented"),
        default="sealed",
        help="Enclosure alignment (default: %(default)s).",
    )
    parser.add_argument(
        "--volume-l",
        type=_positive_float,
        default=55.0,
        help="Net enclosure volume in litres (default: %(default)s).",
    )
    parser.add_argument(
        "--leakage-q",
        type=_positive_float,
        default=12.0,
        help="Leakage quality factor (applies to sealed and vented designs).",
    )
    parser.add_argument(
        "--drive-voltage",
        type=_positive_float,
        default=2.83,
        help="Drive voltage applied to the solver (default: %(default)s).",
    )
    parser.add_argument(
        "--mic-distance-m",
        type=_positive_float,
        default=1.0,
        help="Microphone distance used for SPL and jet-noise references.",
    )
    parser.add_argument(
        "--freq-start",
        type=_positive_float,
        default=20.0,
        help="Start frequency for the sweep in Hz (default: %(default)s).",
    )
    parser.add_argument(
        "--freq-stop",
        type=_positive_float,
        default=200.0,
        help="Stop frequency for the sweep in Hz (default: %(default)s).",
    )
    parser.add_argument(
        "--freq-count",
        type=_positive_int,
        default=97,
        help="Number of frequency samples (default: %(default)s).",
    )
    parser.add_argument(
        "--spacing",
        choices=("linear", "log"),
        default="log",
        help="Frequency spacing mode (default: %(default)s).",
    )
    parser.add_argument(
        "--grid-resolution",
        type=_positive_int,
        default=24,
        help="Interior pressure grid resolution (default: %(default)s).",
    )
    parser.add_argument(
        "--snapshot-stride",
        type=_positive_int,
        default=12,
        help="Store every Nth interior snapshot (default: %(default)s).",
    )
    parser.add_argument(
        "--disable-creep",
        action="store_true",
        help="Disable suspension creep model for the run.",
    )
    parser.add_argument(
        "--port-diameter-m",
        type=_positive_float,
        default=0.1,
        help="Port diameter in metres (vented mode only).",
    )
    parser.add_argument(
        "--port-length-m",
        type=_positive_float,
        default=0.25,
        help="Port length in metres (vented mode only).",
    )
    parser.add_argument(
        "--port-count",
        type=_positive_int,
        default=1,
        help="Number of identical ports (vented mode only).",
    )
    parser.add_argument(
        "--port-flare-factor",
        type=_positive_float,
        default=1.6,
        help="Port flare end correction factor (vented mode only).",
    )
    parser.add_argument(
        "--port-loss-q",
        type=_positive_float,
        default=18.0,
        help="Port loss quality factor (vented mode only).",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output with indentation.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress human-readable summary output.",
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = _parse_args(list(argv) if argv is not None else None)
    frequencies = _build_frequency_axis(args.freq_start, args.freq_stop, args.freq_count, args.spacing)
    solver = _build_solver(args)

    result, summary = solver.frequency_response(
        frequencies,
        mic_distance_m=args.mic_distance_m,
        snapshot_stride=args.snapshot_stride,
    )

    output_path = args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)

    metadata: dict[str, object] = {
        "mode": args.mode,
        "volume_l": args.volume_l,
        "drive_voltage": args.drive_voltage,
        "mic_distance_m": args.mic_distance_m,
        "grid_resolution": args.grid_resolution,
        "suspension_creep_enabled": not args.disable_creep,
        "leakage_q": args.leakage_q,
    }
    if args.mode == "vented":
        metadata["port"] = {
            "diameter_m": args.port_diameter_m,
            "length_m": args.port_length_m,
            "count": args.port_count,
            "flare_factor": args.port_flare_factor,
            "loss_q": args.port_loss_q,
        }

    frequencies_out = list(result.frequency_hz)
    directivity_index = list(result.directivity_index_db)
    directivity_db = [list(samples) for samples in result.directivity_response_db]
    angles = list(result.directivity_angles_deg)
    beamwidths = _compute_beamwidths(angles, directivity_db)

    peak_frequency = None
    peak_index = None
    if directivity_index and frequencies_out:
        peak_pos = max(range(len(directivity_index)), key=directivity_index.__getitem__)
        peak_index = directivity_index[peak_pos]
        peak_frequency = frequencies_out[peak_pos]

    summary_payload = {
        "max_directivity_index_db": summary.max_directivity_index_db,
        "mean_directivity_index_db": summary.mean_directivity_index_db,
        "angles_deg": list(summary.directivity_angles_deg),
        "beamwidth_6db_deg": beamwidths,
        "mean_beamwidth_6db_deg": _mean(beamwidths),
    }

    if args.format == "csv":
        _export_csv(
            output_path,
            frequencies_out,
            directivity_index,
            beamwidths,
            directivity_db,
            angles,
        )
    else:
        _export_json(
            output_path,
            metadata=metadata,
            frequencies=frequencies_out,
            directivity_index=directivity_index,
            beamwidths=beamwidths,
            directivity_db=directivity_db,
            angles=angles,
            summary=summary_payload,
            peak_frequency=peak_frequency,
            peak_index=peak_index,
            pretty=args.pretty,
        )

    if not args.quiet:
        header = f"Hybrid directivity export ({args.mode}, {args.volume_l:.1f} L)"
        print(header)
        if peak_frequency is not None and peak_index is not None:
            print(f"  Peak directivity index: {peak_index:.2f} dB at {peak_frequency:.1f} Hz")
        if summary.mean_directivity_index_db is not None:
            print(f"  Mean directivity index: {summary.mean_directivity_index_db:.2f} dB")
        mean_beamwidth = _mean(beamwidths)
        if mean_beamwidth is not None:
            print(f"  Mean -6 dB beamwidth: {mean_beamwidth:.1f}°")
        if angles:
            angle_labels = ", ".join(f"{angle:g}°" for angle in angles)
            print(f"  Sampled angles: {angle_labels}")
        print(f"  Wrote {args.format.upper()} output to {output_path}")

    return 0


if __name__ == "__main__":  # pragma: no cover - tested via subprocess
    raise SystemExit(main())
