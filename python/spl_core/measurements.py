"""Measurement ingestion utilities for closing the solver feedback loop."""

from __future__ import annotations

import io
import json
import math
import zipfile
from bisect import bisect_left
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, TextIO

from .acoustics.sealed import SealedBoxResponse
from .acoustics.vented import VentedBoxResponse


@dataclass(slots=True)
class MeasurementTrace:
    """Frequency-domain measurement data captured from the field."""

    frequency_hz: list[float]
    spl_db: list[float] | None = None
    phase_deg: list[float] | None = None
    impedance_ohm: list[complex] | None = None
    thd_percent: list[float] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"frequency_hz": list(self.frequency_hz)}
        if self.spl_db is not None:
            payload["spl_db"] = list(self.spl_db)
        if self.phase_deg is not None:
            payload["phase_deg"] = list(self.phase_deg)
        if self.impedance_ohm is not None:
            payload["impedance_real"] = [float(z.real) for z in self.impedance_ohm]
            payload["impedance_imag"] = [float(z.imag) for z in self.impedance_ohm]
        if self.thd_percent is not None:
            payload["thd_percent"] = list(self.thd_percent)
        return payload

    def resample(self, axis_hz: Sequence[float]) -> MeasurementTrace:
        if not self.frequency_hz:
            raise ValueError("Measurement trace is empty")
        order = sorted(range(len(self.frequency_hz)), key=self.frequency_hz.__getitem__)
        freq_sorted = [self.frequency_hz[i] for i in order]

        def _sort(values: list[Any] | None) -> list[Any] | None:
            if values is None:
                return None
            return [values[i] for i in order]

        spl_sorted = _sort(self.spl_db)
        phase_sorted = _sort(self.phase_deg)
        imp_sorted = _sort(self.impedance_ohm)
        thd_sorted = _sort(self.thd_percent)

        def _interp_series(values: list[Any] | None) -> list[Any] | None:
            if values is None:
                return None
            return [_interp(freq_sorted, values, target) for target in axis_hz]

        return MeasurementTrace(
            frequency_hz=list(axis_hz),
            spl_db=_interp_series(spl_sorted),
            phase_deg=_interp_series(phase_sorted),
            impedance_ohm=_interp_series(imp_sorted),
            thd_percent=_interp_series(thd_sorted),
        )


@dataclass(slots=True)
class MeasurementDelta:
    """Per-frequency error between measurement and prediction."""

    frequency_hz: list[float]
    spl_delta_db: list[float] | None = None
    phase_delta_deg: list[float] | None = None
    impedance_delta_ohm: list[float] | None = None
    thd_delta_percent: list[float] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"frequency_hz": list(self.frequency_hz)}
        if self.spl_delta_db is not None:
            payload["spl_delta_db"] = list(self.spl_delta_db)
        if self.phase_delta_deg is not None:
            payload["phase_delta_deg"] = list(self.phase_delta_deg)
        if self.impedance_delta_ohm is not None:
            payload["impedance_delta_ohm"] = list(self.impedance_delta_ohm)
        if self.thd_delta_percent is not None:
            payload["thd_delta_percent"] = list(self.thd_delta_percent)
        return payload


@dataclass(slots=True)
class MeasurementStats:
    """Aggregated error metrics summarising measurement fit."""

    sample_count: int
    spl_rmse_db: float | None
    spl_bias_db: float | None
    max_spl_delta_db: float | None
    phase_rmse_deg: float | None
    impedance_mag_rmse_ohm: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_count": self.sample_count,
            "spl_rmse_db": self.spl_rmse_db,
            "spl_bias_db": self.spl_bias_db,
            "max_spl_delta_db": self.max_spl_delta_db,
            "phase_rmse_deg": self.phase_rmse_deg,
            "impedance_mag_rmse_ohm": self.impedance_mag_rmse_ohm,
        }


def measurement_from_response(response: SealedBoxResponse | VentedBoxResponse) -> MeasurementTrace:
    return MeasurementTrace(
        frequency_hz=list(response.frequency_hz),
        spl_db=list(response.spl_db),
        impedance_ohm=list(response.impedance_ohm),
    )


def parse_klippel_dat(payload: str | TextIO) -> MeasurementTrace:
    if isinstance(payload, str):
        text = payload
    else:
        text = payload.read()
    freq: list[float] = []
    spl: list[float] = []
    phase: list[float | None] | None = None
    imp_real: list[float | None] | None = None
    imp_imag: list[float | None] | None = None

    for row in _normalise_lines(text):
        if not row:
            continue
        try:
            frequency = float(row[0])
            spl_value = float(row[1])
        except (ValueError, IndexError):
            continue
        freq.append(frequency)
        spl.append(spl_value)

        if len(row) > 2:
            phase = phase or [None] * (len(freq) - 1)
            try:
                phase.append(float(row[2]))
            except ValueError:
                phase.append(math.nan)
        elif phase is not None:
            phase.append(math.nan)

        if len(row) > 4:
            imp_real = imp_real or [None] * (len(freq) - 1)
            imp_imag = imp_imag or [None] * (len(freq) - 1)
            try:
                imp_real.append(float(row[3]))
                imp_imag.append(float(row[4]))
            except ValueError:
                imp_real.append(math.nan)
                imp_imag.append(math.nan)
        elif imp_real is not None and imp_imag is not None:
            imp_real.append(math.nan)
            imp_imag.append(math.nan)

    impedance: list[complex] | None = None
    if imp_real is not None and imp_imag is not None:
        impedance = [
            complex(_coalesce(real), _coalesce(imag))
            for real, imag in zip(imp_real, imp_imag, strict=True)
        ]

    return MeasurementTrace(
        frequency_hz=freq,
        spl_db=spl,
        phase_deg=_finalise_optional(phase),
        impedance_ohm=impedance,
    )


def parse_rew_mdat(payload: bytes | bytearray | str | TextIO) -> MeasurementTrace:
    raw: bytes
    if isinstance(payload, bytes | bytearray):
        raw = bytes(payload)
    elif isinstance(payload, str):
        raw = payload.encode("utf-8")
    else:
        raw = payload.read().encode("utf-8")
    buffer = io.BytesIO(raw)
    with zipfile.ZipFile(buffer) as archive:
        name = _select_payload_name(archive.namelist())
        with archive.open(name) as handle:
            content = handle.read()
    if name.lower().endswith(".json"):
        data = json.loads(content.decode("utf-8"))
        payload_dict = data.get("measurement", data)
        freq = _as_float_list(payload_dict.get("frequency"))
        spl = _as_float_list(payload_dict.get("spl"))
        if freq is None or spl is None:
            raise ValueError("JSON payload missing frequency/SPL arrays")
        phase = _as_float_list(payload_dict.get("phase"))
        imp_real = _as_float_list(payload_dict.get("impedance_real"))
        imp_imag = _as_float_list(payload_dict.get("impedance_imag"))
    else:
        text = content.decode("utf-8")
        trace = parse_klippel_dat(text)
        return trace

    if imp_real is not None and imp_imag is not None:
        impedance = [complex(r, i) for r, i in zip(imp_real, imp_imag, strict=True)]
    elif imp_real is None and imp_imag is None:
        impedance = None
    else:
        raise ValueError("Impedance arrays must include both real and imaginary parts")

    return MeasurementTrace(
        frequency_hz=freq,
        spl_db=spl,
        phase_deg=phase,
        impedance_ohm=impedance,
    )


def compare_measurement_to_prediction(
    measurement: MeasurementTrace,
    prediction: MeasurementTrace,
) -> tuple[MeasurementDelta, MeasurementStats]:
    if not measurement.frequency_hz:
        raise ValueError("Measurement trace is empty")
    prediction_resampled = prediction.resample(measurement.frequency_hz)

    spl_delta = _difference_series(measurement.spl_db, prediction_resampled.spl_db)
    phase_delta = _difference_series(measurement.phase_deg, prediction_resampled.phase_deg)
    impedance_delta = _impedance_delta(
        measurement.impedance_ohm, prediction_resampled.impedance_ohm
    )

    stats = MeasurementStats(
        sample_count=len(measurement.frequency_hz),
        spl_rmse_db=_rmse(spl_delta),
        spl_bias_db=_mean(spl_delta),
        max_spl_delta_db=_max_abs(spl_delta),
        phase_rmse_deg=_rmse(phase_delta),
        impedance_mag_rmse_ohm=_rmse(impedance_delta),
    )

    delta = MeasurementDelta(
        frequency_hz=list(measurement.frequency_hz),
        spl_delta_db=spl_delta,
        phase_delta_deg=phase_delta,
        impedance_delta_ohm=impedance_delta,
    )
    return delta, stats


# --- helpers -----------------------------------------------------------------


def _normalise_lines(text: str) -> Iterable[list[str]]:
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if ";" in line:
            yield [segment.strip() for segment in line.split(";") if segment.strip()]
        else:
            yield [segment.strip() for segment in line.replace(",", " ").split() if segment.strip()]


def _select_payload_name(names: list[str]) -> str:
    candidates = [name for name in names if not name.endswith("/")]
    if not candidates:
        raise ValueError("No measurement payload found in archive")
    candidates.sort()
    return candidates[0]


def _as_float_list(value: Any) -> list[float] | None:
    if value is None:
        return None
    return [float(item) for item in value]


def _coalesce(value: float | None) -> float:
    if value is None:
        return math.nan
    return float(value)


def _finalise_optional(values: list[float | None] | None) -> list[float] | None:
    if values is None:
        return None
    return [_coalesce(value) for value in values]


def _interp(freq: Sequence[float], values: Sequence[Any], target: float) -> Any:
    if target <= freq[0]:
        return values[0]
    if target >= freq[-1]:
        return values[-1]
    idx = bisect_left(freq, target)
    if idx <= 0:
        return values[0]
    if idx >= len(freq):
        return values[-1]
    x0 = freq[idx - 1]
    x1 = freq[idx]
    y0 = values[idx - 1]
    y1 = values[idx]
    if x1 == x0:
        return y0
    ratio = (target - x0) / (x1 - x0)
    if isinstance(y0, complex) or isinstance(y1, complex):
        return complex(
            float(y0.real) + (float(y1.real) - float(y0.real)) * ratio,
            float(y0.imag) + (float(y1.imag) - float(y0.imag)) * ratio,
        )
    return float(y0) + (float(y1) - float(y0)) * ratio


def _difference_series(
    measurement: Sequence[float] | None,
    prediction: Sequence[float] | None,
) -> list[float] | None:
    if measurement is None or prediction is None:
        return None
    return [float(m) - float(p) for m, p in zip(measurement, prediction, strict=True)]


def _impedance_delta(
    measurement: Sequence[complex] | None,
    prediction: Sequence[complex] | None,
) -> list[float] | None:
    if measurement is None or prediction is None:
        return None
    return [abs(m) - abs(p) for m, p in zip(measurement, prediction, strict=True)]


def _rmse(values: Sequence[float] | None) -> float | None:
    if values is None:
        return None
    valid = [v for v in values if not math.isnan(v)]
    if not valid:
        return None
    return math.sqrt(sum(v * v for v in valid) / len(valid))


def _mean(values: Sequence[float] | None) -> float | None:
    if values is None:
        return None
    valid = [v for v in values if not math.isnan(v)]
    if not valid:
        return None
    return sum(valid) / len(valid)


def _max_abs(values: Sequence[float] | None) -> float | None:
    if values is None:
        return None
    valid = [abs(v) for v in values if not math.isnan(v)]
    if not valid:
        return None
    return max(valid)


__all__ = [
    "MeasurementTrace",
    "MeasurementDelta",
    "MeasurementStats",
    "measurement_from_response",
    "parse_klippel_dat",
    "parse_rew_mdat",
    "compare_measurement_to_prediction",
]
