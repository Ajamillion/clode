"""Analytical vented-box solver built on classic lumped parameters."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from math import log10, pi

from ..drivers import AIR_DENSITY, DriverParameters, PortGeometry, VentedBoxDesign
from ._utils import find_band_edges
from .sealed import P_REF


@dataclass(slots=True)
class VentedBoxResponse:
    """Frequency response summary for a vented alignment."""

    frequency_hz: list[float]
    spl_db: list[float]
    impedance_ohm: list[complex]
    cone_velocity_ms: list[float]
    cone_displacement_m: list[float]
    port_air_velocity_ms: list[float]

    def to_dict(self) -> dict[str, list[float]]:
        return {
            "frequency_hz": list(self.frequency_hz),
            "spl_db": list(self.spl_db),
            "impedance_real": [float(z.real) for z in self.impedance_ohm],
            "impedance_imag": [float(z.imag) for z in self.impedance_ohm],
            "cone_velocity_ms": list(self.cone_velocity_ms),
            "cone_displacement_m": list(self.cone_displacement_m),
            "port_velocity_ms": list(self.port_air_velocity_ms),
        }


@dataclass(slots=True)
class VentedAlignmentSummary:
    """Key figures describing the vented system alignment."""

    fb_hz: float
    f3_low_hz: float | None
    f3_high_hz: float | None
    max_spl_db: float
    max_cone_velocity_ms: float
    max_cone_displacement_m: float
    max_port_velocity_ms: float
    excursion_ratio: float | None
    excursion_headroom_db: float | None
    safe_drive_voltage_v: float | None

    def to_dict(self) -> dict[str, float | None]:
        return {
            "fb_hz": self.fb_hz,
            "f3_low_hz": self.f3_low_hz,
            "f3_high_hz": self.f3_high_hz,
            "max_spl_db": self.max_spl_db,
            "max_cone_velocity_ms": self.max_cone_velocity_ms,
            "max_cone_displacement_m": self.max_cone_displacement_m,
            "max_port_velocity_ms": self.max_port_velocity_ms,
            "excursion_ratio": self.excursion_ratio,
            "excursion_headroom_db": self.excursion_headroom_db,
            "safe_drive_voltage_v": self.safe_drive_voltage_v,
        }


class VentedBoxSolver:
    """Simplified bass-reflex solver using lumped acoustic elements."""

    def __init__(
        self,
        driver: DriverParameters,
        box: VentedBoxDesign,
        drive_voltage: float = 2.83,
    ) -> None:
        if drive_voltage <= 0:
            raise ValueError("Drive voltage must be positive")

        self.driver = driver
        self.box = box
        self.drive_voltage = drive_voltage

        self._cms = driver.compliance()
        self._cab_acoustic = box.acoustic_compliance()
        self._port: PortGeometry = box.port

        self._map = self._port.acoustic_mass()
        self._rap = self._port.series_resistance(self._cab_acoustic)
        self._rleak = box.leakage_resistance(self._cab_acoustic)

        self._rms = driver.mechanical_resistance()

    def tuning_frequency(self) -> float:
        """Return the enclosure tuning frequency (Fb)."""

        return self._port.tuning_frequency(self._cab_acoustic)

    def frequency_response(
        self,
        frequencies_hz: Iterable[float],
        mic_distance_m: float = 1.0,
    ) -> VentedBoxResponse:
        """Compute SPL, impedance, and velocity traces for the vented system."""

        if mic_distance_m <= 0:
            raise ValueError("Microphone distance must be positive")

        freq_list: list[float] = []
        spl_list: list[float] = []
        imp_list: list[complex] = []
        cone_vel_list: list[float] = []
        disp_list: list[float] = []
        port_vel_list: list[float] = []

        driver = self.driver
        sd_sq = driver.sd_m2**2
        port_area = max(self._port.area_m2(), 1e-9)

        for f in frequencies_hz:
            if f <= 0:
                continue

            omega = 2 * pi * f

            z_cab = 1.0 / (1j * omega * self._cab_acoustic)
            if self._rleak is not None:
                z_cab = 1.0 / (1.0 / z_cab + 1.0 / self._rleak)

            z_port = self._rap + 1j * omega * self._map
            z_load = 1.0 / (1.0 / z_cab + 1.0 / z_port)

            z_mech = self._rms + 1j * omega * driver.mms_kg + 1.0 / (1j * omega * self._cms)
            z_total_mech = z_mech + sd_sq * z_load

            ze = driver.re_ohm + 1j * omega * driver.le_h + (driver.bl_t_m**2) / z_total_mech

            current = self.drive_voltage / ze
            force = driver.bl_t_m * current
            cone_velocity = force / z_total_mech
            volume_velocity = cone_velocity * driver.sd_m2

            pressure = omega * AIR_DENSITY * abs(volume_velocity) / (2 * pi * mic_distance_m)
            spl = 20.0 * log10(max(pressure / P_REF, 1e-12))

            acoustic_pressure = z_load * volume_velocity
            port_volume_velocity = acoustic_pressure / z_port
            port_velocity = abs(port_volume_velocity) / port_area
            displacement = abs(cone_velocity) / max(omega, 1e-9)

            freq_list.append(f)
            spl_list.append(spl)
            imp_list.append(ze)
            cone_vel_list.append(abs(cone_velocity))
            disp_list.append(displacement)
            port_vel_list.append(port_velocity)

        return VentedBoxResponse(freq_list, spl_list, imp_list, cone_vel_list, disp_list, port_vel_list)

    def alignment_summary(self, response: VentedBoxResponse) -> VentedAlignmentSummary:
        max_spl = max(response.spl_db, default=0.0)
        f3_low, f3_high = find_band_edges(response.frequency_hz, response.spl_db, 3.0)
        max_cone_velocity = max(response.cone_velocity_ms, default=0.0)
        max_cone_displacement = max(response.cone_displacement_m, default=0.0)
        max_port_velocity = max(response.port_air_velocity_ms, default=0.0)

        excursion_ratio: float | None = None
        excursion_headroom_db: float | None = None
        safe_drive: float | None = None

        xmax = self.driver.xmax_m()
        if xmax and max_cone_displacement > 0.0:
            excursion_ratio = max_cone_displacement / xmax
            excursion_headroom_db = -20.0 * log10(excursion_ratio)
            safe_drive = self.drive_voltage / max(excursion_ratio, 1.0)

        return VentedAlignmentSummary(
            fb_hz=self.tuning_frequency(),
            f3_low_hz=f3_low,
            f3_high_hz=f3_high,
            max_spl_db=max_spl,
            max_cone_velocity_ms=max_cone_velocity,
            max_cone_displacement_m=max_cone_displacement,
            max_port_velocity_ms=max_port_velocity,
            excursion_ratio=excursion_ratio,
            excursion_headroom_db=excursion_headroom_db,
            safe_drive_voltage_v=safe_drive,
        )


__all__ = ["VentedBoxSolver", "VentedBoxResponse", "VentedAlignmentSummary"]
