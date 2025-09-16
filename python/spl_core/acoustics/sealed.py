"""Simplified sealed-box acoustic solver.

This module intentionally focuses on analytical formulations that run without
third-party numerical dependencies. The implementation provides a physics-
grounded baseline that we can extend with higher fidelity models (modal
extensions, non-linear suspension) in later milestones.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import log10, pi, sqrt
from typing import Iterable, List

from ..drivers import AIR_DENSITY, BoxDesign, DriverParameters
from ._utils import find_band_edges

P_REF = 20e-6  # 20 µPa reference pressure for SPL


@dataclass(slots=True)
class SealedBoxResponse:
    """Frequency-domain response of a sealed-box system."""

    frequency_hz: List[float]
    spl_db: List[float]
    impedance_ohm: List[complex]
    cone_velocity_ms: List[float]

    def to_dict(self) -> dict[str, List[float]]:
        """Return a JSON-serialisable representation of the response."""

        return {
            "frequency_hz": list(self.frequency_hz),
            "spl_db": list(self.spl_db),
            "impedance_real": [float(z.real) for z in self.impedance_ohm],
            "impedance_imag": [float(z.imag) for z in self.impedance_ohm],
            "cone_velocity_ms": list(self.cone_velocity_ms),
        }


@dataclass(slots=True)
class SealedAlignmentSummary:
    """Key figures of merit describing a sealed alignment."""

    fc_hz: float
    qtc: float
    f3_low_hz: float | None
    f3_high_hz: float | None
    max_spl_db: float
    max_cone_velocity_ms: float

    def to_dict(self) -> dict[str, float | None]:
        return {
            "fc_hz": self.fc_hz,
            "qtc": self.qtc,
            "f3_low_hz": self.f3_low_hz,
            "f3_high_hz": self.f3_high_hz,
            "max_spl_db": self.max_spl_db,
            "max_cone_velocity_ms": self.max_cone_velocity_ms,
        }


class SealedBoxSolver:
    """Analytical solver for classic sealed enclosures."""

    def __init__(self, driver: DriverParameters, box: BoxDesign, drive_voltage: float = 2.83):
        self.driver = driver
        self.box = box
        self.drive_voltage = drive_voltage

        self._cms = driver.compliance()
        self._cab = box.air_compliance(driver)
        self._cms_total = 1.0 / (1.0 / self._cms + 1.0 / self._cab)

        self._w_s = 2 * pi * driver.fs_hz
        self._qes = driver.qes()
        self._qms = driver.qms()
        self._rms = driver.mechanical_resistance()

    def system_resonance(self) -> float:
        """Return the resonance frequency (Fc) of the boxed system."""

        return 1.0 / (2 * pi * sqrt(self.driver.mms_kg * self._cms_total))

    def system_qtc(self) -> float:
        """Return total system Q including electrical damping."""

        qes_box = self._qes * (self._cms / self._cms_total)
        inv_qtc = 1.0 / self._qms + 1.0 / qes_box
        return 1.0 / inv_qtc

    def frequency_response(self, frequencies_hz: Iterable[float], mic_distance_m: float = 1.0) -> SealedBoxResponse:
        """Compute SPL/impedance over the requested frequencies."""

        freq_list: List[float] = []
        spl_list: List[float] = []
        imp_list: List[complex] = []
        vel_list: List[float] = []

        cms_total = self._cms_total
        driver = self.driver

        for f in frequencies_hz:
            if f <= 0:
                continue
            omega = 2 * pi * f

            # Mechanical impedance of the moving system + box air load
            zm = self._rms + 1j * (omega * driver.mms_kg - 1.0 / (omega * cms_total))

            # Total electrical impedance seen by the amplifier
            ze = driver.re_ohm + 1j * omega * driver.le_h + (driver.bl_t_m**2) / zm

            current = self.drive_voltage / ze
            force = driver.bl_t_m * current
            velocity = force / zm
            volume_velocity = velocity * driver.sd_m2

            pressure = omega * AIR_DENSITY * abs(volume_velocity) / (2 * pi * mic_distance_m)
            spl = 20.0 * log10(max(pressure / P_REF, 1e-12))

            freq_list.append(f)
            spl_list.append(spl)
            imp_list.append(ze)
            vel_list.append(abs(velocity))

        return SealedBoxResponse(freq_list, spl_list, imp_list, vel_list)

    def alignment_summary(self, response: SealedBoxResponse) -> SealedAlignmentSummary:
        """Derive key alignment metrics from a previously computed response."""

        max_spl = max(response.spl_db, default=0.0)
        f3_low, f3_high = find_band_edges(response.frequency_hz, response.spl_db, 3.0)
        max_velocity = max(response.cone_velocity_ms, default=0.0)

        return SealedAlignmentSummary(
            fc_hz=self.system_resonance(),
            qtc=self.system_qtc(),
            f3_low_hz=f3_low,
            f3_high_hz=f3_high,
            max_spl_db=max_spl,
            max_cone_velocity_ms=max_velocity,
        )


__all__ = ["SealedBoxSolver", "SealedBoxResponse", "SealedAlignmentSummary"]
