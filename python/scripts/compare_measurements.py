"""CLI for comparing field measurements against solver predictions."""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import sys
from collections.abc import Mapping, Sequence

SCRIPT_PATH = pathlib.Path(__file__).resolve()
PYTHON_ROOT = SCRIPT_PATH.parent.parent
PROJECT_ROOT = PYTHON_ROOT.parent

for candidate in (PROJECT_ROOT, PYTHON_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from spl_core import (  # noqa: E402 - path adjusted above
    DEFAULT_DRIVER,
    BoxDesign,
    CalibrationParameter,
    MeasurementTrace,
    PortGeometry,
    SealedBoxSolver,
    VentedBoxDesign,
    VentedBoxSolver,
    compare_measurement_to_prediction,
    derive_calibration_overrides,
    derive_calibration_update,
    measurement_from_response,
    parse_klippel_dat,
    parse_rew_mdat,
    recommended_vented_alignment,
)


def _load_measurement(path: pathlib.Path, fmt: str) -> MeasurementTrace:
    if fmt == "auto":
        fmt = "rew" if path.suffix.lower() in {".mdat", ".zip", ".json"} else "klippel"

    if fmt == "rew":
        return parse_rew_mdat(path.read_bytes())
    if fmt == "klippel":
        return parse_klippel_dat(path.read_text(encoding="utf-8"))
    raise ValueError(f"Unsupported measurement format: {fmt}")


def _response_axis(trace: MeasurementTrace) -> list[float]:
    axis = sorted({f for f in trace.frequency_hz if f > 0})
    if not axis:
        raise ValueError("Measurement trace does not contain positive frequencies")
    return axis


def _build_sealed_solver(volume_l: float, leakage_q: float | None, drive_voltage: float) -> SealedBoxSolver:
    box = BoxDesign(volume_l=max(volume_l, 1.0), leakage_q=leakage_q or 15.0)
    return SealedBoxSolver(DEFAULT_DRIVER, box, drive_voltage=drive_voltage)


def _build_vented_solver(
    volume_l: float,
    leakage_q: float | None,
    drive_voltage: float,
    *,
    port_diameter: float | None,
    port_length: float | None,
    port_count: int | None,
    flare_factor: float | None,
    port_loss_q: float | None,
) -> VentedBoxSolver:
    base = recommended_vented_alignment(volume_l)
    port = PortGeometry(
        diameter_m=max(port_diameter if port_diameter is not None else base.port.diameter_m, 0.02),
        length_m=max(port_length if port_length is not None else base.port.length_m, 0.05),
        count=port_count if port_count and port_count > 0 else base.port.count,
        flare_factor=max(flare_factor if flare_factor is not None else base.port.flare_factor, 1.0),
        loss_q=max(port_loss_q if port_loss_q is not None else base.port.loss_q, 0.5),
    )

    design = VentedBoxDesign(
        volume_l=max(volume_l, 1.0),
        port=port,
        leakage_q=leakage_q if leakage_q is not None else base.leakage_q,
    )
    return VentedBoxSolver(DEFAULT_DRIVER, design, drive_voltage=drive_voltage)


def _format_float(value: float | None) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "–"
    return f"{value:.2f}"


def _format_percent(value: float | None) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "–"
    return f"{value * 100:+.1f}%"


def _format_scale(scale: float | None) -> str:
    if scale is None:
        return "–"
    return _format_percent(scale - 1.0)


def _scale_to_db(scale: float | None) -> float | None:
    if scale is None or scale <= 0:
        return None
    return 20.0 * math.log10(scale)


def _clamp_weight(weight: float) -> float:
    if weight < 0.0:
        return 0.0
    if weight > 1.0:
        return 1.0
    return weight


def _format_weight(weight: float) -> str:
    return f"{_clamp_weight(weight) * 100:.0f}%"


def _format_calibration_db(parameter: CalibrationParameter | None) -> str:
    if parameter is None:
        return "–"
    base = _format_float(parameter.mean)
    interval = parameter.credible_interval
    weight = _format_weight(parameter.update_weight)
    if interval:
        lower, upper, _confidence = interval
        return (
            f"{base} (95%: {_format_float(lower)} → {_format_float(upper)}, weight {weight})"
        )
    return f"{base} (weight {weight})"


def _format_calibration_scale(parameter: CalibrationParameter | None) -> str:
    if parameter is None:
        return "–"
    base = _format_percent(parameter.mean - 1.0)
    interval = parameter.credible_interval
    weight = _format_weight(parameter.update_weight)
    if interval:
        lower, upper, _confidence = interval
        return (
            f"{base} (95%: {_format_percent(lower - 1.0)} → {_format_percent(upper - 1.0)}, weight {weight})"
        )
    return f"{base} (weight {weight})"


def _write_json(
    path: pathlib.Path | None,
    payload: Mapping[str, object | None],
    pretty: bool,
) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    data = dict(payload)
    path.write_text(
        json.dumps(data, indent=2 if pretty else None, sort_keys=pretty),
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("measurement", type=pathlib.Path, help="Path to a Klippel DAT or REW MDAT export")
    parser.add_argument(
        "--alignment",
        choices=("sealed", "vented"),
        default="sealed",
        help="Solver alignment to compare against (default: sealed)",
    )
    parser.add_argument("--volume", type=float, default=55.0, help="Enclosure volume in litres (default: 55)")
    parser.add_argument("--drive-voltage", type=float, default=2.83, help="Drive voltage used for prediction")
    parser.add_argument("--leakage-q", type=float, help="Override leakage Q factor for the enclosure")
    parser.add_argument(
        "--format",
        choices=("auto", "klippel", "rew"),
        default="auto",
        help="Measurement file format (auto-detected by default)",
    )
    parser.add_argument("--port-diameter", type=float, help="Override vented port diameter in metres")
    parser.add_argument("--port-length", type=float, help="Override vented port length in metres")
    parser.add_argument("--port-count", type=int, help="Override the number of ports in the vented alignment")
    parser.add_argument("--flare-factor", type=float, help="Override the vented port flare correction factor")
    parser.add_argument("--port-loss-q", type=float, help="Override the vented port loss Q")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable stats to stdout")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON outputs")
    parser.add_argument("--stats-output", type=pathlib.Path, help="Write aggregated stats to a JSON file")
    parser.add_argument("--delta-output", type=pathlib.Path, help="Write per-frequency deltas to a JSON file")
    parser.add_argument(
        "--diagnosis-output",
        type=pathlib.Path,
        help="Write systematic error diagnosis to a JSON file",
    )
    parser.add_argument(
        "--calibration-output",
        type=pathlib.Path,
        help="Write Bayesian calibration posterior to a JSON file",
    )
    parser.add_argument(
        "--overrides-output",
        type=pathlib.Path,
        help="Write solver override recommendations derived from calibration to JSON",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.measurement.exists():
        parser.error(f"Measurement file not found: {args.measurement}")

    measurement = _load_measurement(args.measurement, args.format)
    axis = _response_axis(measurement)

    solver: SealedBoxSolver | VentedBoxSolver
    port_length_m: float | None = None

    if args.alignment == "sealed":
        solver = _build_sealed_solver(args.volume, args.leakage_q, args.drive_voltage)
    else:
        solver = _build_vented_solver(
            args.volume,
            args.leakage_q,
            args.drive_voltage,
            port_diameter=args.port_diameter,
            port_length=args.port_length,
            port_count=args.port_count,
            flare_factor=args.flare_factor,
            port_loss_q=args.port_loss_q,
        )
        port_length_m = solver.box.port.length_m

    prediction = measurement_from_response(solver.frequency_response(axis, 1.0))
    delta, stats, diagnosis = compare_measurement_to_prediction(
        measurement,
        prediction,
        port_length_m=port_length_m,
    )
    calibration = derive_calibration_update(diagnosis)
    overrides = derive_calibration_overrides(
        calibration,
        drive_voltage_v=args.drive_voltage,
        port_length_m=port_length_m,
        leakage_q=solver.box.leakage_q,
    )

    _write_json(args.delta_output, delta.to_dict(), args.pretty)
    _write_json(args.stats_output, stats.to_dict(), args.pretty)
    _write_json(args.diagnosis_output, diagnosis.to_dict(), args.pretty)
    _write_json(args.calibration_output, calibration.to_dict(), args.pretty)
    _write_json(args.overrides_output, overrides.to_dict(), args.pretty)

    if args.json:
        payload = {
            "alignment": args.alignment,
            "stats": stats.to_dict(),
            "diagnosis": diagnosis.to_dict(),
            "calibration": calibration.to_dict(),
            "calibration_overrides": overrides.to_dict(),
        }
        print(json.dumps(payload, indent=2 if args.pretty else None))
    else:
        print(f"Alignment: {args.alignment}")
        print(f"Sample count: {stats.sample_count}")
        print(f"SPL RMSE: {_format_float(stats.spl_rmse_db)} dB")
        print(f"SPL bias: {_format_float(stats.spl_bias_db)} dB")
        print(f"Max SPL delta: {_format_float(stats.max_spl_delta_db)} dB")
        print(f"Phase RMSE: {_format_float(stats.phase_rmse_deg)} °")
        print(f"Impedance RMSE: {_format_float(stats.impedance_mag_rmse_ohm)} Ω")
        print(f"Level trim suggestion: {_format_float(diagnosis.recommended_level_trim_db)} dB")
        print(f"Low-band bias: {_format_float(diagnosis.low_band_bias_db)} dB")
        print(f"Mid-band bias: {_format_float(diagnosis.mid_band_bias_db)} dB")
        print(f"High-band bias: {_format_float(diagnosis.high_band_bias_db)} dB")
        print(f"Tuning shift: {_format_float(diagnosis.tuning_shift_hz)} Hz")
        if diagnosis.recommended_port_length_m is not None:
            percent_delta = (
                diagnosis.recommended_port_length_scale - 1.0
                if diagnosis.recommended_port_length_scale is not None
                else None
            )
            print(
                "Port length adjustment: "
                f"{_format_float(diagnosis.recommended_port_length_m)} m"
                f" ({_format_percent(percent_delta)})"
            )
        else:
            print("Port length adjustment: –")
        if diagnosis.leakage_hint:
            hint = "Decrease leakage Q" if diagnosis.leakage_hint == "lower_q" else "Increase leakage Q"
            print(f"Leakage hint: {hint}")
        else:
            print("Leakage hint: –")
        if diagnosis.notes:
            print("Notes:")
            for note in diagnosis.notes:
                print(f"  • {note}")
        print(f"Posterior level trim: {_format_calibration_db(calibration.level_trim_db)}")
        print(f"Posterior port scale: {_format_calibration_scale(calibration.port_length_scale)}")
        print(f"Posterior leakage scale: {_format_calibration_scale(calibration.leakage_q_scale)}")
        drive_scale = overrides.drive_voltage_scale
        drive_db = _scale_to_db(drive_scale)
        print(
            "Calibrated drive voltage: "
            f"{_format_float(overrides.drive_voltage_v)} V"
            f" ({_format_scale(drive_scale)} / {_format_float(drive_db)} dB)"
        )
        print(
            "Calibrated port length: "
            f"{_format_float(overrides.port_length_m)} m"
            f" ({_format_scale(overrides.port_length_scale)})"
        )
        print(
            "Calibrated leakage Q: "
            f"{_format_float(overrides.leakage_q)}"
            f" ({_format_scale(overrides.leakage_q_scale)})"
        )
        if calibration.notes:
            print("Calibration notes:")
            for note in calibration.notes:
                print(f"  - {note}")

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
