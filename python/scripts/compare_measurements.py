"""CLI for comparing field measurements against solver predictions."""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import sys
from collections.abc import Mapping, Sequence
from typing import cast

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
    apply_calibration_overrides_to_box,
    apply_calibration_overrides_to_drive_voltage,
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


def _format_frequency(value: float | None) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "–"
    if value >= 1000.0:
        return f"{value / 1000.0:.2f} kHz"
    return f"{value:.1f} Hz"


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
    parser.add_argument(
        "--apply-overrides",
        action="store_true",
        help="Re-run the solver using derived calibration overrides to preview corrected stats",
    )
    parser.add_argument(
        "--calibrated-stats-output",
        type=pathlib.Path,
        help="Write stats for the calibrated rerun to JSON",
    )
    parser.add_argument(
        "--calibrated-delta-output",
        type=pathlib.Path,
        help="Write per-frequency deltas after applying calibration overrides",
    )
    parser.add_argument(
        "--calibrated-diagnosis-output",
        type=pathlib.Path,
        help="Write diagnosis notes for the calibrated rerun",
    )
    parser.add_argument(
        "--min-frequency",
        type=float,
        help="Lower frequency bound in Hz for comparison (defaults to measurement minimum)",
    )
    parser.add_argument(
        "--max-frequency",
        type=float,
        help="Upper frequency bound in Hz for comparison (defaults to measurement maximum)",
    )
    parser.add_argument(
        "--smoothing-fraction",
        type=float,
        help="Apply 1/N octave smoothing to SPL comparisons (provide N > 0)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.measurement.exists():
        parser.error(f"Measurement file not found: {args.measurement}")

    measurement = _load_measurement(args.measurement, args.format)
    min_freq = args.min_frequency
    max_freq = args.max_frequency
    if min_freq is not None and max_freq is not None and min_freq > max_freq:
        parser.error("--min-frequency must be less than or equal to --max-frequency")

    smoothing_fraction = args.smoothing_fraction
    if smoothing_fraction is not None and smoothing_fraction <= 0:
        parser.error("--smoothing-fraction must be greater than zero")

    banded_measurement = measurement
    if min_freq is not None or max_freq is not None:
        try:
            banded_measurement = measurement.bandpass(min_freq, max_freq)
        except ValueError as exc:
            parser.error(str(exc))

    axis = _response_axis(banded_measurement)
    band_min = min(banded_measurement.frequency_hz)
    band_max = max(banded_measurement.frequency_hz)

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
        banded_measurement,
        prediction,
        smoothing_fraction=smoothing_fraction,
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

    calibrated_stats = None
    calibrated_delta = None
    calibrated_diagnosis = None
    calibrated_drive = None
    calibrated_box = None
    calibrated_port_length = None

    if args.apply_overrides:
        calibrated_box = apply_calibration_overrides_to_box(solver.box, overrides)
        calibrated_drive = apply_calibration_overrides_to_drive_voltage(solver.drive_voltage, overrides)

        calibrated_solver: SealedBoxSolver | VentedBoxSolver
        if isinstance(solver, SealedBoxSolver):
            sealed_box = cast(BoxDesign, calibrated_box)
            calibrated_solver = SealedBoxSolver(DEFAULT_DRIVER, sealed_box, drive_voltage=calibrated_drive)
            calibrated_port_length = None
        else:
            vented_box = cast(VentedBoxDesign, calibrated_box)
            calibrated_solver = VentedBoxSolver(
                DEFAULT_DRIVER,
                vented_box,
                drive_voltage=calibrated_drive,
            )
            calibrated_port_length = vented_box.port.length_m

        calibrated_prediction = measurement_from_response(calibrated_solver.frequency_response(axis, 1.0))
        calibrated_delta, calibrated_stats, calibrated_diagnosis = compare_measurement_to_prediction(
            banded_measurement,
            calibrated_prediction,
            smoothing_fraction=smoothing_fraction,
            port_length_m=calibrated_port_length,
        )

        _write_json(
            args.calibrated_delta_output,
            calibrated_delta.to_dict(),
            args.pretty,
        )
        _write_json(
            args.calibrated_stats_output,
            calibrated_stats.to_dict(),
            args.pretty,
        )
        _write_json(
            args.calibrated_diagnosis_output,
            calibrated_diagnosis.to_dict(),
            args.pretty,
        )

    if args.json:
        payload = {
            "alignment": args.alignment,
            "frequency_band": {
                "min_hz": band_min,
                "max_hz": band_max,
            },
            "smoothing_fraction": smoothing_fraction,
            "stats": stats.to_dict(),
            "diagnosis": diagnosis.to_dict(),
            "calibration": calibration.to_dict(),
            "calibration_overrides": overrides.to_dict(),
        }
        if calibrated_stats and calibrated_delta and calibrated_diagnosis:
            payload["calibrated"] = {
                "drive_voltage_v": calibrated_drive,
                "leakage_q": getattr(calibrated_box, "leakage_q", None) if calibrated_box else None,
                "port_length_m": calibrated_port_length,
                "stats": calibrated_stats.to_dict(),
                "diagnosis": calibrated_diagnosis.to_dict(),
                "delta": calibrated_delta.to_dict(),
            }
        print(json.dumps(payload, indent=2 if args.pretty else None))
    else:
        print(f"Alignment: {args.alignment}")
        print(f"Sample count: {stats.sample_count}")
        print(
            "Frequency band: "
            f"{_format_frequency(band_min)}"
            f" → {_format_frequency(band_max)}"
        )
        if smoothing_fraction and smoothing_fraction > 0:
            print(f"Smoothing: 1/{smoothing_fraction:g} octave")
        else:
            print("Smoothing: none")
        print(f"SPL RMSE: {_format_float(stats.spl_rmse_db)} dB")
        print(f"SPL MAE: {_format_float(stats.spl_mae_db)} dB")
        print(f"SPL bias: {_format_float(stats.spl_bias_db)} dB")
        print(f"SPL correlation: {_format_float(stats.spl_pearson_r)}")
        print(f"SPL R²: {_format_float(stats.spl_r_squared)}")
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

        if calibrated_stats and calibrated_delta and calibrated_diagnosis:
            print("\nCalibrated rerun using derived overrides:")
            base_drive = solver.drive_voltage
            drive_scale = None
            if base_drive > 0 and calibrated_drive:
                drive_scale = calibrated_drive / base_drive
            print(
                "Calibrated drive voltage: "
                f"{_format_float(calibrated_drive)} V"
                f" ({_format_scale(drive_scale)})"
            )
            base_leakage = getattr(solver.box, "leakage_q", None)
            calibrated_leakage = getattr(calibrated_box, "leakage_q", None) if calibrated_box else None
            leakage_scale = None
            if base_leakage and calibrated_leakage:
                leakage_scale = calibrated_leakage / base_leakage if base_leakage > 0 else None
            print(
                "Calibrated leakage Q: "
                f"{_format_float(calibrated_leakage)}"
                f" ({_format_scale(leakage_scale)})"
            )
            if calibrated_port_length is not None:
                base_port = port_length_m
                port_scale = None
                if base_port and base_port > 0:
                    port_scale = calibrated_port_length / base_port
                print(
                    "Calibrated port length: "
                    f"{_format_float(calibrated_port_length)} m"
                    f" ({_format_scale(port_scale)})"
                )
            print(
                "SPL RMSE after calibration: "
                f"{_format_float(calibrated_stats.spl_rmse_db)} dB"
                f" (was {_format_float(stats.spl_rmse_db)} dB)"
            )
            print(
                "SPL MAE after calibration: "
                f"{_format_float(calibrated_stats.spl_mae_db)} dB"
                f" (was {_format_float(stats.spl_mae_db)} dB)"
            )
            print(
                "SPL bias after calibration: "
                f"{_format_float(calibrated_stats.spl_bias_db)} dB"
                f" (was {_format_float(stats.spl_bias_db)} dB)"
            )
            print(
                "SPL correlation after calibration: "
                f"{_format_float(calibrated_stats.spl_pearson_r)}"
                f" (was {_format_float(stats.spl_pearson_r)})"
            )
            print(
                "SPL R² after calibration: "
                f"{_format_float(calibrated_stats.spl_r_squared)}"
                f" (was {_format_float(stats.spl_r_squared)})"
            )
            print(
                "Max SPL delta after calibration: "
                f"{_format_float(calibrated_stats.max_spl_delta_db)} dB"
                f" (was {_format_float(stats.max_spl_delta_db)} dB)"
            )
            print(
                "Phase RMSE after calibration: "
                f"{_format_float(calibrated_stats.phase_rmse_deg)} °"
                f" (was {_format_float(stats.phase_rmse_deg)} °)"
            )
            print(
                "Impedance RMSE after calibration: "
                f"{_format_float(calibrated_stats.impedance_mag_rmse_ohm)} Ω"
                f" (was {_format_float(stats.impedance_mag_rmse_ohm)} Ω)"
            )
            if calibrated_diagnosis.notes:
                print("Updated notes:")
                for note in calibrated_diagnosis.notes:
                    print(f"  - {note}")

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
