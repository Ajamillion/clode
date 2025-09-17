"""Measurement-driven calibration helpers with Bayesian updates."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, overload

from .drivers import BoxDesign, PortGeometry, VentedBoxDesign
from .measurements import MeasurementDiagnosis


@dataclass(slots=True)
class ParameterPrior:
    """Gaussian prior for a calibration parameter."""

    mean: float
    variance: float

    def to_dict(self) -> dict[str, float]:
        return {"mean": float(self.mean), "variance": float(self.variance)}


@dataclass(slots=True)
class CalibrationParameter:
    """Posterior estimate for a calibration parameter."""

    mean: float
    variance: float
    prior_mean: float
    prior_variance: float
    observation: float | None
    observation_variance: float | None
    update_weight: float
    credible_interval: tuple[float, float, float] | None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "mean": self.mean,
            "variance": self.variance,
            "prior_mean": self.prior_mean,
            "prior_variance": self.prior_variance,
            "update_weight": self.update_weight,
        }
        if self.observation is not None:
            payload["observation"] = self.observation
        if self.observation_variance is not None:
            payload["observation_variance"] = self.observation_variance
        if self.credible_interval is not None:
            lower, upper, confidence = self.credible_interval
            payload["credible_interval"] = {
                "lower": lower,
                "upper": upper,
                "confidence": confidence,
            }
        payload["stddev"] = math.sqrt(self.variance) if self.variance > 0 else 0.0
        return payload


@dataclass(slots=True)
class CalibrationPrior:
    """Prior bundle for measurement-driven calibration."""

    level_trim_db: ParameterPrior
    port_length_scale: ParameterPrior
    leakage_q_scale: ParameterPrior

    @classmethod
    def default(cls) -> CalibrationPrior:
        return cls(
            level_trim_db=ParameterPrior(mean=0.0, variance=4.0),
            port_length_scale=ParameterPrior(mean=1.0, variance=0.04),
            leakage_q_scale=ParameterPrior(mean=1.0, variance=0.09),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "level_trim_db": self.level_trim_db.to_dict(),
            "port_length_scale": self.port_length_scale.to_dict(),
            "leakage_q_scale": self.leakage_q_scale.to_dict(),
        }


@dataclass(slots=True)
class CalibrationUpdate:
    """Posterior calibration estimates derived from a measurement diagnosis."""

    level_trim_db: CalibrationParameter | None
    port_length_scale: CalibrationParameter | None
    leakage_q_scale: CalibrationParameter | None
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "level_trim_db": self.level_trim_db.to_dict() if self.level_trim_db else None,
            "port_length_scale": self.port_length_scale.to_dict() if self.port_length_scale else None,
            "leakage_q_scale": self.leakage_q_scale.to_dict() if self.leakage_q_scale else None,
            "notes": list(self.notes),
        }


@dataclass(slots=True)
class CalibrationOverrides:
    """Concrete solver overrides derived from a calibration update."""

    drive_voltage_scale: float | None
    drive_voltage_v: float | None
    port_length_scale: float | None
    port_length_m: float | None
    leakage_q_scale: float | None
    leakage_q: float | None

    def to_dict(self) -> dict[str, float | None]:
        return {
            "drive_voltage_scale": self.drive_voltage_scale,
            "drive_voltage_v": self.drive_voltage_v,
            "port_length_scale": self.port_length_scale,
            "port_length_m": self.port_length_m,
            "leakage_q_scale": self.leakage_q_scale,
            "leakage_q": self.leakage_q,
        }


DEFAULT_CALIBRATION_PRIOR = CalibrationPrior.default()
_LEVEL_OBS_VARIANCE = 0.75 ** 2
_PORT_SCALE_OBS_VARIANCE = 0.08 ** 2
_LEAKAGE_OBS_VARIANCE = 0.15 ** 2
_CONFIDENCE = 0.95


def derive_calibration_update(
    diagnosis: MeasurementDiagnosis,
    prior: CalibrationPrior | None = None,
) -> CalibrationUpdate:
    """Apply simple Gaussian Bayesian updates based on measurement diagnosis."""

    priors = prior or CalibrationPrior.default()
    level = _update_level_trim(diagnosis, priors.level_trim_db)
    port = _update_port_scale(diagnosis, priors.port_length_scale)
    leakage = _update_leakage_scale(diagnosis, priors.leakage_q_scale)

    notes = list(_format_notes(("Level trim", level), ("Port scale", port), ("Leakage Q", leakage)))
    return CalibrationUpdate(level_trim_db=level, port_length_scale=port, leakage_q_scale=leakage, notes=notes)


def derive_calibration_overrides(
    calibration: CalibrationUpdate,
    *,
    drive_voltage_v: float | None = None,
    port_length_m: float | None = None,
    leakage_q: float | None = None,
) -> CalibrationOverrides:
    """Convert posterior calibration parameters into solver overrides.

    The helper projects the Bayesian posteriors onto concrete solver inputs so automated
    reruns can be seeded with the inferred corrections. Level trims are translated into a
    multiplicative drive-voltage scale (positive dB trims decrease voltage, negative trims
    increase it). Port length and leakage factors apply directly to the supplied baselines.
    Missing priors simply propagate ``None`` so callers can selectively override values.
    """

    drive_scale = _drive_voltage_scale(calibration.level_trim_db)
    drive_voltage = _scaled_value(drive_voltage_v, drive_scale)

    port_scale = _positive_mean(calibration.port_length_scale)
    port_length = _scaled_value(port_length_m, port_scale)

    leakage_scale = _positive_mean(calibration.leakage_q_scale)
    leakage_value = _scaled_value(leakage_q, leakage_scale)

    return CalibrationOverrides(
        drive_voltage_scale=drive_scale,
        drive_voltage_v=drive_voltage,
        port_length_scale=port_scale,
        port_length_m=port_length,
        leakage_q_scale=leakage_scale,
        leakage_q=leakage_value,
    )


def apply_calibration_overrides_to_drive_voltage(
    base_voltage_v: float, overrides: CalibrationOverrides | None
) -> float:
    """Project drive-voltage overrides onto a concrete solver input.

    The helper favours absolute voltage recommendations when present and falls back
    to multiplicative scaling. Invalid or non-positive suggestions are ignored so the
    original drive level is preserved.
    """

    if overrides is None:
        return base_voltage_v

    candidate = overrides.drive_voltage_v
    if candidate is None and overrides.drive_voltage_scale is not None:
        scale = overrides.drive_voltage_scale
        if math.isfinite(scale) and scale > 0:
            candidate = base_voltage_v * scale

    if candidate is None or not math.isfinite(candidate) or candidate <= 0:
        return base_voltage_v
    return float(candidate)


@overload
def apply_calibration_overrides_to_box(
    box: BoxDesign, overrides: CalibrationOverrides | None
) -> BoxDesign:
    ...


@overload
def apply_calibration_overrides_to_box(
    box: VentedBoxDesign, overrides: CalibrationOverrides | None
) -> VentedBoxDesign:
    ...


def apply_calibration_overrides_to_box(
    box: BoxDesign | VentedBoxDesign, overrides: CalibrationOverrides | None
) -> BoxDesign | VentedBoxDesign:
    """Return a copy of ``box`` with calibration overrides applied.

    Only the parameters that can be corrected via measurement feedback are touched:
    leakage ``Q`` for both alignments and port length for vented boxes. Unknown or
    invalid override suggestions fall back to the original geometry.
    """

    if overrides is None:
        return box

    leakage_q = _resolved_positive(
        getattr(box, "leakage_q", 0.0),
        overrides.leakage_q,
        overrides.leakage_q_scale,
    )

    if isinstance(box, VentedBoxDesign):
        port = box.port
        length = _resolved_positive(
            port.length_m,
            overrides.port_length_m,
            overrides.port_length_scale,
        )
        updated_port = PortGeometry(
            diameter_m=port.diameter_m,
            length_m=length,
            count=port.count,
            flare_factor=port.flare_factor,
            loss_q=port.loss_q,
        )
        return VentedBoxDesign(
            volume_l=box.volume_l,
            port=updated_port,
            leakage_q=leakage_q,
        )

    return BoxDesign(volume_l=box.volume_l, leakage_q=leakage_q)


def _update_level_trim(
    diagnosis: MeasurementDiagnosis, prior: ParameterPrior
) -> CalibrationParameter | None:
    observation = diagnosis.recommended_level_trim_db
    if observation is None or math.isnan(observation):
        return None
    posterior_mean, posterior_variance = _gaussian_update(
        prior.mean, prior.variance, observation, _LEVEL_OBS_VARIANCE
    )
    return _parameter(
        posterior_mean,
        posterior_variance,
        prior,
        observation,
        _LEVEL_OBS_VARIANCE,
    )


def _update_port_scale(
    diagnosis: MeasurementDiagnosis, prior: ParameterPrior
) -> CalibrationParameter | None:
    observation = diagnosis.recommended_port_length_scale
    if observation is None or math.isnan(observation):
        return None
    posterior_mean, posterior_variance = _gaussian_update(
        prior.mean, prior.variance, observation, _PORT_SCALE_OBS_VARIANCE
    )
    return _parameter(
        posterior_mean,
        posterior_variance,
        prior,
        observation,
        _PORT_SCALE_OBS_VARIANCE,
    )


def _update_leakage_scale(
    diagnosis: MeasurementDiagnosis, prior: ParameterPrior
) -> CalibrationParameter | None:
    observation = _leakage_observation(diagnosis)
    if observation is None:
        return None
    posterior_mean, posterior_variance = _gaussian_update(
        prior.mean, prior.variance, observation, _LEAKAGE_OBS_VARIANCE
    )
    return _parameter(
        posterior_mean,
        posterior_variance,
        prior,
        observation,
        _LEAKAGE_OBS_VARIANCE,
    )


def _parameter(
    posterior_mean: float,
    posterior_variance: float,
    prior: ParameterPrior,
    observation: float | None,
    observation_variance: float | None,
) -> CalibrationParameter:
    if prior.variance <= 0:
        update_weight = 1.0
    else:
        update_weight = 1.0 - min(posterior_variance / prior.variance, 1.0)
    credible_interval = _credible_interval(posterior_mean, posterior_variance, _CONFIDENCE)
    return CalibrationParameter(
        mean=posterior_mean,
        variance=posterior_variance,
        prior_mean=prior.mean,
        prior_variance=prior.variance,
        observation=observation,
        observation_variance=observation_variance,
        update_weight=update_weight if observation is not None else 0.0,
        credible_interval=credible_interval,
    )


def _drive_voltage_scale(parameter: CalibrationParameter | None) -> float | None:
    if parameter is None:
        return None
    scale = 10.0 ** (-(parameter.mean) / 20.0)
    if not math.isfinite(scale) or scale <= 0:
        return None
    return scale


def _positive_mean(parameter: CalibrationParameter | None) -> float | None:
    if parameter is None:
        return None
    if not math.isfinite(parameter.mean) or parameter.mean <= 0:
        return None
    return parameter.mean


def _scaled_value(base: float | None, scale: float | None) -> float | None:
    if base is None or scale is None:
        return None
    if not math.isfinite(base) or base <= 0:
        return None
    value = base * scale
    return value if math.isfinite(value) and value > 0 else None


def _resolved_positive(base: float, value: float | None, scale: float | None) -> float:
    """Return a positive override if suggested, otherwise fall back to ``base``."""

    candidate = value if value is not None else None
    if candidate is None and scale is not None and math.isfinite(scale) and scale > 0:
        candidate = base * scale

    if candidate is None or not math.isfinite(candidate) or candidate <= 0:
        return float(base)
    return float(candidate)


def _gaussian_update(
    prior_mean: float,
    prior_variance: float,
    observation: float,
    observation_variance: float,
) -> tuple[float, float]:
    if prior_variance <= 0:
        return observation, observation_variance
    precision_prior = 1.0 / prior_variance
    precision_obs = 1.0 / observation_variance
    posterior_variance = 1.0 / (precision_prior + precision_obs)
    posterior_mean = posterior_variance * (precision_prior * prior_mean + precision_obs * observation)
    return posterior_mean, posterior_variance


def _leakage_observation(diagnosis: MeasurementDiagnosis) -> float | None:
    hint = diagnosis.leakage_hint
    if hint == "lower_q":
        return 1.15
    if hint == "raise_q":
        return 0.85
    return None


def _credible_interval(mean: float, variance: float, confidence: float) -> tuple[float, float, float] | None:
    if variance <= 0:
        return None
    if not 0 < confidence < 1:
        confidence = 0.95
    z = _z_score(confidence)
    sigma = math.sqrt(variance)
    return mean - z * sigma, mean + z * sigma, confidence


def _z_score(confidence: float) -> float:
    # For two-tailed normal interval, approximate inverse error function.
    return 1.959963984540054 if abs(confidence - 0.95) < 1e-6 else _approximate_z(confidence)


def _approximate_z(confidence: float) -> float:
    # Winitzki approximation for erfinv translated to two-tailed z-score.
    if confidence <= 0 or confidence >= 1:
        return 1.959963984540054
    p = 1.0 - (1.0 - confidence) / 2.0
    # Avoid log of zero.
    if p <= 0 or p >= 1:
        return 1.959963984540054
    t = math.sqrt(-2.0 * math.log(1.0 - p))
    # Coefficients tuned for reasonable accuracy (<1e-3) across (0.8, 0.999)
    c0, c1, c2 = 2.515517, 0.802853, 0.010328
    d1, d2, d3 = 1.432788, 0.189269, 0.001308
    return t - (c0 + c1 * t + c2 * t * t) / (1 + d1 * t + d2 * t * t + d3 * t * t * t)


def _format_notes(*entries: tuple[str, CalibrationParameter | None]) -> Iterable[str]:
    for label, parameter in entries:
        if parameter is None:
            continue
        interval = parameter.credible_interval
        if interval is None:
            yield f"{label}: {parameter.mean:+.3f}"
        else:
            lower, upper, confidence = interval
            percent = int(round(confidence * 100))
            yield (
                f"{label}: {parameter.mean:+.3f} (±{percent}% window {lower:+.3f} → {upper:+.3f})"
            )


__all__ = [
    "ParameterPrior",
    "CalibrationParameter",
    "CalibrationPrior",
    "CalibrationUpdate",
    "DEFAULT_CALIBRATION_PRIOR",
    "derive_calibration_update",
]
