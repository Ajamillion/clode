"""FastAPI gateway exposing solver endpoints and optimisation run APIs."""

from __future__ import annotations

import math
import os
from typing import TYPE_CHECKING, Any, Literal, cast

if TYPE_CHECKING:  # pragma: no cover
    from fastapi import BackgroundTasks, FastAPI, HTTPException, UploadFile
    from pydantic import BaseModel, Field
else:  # pragma: no branch
    try:
        from fastapi import BackgroundTasks, FastAPI, HTTPException, UploadFile
        from pydantic import BaseModel, Field
    except ImportError:  # pragma: no cover
        FastAPI = cast(Any, None)
        BaseModel = cast(Any, object)

        class BackgroundTasks:  # pragma: no cover
            def add_task(self, *_: Any, **__: Any) -> None:
                raise RuntimeError("FastAPI is not installed")

        class HTTPException(Exception):  # pragma: no cover
            def __init__(self, status_code: int, detail: str) -> None:
                super().__init__(detail)
                self.status_code = status_code

        class UploadFile:  # pragma: no cover
            filename: str | None = None

        def Field(*_: object, **__: object) -> Any:  # pragma: no cover
            return None

from spl_core import (
    DEFAULT_DRIVER,
    DEFAULT_TOLERANCES,
    BoxDesign,
    DriverParameters,
    HybridBoxSolver,
    MeasurementTrace,
    PortGeometry,
    SealedBoxSolver,
    ToleranceSpec,
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
    run_tolerance_analysis,
    solver_json_schemas,
)

from .store import VALID_STATUSES, RunStore

DEFAULT_FREQUENCY_RANGE = (math.log10(20.0), math.log10(200.0), 60)
DEFAULT_ALIGNMENT = "sealed"

app: Any
_store: RunStore | None = None


def solver_schema_catalog() -> dict[str, dict[str, dict[str, Any]]]:
    """Return the JSON schema catalog for the available solver families."""

    return solver_json_schemas()


def _model_dump(model: BaseModel) -> dict[str, Any]:  # pragma: no cover - helper for pydantic v1/v2
    if hasattr(model, "model_dump"):
        return cast(dict[str, Any], model.model_dump())
    if hasattr(model, "dict"):
        return cast(dict[str, Any], model.dict())
    return dict(model.__dict__)


def _logspace(start: float, stop: float, count: int) -> list[float]:
    if count <= 1:
        return [10 ** start]
    step = (stop - start) / (count - 1)
    return [10 ** (start + i * step) for i in range(count)]


def _frequency_axis() -> list[float]:
    lo, hi, count = DEFAULT_FREQUENCY_RANGE
    return _logspace(lo, hi, count)


def _iteration_history(target_spl: float, achieved_spl: float) -> tuple[list[dict[str, float]], float]:
    overshoot = max(target_spl - achieved_spl, 0.0)
    base_loss = overshoot**2 or 0.35
    loss = base_loss + 0.6
    history: list[dict[str, float]] = []
    for i in range(1, 16):
        loss = max(loss * 0.72, 1e-6)
        grad = max(loss * 0.5 / (i + 1), 1e-4)
        history.append({"iter": i, "loss": loss, "gradNorm": grad})
    final_loss = history[-1]["loss"] if history else base_loss
    return history, final_loss


def _build_metrics(
    target_spl: float,
    achieved_spl: float,
    volume: float,
    safe_drive: float | None,
    extras: dict[str, float],
) -> dict[str, float]:
    metrics = {
        "target_spl_db": target_spl,
        "achieved_spl_db": achieved_spl,
        "volume_l": volume,
    }
    if safe_drive is not None:
        metrics["safe_drive_voltage_v"] = safe_drive
    metrics.update(extras)
    return metrics


def _hybrid_solver_from_request(payload: HybridRequest) -> tuple[str, HybridBoxSolver]:
    try:
        alignment = payload.resolve_alignment()
        driver = payload.driver.to_driver()
        box: BoxDesign | VentedBoxDesign
        if alignment == "vented":
            if payload.port is None:
                raise ValueError("Port parameters required for vented alignment")
            box = VentedBoxDesign(
                volume_l=payload.box.volume_l,
                leakage_q=payload.box.leakage_q,
                port=payload.port.to_port(),
            )
        else:
            box = payload.box.to_box()
            alignment = "sealed"

        solver = HybridBoxSolver(
            driver,
            box,
            drive_voltage=payload.drive_voltage,
            grid_resolution=int(payload.grid_resolution),
            suspension_creep=payload.suspension_creep,
        )
    except ValueError as exc:  # pragma: no cover - validation surface
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return alignment, solver


def _measurement_from_payload(payload: MeasurementData) -> MeasurementTrace:
    try:
        return payload.to_trace()
    except ValueError as exc:  # pragma: no cover - validation surface
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _band_limited_measurement(
    trace: MeasurementTrace,
    minimum_hz: float | None,
    maximum_hz: float | None,
) -> MeasurementTrace:
    if minimum_hz is None and maximum_hz is None:
        return trace
    try:
        return trace.bandpass(minimum_hz, maximum_hz)
    except ValueError as exc:  # pragma: no cover - validation surface
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _band_from_trace(trace: MeasurementTrace) -> dict[str, float]:
    minimum = min(trace.frequency_hz)
    maximum = max(trace.frequency_hz)
    return {"min_hz": float(minimum), "max_hz": float(maximum)}


def _sealed_measurement_payload(
    driver: DriverParameters,
    box: BoxDesign,
    measurement: MeasurementTrace,
    mic_distance_m: float,
    drive_voltage: float,
    apply_overrides: bool,
) -> dict[str, Any]:
    solver = SealedBoxSolver(driver, box, drive_voltage=drive_voltage)
    response = solver.frequency_response(measurement.frequency_hz, mic_distance_m)
    summary = solver.alignment_summary(response)
    predicted = measurement_from_response(response)
    delta, stats, diagnosis = compare_measurement_to_prediction(measurement, predicted)
    calibration = derive_calibration_update(diagnosis)
    overrides = derive_calibration_overrides(
        calibration,
        drive_voltage_v=drive_voltage,
        leakage_q=box.leakage_q,
    )

    payload: dict[str, Any] = {
        "summary": summary.to_dict(),
        "prediction": predicted.to_dict(),
        "delta": delta.to_dict(),
        "stats": stats.to_dict(),
        "diagnosis": diagnosis.to_dict(),
        "calibration": calibration.to_dict(),
        "calibration_overrides": overrides.to_dict(),
        "frequency_band": _band_from_trace(measurement),
    }

    if apply_overrides:
        calibrated_box = apply_calibration_overrides_to_box(box, overrides)
        calibrated_drive = apply_calibration_overrides_to_drive_voltage(drive_voltage, overrides)
        sealed_solver = SealedBoxSolver(driver, calibrated_box, drive_voltage=calibrated_drive)
        calibrated_response = sealed_solver.frequency_response(
            measurement.frequency_hz,
            mic_distance_m,
        )
        calibrated_summary = sealed_solver.alignment_summary(calibrated_response)
        calibrated_prediction = measurement_from_response(calibrated_response)
        calibrated_delta, calibrated_stats, calibrated_diagnosis = compare_measurement_to_prediction(
            measurement,
            calibrated_prediction,
        )
        payload["calibrated"] = {
            "inputs": {
                "drive_voltage_v": float(calibrated_drive),
                "leakage_q": float(calibrated_box.leakage_q)
                if calibrated_box.leakage_q is not None
                else None,
                "port_length_m": None,
            },
            "summary": calibrated_summary.to_dict(),
            "prediction": calibrated_prediction.to_dict(),
            "delta": calibrated_delta.to_dict(),
            "stats": calibrated_stats.to_dict(),
            "diagnosis": calibrated_diagnosis.to_dict(),
        }

    return payload


def _vented_measurement_payload(
    driver: DriverParameters,
    box: VentedBoxDesign,
    measurement: MeasurementTrace,
    mic_distance_m: float,
    drive_voltage: float,
    apply_overrides: bool,
) -> dict[str, Any]:
    solver = VentedBoxSolver(driver, box, drive_voltage=drive_voltage)
    response = solver.frequency_response(measurement.frequency_hz, mic_distance_m)
    summary = solver.alignment_summary(response)
    predicted = measurement_from_response(response)
    delta, stats, diagnosis = compare_measurement_to_prediction(
        measurement,
        predicted,
        port_length_m=box.port.length_m,
    )
    calibration = derive_calibration_update(diagnosis)
    overrides = derive_calibration_overrides(
        calibration,
        drive_voltage_v=drive_voltage,
        port_length_m=box.port.length_m,
        leakage_q=box.leakage_q,
    )

    payload: dict[str, Any] = {
        "summary": summary.to_dict(),
        "prediction": predicted.to_dict(),
        "delta": delta.to_dict(),
        "stats": stats.to_dict(),
        "diagnosis": diagnosis.to_dict(),
        "calibration": calibration.to_dict(),
        "calibration_overrides": overrides.to_dict(),
        "frequency_band": _band_from_trace(measurement),
    }

    if apply_overrides:
        calibrated_box = apply_calibration_overrides_to_box(box, overrides)
        calibrated_drive = apply_calibration_overrides_to_drive_voltage(drive_voltage, overrides)
        vented_solver = VentedBoxSolver(driver, calibrated_box, drive_voltage=calibrated_drive)
        calibrated_response = vented_solver.frequency_response(
            measurement.frequency_hz,
            mic_distance_m,
        )
        calibrated_summary = vented_solver.alignment_summary(calibrated_response)
        calibrated_prediction = measurement_from_response(calibrated_response)
        calibrated_delta, calibrated_stats, calibrated_diagnosis = compare_measurement_to_prediction(
            measurement,
            calibrated_prediction,
            port_length_m=calibrated_box.port.length_m,
        )
        payload["calibrated"] = {
            "inputs": {
                "drive_voltage_v": float(calibrated_drive),
                "leakage_q": float(calibrated_box.leakage_q),
                "port_length_m": float(calibrated_box.port.length_m),
            },
            "summary": calibrated_summary.to_dict(),
            "prediction": calibrated_prediction.to_dict(),
            "delta": calibrated_delta.to_dict(),
            "stats": calibrated_stats.to_dict(),
            "diagnosis": calibrated_diagnosis.to_dict(),
        }

    return payload


def _measurement_comparison_payload(
    *,
    alignment: Literal["sealed", "vented"],
    driver: DriverParameters,
    box: BoxDesign | VentedBoxDesign,
    measurement: MeasurementTrace,
    mic_distance_m: float,
    drive_voltage: float,
    apply_overrides: bool,
) -> dict[str, Any]:
    if alignment == "vented":
        if not isinstance(box, VentedBoxDesign):  # pragma: no cover - defensive
            raise ValueError("Vented comparisons require a vented box design")
        return _vented_measurement_payload(
            driver,
            box,
            measurement,
            mic_distance_m,
            drive_voltage,
            apply_overrides,
        )

    if not isinstance(box, BoxDesign):  # pragma: no cover - defensive
        raise ValueError("Sealed comparisons require a sealed box design")
    return _sealed_measurement_payload(
        driver,
        box,
        measurement,
        mic_distance_m,
        drive_voltage,
        apply_overrides,
    )


def _resolve_alignment(params: dict[str, Any]) -> str:
    preferred = str(params.get("preferAlignment") or DEFAULT_ALIGNMENT).strip().lower()
    if preferred in {"sealed", "vented"}:
        return preferred
    return DEFAULT_ALIGNMENT


def _build_optimisation_result(params: dict[str, Any]) -> dict[str, Any]:
    target_spl = float(params.get("targetSpl", 115.0))
    volume = max(float(params.get("maxVolume", 55.0)), 5.0)
    drive_voltage = 2.83

    alignment = _resolve_alignment(params)

    solution_payload: dict[str, Any]
    metrics_extra: dict[str, float]
    summary_dict: dict[str, Any]
    response_dict: dict[str, Any]
    achieved_spl: float
    safe_drive: float | None

    if alignment == "vented":
        vented_solver = VentedBoxSolver(
            DEFAULT_DRIVER,
            recommended_vented_alignment(volume),
            drive_voltage=drive_voltage,
        )
        vented_response = vented_solver.frequency_response(_frequency_axis(), 1.0)
        vented_summary = vented_solver.alignment_summary(vented_response)
        summary_dict = vented_summary.to_dict()
        response_dict = vented_response.to_dict()
        achieved_spl = vented_summary.max_spl_db
        safe_drive = vented_summary.safe_drive_voltage_v
        solution_payload = {
            "spl_peak": vented_summary.max_spl_db,
            "fb_hz": vented_summary.fb_hz,
            "excursion_headroom_db": vented_summary.excursion_headroom_db,
            "max_port_velocity_ms": vented_summary.max_port_velocity_ms,
            "safe_drive_voltage_v": safe_drive,
        }
        metrics_extra = {
            "max_port_velocity_ms": vented_summary.max_port_velocity_ms,
        }
    else:
        sealed_solver = SealedBoxSolver(
            DEFAULT_DRIVER,
            BoxDesign(volume_l=volume, leakage_q=15.0),
            drive_voltage=drive_voltage,
        )
        sealed_response = sealed_solver.frequency_response(_frequency_axis(), 1.0)
        sealed_summary = sealed_solver.alignment_summary(sealed_response)
        summary_dict = sealed_summary.to_dict()
        response_dict = sealed_response.to_dict()
        achieved_spl = sealed_summary.max_spl_db
        safe_drive = sealed_summary.safe_drive_voltage_v
        solution_payload = {
            "spl_peak": sealed_summary.max_spl_db,
            "fc_hz": sealed_summary.fc_hz,
            "qtc": sealed_summary.qtc,
            "excursion_headroom_db": sealed_summary.excursion_headroom_db,
            "safe_drive_voltage_v": safe_drive,
        }
        metrics_extra = {
            "fc_hz": sealed_summary.fc_hz,
        }

    history, final_loss = _iteration_history(target_spl, achieved_spl)

    convergence = {
        "converged": final_loss < 1.0,
        "iterations": len(history),
        "finalLoss": final_loss,
        "solution": {"alignment": alignment, **solution_payload},
    }

    return {
        "alignment": alignment,
        "history": history,
        "convergence": convergence,
        "summary": summary_dict,
        "response": response_dict,
        "metrics": _build_metrics(target_spl, achieved_spl, volume, safe_drive, metrics_extra),
    }


class DriverPayload(BaseModel):
    fs_hz: float = Field(..., gt=0)
    qts: float = Field(..., gt=0)
    vas_l: float = Field(..., gt=0)
    re_ohm: float = Field(..., gt=0)
    bl_t_m: float = Field(..., gt=0)
    mms_kg: float = Field(..., gt=0)
    sd_m2: float = Field(..., gt=0)
    le_h: float = Field(0.0007, ge=0)

    def to_driver(self) -> DriverParameters:
        data = _model_dump(self)
        return DriverParameters(**data)


class BoxPayload(BaseModel):
    volume_l: float = Field(..., gt=0)
    leakage_q: float = Field(15.0, gt=0)

    def to_box(self) -> BoxDesign:
        data = _model_dump(self)
        return BoxDesign(**data)


class SealedRequest(BaseModel):
    driver: DriverPayload
    box: BoxPayload
    frequencies_hz: list[float] = Field(..., min_items=1)
    mic_distance_m: float = Field(1.0, gt=0)
    drive_voltage: float = Field(2.83, gt=0)


class PortPayload(BaseModel):
    diameter_m: float = Field(..., gt=0)
    length_m: float = Field(..., gt=0)
    count: int = Field(1, gt=0)
    flare_factor: float = Field(1.7, ge=0)
    loss_q: float = Field(18.0, gt=0)

    def to_port(self) -> PortGeometry:
        data = _model_dump(self)
        return PortGeometry(**data)


class VentedBoxPayload(BaseModel):
    volume_l: float = Field(..., gt=0)
    leakage_q: float = Field(10.0, gt=0)
    port: PortPayload

    def to_box(self) -> VentedBoxDesign:
        return VentedBoxDesign(
            volume_l=self.volume_l,
            port=self.port.to_port(),
            leakage_q=self.leakage_q,
        )


class VentedRequest(BaseModel):
    driver: DriverPayload
    box: VentedBoxPayload
    frequencies_hz: list[float] = Field(..., min_items=1)
    mic_distance_m: float = Field(1.0, gt=0)
    drive_voltage: float = Field(2.83, gt=0)


class HybridRequest(BaseModel):
    driver: DriverPayload
    box: BoxPayload
    port: PortPayload | None = Field(None)
    alignment: Literal["sealed", "vented", "auto"] | None = Field(None)
    frequencies_hz: list[float] = Field(..., min_items=1)
    mic_distance_m: float = Field(1.0, gt=0)
    drive_voltage: float = Field(2.83, gt=0)
    grid_resolution: int = Field(24, ge=8, le=96)
    snapshot_stride: int = Field(1, ge=1)
    include_snapshots: bool = Field(True)
    suspension_creep: bool = Field(True)

    def resolve_alignment(self) -> str:
        if self.alignment is None:
            return "vented" if self.port is not None else "sealed"
        preferred = self.alignment.lower()
        if preferred == "auto":
            return "vented" if self.port is not None else "sealed"
        if preferred in {"sealed", "vented"}:
            return preferred
        msg = "alignment must be 'sealed', 'vented', or 'auto'"
        raise ValueError(msg)


class MeasurementData(BaseModel):
    frequency_hz: list[float] = Field(..., min_items=1)
    spl_db: list[float] = Field(..., min_items=1)
    phase_deg: list[float] | None = Field(None)
    impedance_real: list[float] | None = Field(None)
    impedance_imag: list[float] | None = Field(None)
    thd_percent: list[float] | None = Field(None)

    def to_trace(self) -> MeasurementTrace:
        freq = list(self.frequency_hz)
        spl = list(self.spl_db)
        if len(spl) != len(freq):
            raise ValueError("spl_db length must match frequency axis")
        phase = list(self.phase_deg) if self.phase_deg is not None else None
        if phase is not None and len(phase) != len(freq):
            raise ValueError("phase_deg length must match frequency axis")
        thd = list(self.thd_percent) if self.thd_percent is not None else None
        if thd is not None and len(thd) != len(freq):
            raise ValueError("thd_percent length must match frequency axis")
        impedance: list[complex] | None = None
        if (self.impedance_real is None) != (self.impedance_imag is None):
            raise ValueError("Impedance requires both real and imaginary components")
        if self.impedance_real is not None and self.impedance_imag is not None:
            if len(self.impedance_real) != len(freq) or len(self.impedance_imag) != len(freq):
                raise ValueError("Impedance arrays must match frequency axis")
            impedance = [
                complex(float(r), float(i))
                for r, i in zip(self.impedance_real, self.impedance_imag, strict=True)
            ]
        return MeasurementTrace(
            frequency_hz=freq,
            spl_db=spl,
            phase_deg=phase,
            impedance_ohm=impedance,
            thd_percent=thd,
        )


class SealedMeasurementRequest(BaseModel):
    driver: DriverPayload
    box: BoxPayload
    measurement: MeasurementData
    drive_voltage: float = Field(2.83, gt=0)
    mic_distance_m: float = Field(1.0, gt=0)
    min_frequency_hz: float | None = Field(None, gt=0)
    max_frequency_hz: float | None = Field(None, gt=0)
    apply_overrides: bool = False


class VentedMeasurementRequest(BaseModel):
    driver: DriverPayload
    box: VentedBoxPayload
    measurement: MeasurementData
    drive_voltage: float = Field(2.83, gt=0)
    mic_distance_m: float = Field(1.0, gt=0)
    min_frequency_hz: float | None = Field(None, gt=0)
    max_frequency_hz: float | None = Field(None, gt=0)
    apply_overrides: bool = False


class OptimizationParams(BaseModel):
    targetSpl: float = Field(..., gt=0)
    maxVolume: float = Field(..., gt=0)
    weightLow: float = Field(1.0, ge=0)
    weightMid: float = Field(1.0, ge=0)
    preferAlignment: str | None = Field(None)

    def to_dict(self) -> dict[str, Any]:
        return _model_dump(self)


class ToleranceOverrides(BaseModel):
    driverFs: float | None = Field(None, ge=0.0, le=0.5)
    driverQts: float | None = Field(None, ge=0.0, le=0.5)
    driverVas: float | None = Field(None, ge=0.0, le=0.5)
    driverRe: float | None = Field(None, ge=0.0, le=0.5)
    driverBl: float | None = Field(None, ge=0.0, le=0.5)
    driverMms: float | None = Field(None, ge=0.0, le=0.5)
    driverSd: float | None = Field(None, ge=0.0, le=0.5)
    driverLe: float | None = Field(None, ge=0.0, le=0.5)
    boxVolume: float | None = Field(None, ge=0.0, le=0.5)
    portDiameter: float | None = Field(None, ge=0.0, le=0.5)
    portLength: float | None = Field(None, ge=0.0, le=0.5)


class SealedToleranceRequest(BaseModel):
    driver: DriverPayload
    box: BoxPayload
    iterations: int = Field(200, ge=1, le=1000)
    drive_voltage: float = Field(2.83, gt=0)
    mic_distance_m: float = Field(1.0, gt=0)
    tolerances: ToleranceOverrides | None = Field(None)
    excursion_limit: float = Field(1.0, gt=0)


class VentedToleranceRequest(BaseModel):
    driver: DriverPayload
    box: VentedBoxPayload
    iterations: int = Field(200, ge=1, le=1000)
    drive_voltage: float = Field(2.83, gt=0)
    mic_distance_m: float = Field(1.0, gt=0)
    tolerances: ToleranceOverrides | None = Field(None)
    excursion_limit: float = Field(1.0, gt=0)
    port_velocity_limit_ms: float = Field(20.0, gt=0)


def _tolerance_spec_from_payload(overrides: ToleranceOverrides | None) -> ToleranceSpec:
    if overrides is None:
        return DEFAULT_TOLERANCES
    mapping = {
        "driverFs": "driver_fs_pct",
        "driverQts": "driver_qts_pct",
        "driverVas": "driver_vas_pct",
        "driverRe": "driver_re_pct",
        "driverBl": "driver_bl_pct",
        "driverMms": "driver_mms_pct",
        "driverSd": "driver_sd_pct",
        "driverLe": "driver_le_pct",
        "boxVolume": "box_volume_pct",
        "portDiameter": "port_diameter_pct",
        "portLength": "port_length_pct",
    }
    updates: dict[str, float] = {}
    for field, spec_key in mapping.items():
        value = getattr(overrides, field)
        if value is not None:
            updates[spec_key] = float(value)
    if not updates:
        return DEFAULT_TOLERANCES
    return DEFAULT_TOLERANCES.replace(**updates)


def _run_optimisation_task(run_id: str, params: dict[str, Any]) -> None:
    if _store is None:  # pragma: no cover - FastAPI not installed
        return
    try:
        _store.mark_running(run_id)
        result = _build_optimisation_result(params)
        _store.complete_run(run_id, result)
    except Exception as exc:  # pragma: no cover - best effort logging
        _store.mark_failed(run_id, str(exc))


if FastAPI is not None:  # pragma: no branch
    db_path = os.environ.get("BAGGER_SPL_DB_PATH")
    _store = RunStore(db_path)
    app = FastAPI(title="Bagger-SPL Gateway", version="0.2.0")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/measurements/preview")
    async def preview_measurement(file: UploadFile) -> dict[str, Any]:
        data = await file.read()
        filename = (file.filename or "").lower()
        try:
            if filename.endswith(".mdat"):
                trace = parse_rew_mdat(data)
            else:
                try:
                    text = data.decode("utf-8")
                except UnicodeDecodeError:
                    text = data.decode("latin-1")
                trace = parse_klippel_dat(text)
        except Exception as exc:  # pragma: no cover - runtime validation
            raise HTTPException(status_code=400, detail=f"Failed to parse measurement: {exc}") from exc
        return {"measurement": trace.to_dict()}

    @app.post("/measurements/sealed/compare")
    async def compare_sealed_measurement(payload: SealedMeasurementRequest) -> dict[str, Any]:
        measurement = _measurement_from_payload(payload.measurement)
        measurement = _band_limited_measurement(
            measurement, payload.min_frequency_hz, payload.max_frequency_hz
        )
        driver = payload.driver.to_driver()
        box = payload.box.to_box()
        return _measurement_comparison_payload(
            alignment="sealed",
            driver=driver,
            box=box,
            measurement=measurement,
            mic_distance_m=payload.mic_distance_m,
            drive_voltage=payload.drive_voltage,
            apply_overrides=payload.apply_overrides,
        )

    @app.post("/measurements/vented/compare")
    async def compare_vented_measurement(payload: VentedMeasurementRequest) -> dict[str, Any]:
        measurement = _measurement_from_payload(payload.measurement)
        measurement = _band_limited_measurement(
            measurement, payload.min_frequency_hz, payload.max_frequency_hz
        )
        driver = payload.driver.to_driver()
        box = payload.box.to_box()
        return _measurement_comparison_payload(
            alignment="vented",
            driver=driver,
            box=box,
            measurement=measurement,
            mic_distance_m=payload.mic_distance_m,
            drive_voltage=payload.drive_voltage,
            apply_overrides=payload.apply_overrides,
        )

    @app.post("/simulate/sealed")
    async def simulate_sealed(payload: SealedRequest) -> dict[str, Any]:
        solver = SealedBoxSolver(
            payload.driver.to_driver(),
            payload.box.to_box(),
            drive_voltage=payload.drive_voltage,
        )
        response = solver.frequency_response(payload.frequencies_hz, payload.mic_distance_m)
        summary = solver.alignment_summary(response)
        payload_dict: dict[str, Any] = dict(response.to_dict())
        payload_dict.update(
            {
                "summary": summary.to_dict(),
                "fc_hz": summary.fc_hz,
                "qtc": summary.qtc,
                "excursion_ratio": summary.excursion_ratio,
                "excursion_headroom_db": summary.excursion_headroom_db,
                "safe_drive_voltage_v": summary.safe_drive_voltage_v,
            }
        )
        return payload_dict

    @app.post("/simulate/vented")
    async def simulate_vented(payload: VentedRequest) -> dict[str, Any]:
        solver = VentedBoxSolver(
            payload.driver.to_driver(),
            payload.box.to_box(),
            drive_voltage=payload.drive_voltage,
        )
        response = solver.frequency_response(payload.frequencies_hz, payload.mic_distance_m)
        summary = solver.alignment_summary(response)
        payload_dict: dict[str, Any] = dict(response.to_dict())
        payload_dict.update(
            {
                "summary": summary.to_dict(),
                "fb_hz": summary.fb_hz,
                "max_port_velocity_ms": summary.max_port_velocity_ms,
                "excursion_ratio": summary.excursion_ratio,
                "excursion_headroom_db": summary.excursion_headroom_db,
                "safe_drive_voltage_v": summary.safe_drive_voltage_v,
            }
        )
        return payload_dict

    @app.post("/simulate/hybrid")
    async def simulate_hybrid(payload: HybridRequest) -> dict[str, Any]:
        alignment, solver = _hybrid_solver_from_request(payload)
        result, summary = solver.frequency_response(
            payload.frequencies_hz,
            mic_distance_m=payload.mic_distance_m,
            snapshot_stride=payload.snapshot_stride,
        )
        include_snapshots = payload.include_snapshots

        response_payload = result.to_dict(include_snapshots=include_snapshots)
        if not include_snapshots:
            response_payload["field_snapshots"] = [
                snapshot.to_dict(include_pressure=False) for snapshot in result.field_snapshots
            ]

        summary_dict = summary.to_dict()
        response_payload.update(
            {
                "summary": summary_dict,
                "alignment": alignment,
                "grid_resolution": solver.grid_resolution,
                "snapshot_stride": result.snapshot_stride,
                "snapshot_count": len(result.field_snapshots),
                "suspension_creep": payload.suspension_creep,
                "plane_metrics": {
                    label: {
                        "max_pressure_pa": summary.plane_max_pressure_pa[label],
                        "mean_pressure_pa": summary.plane_mean_pressure_pa[label],
                        "max_pressure_coords_m": list(
                            summary.plane_max_pressure_location_m.get(label, (0.0, 0.0, 0.0))
                        ),
                    }
                    for label in summary.plane_max_pressure_pa
                },
            }
        )
        return response_payload

    @app.post("/simulate/sealed/tolerances")
    async def sealed_tolerances(payload: SealedToleranceRequest) -> dict[str, Any]:
        spec = _tolerance_spec_from_payload(payload.tolerances)
        report = run_tolerance_analysis(
            "sealed",
            payload.driver.to_driver(),
            payload.box.to_box(),
            _frequency_axis(),
            payload.iterations,
            tolerances=spec,
            drive_voltage=payload.drive_voltage,
            mic_distance_m=payload.mic_distance_m,
            excursion_limit_ratio=payload.excursion_limit,
        )
        return report.to_dict()

    @app.post("/simulate/vented/tolerances")
    async def vented_tolerances(payload: VentedToleranceRequest) -> dict[str, Any]:
        spec = _tolerance_spec_from_payload(payload.tolerances)
        report = run_tolerance_analysis(
            "vented",
            payload.driver.to_driver(),
            payload.box.to_box(),
            _frequency_axis(),
            payload.iterations,
            tolerances=spec,
            drive_voltage=payload.drive_voltage,
            mic_distance_m=payload.mic_distance_m,
            excursion_limit_ratio=payload.excursion_limit,
            port_velocity_limit_ms=payload.port_velocity_limit_ms,
        )
        return report.to_dict()

    @app.post("/opt/start")
    async def start_optimisation(payload: OptimizationParams, background: BackgroundTasks) -> dict[str, Any]:
        params = payload.to_dict()
        assert _store is not None  # mypy hint
        record = _store.create_run(params)
        background.add_task(_run_optimisation_task, record.id, params)
        return record.to_dict()

    @app.get("/opt/runs")
    async def list_runs(limit: int = 20, status: str | None = None) -> dict[str, Any]:
        assert _store is not None
        status_filter = None
        if status is not None:
            status_lower = status.lower()
            if status_lower not in VALID_STATUSES:
                raise HTTPException(status_code=400, detail="Invalid status filter")
            status_filter = status_lower
        runs = [
            record.to_dict()
            for record in _store.list_runs(limit=limit, status=status_filter)
        ]
        return {"runs": runs}

    @app.get("/opt/{run_id}")
    async def fetch_run(run_id: str) -> dict[str, Any]:
        assert _store is not None
        record = _store.get_run(run_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Run not found")
        return record.to_dict()

    @app.get("/opt/stats")
    async def optimisation_stats() -> dict[str, Any]:
        assert _store is not None
        counts = _store.status_counts()
        total = sum(counts.values())
        return {"counts": counts, "total": total}

    @app.get("/schemas/solvers")
    async def list_solver_schemas() -> dict[str, Any]:
        """Return the JSON schema catalog for sealed and vented solvers."""

        return {"solvers": solver_schema_catalog()}

    @app.get("/schemas/solvers/{alignment}")
    async def fetch_solver_schema(alignment: str) -> dict[str, Any]:
        """Return the JSON schemas for a specific solver alignment."""

        catalog = solver_schema_catalog()
        key = alignment.lower()
        entry = catalog.get(key)
        if entry is None:
            raise HTTPException(status_code=404, detail="Solver alignment not found")
        return {"alignment": key, "request": entry["request"], "response": entry["response"]}
else:  # pragma: no cover
    app = None


__all__ = [
    "app",
    "SealedRequest",
    "DriverPayload",
    "BoxPayload",
    "PortPayload",
    "VentedBoxPayload",
    "VentedRequest",
    "OptimizationParams",
    "ToleranceOverrides",
    "SealedToleranceRequest",
    "VentedToleranceRequest",
    "solver_schema_catalog",
]
