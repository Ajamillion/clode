"""Measurement ingestion utilities for closing the solver feedback loop."""

from __future__ import annotations

import io
import json
import math
import zipfile
from bisect import bisect_left, bisect_right
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

    def bandpass(self, minimum_hz: float | None, maximum_hz: float | None) -> MeasurementTrace:
        """Return a copy of the trace limited to the provided frequency band."""

        if minimum_hz is None and maximum_hz is None:
            return self

        if minimum_hz is not None and maximum_hz is not None and minimum_hz > maximum_hz:
            raise ValueError("Minimum frequency must be less than or equal to maximum frequency")

        indices: list[int] = []
        for idx, freq in enumerate(self.frequency_hz):
            if minimum_hz is not None and freq < minimum_hz:
                continue
            if maximum_hz is not None and freq > maximum_hz:
                continue
            indices.append(idx)

        if not indices:
            raise ValueError("No samples fall within the requested frequency band")

        def _slice(series: list[Any] | None) -> list[Any] | None:
            if series is None:
                return None
            return [series[i] for i in indices]

        return MeasurementTrace(
            frequency_hz=[self.frequency_hz[i] for i in indices],
            spl_db=_slice(self.spl_db),
            phase_deg=_slice(self.phase_deg),
            impedance_ohm=_slice(self.impedance_ohm),
            thd_percent=_slice(self.thd_percent),
        )

    def fractional_octave_smooth(
        self,
        fraction: float,
        *,
        fields: Sequence[str] | None = None,
    ) -> MeasurementTrace:
        """Return a smoothed copy using a 1/N-octave moving average."""

        if fraction <= 0:
            fields = fields or ()
        target_fields = set(fields or ("spl_db",))
        freq = list(self.frequency_hz)

        def _apply(series: list[float] | None, field: str) -> list[float] | None:
            if series is None:
                return None
            if fraction <= 0 or field not in target_fields:
                return list(series)
            return _fractional_octave_smooth_series(freq, series, fraction)

        impedance = None
        if self.impedance_ohm is not None:
            real = [float(z.real) for z in self.impedance_ohm]
            imag = [float(z.imag) for z in self.impedance_ohm]
            smooth_real = _apply(real, "impedance_ohm")
            smooth_imag = _apply(imag, "impedance_ohm")
            if smooth_real is not None and smooth_imag is not None:
                impedance = [
                    complex(r, i)
                    for r, i in zip(smooth_real, smooth_imag, strict=True)
                ]

        return MeasurementTrace(
            frequency_hz=freq,
            spl_db=_apply(self.spl_db, "spl_db"),
            phase_deg=_apply(self.phase_deg, "phase_deg"),
            impedance_ohm=impedance,
            thd_percent=_apply(self.thd_percent, "thd_percent"),
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
    minimum_frequency_hz: float
    maximum_frequency_hz: float
    spl_rmse_db: float | None
    spl_mae_db: float | None
    spl_bias_db: float | None
    spl_median_abs_dev_db: float | None
    spl_std_dev_db: float | None
    spl_pearson_r: float | None
    spl_r_squared: float | None
    spl_p95_abs_error_db: float | None
    spl_highest_delta_db: float | None
    spl_lowest_delta_db: float | None
    max_spl_delta_db: float | None
    phase_rmse_deg: float | None
    impedance_mag_rmse_ohm: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_count": self.sample_count,
            "minimum_frequency_hz": self.minimum_frequency_hz,
            "maximum_frequency_hz": self.maximum_frequency_hz,
            "spl_rmse_db": self.spl_rmse_db,
            "spl_mae_db": self.spl_mae_db,
            "spl_bias_db": self.spl_bias_db,
            "spl_median_abs_dev_db": self.spl_median_abs_dev_db,
            "spl_std_dev_db": self.spl_std_dev_db,
            "spl_pearson_r": self.spl_pearson_r,
            "spl_r_squared": self.spl_r_squared,
            "spl_p95_abs_error_db": self.spl_p95_abs_error_db,
            "spl_highest_delta_db": self.spl_highest_delta_db,
            "spl_lowest_delta_db": self.spl_lowest_delta_db,
            "max_spl_delta_db": self.max_spl_delta_db,
            "phase_rmse_deg": self.phase_rmse_deg,
            "impedance_mag_rmse_ohm": self.impedance_mag_rmse_ohm,
        }


@dataclass(slots=True)
class MeasurementDiagnosis:
    """Heuristic suggestions derived from measurement deltas."""

    overall_bias_db: float | None
    recommended_level_trim_db: float | None
    low_band_bias_db: float | None
    mid_band_bias_db: float | None
    high_band_bias_db: float | None
    tuning_shift_hz: float | None
    recommended_port_length_m: float | None
    recommended_port_length_scale: float | None
    leakage_hint: str | None
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_bias_db": self.overall_bias_db,
            "recommended_level_trim_db": self.recommended_level_trim_db,
            "low_band_bias_db": self.low_band_bias_db,
            "mid_band_bias_db": self.mid_band_bias_db,
            "high_band_bias_db": self.high_band_bias_db,
            "tuning_shift_hz": self.tuning_shift_hz,
            "recommended_port_length_m": self.recommended_port_length_m,
            "recommended_port_length_scale": self.recommended_port_length_scale,
            "leakage_hint": self.leakage_hint,
            "notes": list(self.notes),
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
    *,
    smoothing_fraction: float | None = None,
    port_length_m: float | None = None,
) -> tuple[MeasurementDelta, MeasurementStats, MeasurementDiagnosis]:
    if not measurement.frequency_hz:
        raise ValueError("Measurement trace is empty")

    measurement_original = measurement
    prediction_resampled = prediction.resample(measurement_original.frequency_hz)

    smoothing = None
    if smoothing_fraction is not None and smoothing_fraction > 0:
        smoothing = float(smoothing_fraction)
        measurement_for_stats = measurement_original.fractional_octave_smooth(smoothing)
        prediction_for_stats = prediction_resampled.fractional_octave_smooth(smoothing)
    else:
        measurement_for_stats = measurement_original
        prediction_for_stats = prediction_resampled

    spl_delta = _difference_series(
        measurement_for_stats.spl_db, prediction_for_stats.spl_db
    )
    phase_delta = _difference_series(
        measurement_for_stats.phase_deg, prediction_for_stats.phase_deg
    )
    impedance_delta = _impedance_delta(
        measurement_for_stats.impedance_ohm, prediction_for_stats.impedance_ohm
    )

    if not measurement_for_stats.frequency_hz:
        msg = "Measurement trace is empty after preprocessing"
        raise ValueError(msg)

    min_freq = float(min(measurement_for_stats.frequency_hz))
    max_freq = float(max(measurement_for_stats.frequency_hz))

    stats = MeasurementStats(
        sample_count=len(measurement_for_stats.frequency_hz),
        minimum_frequency_hz=min_freq,
        maximum_frequency_hz=max_freq,
        spl_rmse_db=_rmse(spl_delta),
        spl_mae_db=_mae(spl_delta),
        spl_bias_db=_mean(spl_delta),
        spl_median_abs_dev_db=_median_abs_deviation(spl_delta),
        spl_std_dev_db=_stddev(spl_delta),
        spl_pearson_r=_pearson_correlation(
            measurement_for_stats.spl_db, prediction_for_stats.spl_db
        ),
        spl_r_squared=_coefficient_of_determination(
            measurement_for_stats.spl_db, prediction_for_stats.spl_db
        ),
        spl_p95_abs_error_db=_percentile_abs(spl_delta, 0.95),
        spl_highest_delta_db=_max_value(spl_delta),
        spl_lowest_delta_db=_min_value(spl_delta),
        max_spl_delta_db=_max_abs(spl_delta),
        phase_rmse_deg=_rmse(phase_delta),
        impedance_mag_rmse_ohm=_rmse(impedance_delta),
    )

    delta = MeasurementDelta(
        frequency_hz=list(measurement_for_stats.frequency_hz),
        spl_delta_db=spl_delta,
        phase_delta_deg=phase_delta,
        impedance_delta_ohm=impedance_delta,
    )
    diagnosis = _diagnose_bias(
        measurement_for_stats.frequency_hz,
        spl_delta,
        measurement_original.spl_db,
        prediction_resampled.spl_db,
        port_length_m=port_length_m,
    )
    return delta, stats, diagnosis


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


def _fractional_octave_smooth_series(
    frequency_hz: Sequence[float],
    values: Sequence[float],
    fraction: float,
) -> list[float]:
    if len(frequency_hz) != len(values):
        raise ValueError("Frequency and value arrays must be the same length")
    if fraction <= 0:
        return [float(value) for value in values]

    count = len(frequency_hz)
    order = sorted(range(count), key=frequency_hz.__getitem__)
    freq_sorted = [float(frequency_hz[i]) for i in order]
    values_sorted = [float(values[i]) for i in order]

    bandwidth = 2.0 ** (1.0 / (2.0 * fraction))
    smoothed_sorted: list[float] = []
    min_window = min(3, count)
    for idx, centre in enumerate(freq_sorted):
        lower = centre / bandwidth
        upper = centre * bandwidth
        start = bisect_left(freq_sorted, lower)
        stop = bisect_right(freq_sorted, upper)
        if stop - start < min_window:
            start = max(0, idx - (min_window // 2))
            stop = min(count, start + min_window)
            start = max(0, stop - min_window)
        window = values_sorted[start:stop] or [values_sorted[idx]]
        smoothed_sorted.append(sum(window) / len(window))

    smoothed = [0.0] * count
    for sorted_idx, original_idx in enumerate(order):
        smoothed[original_idx] = smoothed_sorted[sorted_idx]
    return smoothed


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


def _mae(values: Sequence[float] | None) -> float | None:
    if values is None:
        return None
    valid = [abs(v) for v in values if not math.isnan(v)]
    if not valid:
        return None
    return sum(valid) / len(valid)


def _median(values: Sequence[float]) -> float:
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[mid]
    return 0.5 * (ordered[mid - 1] + ordered[mid])


def _median_abs_deviation(values: Sequence[float] | None) -> float | None:
    if values is None:
        return None
    valid = [v for v in values if not math.isnan(v)]
    if not valid:
        return None
    centre = _median(valid)
    deviations = [abs(value - centre) for value in valid]
    if not deviations:
        return 0.0
    return _median(deviations)


def _stddev(values: Sequence[float] | None) -> float | None:
    if values is None:
        return None
    valid = [v for v in values if not math.isnan(v)]
    if not valid:
        return None
    if len(valid) == 1:
        return 0.0
    mean = math.fsum(valid) / len(valid)
    variance = math.fsum((value - mean) ** 2 for value in valid) / len(valid)
    return math.sqrt(variance)


def _pearson_correlation(
    measurement: Sequence[float] | None,
    prediction: Sequence[float] | None,
) -> float | None:
    if measurement is None or prediction is None:
        return None
    pairs: list[tuple[float, float]] = []
    for meas, pred in zip(measurement, prediction, strict=True):
        if meas is None or pred is None:
            continue
        m_val = float(meas)
        p_val = float(pred)
        if math.isnan(m_val) or math.isnan(p_val):
            continue
        pairs.append((m_val, p_val))
    if len(pairs) < 2:
        return None
    mean_meas = math.fsum(value[0] for value in pairs) / len(pairs)
    mean_pred = math.fsum(value[1] for value in pairs) / len(pairs)
    cov = math.fsum((m - mean_meas) * (p - mean_pred) for m, p in pairs)
    var_meas = math.fsum((m - mean_meas) ** 2 for m, _ in pairs)
    var_pred = math.fsum((p - mean_pred) ** 2 for _, p in pairs)
    denom = math.sqrt(var_meas * var_pred)
    if denom <= 0.0:
        return None
    return cov / denom


def _coefficient_of_determination(
    measurement: Sequence[float] | None,
    prediction: Sequence[float] | None,
) -> float | None:
    if measurement is None or prediction is None:
        return None
    pairs: list[tuple[float, float]] = []
    for meas, pred in zip(measurement, prediction, strict=True):
        if meas is None or pred is None:
            continue
        m_val = float(meas)
        p_val = float(pred)
        if math.isnan(m_val) or math.isnan(p_val):
            continue
        pairs.append((m_val, p_val))
    if len(pairs) < 2:
        return None
    mean_meas = math.fsum(value[0] for value in pairs) / len(pairs)
    ss_tot = math.fsum((m - mean_meas) ** 2 for m, _ in pairs)
    if ss_tot <= 0.0:
        return None
    ss_res = math.fsum((m - p) ** 2 for m, p in pairs)
    return 1.0 - (ss_res / ss_tot)


def _max_abs(values: Sequence[float] | None) -> float | None:
    if values is None:
        return None
    valid = [abs(v) for v in values if not math.isnan(v)]
    if not valid:
        return None
    return max(valid)


def _max_value(values: Sequence[float] | None) -> float | None:
    if values is None:
        return None
    best: float | None = None
    for value in values:
        if math.isnan(value):
            continue
        if best is None or value > best:
            best = value
    return best


def _min_value(values: Sequence[float] | None) -> float | None:
    if values is None:
        return None
    best: float | None = None
    for value in values:
        if math.isnan(value):
            continue
        if best is None or value < best:
            best = value
    return best


def _percentile_abs(values: Sequence[float] | None, percentile: float) -> float | None:
    if values is None:
        return None
    valid = sorted(abs(v) for v in values if not math.isnan(v))
    if not valid:
        return None
    if percentile <= 0.0:
        return valid[0]
    if percentile >= 1.0:
        return valid[-1]
    position = percentile * (len(valid) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return valid[lower]
    weight = position - lower
    return valid[lower] * (1.0 - weight) + valid[upper] * weight


def _band_mean(
    frequency: Sequence[float],
    values: Sequence[float] | None,
    *,
    low: float | None,
    high: float | None,
) -> float | None:
    if values is None:
        return None
    acc: list[float] = []
    for f, value in zip(frequency, values, strict=True):
        if math.isnan(value):
            continue
        if low is not None and f < low:
            continue
        if high is not None and f >= high:
            continue
        acc.append(value)
    if not acc:
        return None
    return sum(acc) / len(acc)


def _peak_frequency(frequency: Sequence[float], values: Sequence[float] | None) -> float | None:
    if values is None:
        return None
    best_freq: float | None = None
    best_value: float | None = None
    for f, value in zip(frequency, values, strict=True):
        if math.isnan(value):
            continue
        if best_value is None or value > best_value:
            best_value = value
            best_freq = f
    return best_freq


def _diagnose_bias(
    frequency: Sequence[float],
    spl_delta: Sequence[float] | None,
    measurement_spl: Sequence[float] | None,
    predicted_spl: Sequence[float] | None,
    *,
    port_length_m: float | None,
) -> MeasurementDiagnosis:
    overall_bias = _mean(spl_delta)
    level_trim = -overall_bias if overall_bias is not None else None

    low_bias = _band_mean(frequency, spl_delta, low=None, high=45.0)
    mid_bias = _band_mean(frequency, spl_delta, low=45.0, high=120.0)
    high_bias = _band_mean(frequency, spl_delta, low=120.0, high=None)

    peak_measured = _peak_frequency(frequency, measurement_spl)
    peak_predicted = _peak_frequency(frequency, predicted_spl)
    tuning_shift: float | None = None
    recommended_length_m: float | None = None
    length_scale: float | None = None
    if (
        peak_measured is not None
        and peak_predicted is not None
        and peak_measured > 0
        and peak_predicted > 0
    ):
        tuning_shift = peak_measured - peak_predicted
        if port_length_m and port_length_m > 0:
            length_scale = (peak_predicted / peak_measured) ** 2
            recommended_length_m = port_length_m * length_scale

    leakage_hint: str | None = None
    notes: list[str] = []

    if overall_bias is not None and abs(overall_bias) > 0.5:
        direction = "reduce" if overall_bias > 0 else "increase"
        notes.append(
            f"Apply a {direction} of approximately {abs(overall_bias):.1f} dB to align overall level."
        )

    if tuning_shift is not None and abs(tuning_shift) > 0.8:
        shift_dir = "higher" if tuning_shift > 0 else "lower"
        notes.append(
            f"Measured tuning appears {shift_dir} by {abs(tuning_shift):.1f} Hz relative to prediction."
        )
        if length_scale is not None and abs(length_scale - 1.0) > 0.05:
            adj = "longer" if length_scale > 1.0 else "shorter"
            notes.append(
                f"Adjust port length {adj} by about {abs((length_scale - 1.0) * 100):.1f}% to compensate."
            )

    if low_bias is not None and mid_bias is not None:
        delta = low_bias - mid_bias
        if delta <= -1.5:
            leakage_hint = "lower_q"
            notes.append(
                "Low-band output is weaker than expected; consider reducing leakage Q or checking for leaks."
            )
        elif delta >= 1.5:
            leakage_hint = "raise_q"
            notes.append(
                "Low-band output is stronger than predicted; consider increasing leakage Q or adding damping."
            )

    for label, value in (("low", low_bias), ("mid", mid_bias), ("high", high_bias)):
        if value is not None and abs(value) > 1.0:
            notes.append(f"Average {label} band bias is {value:+.1f} dB.")

    return MeasurementDiagnosis(
        overall_bias_db=overall_bias,
        recommended_level_trim_db=level_trim,
        low_band_bias_db=low_bias,
        mid_band_bias_db=mid_bias,
        high_band_bias_db=high_bias,
        tuning_shift_hz=tuning_shift,
        recommended_port_length_m=recommended_length_m,
        recommended_port_length_scale=length_scale,
        leakage_hint=leakage_hint,
        notes=notes,
    )


__all__ = [
    "MeasurementTrace",
    "MeasurementDelta",
    "MeasurementStats",
    "MeasurementDiagnosis",
    "measurement_from_response",
    "parse_klippel_dat",
    "parse_rew_mdat",
    "compare_measurement_to_prediction",
]
