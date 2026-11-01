from __future__ import annotations

import numpy as np
import pytest

from raw_corruptions import RAW_CORRUPTION_KINDS, RawCorruptionSpec, apply_raw_corruption


@pytest.mark.parametrize("kind", RAW_CORRUPTION_KINDS)
def test_finite_and_unaffected_channels_unchanged(kind: str) -> None:
    rng = np.random.default_rng(5)
    values = rng.normal(size=(4 * 2000, 8))
    result = apply_raw_corruption(
        values,
        RawCorruptionSpec(kind, 0.7, (1, 3), 1, 2),
        sample_rate_hz=250,
        window_samples=2000,
        seed=19,
    )
    assert np.all(np.isfinite(result.values))
    assert np.array_equal(result.values[:, [0, 2, 4, 5, 6, 7]], values[:, [0, 2, 4, 5, 6, 7]])
    assert np.all(result.quality[1:3, [1, 3]] == pytest.approx(0.3))


@pytest.mark.parametrize("kind", ("broadband_noise", "drift", "burst", "cable_motion"))
def test_stronger_severity_increases_perturbation_energy(kind: str) -> None:
    rng = np.random.default_rng(13)
    values = rng.normal(size=(3 * 2000, 8))
    weak = apply_raw_corruption(
        values, RawCorruptionSpec(kind, 0.25, (0,), 1, 1),
        sample_rate_hz=250, window_samples=2000, seed=23,
    )
    strong = apply_raw_corruption(
        values, RawCorruptionSpec(kind, 0.90, (0,), 1, 1),
        sample_rate_hz=250, window_samples=2000, seed=23,
    )
    window = slice(2000, 4000)
    weak_energy = np.mean((weak.values[window, 0] - values[window, 0]) ** 2)
    strong_energy = np.mean((strong.values[window, 0] - values[window, 0]) ** 2)
    assert strong_energy > weak_energy


def test_corruption_mask_is_exact() -> None:
    values = np.zeros((5 * 2000, 8))
    result = apply_raw_corruption(
        values, RawCorruptionSpec("flatline", 1.0, (2, 5), 2, 2),
        sample_rate_hz=250, window_samples=2000, seed=31,
    )
    expected = np.zeros((5, 8), dtype=bool)
    expected[2:4, [2, 5]] = True
    assert np.array_equal(result.corruption_mask, expected)


def test_every_labeled_burst_window_contains_a_change() -> None:
    rng = np.random.default_rng(41)
    values = rng.normal(size=(5 * 2000, 8))
    result = apply_raw_corruption(
        values, RawCorruptionSpec("burst", 0.25, (1,), 1, 3),
        sample_rate_hz=250, window_samples=2000, seed=43,
    )
    for window in range(1, 4):
        block = slice(window * 2000, (window + 1) * 2000)
        assert np.any(result.values[block, 1] != values[block, 1])
