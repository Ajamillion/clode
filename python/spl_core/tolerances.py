"""Monte Carlo tolerance analysis utilities for enclosure alignments."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, MutableMapping, Sequence
from dataclasses import asdict, dataclass, replace
from math import ceil, floor
from random import Random
from statistics import mean, pstdev

from .acoustics.sealed import SealedBoxSolver
from .acoustics.vented import VentedBoxSolver
from .drivers import BoxDesign, DriverParameters, PortGeometry, VentedBoxDesign


def _percentile(sorted_values: Sequence[float], quantile: float) -> float:
    if not 0.0 <= quantile <= 1.0:
        raise ValueError("quantile must be between 0 and 1")
    if not sorted_values:
        raise ValueError("cannot compute percentile of empty data")
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = (len(sorted_values) - 1) * quantile
    lower = floor(pos)
    upper = ceil(pos)
    if lower == upper:
        return sorted_values[lower]
    lower_val = sorted_values[lower]
    upper_val = sorted_values[upper]
    weight = pos - lower
    return lower_val * (1.0 - weight) + upper_val * weight


def _vary(value: float, deviation: float, rng: Random, *, floor_value: float = 1e-9) -> float:
    if deviation <= 0.0 or value == 0.0:
        return float(value)
    delta = rng.uniform(-deviation, deviation)
    varied = value * (1.0 + delta)
    if varied == 0.0:
        return floor_value
    return max(varied, floor_value)


@dataclass(slots=True)
class ToleranceSpec:
    """Percentage tolerances applied during Monte Carlo sampling."""

    driver_fs_pct: float = 0.15
    driver_qts_pct: float = 0.20
    driver_vas_pct: float = 0.10
    driver_re_pct: float = 0.05
    driver_bl_pct: float = 0.05
    driver_mms_pct: float = 0.05
    driver_sd_pct: float = 0.02
    driver_le_pct: float = 0.10
    box_volume_pct: float = 0.05
    port_diameter_pct: float = 0.06
    port_length_pct: float = 0.08

    def replace(self, **updates: float) -> ToleranceSpec:
        return replace(self, **updates)

    def to_dict(self) -> dict[str, float]:
        return {key: float(value) for key, value in asdict(self).items()}


@dataclass(slots=True)
class MetricStats:
    """Aggregated statistics for a Monte Carlo metric."""

    mean: float
    stddev: float
    minimum: float
    maximum: float
    percentile_05: float
    percentile_95: float

    def to_dict(self) -> dict[str, float]:
        return {
            "mean": self.mean,
            "stddev": self.stddev,
            "min": self.minimum,
            "max": self.maximum,
            "p05": self.percentile_05,
            "p95": self.percentile_95,
        }


@dataclass(slots=True)
class ToleranceReport:
    """Summary of a Monte Carlo tolerance analysis."""

    alignment: str
    runs: int
    baseline_summary: Mapping[str, float | None]
    metrics: Mapping[str, MetricStats]
    tolerances: ToleranceSpec
    excursion_limit_ratio: float
    excursion_exceedance_rate: float
    port_velocity_limit_ms: float | None
    port_velocity_exceedance_rate: float | None
    worst_case_spl_delta_db: float | None
    risk_rating: str
    risk_factors: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "alignment": self.alignment,
            "runs": self.runs,
            "baseline": dict(self.baseline_summary),
            "tolerances": self.tolerances.to_dict(),
            "excursion_limit_ratio": self.excursion_limit_ratio,
            "excursion_exceedance_rate": self.excursion_exceedance_rate,
            "port_velocity_limit_ms": self.port_velocity_limit_ms,
            "port_velocity_exceedance_rate": self.port_velocity_exceedance_rate,
            "worst_case_spl_delta_db": self.worst_case_spl_delta_db,
            "risk_rating": self.risk_rating,
            "risk_factors": list(self.risk_factors),
            "metrics": {name: stats.to_dict() for name, stats in self.metrics.items()},
        }


DEFAULT_TOLERANCES = ToleranceSpec()


def _collect_stat(values: Iterable[float]) -> MetricStats:
    data = [float(v) for v in values]
    if not data:
        raise ValueError("cannot compute statistics for empty metric")
    sorted_values = sorted(data)
    return MetricStats(
        mean=mean(data),
        stddev=pstdev(data),
        minimum=sorted_values[0],
        maximum=sorted_values[-1],
        percentile_05=_percentile(sorted_values, 0.05),
        percentile_95=_percentile(sorted_values, 0.95),
    )


def _vary_driver(driver: DriverParameters, spec: ToleranceSpec, rng: Random) -> DriverParameters:
    return DriverParameters(
        fs_hz=_vary(driver.fs_hz, spec.driver_fs_pct, rng),
        qts=max(_vary(driver.qts, spec.driver_qts_pct, rng), 1e-3),
        re_ohm=max(_vary(driver.re_ohm, spec.driver_re_pct, rng), 1e-3),
        bl_t_m=max(_vary(driver.bl_t_m, spec.driver_bl_pct, rng), 1e-3),
        mms_kg=max(_vary(driver.mms_kg, spec.driver_mms_pct, rng), 1e-6),
        sd_m2=max(_vary(driver.sd_m2, spec.driver_sd_pct, rng), 1e-6),
        le_h=_vary(driver.le_h, spec.driver_le_pct, rng, floor_value=0.0),
        vas_l=None if driver.vas_l is None else max(_vary(driver.vas_l, spec.driver_vas_pct, rng), 1e-6),
        xmax_mm=driver.xmax_mm,
    )


def _vary_box(box: BoxDesign, spec: ToleranceSpec, rng: Random) -> BoxDesign:
    return BoxDesign(
        volume_l=max(_vary(box.volume_l, spec.box_volume_pct, rng), 1e-3),
        leakage_q=box.leakage_q,
    )


def _vary_vented_box(box: VentedBoxDesign, spec: ToleranceSpec, rng: Random) -> VentedBoxDesign:
    port = box.port
    varied_port = PortGeometry(
        diameter_m=max(_vary(port.diameter_m, spec.port_diameter_pct, rng), 1e-4),
        length_m=max(_vary(port.length_m, spec.port_length_pct, rng), 1e-4),
        count=port.count,
        flare_factor=port.flare_factor,
        loss_q=port.loss_q,
    )
    return VentedBoxDesign(
        volume_l=max(_vary(box.volume_l, spec.box_volume_pct, rng), 1e-3),
        port=varied_port,
        leakage_q=box.leakage_q,
    )


def _summarise_metrics(metrics: Mapping[str, list[float]]) -> dict[str, MetricStats]:
    summary: dict[str, MetricStats] = {}
    for name, values in metrics.items():
        try:
            summary[name] = _collect_stat(values)
        except ValueError:
            continue
    return summary


def _worst_case_delta(
    baseline: Mapping[str, float | None], metrics: Mapping[str, list[float]]
) -> float | None:
    base_max = baseline.get("max_spl_db")
    spl_values = metrics.get("max_spl_db")
    if base_max is None or not spl_values:
        return None
    return float(base_max) - min(spl_values)


def _assess_risk(
    *,
    excursion_rate: float,
    excursion_limit_ratio: float,
    port_velocity_rate: float | None,
    port_velocity_limit_ms: float | None,
    worst_case_delta_db: float | None,
) -> tuple[str, tuple[str, ...]]:
    """Classify the tolerance snapshot into a qualitative risk rating."""

    levels = {"low": 0, "moderate": 1, "high": 2}
    rating = "low"
    factors: list[str] = []

    def flag(level: str, message: str) -> None:
        nonlocal rating
        if levels[level] > levels[rating]:
            rating = level
        factors.append(message)

    if excursion_rate >= 0.2:
        flag(
            "high",
            f"{excursion_rate:.0%} of iterations exceeded the excursion limit ({excursion_limit_ratio:.2f}×).",
        )
    elif excursion_rate >= 0.05:
        flag(
            "moderate",
            f"{excursion_rate:.0%} of iterations nudged past the excursion limit ({excursion_limit_ratio:.2f}×).",
        )

    if port_velocity_rate is not None and port_velocity_limit_ms is not None:
        if port_velocity_rate >= 0.18:
            flag(
                "high",
                f"{port_velocity_rate:.0%} of runs exceeded the {port_velocity_limit_ms:.1f} m/s port velocity limit.",
            )
        elif port_velocity_rate >= 0.08:
            flag(
                "moderate",
                f"{port_velocity_rate:.0%} of runs approached the {port_velocity_limit_ms:.1f} m/s port velocity ceiling.",
            )

    if worst_case_delta_db is not None:
        if worst_case_delta_db >= 3.0:
            flag(
                "high",
                f"Worst-case SPL dropped by {worst_case_delta_db:.1f} dB across tolerance samples.",
            )
        elif worst_case_delta_db >= 1.5:
            flag(
                "moderate",
                f"SPL varied by up to {worst_case_delta_db:.1f} dB across tolerance samples.",
            )

    if not factors:
        factors.append("All monitored tolerance checks stayed within the configured limits.")
    return rating, tuple(factors)


def _sealed_report(
    driver: DriverParameters,
    design: BoxDesign,
    frequencies_hz: Sequence[float],
    iterations: int,
    spec: ToleranceSpec,
    rng: Random,
    drive_voltage: float,
    mic_distance_m: float,
    excursion_limit_ratio: float,
) -> ToleranceReport:
    solver = SealedBoxSolver(driver, design, drive_voltage=drive_voltage)
    response = solver.frequency_response(frequencies_hz, mic_distance_m)
    baseline = solver.alignment_summary(response)
    baseline_dict = baseline.to_dict()

    metrics: MutableMapping[str, list[float]] = {}
    excursion_failures = 0

    def record_metric(name: str, value: float | None) -> None:
        if value is None:
            return
        metrics.setdefault(name, []).append(float(value))

    for _ in range(iterations):
        varied_driver = _vary_driver(driver, spec, rng)
        varied_design = _vary_box(design, spec, rng)
        varied_solver = SealedBoxSolver(varied_driver, varied_design, drive_voltage=drive_voltage)
        varied_response = varied_solver.frequency_response(frequencies_hz, mic_distance_m)
        summary = varied_solver.alignment_summary(varied_response)

        for key, value in summary.to_dict().items():
            if isinstance(value, int | float):
                record_metric(key, value)

        if summary.excursion_ratio is not None and summary.excursion_ratio > excursion_limit_ratio:
            excursion_failures += 1

    metric_stats = _summarise_metrics(metrics)
    worst_case_delta = _worst_case_delta(baseline_dict, metrics)
    excursion_rate = excursion_failures / iterations

    risk_rating, risk_factors = _assess_risk(
        excursion_rate=excursion_rate,
        excursion_limit_ratio=excursion_limit_ratio,
        port_velocity_rate=None,
        port_velocity_limit_ms=None,
        worst_case_delta_db=worst_case_delta,
    )

    return ToleranceReport(
        alignment="sealed",
        runs=iterations,
        baseline_summary=baseline_dict,
        metrics=metric_stats,
        tolerances=spec,
        excursion_limit_ratio=excursion_limit_ratio,
        excursion_exceedance_rate=excursion_rate,
        port_velocity_limit_ms=None,
        port_velocity_exceedance_rate=None,
        worst_case_spl_delta_db=worst_case_delta,
        risk_rating=risk_rating,
        risk_factors=risk_factors,
    )


def _vented_report(
    driver: DriverParameters,
    design: VentedBoxDesign,
    frequencies_hz: Sequence[float],
    iterations: int,
    spec: ToleranceSpec,
    rng: Random,
    drive_voltage: float,
    mic_distance_m: float,
    excursion_limit_ratio: float,
    port_velocity_limit_ms: float | None,
) -> ToleranceReport:
    solver = VentedBoxSolver(driver, design, drive_voltage=drive_voltage)
    response = solver.frequency_response(frequencies_hz, mic_distance_m)
    baseline = solver.alignment_summary(response)
    baseline_dict = baseline.to_dict()

    metrics: MutableMapping[str, list[float]] = {}
    excursion_failures = 0
    port_failures = 0

    def record_metric(name: str, value: float | None) -> None:
        if value is None:
            return
        metrics.setdefault(name, []).append(float(value))

    for _ in range(iterations):
        varied_driver = _vary_driver(driver, spec, rng)
        varied_design = _vary_vented_box(design, spec, rng)
        varied_solver = VentedBoxSolver(varied_driver, varied_design, drive_voltage=drive_voltage)
        varied_response = varied_solver.frequency_response(frequencies_hz, mic_distance_m)
        summary = varied_solver.alignment_summary(varied_response)

        for key, value in summary.to_dict().items():
            if isinstance(value, int | float):
                record_metric(key, value)

        if summary.excursion_ratio is not None and summary.excursion_ratio > excursion_limit_ratio:
            excursion_failures += 1
        if port_velocity_limit_ms is not None and summary.max_port_velocity_ms > port_velocity_limit_ms:
            port_failures += 1

    metric_stats = _summarise_metrics(metrics)
    worst_case_delta = _worst_case_delta(baseline_dict, metrics)
    excursion_rate = excursion_failures / iterations
    port_rate = None if port_velocity_limit_ms is None else port_failures / iterations

    risk_rating, risk_factors = _assess_risk(
        excursion_rate=excursion_rate,
        excursion_limit_ratio=excursion_limit_ratio,
        port_velocity_rate=port_rate,
        port_velocity_limit_ms=port_velocity_limit_ms,
        worst_case_delta_db=worst_case_delta,
    )

    return ToleranceReport(
        alignment="vented",
        runs=iterations,
        baseline_summary=baseline_dict,
        metrics=metric_stats,
        tolerances=spec,
        excursion_limit_ratio=excursion_limit_ratio,
        excursion_exceedance_rate=excursion_rate,
        port_velocity_limit_ms=port_velocity_limit_ms,
        port_velocity_exceedance_rate=port_rate,
        worst_case_spl_delta_db=worst_case_delta,
        risk_rating=risk_rating,
        risk_factors=risk_factors,
    )


def run_tolerance_analysis(
    alignment: str,
    driver: DriverParameters,
    design: BoxDesign | VentedBoxDesign,
    frequencies_hz: Sequence[float],
    iterations: int,
    *,
    tolerances: ToleranceSpec | None = None,
    rng: Random | None = None,
    drive_voltage: float = 2.83,
    mic_distance_m: float = 1.0,
    excursion_limit_ratio: float = 1.0,
    port_velocity_limit_ms: float | None = None,
) -> ToleranceReport:
    """Run a Monte Carlo sweep returning aggregated statistics for the alignment."""

    if iterations <= 0:
        raise ValueError("iterations must be positive")
    if not frequencies_hz:
        raise ValueError("frequencies_hz must not be empty")

    spec = tolerances or DEFAULT_TOLERANCES
    rng = rng or Random()

    if alignment == "sealed":
        if not isinstance(design, BoxDesign):
            raise TypeError("Sealed analysis requires a BoxDesign")
        return _sealed_report(
            driver,
            design,
            frequencies_hz,
            iterations,
            spec,
            rng,
            drive_voltage,
            mic_distance_m,
            excursion_limit_ratio,
        )
    if alignment == "vented":
        if not isinstance(design, VentedBoxDesign):
            raise TypeError("Vented analysis requires a VentedBoxDesign")
        return _vented_report(
            driver,
            design,
            frequencies_hz,
            iterations,
            spec,
            rng,
            drive_voltage,
            mic_distance_m,
            excursion_limit_ratio,
            port_velocity_limit_ms,
        )
    raise ValueError("alignment must be 'sealed' or 'vented'")



__all__ = [
    "ToleranceSpec",
    "MetricStats",
    "ToleranceReport",
    "DEFAULT_TOLERANCES",
    "run_tolerance_analysis",
]
