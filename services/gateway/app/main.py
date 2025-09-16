"""Minimal FastAPI gateway exposing the sealed-box solver."""

from __future__ import annotations

from typing import Dict, List

try:  # pragma: no cover - FastAPI is optional for the unit test sweep
    from fastapi import FastAPI
    from pydantic import BaseModel, Field
except ImportError:  # pragma: no cover
    FastAPI = None  # type: ignore
    BaseModel = object  # type: ignore
    Field = lambda *_, **__: None  # type: ignore

from spl_core import BoxDesign, DriverParameters, SealedBoxSolver


class DriverPayload(BaseModel):  # type: ignore[misc]
    fs_hz: float = Field(..., gt=0)
    qts: float = Field(..., gt=0)
    vas_l: float = Field(..., gt=0)
    re_ohm: float = Field(..., gt=0)
    bl_t_m: float = Field(..., gt=0)
    mms_kg: float = Field(..., gt=0)
    sd_m2: float = Field(..., gt=0)
    le_h: float = Field(0.0007, ge=0)

    def to_driver(self) -> DriverParameters:
        data: Dict[str, float]
        if hasattr(self, "model_dump"):
            data = self.model_dump()  # type: ignore[assignment]
        else:  # pragma: no cover - fallback for type checkers
            data = dict(self.__dict__)
        return DriverParameters(**data)  # type: ignore[arg-type]


class BoxPayload(BaseModel):  # type: ignore[misc]
    volume_l: float = Field(..., gt=0)
    leakage_q: float = Field(15.0, gt=0)

    def to_box(self) -> BoxDesign:
        data: Dict[str, float]
        if hasattr(self, "model_dump"):
            data = self.model_dump()  # type: ignore[assignment]
        else:  # pragma: no cover
            data = dict(self.__dict__)
        return BoxDesign(**data)  # type: ignore[arg-type]


class SealedRequest(BaseModel):  # type: ignore[misc]
    driver: DriverPayload
    box: BoxPayload
    frequencies_hz: List[float] = Field(..., min_items=1)
    mic_distance_m: float = Field(1.0, gt=0)
    drive_voltage: float = Field(2.83, gt=0)


if FastAPI is not None:  # pragma: no branch
    app = FastAPI(title="Bagger-SPL Gateway", version="0.1.0")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/simulate/sealed")
    async def simulate_sealed(payload: SealedRequest) -> dict[str, List[float]]:
        solver = SealedBoxSolver(
            payload.driver.to_driver(),
            payload.box.to_box(),
            drive_voltage=payload.drive_voltage,
        )
        response = solver.frequency_response(payload.frequencies_hz, payload.mic_distance_m)
        return {
            "frequency_hz": response.frequency_hz,
            "spl_db": response.spl_db,
            "impedance_real": [float(z.real) for z in response.impedance_ohm],
            "impedance_imag": [float(z.imag) for z in response.impedance_ohm],
            "cone_velocity_ms": response.cone_velocity_ms,
            "fc_hz": solver.system_resonance(),
            "qtc": solver.system_qtc(),
        }
else:  # pragma: no cover
    app = None  # type: ignore


__all__ = ["app", "SealedRequest", "DriverPayload", "BoxPayload"]
