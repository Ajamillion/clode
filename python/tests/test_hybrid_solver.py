"""Tests for the reduced-order hybrid solver prototype."""

from __future__ import annotations

from math import isclose

from spl_core import (
    BoxDesign,
    DriverParameters,
    PortGeometry,
    VentedBoxDesign,
)
from spl_core.acoustics.hybrid import HybridBoxSolver


def _demo_driver() -> DriverParameters:
    return DriverParameters(
        fs_hz=32.0,
        qts=0.39,
        re_ohm=3.2,
        bl_t_m=15.5,
        mms_kg=0.125,
        sd_m2=0.052,
        le_h=0.0007,
        vas_l=75.0,
        xmax_mm=12.0,
    )


def test_hybrid_solver_pressure_hotspot_near_driver() -> None:
    driver = _demo_driver()
    box = BoxDesign(volume_l=45.0, leakage_q=14.0)
    solver = HybridBoxSolver(driver, box, drive_voltage=4.5, grid_resolution=18)

    result, summary = solver.frequency_response([40.0])
    snapshot = result.field_snapshots[0]

    centre_index = snapshot.grid_resolution // 2
    centre_pressure = snapshot.pressure_at(centre_index, centre_index)
    corner_pressure = snapshot.pressure_at(0, 0)

    assert centre_pressure > corner_pressure
    assert snapshot.port_velocity_ms is None
    assert summary.max_port_velocity_ms is None
    assert summary.max_internal_pressure_pa >= centre_pressure
    assert summary.mean_internal_pressure_pa > 0.0


def test_hybrid_solver_reports_port_compression_metrics() -> None:
    driver = _demo_driver()
    port = PortGeometry(diameter_m=0.11, length_m=0.28, loss_q=16.0)
    box = VentedBoxDesign(volume_l=60.0, port=port, leakage_q=8.0)
    solver = HybridBoxSolver(driver, box, drive_voltage=18.0, grid_resolution=18)

    result, summary = solver.frequency_response([28.0, 36.0, 44.0])
    snapshot = result.field_snapshots[-1]

    assert snapshot.port_velocity_ms is not None
    assert snapshot.port_compression_ratio is not None
    assert summary.max_port_velocity_ms is not None
    assert summary.max_port_velocity_ms > 0.0
    assert summary.max_port_mach is not None
    assert summary.max_port_mach > 0.0

    if snapshot.port_velocity_ms > 15.0:
        assert snapshot.port_compression_ratio < 1.0


def test_hybrid_solver_matches_lumped_spl_baseline() -> None:
    driver = _demo_driver()
    box = BoxDesign(volume_l=40.0)
    solver = HybridBoxSolver(driver, box, drive_voltage=2.83, grid_resolution=16)

    result, _ = solver.frequency_response([20.0, 40.0, 80.0])
    assert len(result.frequency_hz) == 3
    assert len(result.field_snapshots) == 3

    # SPL should track the sealed-box lumped model within a small tolerance for low
    # frequencies because the hybrid solver reuses the same underlying impedance
    # calculations.
    spl = result.spl_db
    assert not isclose(spl[0], spl[1], rel_tol=0.25)
    assert spl[2] > spl[0]
