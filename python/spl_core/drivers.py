"""Driver and enclosure data models used across the simulation core."""

from __future__ import annotations

from dataclasses import dataclass
from math import pi

AIR_DENSITY = 1.2041  # kg/m^3 at 20°C
SPEED_OF_SOUND = 343.0  # m/s at 20°C


@dataclass(slots=True)
class DriverParameters:
    """Minimal Thiele/Small parameter set for low-frequency simulations."""

    fs_hz: float
    """Free-air resonance frequency (Hz)."""

    qts: float
    """Total Q at fs (dimensionless)."""

    re_ohm: float
    """DC resistance of the voice coil (ohms)."""

    bl_t_m: float
    """Force factor (Tesla-metres)."""

    mms_kg: float
    """Moving mass including air load (kilograms)."""

    sd_m2: float
    """Effective piston area (square metres)."""

    le_h: float = 0.0007
    """Voice-coil inductance (Henries)."""

    vas_l: float | None = None
    """Equivalent compliance volume (litres). Optional if Cms derived from fs/mms."""

    def vas_m3(self) -> float:
        """Return the compliance volume in cubic metres."""

        if self.vas_l is not None:
            return self.vas_l / 1000.0
        return self.compliance() * AIR_DENSITY * SPEED_OF_SOUND**2 * self.sd_m2**2

    def compliance(self) -> float:
        """Return the mechanical compliance Cms (m/N)."""

        return 1.0 / ((2 * pi * self.fs_hz) ** 2 * self.mms_kg)

    def qes(self) -> float:
        """Electrical Q derived from BL, Re, and moving mass."""

        w_s = 2 * pi * self.fs_hz
        return (w_s * self.mms_kg * self.re_ohm) / (self.bl_t_m**2)

    def qms(self) -> float:
        """Mechanical Q derived from Qts and Qes."""

        qes = self.qes()
        if qes <= 0:
            raise ValueError("Qes must be positive")
        inv_qms = 1.0 / self.qts - 1.0 / qes
        if inv_qms <= 0:
            # fall back to lightly damped assumption
            inv_qms = 1.0 / (self.qts * 1.2)
        return 1.0 / inv_qms

    def mechanical_resistance(self) -> float:
        """Return Rms (mechanical losses) in N·s/m."""

        w_s = 2 * pi * self.fs_hz
        return (w_s * self.mms_kg) / self.qms()


@dataclass(slots=True)
class BoxDesign:
    """Parameters describing a sealed enclosure."""

    volume_l: float
    """Net internal volume (litres)."""

    leakage_q: float = 15.0
    """Optional leakage quality factor (larger => lower leakage)."""

    def volume_m3(self) -> float:
        """Return enclosure volume in cubic metres."""

        return self.volume_l / 1000.0

    def air_compliance(self, driver: DriverParameters) -> float:
        """Return Cab, the acoustic compliance of the enclosed air."""

        return self.volume_m3() / (AIR_DENSITY * SPEED_OF_SOUND**2 * driver.sd_m2**2)
