"""Utility helpers shared across acoustic solvers."""

from __future__ import annotations

from typing import List, Sequence, Tuple


def find_band_edges(
    frequencies: Sequence[float],
    values: Sequence[float],
    drop_db: float,
) -> Tuple[float | None, float | None]:
    """Return approximate low/high frequencies where ``values`` fall ``drop_db`` below the peak.

    The inputs are treated as sampled points of a smooth response curve. The search assumes
    ``frequencies`` are unique but not necessarily sorted. Linear interpolation is used to
    estimate the crossing locations around the global peak. When no crossing is detected on
    a given side of the peak (e.g. monotonically increasing samples) the nearest boundary
    frequency is returned instead of ``None`` to signal the limited bandwidth capture.
    """

    if len(frequencies) != len(values) or not frequencies:
        return (None, None)

    pairs = sorted(zip(frequencies, values), key=lambda item: item[0])
    freqs: List[float] = [float(f) for f, _ in pairs]
    mags: List[float] = [float(v) for _, v in pairs]

    peak_val = max(mags)
    threshold = peak_val - drop_db
    peak_idx = mags.index(peak_val)

    low = _search_edge(freqs, mags, peak_idx, -1, threshold)
    high = _search_edge(freqs, mags, peak_idx, 1, threshold)
    return (low, high)


def _search_edge(
    freqs: Sequence[float],
    mags: Sequence[float],
    start_idx: int,
    step: int,
    threshold: float,
) -> float | None:
    prev_freq = freqs[start_idx]
    prev_val = mags[start_idx]

    idx = start_idx + step
    while 0 <= idx < len(freqs):
        freq = freqs[idx]
        val = mags[idx]
        if val == threshold:
            return freq
        if _crosses(prev_val, val, threshold):
            return _interpolate(prev_freq, prev_val, freq, val, threshold)
        prev_freq = freq
        prev_val = val
        idx += step

    return prev_freq


def _crosses(a: float, b: float, threshold: float) -> bool:
    return (a - threshold) * (b - threshold) <= 0.0 and a != b


def _interpolate(f1: float, v1: float, f2: float, v2: float, threshold: float) -> float:
    if v2 == v1:
        return (f1 + f2) / 2.0
    ratio = (threshold - v1) / (v2 - v1)
    return f1 + ratio * (f2 - f1)


__all__ = ["find_band_edges"]
