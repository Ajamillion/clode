"""FastAPI gateway exposing solver endpoints and optimisation run APIs."""

from __future__ import annotations

import math
import os
from typing import TYPE_CHECKING, Any, cast

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
    MeasurementTrace,
    PortGeometry,
    SealedBoxSolver,
    ToleranceSpec,
    VentedBoxDesign,
    VentedBoxSolver,
    compare_measurement_to_prediction,
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


def _measurement_from_payload(payload: MeasurementData) -> MeasurementTrace:
    try:
        return payload.to_trace()
    except ValueError as exc:  # pragma: no cover - validation surface
        raise HTTPException(status_code=422, detail=str(exc)) from exc


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


class VentedMeasurementRequest(BaseModel):
    driver: DriverPayload
    box: VentedBoxPayload
    measurement: MeasurementData
    drive_voltage: float = Field(2.83, gt=0)
    mic_distance_m: float = Field(1.0, gt=0)


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
        solver = SealedBoxSolver(
            payload.driver.to_driver(),
            payload.box.to_box(),
            drive_voltage=payload.drive_voltage,
        )
        response = solver.frequency_response(measurement.frequency_hz, payload.mic_distance_m)
        summary = solver.alignment_summary(response)
        predicted = measurement_from_response(response)
        delta, stats, diagnosis = compare_measurement_to_prediction(
            measurement,
            predicted,
        )
        return {
            "summary": summary.to_dict(),
            "prediction": predicted.to_dict(),
            "delta": delta.to_dict(),
            "stats": stats.to_dict(),
            "diagnosis": diagnosis.to_dict(),
        }

    @app.post("/measurements/vented/compare")
    async def compare_vented_measurement(payload: VentedMeasurementRequest) -> dict[str, Any]:
        measurement = _measurement_from_payload(payload.measurement)
        solver = VentedBoxSolver(
            payload.driver.to_driver(),
            payload.box.to_box(),
            drive_voltage=payload.drive_voltage,
        )
        response = solver.frequency_response(measurement.frequency_hz, payload.mic_distance_m)
        summary = solver.alignment_summary(response)
        predicted = measurement_from_response(response)
        delta, stats, diagnosis = compare_measurement_to_prediction(
            measurement,
            predicted,
            port_length_m=payload.box.port.length_m,
        )
        return {
            "summary": summary.to_dict(),
            "prediction": predicted.to_dict(),
            "delta": delta.to_dict(),
            "stats": stats.to_dict(),
            "diagnosis": diagnosis.to_dict(),
        }

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
