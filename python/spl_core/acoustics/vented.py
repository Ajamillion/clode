"""Analytical vented-box solver built on classic lumped parameters."""

from __future__ import annotations

from dataclasses import dataclass
from math import log10, pi
from typing import Iterable, List

from ..drivers import AIR_DENSITY, DriverParameters, PortGeometry, VentedBoxDesign
from .sealed import P_REF


@dataclass(slots=True)
class VentedBoxResponse:
    """Frequency response summary for a vented alignment."""

    frequency_hz: List[float]
    spl_db: List[float]
    impedance_ohm: List[complex]
    cone_velocity_ms: List[float]
    port_air_velocity_ms: List[float]


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

        freq_list: List[float] = []
        spl_list: List[float] = []
        imp_list: List[complex] = []
        cone_vel_list: List[float] = []
        port_vel_list: List[float] = []

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

            freq_list.append(f)
            spl_list.append(spl)
            imp_list.append(ze)
            cone_vel_list.append(abs(cone_velocity))
            port_vel_list.append(port_velocity)

        return VentedBoxResponse(freq_list, spl_list, imp_list, cone_vel_list, port_vel_list)


__all__ = ["VentedBoxSolver", "VentedBoxResponse"]
