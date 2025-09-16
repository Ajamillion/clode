"""Minimal FastAPI gateway exposing the sealed-box solver."""

from __future__ import annotations

from typing import Any, cast

try:  # pragma: no cover - FastAPI is optional for the unit test sweep
    from fastapi import FastAPI
    from pydantic import BaseModel, Field
except ImportError:  # pragma: no cover
    FastAPI = None
    BaseModel = object

    def Field(*_: object, **__: object) -> Any:
        return None

from spl_core import (
    BoxDesign,
    DriverParameters,
    PortGeometry,
    SealedBoxSolver,
    VentedBoxDesign,
    VentedBoxSolver,
)

app: Any

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
        data: dict[str, float]
        if hasattr(self, "model_dump"):
            data = cast(dict[str, float], self.model_dump())
        else:  # pragma: no cover - fallback for type checkers
            data = dict(self.__dict__)
        return DriverParameters(**data)


class BoxPayload(BaseModel):
    volume_l: float = Field(..., gt=0)
    leakage_q: float = Field(15.0, gt=0)

    def to_box(self) -> BoxDesign:
        data: dict[str, float]
        if hasattr(self, "model_dump"):
            data = cast(dict[str, float], self.model_dump())
        else:  # pragma: no cover
            data = dict(self.__dict__)
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
        data: dict[str, Any]
        if hasattr(self, "model_dump"):
            data = cast(dict[str, Any], self.model_dump())
        else:  # pragma: no cover
            data = dict(self.__dict__)
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


if FastAPI is not None:  # pragma: no branch
    app = FastAPI(title="Bagger-SPL Gateway", version="0.1.0")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

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
]
