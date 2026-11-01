from __future__ import annotations

import numpy as np

from raw_sqi_features import FEATURE_NAMES, extract_raw_sqi_features


def test_shape_and_finite() -> None:
    rng = np.random.default_rng(7)
    values = rng.normal(size=(2 * 2000, 8))
    result = extract_raw_sqi_features(values, sample_rate_hz=250, window_samples=2000)
    assert result.values.shape == (2, 8, len(FEATURE_NAMES))
    assert np.all(np.isfinite(result.values))


def test_high_frequency_motion_signature() -> None:
    fs = 250
    samples = 2000
    time = np.arange(samples) / fs
    baseline = np.sin(2 * np.pi * 10 * time)
    motion = baseline + 4.0 * np.sin(2 * np.pi * 40 * time)
    values = np.zeros((2 * samples, 8))
    values[:samples] = baseline[:, None]
    values[samples:] = motion[:, None]
    result = extract_raw_sqi_features(values, sample_rate_hz=fs, window_samples=samples)
    high_index = FEATURE_NAMES.index("high_31_50_ratio")
    assert np.all(result.values[1, :, high_index] > result.values[0, :, high_index])


def test_flatline_signature() -> None:
    rng = np.random.default_rng(11)
    values = rng.normal(size=(2000, 8))
    values[:, 0] = 3.0
    result = extract_raw_sqi_features(values, sample_rate_hz=250, window_samples=2000)
    flat_index = FEATURE_NAMES.index("flat_step_fraction")
    assert result.values[0, 0, flat_index] == 1.0
    assert np.all(result.values[0, 1:, flat_index] < 0.01)
