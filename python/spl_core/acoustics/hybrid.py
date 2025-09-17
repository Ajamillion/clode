"""Reduced-order hybrid solver that sketches FEM/BEM behaviour.

The implementation intentionally avoids external numerical dependencies so the
module can run inside lightweight development environments.  It blends the
existing lumped-parameter sealed/vented models with a coarse interior field
estimator that mimics what an eventual FEM/BEM adaptor would expose.  The
result provides richer telemetry – pressure maps, port compression estimates,
and Mach numbers – that downstream services can consume while the full high-
fidelity pipeline is still under construction.
"""

from __future__ import annotations

import cmath
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from math import exp, log10, pi, sqrt

from ..drivers import (
    AIR_DENSITY,
    SPEED_OF_SOUND,
    BoxDesign,
    DriverParameters,
    PortGeometry,
    VentedBoxDesign,
)
from .sealed import P_REF


@dataclass(slots=True)
class HybridFieldSnapshot:
    """Snapshot of the interior pressure field at a single frequency."""

    frequency_hz: float
    grid_resolution: int
    pressure_rms_pa: list[float]
    max_pressure_pa: float
    cone_velocity_ms: float
    port_velocity_ms: float | None
    port_compression_ratio: float | None
    port_mach: float | None

    def pressure_at(self, x_index: int, y_index: int) -> float:
        """Return the pressure value at the requested grid coordinate."""

        if not (0 <= x_index < self.grid_resolution):
            msg = f"x index {x_index} outside 0..{self.grid_resolution - 1}"
            raise IndexError(msg)
        if not (0 <= y_index < self.grid_resolution):
            msg = f"y index {y_index} outside 0..{self.grid_resolution - 1}"
            raise IndexError(msg)
        offset = y_index * self.grid_resolution + x_index
        return self.pressure_rms_pa[offset]


@dataclass(slots=True)
class HybridSolverResult:
    """Frequency response enriched with interior field snapshots."""

    frequency_hz: list[float]
    spl_db: list[float]
    impedance_ohm: list[complex]
    cone_velocity_ms: list[float]
    port_velocity_ms: list[float]
    field_snapshots: list[HybridFieldSnapshot]

    def to_dict(self) -> dict[str, Sequence[float]]:
        """Return a JSON-friendly view of the numeric traces."""

        return {
            "frequency_hz": list(self.frequency_hz),
            "spl_db": list(self.spl_db),
            "impedance_real": [float(z.real) for z in self.impedance_ohm],
            "impedance_imag": [float(z.imag) for z in self.impedance_ohm],
            "cone_velocity_ms": list(self.cone_velocity_ms),
            "port_velocity_ms": list(self.port_velocity_ms),
        }


@dataclass(slots=True)
class HybridSolverSummary:
    """Aggregated metrics describing the hybrid solver run."""

    max_internal_pressure_pa: float
    mean_internal_pressure_pa: float
    max_port_velocity_ms: float | None
    max_port_mach: float | None

    def to_dict(self) -> dict[str, float | None]:
        return {
            "max_internal_pressure_pa": self.max_internal_pressure_pa,
            "mean_internal_pressure_pa": self.mean_internal_pressure_pa,
            "max_port_velocity_ms": self.max_port_velocity_ms,
            "max_port_mach": self.max_port_mach,
        }


@dataclass(slots=True)
class _AcousticSource:
    position: tuple[float, float, float]
    volume_velocity: complex
    direction: tuple[float, float, float]
    cardioid: float


class HybridBoxSolver:
    """Bridge between lumped models and the upcoming FEM/BEM adaptor."""

    def __init__(
        self,
        driver: DriverParameters,
        enclosure: BoxDesign | VentedBoxDesign,
        *,
        drive_voltage: float = 2.83,
        grid_resolution: int = 24,
    ) -> None:
        if drive_voltage <= 0:
            raise ValueError("Drive voltage must be positive")
        if grid_resolution < 8:
            raise ValueError("Grid resolution must be at least 8 points")

        self.driver = driver
        self.enclosure = enclosure
        self.drive_voltage = drive_voltage
        self._grid_resolution = int(grid_resolution)

        self._volume_m3 = max(enclosure.volume_m3(), 1e-6)
        self._side_length = self._volume_m3 ** (1.0 / 3.0)
        self._field_plane_z = 0.5 * self._side_length
        self._driver_position = (
            0.5 * self._side_length,
            0.6 * self._side_length,
            0.08 * self._side_length,
        )
        self._grid_points = self._build_grid_points()
        self._port_threshold = 17.0  # m/s threshold where compression becomes noticeable

        self._cms = driver.compliance()
        self._rms = driver.mechanical_resistance()

        self._port: PortGeometry | None = None
        self._cab_acoustic: float | None = None
        self._map: float | None = None
        self._rap: float | None = None
        self._rleak: float | None = None
        self._port_position: tuple[float, float, float] | None = None
        self._cab_mech: float | None = None
        self._cms_total: float | None = None
        self._boundary_loss = 1.5

        if isinstance(enclosure, VentedBoxDesign):
            self._mode = "vented"
            self._port = enclosure.port
            self._cab_acoustic = enclosure.acoustic_compliance()
            self._map = self._port.acoustic_mass()
            self._rap = self._port.series_resistance(self._cab_acoustic)
            self._rleak = enclosure.leakage_resistance(self._cab_acoustic)
            self._boundary_loss = 1.35
            self._port_position = (
                0.5 * self._side_length,
                0.2 * self._side_length,
                0.08 * self._side_length,
            )
            self._cms_total = None
        else:
            self._mode = "sealed"
            self._port = None
            self._cab_mech = enclosure.air_compliance(driver)
            self._cms_total = 1.0 / (1.0 / self._cms + 1.0 / self._cab_mech)
            self._boundary_loss = 1.6
            self._port_position = None
            self._cab_acoustic = None
            self._map = None
            self._rap = None
            self._rleak = None

    @property
    def grid_resolution(self) -> int:
        return self._grid_resolution

    def frequency_response(
        self,
        frequencies_hz: Iterable[float],
        *,
        mic_distance_m: float = 1.0,
    ) -> tuple[HybridSolverResult, HybridSolverSummary]:
        if mic_distance_m <= 0:
            raise ValueError("Microphone distance must be positive")

        freq_list: list[float] = []
        spl_list: list[float] = []
        impedance: list[complex] = []
        cone_velocity: list[float] = []
        port_velocity: list[float] = []
        snapshots: list[HybridFieldSnapshot] = []

        total_pressure = 0.0
        total_cells = 0
        max_pressure = 0.0
        max_port_velocity = 0.0
        max_port_mach = 0.0

        for freq in frequencies_hz:
            if freq <= 0:
                continue

            omega = 2 * pi * freq
            k = omega / SPEED_OF_SOUND

            if self._mode == "sealed":
                (
                    volume_velocity,
                    ze,
                    cone_vel,
                ) = self._sealed_state(omega)
                port_vol_velocity: complex | None = None
                port_vel = None
                compression = None
            else:
                (
                    volume_velocity,
                    ze,
                    cone_vel,
                    port_vol_velocity,
                    port_vel,
                    compression,
                ) = self._vented_state(omega)

            field = self._compute_pressure_field(omega, k, volume_velocity, port_vol_velocity)
            max_field_pressure = max(field, default=0.0)

            snapshots.append(
                HybridFieldSnapshot(
                    frequency_hz=freq,
                    grid_resolution=self._grid_resolution,
                    pressure_rms_pa=field,
                    max_pressure_pa=max_field_pressure,
                    cone_velocity_ms=abs(cone_vel),
                    port_velocity_ms=port_vel,
                    port_compression_ratio=compression,
                    port_mach=(port_vel / SPEED_OF_SOUND) if port_vel is not None else None,
                )
            )

            pressure = omega * AIR_DENSITY * abs(volume_velocity) / (2 * pi * mic_distance_m)
            spl = 20.0 * log10(max(pressure / P_REF, 1e-12))

            freq_list.append(freq)
            spl_list.append(spl)
            impedance.append(ze)
            cone_velocity.append(abs(cone_vel))
            port_velocity.append(port_vel or 0.0)

            total_pressure += sum(field)
            total_cells += len(field)
            max_pressure = max(max_pressure, max_field_pressure)
            if port_vel is not None:
                max_port_velocity = max(max_port_velocity, port_vel)
                max_port_mach = max(max_port_mach, port_vel / SPEED_OF_SOUND)

        mean_pressure = total_pressure / total_cells if total_cells else 0.0
        summary = HybridSolverSummary(
            max_internal_pressure_pa=max_pressure,
            mean_internal_pressure_pa=mean_pressure,
            max_port_velocity_ms=max_port_velocity if self._mode == "vented" else None,
            max_port_mach=max_port_mach if self._mode == "vented" else None,
        )

        result = HybridSolverResult(
            frequency_hz=freq_list,
            spl_db=spl_list,
            impedance_ohm=impedance,
            cone_velocity_ms=cone_velocity,
            port_velocity_ms=port_velocity,
            field_snapshots=snapshots,
        )
        return result, summary

    def _sealed_state(self, omega: float) -> tuple[complex, complex, complex]:
        assert self._cms_total is not None
        driver = self.driver
        zm = self._rms + 1j * (omega * driver.mms_kg - 1.0 / (omega * self._cms_total))
        ze = driver.re_ohm + 1j * omega * driver.le_h + (driver.bl_t_m**2) / zm
        current = self.drive_voltage / ze
        force = driver.bl_t_m * current
        cone_velocity = force / zm
        volume_velocity = cone_velocity * driver.sd_m2
        return volume_velocity, ze, cone_velocity

    def _vented_state(
        self,
        omega: float,
    ) -> tuple[complex, complex, complex, complex | None, float | None, float | None]:
        assert self._port is not None
        assert self._cab_acoustic is not None
        assert self._map is not None
        assert self._rap is not None

        driver = self.driver
        z_cab = 1.0 / (1j * omega * self._cab_acoustic)
        if self._rleak is not None:
            z_cab = 1.0 / (1.0 / z_cab + 1.0 / self._rleak)

        z_port = self._rap + 1j * omega * self._map
        z_load = 1.0 / (1.0 / z_cab + 1.0 / z_port)

        z_mech = self._rms + 1j * omega * driver.mms_kg + 1.0 / (1j * omega * self._cms)
        z_total_mech = z_mech + driver.sd_m2**2 * z_load

        ze = driver.re_ohm + 1j * omega * driver.le_h + (driver.bl_t_m**2) / z_total_mech
        current = self.drive_voltage / ze
        force = driver.bl_t_m * current
        cone_velocity = force / z_total_mech
        volume_velocity = cone_velocity * driver.sd_m2

        acoustic_pressure = z_load * volume_velocity
        port_volume_velocity = acoustic_pressure / z_port
        port_area = max(self._port.area_m2(), 1e-9)
        raw_velocity = abs(port_volume_velocity) / port_area
        port_velocity, compression = self._apply_port_compression(raw_velocity)
        if compression is not None and compression < 1.0:
            port_volume_velocity *= compression

        return (
            volume_velocity,
            ze,
            cone_velocity,
            port_volume_velocity,
            port_velocity,
            compression,
        )

    def _apply_port_compression(self, velocity: float) -> tuple[float | None, float | None]:
        if velocity <= 0.0:
            return None, None
        if velocity <= self._port_threshold:
            return velocity, 1.0
        excess = velocity - self._port_threshold
        compressed = self._port_threshold + 0.35 * excess
        ratio = compressed / velocity if velocity > 0 else 1.0
        return compressed, ratio

    def _build_grid_points(self) -> list[tuple[float, float, float]]:
        step = self._side_length / max(self._grid_resolution - 1, 1)
        points: list[tuple[float, float, float]] = []
        for j in range(self._grid_resolution):
            y = j * step
            for i in range(self._grid_resolution):
                x = i * step
                points.append((x, y, self._field_plane_z))
        return points

    def _compute_pressure_field(
        self,
        omega: float,
        k: float,
        volume_velocity: complex,
        port_volume_velocity: complex | None,
    ) -> list[float]:
        driver_source = _AcousticSource(
            position=self._driver_position,
            volume_velocity=volume_velocity,
            direction=(0.0, 0.0, 1.0),
            cardioid=0.65,
        )
        port_source: _AcousticSource | None = None
        if port_volume_velocity is not None and self._port_position is not None:
            port_source = _AcousticSource(
                position=self._port_position,
                volume_velocity=port_volume_velocity,
                direction=(0.0, 0.0, 1.0),
                cardioid=0.45,
            )

        field: list[float] = []
        for x, y, z in self._grid_points:
            pressure = self._source_pressure(driver_source, x, y, z, omega, k)
            if port_source is not None:
                pressure += self._source_pressure(port_source, x, y, z, omega, k)
            field.append(abs(pressure))
        return field

    def _source_pressure(
        self,
        source: _AcousticSource,
        x: float,
        y: float,
        z: float,
        omega: float,
        k: float,
    ) -> complex:
        sx, sy, sz = source.position
        dx = x - sx
        dy = y - sy
        dz = z - sz
        r = sqrt(dx * dx + dy * dy + dz * dz) + 1e-6

        dir_x, dir_y, dir_z = source.direction
        dot = (dx * dir_x + dy * dir_y + dz * dir_z) / r
        dot = max(-1.0, min(1.0, dot))
        cardioid = (1.0 - source.cardioid) + source.cardioid * 0.5 * (1.0 + dot)

        base = 1j * omega * AIR_DENSITY * source.volume_velocity / (4 * pi * r)
        attenuation = exp(-self._boundary_loss * r / max(self._side_length, 1e-6))
        phase = cmath.exp(-1j * k * r)
        return base * phase * attenuation * cardioid


__all__ = [
    "HybridBoxSolver",
    "HybridSolverResult",
    "HybridSolverSummary",
    "HybridFieldSnapshot",
]
