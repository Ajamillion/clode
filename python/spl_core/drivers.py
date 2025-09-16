"""Driver and enclosure data models used across the simulation core."""

from __future__ import annotations

from dataclasses import dataclass
from math import pi, sqrt

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


@dataclass(slots=True)
class PortGeometry:
    """Simple representation of a circular port."""

    diameter_m: float
    """Port diameter (metres)."""

    length_m: float
    """Physical tube length (metres)."""

    count: int = 1
    """Number of identical ports."""

    flare_factor: float = 1.7
    """End-correction multiplier (~1.7 for one flanged, one free end)."""

    loss_q: float = 18.0
    """Quality factor capturing port losses (higher => lower damping)."""

    def area_m2(self) -> float:
        """Return the combined cross-sectional area of all ports."""

        radius = self.diameter_m / 2.0
        single_area = pi * radius**2
        return single_area * max(self.count, 1)

    def effective_length_m(self) -> float:
        """Return the acoustically effective length including end correction."""

        radius = self.diameter_m / 2.0
        return self.length_m + self.flare_factor * radius

    def acoustic_mass(self) -> float:
        """Return acoustic mass Map (Pa·s²/m³)."""

        area = self.area_m2()
        if area <= 0:
            raise ValueError("Port area must be positive")
        return AIR_DENSITY * self.effective_length_m() / area

    def tuning_frequency(self, cab_acoustic: float) -> float:
        """Return the box tuning frequency derived from Map and acoustic Cab."""

        omega0 = 1.0 / sqrt(self.acoustic_mass() * cab_acoustic)
        return omega0 / (2 * pi)

    def series_resistance(self, cab_acoustic: float) -> float:
        """Return an approximate acoustic resistance modelling port losses."""

        loss_q = max(self.loss_q, 0.5)
        omega0 = 2 * pi * self.tuning_frequency(cab_acoustic)
        return omega0 * self.acoustic_mass() / loss_q


@dataclass(slots=True)
class VentedBoxDesign:
    """Parameters describing a bass-reflex (vented) enclosure."""

    volume_l: float
    """Net internal volume (litres)."""

    port: PortGeometry
    """Primary port geometry."""

    leakage_q: float = 10.0
    """Quality factor representing box leakage/absorption losses."""

    def volume_m3(self) -> float:
        """Return enclosure volume in cubic metres."""

        return self.volume_l / 1000.0

    def air_compliance(self, driver: DriverParameters) -> float:
        """Return mechanical compliance of the enclosed air referenced to the cone."""

        return self.volume_m3() / (AIR_DENSITY * SPEED_OF_SOUND**2 * driver.sd_m2**2)

    def acoustic_compliance(self) -> float:
        """Return acoustic compliance (Cab) in the acoustic domain."""

        return self.volume_m3() / (AIR_DENSITY * SPEED_OF_SOUND**2)

    def leakage_resistance(self, cab_acoustic: float) -> float | None:
        """Return an acoustic resistance approximating leakage losses."""

        if self.leakage_q <= 0:
            return None
        omega0 = 2 * pi * self.port.tuning_frequency(cab_acoustic)
        return self.leakage_q / (omega0 * cab_acoustic)
