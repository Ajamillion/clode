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
    driver_snapshot = next(
        (snap for snap in result.field_snapshots if snap.plane_label == "driver-plane"),
        result.field_snapshots[0],
    )

    centre_index = driver_snapshot.grid_resolution // 2
    centre_pressure = driver_snapshot.pressure_at(centre_index, centre_index)
    corner_pressure = driver_snapshot.pressure_at(0, 0)
    coords = driver_snapshot.max_pressure_coords_m
    side_length = box.volume_m3() ** (1.0 / 3.0)

    assert centre_pressure > corner_pressure
    assert driver_snapshot.port_velocity_ms is None
    assert driver_snapshot.plane_label == "driver-plane"
    assert driver_snapshot.plane_normal == (0.0, 0.0, 1.0)
    assert len(coords) == 3
    assert all(0.0 <= c <= side_length + 1e-6 for c in coords)
    assert isclose(coords[2], driver_snapshot.plane_offset_m, abs_tol=1e-6)
    assert summary.max_port_velocity_ms is None
    assert summary.max_port_vortex_loss_db is None
    assert summary.max_port_noise_spl_db is None
    assert summary.port_noise_reference_distance_m is None
    assert summary.max_internal_pressure_pa >= centre_pressure
    assert summary.mean_internal_pressure_pa > 0.0
    assert summary.plane_max_pressure_pa[driver_snapshot.plane_label] >= centre_pressure
    assert summary.plane_mean_pressure_pa[driver_snapshot.plane_label] > 0.0
    assert summary.max_pressure_location_m is not None
    plane_coords = summary.plane_max_pressure_location_m[driver_snapshot.plane_label]
    for a, b in zip(plane_coords, coords, strict=False):
        assert isclose(a, b, abs_tol=1e-6)
    summary_payload = summary.to_dict()
    assert summary_payload["max_pressure_location_m"] is not None
    assert len(summary_payload["max_pressure_location_m"]) == 3
    assert driver_snapshot.plane_label in summary_payload["plane_max_pressure_location_m"]
    assert "max_port_vortex_loss_db" in summary_payload
    assert summary_payload["max_port_vortex_loss_db"] is None
    assert summary_payload["max_port_noise_spl_db"] is None
    assert summary.max_directivity_index_db is not None
    assert summary.mean_directivity_index_db is not None
    assert summary.directivity_angles_deg
    assert summary.directivity_angles_deg[0] == 0.0


def test_hybrid_solver_reports_port_compression_metrics() -> None:
    driver = _demo_driver()
    port = PortGeometry(diameter_m=0.11, length_m=0.28, loss_q=16.0)
    box = VentedBoxDesign(volume_l=60.0, port=port, leakage_q=8.0)
    solver = HybridBoxSolver(driver, box, drive_voltage=18.0, grid_resolution=18)

    result, summary = solver.frequency_response([28.0, 36.0, 44.0])
    assert len(result.port_vortex_loss_db) == len(result.frequency_hz)
    assert len(result.port_noise_spl_db) == len(result.frequency_hz)
    port_snapshot = next(
        (snap for snap in result.field_snapshots if snap.plane_label == "port-plane"),
        result.field_snapshots[-1],
    )

    assert port_snapshot.port_velocity_ms is not None
    assert port_snapshot.port_compression_ratio is not None
    assert summary.max_port_velocity_ms is not None
    assert summary.max_port_velocity_ms > 0.0
    assert summary.max_port_mach is not None
    assert summary.max_port_mach > 0.0
    assert summary.max_port_vortex_loss_db is not None
    assert summary.max_port_noise_spl_db is not None
    assert summary.port_noise_reference_distance_m == 1.0
    assert summary.plane_max_pressure_pa[port_snapshot.plane_label] >= port_snapshot.max_pressure_pa
    assert port_snapshot.plane_normal == (0.0, 1.0, 0.0)
    assert summary.min_port_compression_ratio is not None
    assert 0.0 < summary.min_port_compression_ratio <= 1.0
    assert isclose(
        summary.plane_max_pressure_location_m[port_snapshot.plane_label][1],
        port_snapshot.plane_offset_m,
        abs_tol=1e-6,
    )

    if port_snapshot.port_velocity_ms > 15.0:
        assert port_snapshot.port_compression_ratio < 1.0
    if port_snapshot.port_velocity_ms and port_snapshot.port_velocity_ms > 6.0:
        assert port_snapshot.port_vortex_loss_db is not None
        assert port_snapshot.port_vortex_loss_db > 0.0
        assert port_snapshot.port_noise_spl_db is not None
        assert summary.max_port_noise_spl_db >= port_snapshot.port_noise_spl_db
    else:
        assert port_snapshot.port_vortex_loss_db in (None, 0.0)
    assert summary.max_directivity_index_db is not None
    assert summary.max_directivity_index_db >= 0.0
    assert summary.directivity_angles_deg
    assert 45.0 in summary.directivity_angles_deg


def test_hybrid_port_noise_tracks_microphone_distance() -> None:
    driver = _demo_driver()
    port = PortGeometry(diameter_m=0.11, length_m=0.28, loss_q=16.0)
    box = VentedBoxDesign(volume_l=60.0, port=port, leakage_q=8.0)

    near_solver = HybridBoxSolver(driver, box, drive_voltage=20.0, grid_resolution=18)
    far_solver = HybridBoxSolver(driver, box, drive_voltage=20.0, grid_resolution=18)

    _, near_summary = near_solver.frequency_response([36.0, 48.0], mic_distance_m=1.0)
    _, far_summary = far_solver.frequency_response([36.0, 48.0], mic_distance_m=2.5)

    assert near_summary.max_port_noise_spl_db is not None
    assert far_summary.max_port_noise_spl_db is not None
    assert isclose(near_summary.port_noise_reference_distance_m or 0.0, 1.0, rel_tol=1e-6)
    assert isclose(far_summary.port_noise_reference_distance_m or 0.0, 2.5, rel_tol=1e-6)
    assert far_summary.max_port_noise_spl_db < near_summary.max_port_noise_spl_db


def test_hybrid_solver_reports_thermal_metrics() -> None:
    driver = _demo_driver()
    box = BoxDesign(volume_l=36.0, leakage_q=10.0)
    solver = HybridBoxSolver(driver, box, drive_voltage=16.0, grid_resolution=16)

    result, summary = solver.frequency_response([25.0, 60.0])

    assert result.voice_coil_temperature_c
    assert result.magnet_temperature_c
    assert result.basket_temperature_c
    assert result.voice_coil_power_w
    assert result.thermal_compression_db
    assert len(result.voice_coil_temperature_c) == len(result.frequency_hz)
    assert all(temp >= summary.thermal_reference_temp_c for temp in result.basket_temperature_c)
    assert summary.max_voice_coil_temp_c is not None
    assert summary.max_voice_coil_temp_c >= max(result.voice_coil_temperature_c) - 1e-6
    assert summary.max_magnet_temp_c is not None
    assert summary.max_basket_temp_c is not None
    assert summary.max_voice_coil_power_w is not None
    assert summary.max_voice_coil_power_w >= max(result.voice_coil_power_w) - 1e-6
    assert summary.thermal_time_constants_s is not None
    assert len(summary.thermal_time_constants_s) == 3
    assert summary.max_thermal_compression_db is not None
    assert summary.max_thermal_compression_db >= 0.0

    compression_values = [value for value in result.thermal_compression_db if value > 0.0]
    if compression_values:
        assert summary.max_thermal_compression_db >= max(compression_values) - 1e-6

    payload = summary.to_dict()
    for key in [
        "max_voice_coil_temp_c",
        "max_magnet_temp_c",
        "max_basket_temp_c",
        "max_voice_coil_power_w",
        "max_thermal_compression_db",
        "thermal_time_constants_s",
        "thermal_reference_temp_c",
    ]:
        assert key in payload


def test_hybrid_solver_matches_lumped_spl_baseline() -> None:
    driver = _demo_driver()
    box = BoxDesign(volume_l=40.0)
    solver = HybridBoxSolver(driver, box, drive_voltage=2.83, grid_resolution=16)

    result, _ = solver.frequency_response([20.0, 40.0, 80.0])
    assert len(result.frequency_hz) == 3
    assert len(result.field_snapshots) >= len(result.frequency_hz)
    labels = {snap.plane_label for snap in result.field_snapshots}
    assert "mid-plane" in labels
    assert result.snapshot_stride == 1
    assert result.directivity_angles_deg
    assert len(result.directivity_response_db) == len(result.directivity_angles_deg)
    assert len(result.directivity_index_db) == len(result.frequency_hz)
    zero_idx = result.directivity_angles_deg.index(0.0)
    assert all(isclose(value, 0.0, abs_tol=1e-6) for value in result.directivity_response_db[zero_idx])
    forty_five_idx = result.directivity_angles_deg.index(45.0)
    off_axis_levels = result.directivity_response_db[forty_five_idx]
    assert len(off_axis_levels) == len(result.frequency_hz)
    assert all(level <= 0.0 for level in off_axis_levels)

    # SPL should track the sealed-box lumped model within a small tolerance for low
    # frequencies because the hybrid solver reuses the same underlying impedance
    # calculations.
    spl = result.spl_db
    assert not isclose(spl[0], spl[1], rel_tol=0.25)
    assert spl[2] > spl[0]


def test_hybrid_solver_downsamples_snapshots_with_stride() -> None:
    driver = _demo_driver()
    box = BoxDesign(volume_l=38.0)
    solver = HybridBoxSolver(driver, box, drive_voltage=3.0, grid_resolution=14)

    frequencies = [25.0, 35.0, 45.0, 55.0]
    stride = 2
    result, _ = solver.frequency_response(frequencies, snapshot_stride=stride)

    assert result.snapshot_stride == stride
    assert len(result.frequency_hz) == len(frequencies)
    plane_labels = {snap.plane_label for snap in result.field_snapshots}
    expected_snapshots = len(plane_labels) * ((len(frequencies) + stride - 1) // stride)
    assert len(result.field_snapshots) == expected_snapshots

    captured_freqs = {snap.frequency_hz for snap in result.field_snapshots}
    # Should only capture every other frequency when stride=2
    assert captured_freqs == {frequencies[i] for i in range(0, len(frequencies), stride)}


def test_hybrid_snapshot_serialisation_includes_plane_metadata() -> None:
    driver = _demo_driver()
    box = BoxDesign(volume_l=30.0)
    solver = HybridBoxSolver(driver, box, drive_voltage=3.0, grid_resolution=12)

    result, summary = solver.frequency_response([35.0])

    payload_without_fields = result.to_dict()
    assert "field_snapshots" not in payload_without_fields
    assert payload_without_fields["snapshot_stride"] == 1

    payload_with_fields = result.to_dict(include_snapshots=True)
    assert "field_snapshots" in payload_with_fields
    assert payload_with_fields["snapshot_stride"] == 1
    snapshot_payload = payload_with_fields["field_snapshots"][0]
    assert "plane_label" in snapshot_payload
    assert "pressure_rms_pa" in snapshot_payload
    assert "max_pressure_coords_m" in snapshot_payload
    assert "port_vortex_loss_db" in snapshot_payload
    assert "port_noise_spl_db" in snapshot_payload
    assert len(snapshot_payload["max_pressure_coords_m"]) == 3
    assert summary.plane_max_pressure_pa[snapshot_payload["plane_label"]] >= snapshot_payload[
        "max_pressure_pa"
    ]


def test_hybrid_solver_reports_suspension_creep_metadata() -> None:
    driver = _demo_driver()
    box = BoxDesign(volume_l=48.0, leakage_q=12.0)
    solver_creep = HybridBoxSolver(driver, box, drive_voltage=2.83, grid_resolution=14)
    solver_rigid = HybridBoxSolver(
        driver,
        box,
        drive_voltage=2.83,
        grid_resolution=14,
        suspension_creep=False,
    )

    frequencies = [12.0]
    result_creep, summary_creep = solver_creep.frequency_response(frequencies)
    result_rigid, summary_rigid = solver_rigid.frequency_response(frequencies)

    assert result_creep.cone_velocity_ms[0] > result_rigid.cone_velocity_ms[0]
    assert summary_creep.suspension_creep_ratio is not None
    assert summary_creep.suspension_creep_ratio > 1.0
    assert summary_creep.suspension_creep_time_constants_s is not None
    assert len(summary_creep.suspension_creep_time_constants_s) >= 1
    assert summary_rigid.suspension_creep_ratio is None

    summary_payload = summary_creep.to_dict()
    assert "suspension_creep_ratio" in summary_payload
    assert summary_payload["suspension_creep_ratio"] == summary_creep.suspension_creep_ratio
    assert summary_payload["suspension_creep_time_constants_s"]
