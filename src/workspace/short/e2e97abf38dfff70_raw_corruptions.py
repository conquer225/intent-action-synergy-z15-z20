"""Deterministic raw-domain corruptions for SQI-v3 training and stress tests."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


RAW_CORRUPTION_KINDS = (
    "flatline",
    "broadband_noise",
    "mains_noise",
    "drift",
    "burst",
    "cable_motion",
)


@dataclass(frozen=True)
class RawCorruptionSpec:
    kind: str
    severity: float
    channels: tuple[int, ...]
    start_window: int
    length_windows: int


@dataclass(frozen=True)
class RawCorruptionResult:
    values: np.ndarray
    quality: np.ndarray  # (windows, channels), 1=clean, 0=worst
    corruption_mask: np.ndarray


def _robust_scale(values: np.ndarray) -> np.ndarray:
    centered = values - np.median(values, axis=0, keepdims=True)
    scale = 1.4826 * np.median(np.abs(centered), axis=0)
    fallback = np.std(values, axis=0)
    return np.maximum(np.where(scale > 1.0e-12, scale, fallback), 1.0e-6)


def apply_raw_corruption(
    eeg: np.ndarray,
    spec: RawCorruptionSpec,
    *,
    sample_rate_hz: float,
    window_samples: int,
    seed: int,
) -> RawCorruptionResult:
    values = np.asarray(eeg, dtype=np.float64)
    if values.ndim != 2 or len(values) % window_samples:
        raise ValueError("EEG must be (samples, channels) with complete windows")
    if spec.kind not in RAW_CORRUPTION_KINDS:
        raise ValueError(f"unsupported raw corruption: {spec.kind}")
    if not 0.0 <= spec.severity <= 1.0:
        raise ValueError("severity must be in [0, 1]")
    windows = len(values) // window_samples
    if spec.start_window < 0 or spec.length_windows <= 0 or spec.start_window + spec.length_windows > windows:
        raise ValueError("corruption episode is outside the recording")
    if not spec.channels or min(spec.channels) < 0 or max(spec.channels) >= values.shape[1]:
        raise ValueError("invalid channel selection")

    result = values.copy()
    quality = np.ones((windows, values.shape[1]), dtype=np.float64)
    mask = np.zeros_like(quality, dtype=bool)
    start = spec.start_window * window_samples
    stop = (spec.start_window + spec.length_windows) * window_samples
    channels = np.asarray(spec.channels, dtype=int)
    mask[spec.start_window:spec.start_window + spec.length_windows, channels] = True
    quality[mask] = 1.0 - spec.severity
    if spec.severity == 0.0:
        return RawCorruptionResult(result, quality, mask)

    rng = np.random.default_rng(seed)
    segment = result[start:stop, channels]
    scale = _robust_scale(values[:, channels])
    samples = len(segment)
    time = np.arange(samples, dtype=np.float64) / sample_rate_hz
    severity = spec.severity

    if spec.kind == "flatline":
        anchor = values[max(0, start - 1), channels]
        tiny = rng.normal(scale=scale * (1.0e-4 * (1.0 - severity)), size=segment.shape)
        result[start:stop, channels] = anchor + tiny
    elif spec.kind == "broadband_noise":
        amplitude = scale * (0.5 + 7.5 * severity)
        result[start:stop, channels] += rng.normal(size=segment.shape) * amplitude
    elif spec.kind == "mains_noise":
        phase = rng.uniform(0.0, 2.0 * np.pi, size=len(channels))
        amplitude = scale * (0.25 + 4.0 * severity)
        wave = np.sin(2.0 * np.pi * 50.0 * time[:, None] + phase[None, :])
        result[start:stop, channels] += wave * amplitude
    elif spec.kind == "drift":
        frequency = rng.uniform(0.10, 0.45, size=len(channels))
        phase = rng.uniform(0.0, 2.0 * np.pi, size=len(channels))
        amplitude = scale * (1.0 + 12.0 * severity)
        wave = np.sin(2.0 * np.pi * time[:, None] * frequency[None, :] + phase[None, :])
        result[start:stop, channels] += wave * amplitude
    elif spec.kind == "burst":
        corrupted = segment.copy()
        # Model an electrode-pop/contact transient as an abrupt displacement
        # followed by exponential recovery. A smooth Gaussian bump is a poor
        # proxy here: sparse smooth events can disappear from robust window
        # summaries despite the abrupt contact change seen by real hardware.
        # Every labeled bad window receives at least one event; extra events
        # increase with severity.
        centers = [
            window * window_samples + int(rng.integers(0, window_samples))
            for window in range(spec.length_windows)
        ]
        extra_count = int(round(spec.length_windows * 4.0 * severity))
        centers.extend(int(rng.integers(0, samples)) for _ in range(extra_count))
        for center in centers:
            decay_seconds = rng.uniform(0.03, 0.35)
            decay_samples = max(1, int(round(decay_seconds * sample_rate_hz)))
            right = min(samples, center + 6 * decay_samples + 1)
            event_time = np.arange(right - center, dtype=np.float64)
            recovery = np.exp(-event_time / decay_samples)[:, None]
            amplitude = scale * rng.uniform(4.0, 18.0, size=len(channels)) * (0.5 + severity)
            sign = rng.choice((-1.0, 1.0), size=len(channels))
            corrupted[center:right] += recovery * amplitude * sign
        result[start:stop, channels] = corrupted
    elif spec.kind == "cable_motion":
        # Combines modest amplitude change with fast oscillation, steps, and
        # sparse transients. This deliberately covers the R3 failure mode
        # without copying any held-out future waveform.
        corrupted = segment.copy()
        frequency = rng.uniform(28.0, 48.0, size=len(channels))
        phase = rng.uniform(0.0, 2.0 * np.pi, size=len(channels))
        hf_amplitude = scale * (0.3 + 3.0 * severity)
        corrupted += np.sin(
            2.0 * np.pi * time[:, None] * frequency[None, :] + phase[None, :]
        ) * hf_amplitude
        step_count = max(1, int(round(spec.length_windows * (1.0 + 4.0 * severity))))
        offset = np.zeros_like(corrupted)
        for _ in range(step_count):
            location = int(rng.integers(0, samples))
            jump = scale * rng.uniform(0.5, 6.0, size=len(channels)) * severity
            jump *= rng.choice((-1.0, 1.0), size=len(channels))
            offset[location:] += jump
        corrupted += offset
        impulse_probability = (0.0005 + 0.004 * severity)
        impulses = rng.random(corrupted.shape) < impulse_probability
        corrupted += impulses * rng.normal(size=corrupted.shape) * scale * (2.0 + 12.0 * severity)
        result[start:stop, channels] = corrupted

    if not np.all(np.isfinite(result)):
        raise ValueError("raw corruption generated non-finite values")
    return RawCorruptionResult(result, quality, mask)
