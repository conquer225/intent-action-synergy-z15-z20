"""Causal raw-domain channel descriptors for SQI v3 experiments."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
from scipy.signal import welch


FEATURE_NAMES = (
    "log_mad",
    "log_p95_abs",
    "log_max_abs",
    "log_derivative_mad",
    "log_max_derivative",
    "transient_fraction",
    "flat_step_fraction",
    "low_1_4_ratio",
    "high_31_50_ratio",
    "mains_48_50_ratio",
    "log_spatial_residual_mad",
)


@dataclass(frozen=True)
class RawSQIFeatures:
    values: np.ndarray  # (windows, channels, features)
    names: tuple[str, ...]


def _integrated_power(freq: np.ndarray, psd: np.ndarray, low: float, high: float) -> np.ndarray:
    bins = (freq >= low) & (freq <= high)
    if not np.any(bins):
        raise ValueError(f"no spectral bins in [{low}, {high}] Hz")
    return np.trapezoid(psd[..., bins], freq[bins], axis=-1)


def extract_raw_sqi_features(
    eeg: np.ndarray,
    *,
    sample_rate_hz: float,
    window_samples: int,
    channel_names: Sequence[str] | None = None,
) -> RawSQIFeatures:
    """Extract present-window descriptors; no future windows or labels are used."""
    values = np.asarray(eeg, dtype=np.float64)
    if values.ndim != 2:
        raise ValueError(f"expected (samples, channels), got {values.shape}")
    if sample_rate_hz <= 100.0:
        raise ValueError("sample rate must exceed 100 Hz for the 48-50 Hz descriptor")
    if window_samples <= 1 or len(values) % window_samples:
        raise ValueError("sample count must be an exact multiple of window_samples")
    if channel_names is not None and len(channel_names) != values.shape[1]:
        raise ValueError("channel_names does not match EEG channel count")

    windows = values.reshape(-1, window_samples, values.shape[1])
    median = np.median(windows, axis=1, keepdims=True)
    centered = windows - median
    mad = np.median(np.abs(centered), axis=1)
    p95 = np.percentile(np.abs(centered), 95, axis=1)
    max_abs = np.max(np.abs(centered), axis=1)

    difference = np.diff(windows, axis=1)
    difference_center = difference - np.median(difference, axis=1, keepdims=True)
    derivative_mad = np.median(np.abs(difference_center), axis=1)
    max_derivative = np.max(np.abs(difference_center), axis=1)
    robust_derivative_scale = np.maximum(1.4826 * derivative_mad, 1.0e-12)
    transient_fraction = np.mean(
        np.abs(difference_center) > 8.0 * robust_derivative_scale[:, None, :], axis=1
    )
    flat_tolerance = np.maximum(np.finfo(np.float64).eps, 1.0e-12 * np.maximum(mad, 1.0))
    flat_fraction = np.mean(np.abs(difference) <= flat_tolerance[:, None, :], axis=1)

    spectral = np.transpose(centered, (0, 2, 1))
    segment_samples = min(int(round(sample_rate_hz * 2.0)), window_samples)
    frequencies, psd = welch(
        spectral,
        fs=sample_rate_hz,
        window="hann",
        nperseg=segment_samples,
        noverlap=segment_samples // 2,
        detrend="constant",
        scaling="density",
        axis=-1,
    )
    total = np.maximum(_integrated_power(frequencies, psd, 1.0, 50.0), 1.0e-18)
    low_ratio = _integrated_power(frequencies, psd, 1.0, 4.0) / total
    high_ratio = _integrated_power(frequencies, psd, 31.0, 50.0) / total
    mains_ratio = _integrated_power(frequencies, psd, 48.0, 50.0) / total

    spatial_median = np.median(windows, axis=2, keepdims=True)
    spatial_residual = np.median(np.abs(windows - spatial_median), axis=1)
    features = np.stack(
        (
            np.log1p(mad),
            np.log1p(p95),
            np.log1p(max_abs),
            np.log1p(derivative_mad),
            np.log1p(max_derivative),
            transient_fraction,
            flat_fraction,
            low_ratio,
            high_ratio,
            mains_ratio,
            np.log1p(spatial_residual),
        ),
        axis=-1,
    )
    if not np.all(np.isfinite(features)):
        raise ValueError("raw SQI features contain non-finite values")
    return RawSQIFeatures(features, FEATURE_NAMES)
