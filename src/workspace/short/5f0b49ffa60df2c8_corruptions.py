"""Deterministic structured corruption for channel-by-band EEG features.

The public SEED-VIG cache contains differential-entropy (DE) features rather
than raw microvolt samples.  Raw voltage limits therefore must not be copied
directly into this module.  Perturbation magnitudes are expressed relative to
the robust, per-recording feature scale (IQR / 1.349).

Input arrays have shape ``(windows, channels, bands)``.  The returned quality
array has shape ``(windows, channels)`` and ranges from zero (unusable) to one
(nominal).  It is a synthetic training/evaluation target, not an impedance
measurement or a clinical signal-quality score.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np


CorruptionKind = Literal[
    "dropout",
    "flatline",
    "broadband_noise",
    "mains_noise",
    "drift",
    "burst",
    "channel_swap",
]

TRAINING_KINDS: tuple[CorruptionKind, ...] = (
    "dropout",
    "flatline",
    "broadband_noise",
    "mains_noise",
    "drift",
    "burst",
)


@dataclass(frozen=True)
class CorruptionSpec:
    """One corruption episode in a feature sequence.

    ``severity`` is dimensionless and constrained to ``[0, 1]``.  ``start``
    and ``length`` refer to feature windows, not raw EEG samples.  A missing
    length means the episode continues to the end of the recording.
    """

    kind: CorruptionKind
    severity: float
    channels: tuple[int, ...]
    start: int = 0
    length: int | None = None


@dataclass(frozen=True)
class CorruptionResult:
    features: np.ndarray
    quality: np.ndarray
    corruption_mask: np.ndarray
    metadata: dict


def _validate(features: np.ndarray, spec: CorruptionSpec) -> tuple[np.ndarray, int, int]:
    x = np.asarray(features)
    if x.ndim != 3:
        raise ValueError("features must have shape (windows, channels, bands)")
    if not np.issubdtype(x.dtype, np.floating):
        raise TypeError("features must use a floating dtype")
    if not np.all(np.isfinite(x)):
        raise ValueError("features contain NaN or infinity before corruption")
    if not 0.0 <= spec.severity <= 1.0:
        raise ValueError("severity must be in [0, 1]")
    if not spec.channels:
        raise ValueError("at least one channel is required")
    if len(set(spec.channels)) != len(spec.channels):
        raise ValueError("channels must be unique")
    if min(spec.channels) < 0 or max(spec.channels) >= x.shape[1]:
        raise IndexError("channel index is outside the feature tensor")
    if spec.start < 0 or spec.start >= x.shape[0]:
        raise IndexError("start is outside the feature sequence")
    end = x.shape[0] if spec.length is None else spec.start + spec.length
    if spec.length is not None and spec.length <= 0:
        raise ValueError("length must be positive")
    if end > x.shape[0]:
        raise IndexError("corruption episode extends past the sequence")
    if spec.kind == "channel_swap" and len(spec.channels) != 2:
        raise ValueError("channel_swap requires exactly two channels")
    return x, spec.start, end


def _robust_scale(x: np.ndarray) -> np.ndarray:
    """Return per-channel/per-band robust scale with a conservative floor."""
    q25, q75 = np.quantile(x, (0.25, 0.75), axis=0)
    scale = (q75 - q25) / 1.349
    fallback = np.std(x, axis=0)
    scale = np.where(scale > 1.0e-6, scale, fallback)
    return np.where(scale > 1.0e-6, scale, 1.0)


def _mains_weights(bands: int) -> np.ndarray:
    """Approximate 50 Hz contamination in an ordered low-to-high band vector."""
    weights = np.zeros(bands, dtype=np.float64)
    weights[-1] = 1.0
    if bands >= 2:
        weights[-2] = 0.15
    return weights


def apply_feature_corruption(
    features: np.ndarray,
    spec: CorruptionSpec,
    *,
    seed: int,
) -> CorruptionResult:
    """Apply one deterministic corruption episode without mutating ``features``."""
    source, start, end = _validate(features, spec)
    x = np.array(source, dtype=np.float64, copy=True)
    quality = np.ones(x.shape[:2], dtype=np.float32)
    mask = np.zeros(x.shape[:2], dtype=bool)
    rng = np.random.default_rng(seed)
    scale = _robust_scale(source)
    severity = float(spec.severity)
    channels = np.asarray(spec.channels, dtype=np.int64)
    segment_length = end - start
    segment = np.arange(start, end)

    if spec.kind == "channel_swap":
        first, second = spec.channels
        temporary = x[start:end, first, :].copy()
        x[start:end, first, :] = x[start:end, second, :]
        x[start:end, second, :] = temporary
        mask[start:end, channels] = True
        # A channel identity error can look electrically healthy.  Keeping its
        # quality at one makes this a deliberately hard, evaluation-only case.
    elif spec.kind == "dropout":
        x[start:end, channels, :] = 0.0
        mask[start:end, channels] = True
        quality[start:end, channels] = 0.0
    elif spec.kind == "flatline":
        floor = np.quantile(source[:, channels, :], 0.01, axis=0)
        x[start:end, channels, :] = floor[None, :, :]
        mask[start:end, channels] = True
        quality[start:end, channels] = 0.05
    elif spec.kind == "broadband_noise":
        offset = (0.5 + 2.5 * severity) * scale[channels]
        jitter = rng.standard_t(df=4, size=(segment_length, len(channels), x.shape[2]))
        jitter *= (0.10 + 0.65 * severity) * scale[channels][None, :, :]
        x[start:end, channels, :] += offset[None, :, :] + jitter
        mask[start:end, channels] = True
        quality[start:end, channels] = max(0.05, 0.65 - 0.55 * severity)
    elif spec.kind == "mains_noise":
        weights = _mains_weights(x.shape[2])
        magnitude = (0.75 + 3.0 * severity) * scale[channels]
        x[start:end, channels, :] += magnitude[None, :, :] * weights[None, None, :]
        mask[start:end, channels] = True
        quality[start:end, channels] = max(0.10, 0.75 - 0.60 * severity)
    elif spec.kind == "drift":
        steps = rng.normal(size=(segment_length, len(channels)))
        walk = np.cumsum(steps, axis=0)
        walk -= walk.mean(axis=0, keepdims=True)
        denominator = walk.std(axis=0, keepdims=True)
        denominator[denominator < 1.0e-6] = 1.0
        walk /= denominator
        magnitude = (0.40 + 2.25 * severity) * scale[channels]
        # Contact drift is strongest in the low bands but can shift every DE
        # feature through changing electrode impedance.
        band_weights = np.linspace(1.0, 0.35, x.shape[2])
        x[start:end, channels, :] += (
            walk[:, :, None] * magnitude[None, :, :] * band_weights[None, None, :]
        )
        mask[start:end, channels] = True
        quality[start:end, channels] = max(0.10, 0.80 - 0.60 * severity)
    elif spec.kind == "burst":
        fraction = 0.05 + 0.30 * severity
        count = max(1, int(round(segment_length * fraction)))
        burst_windows = np.sort(rng.choice(segment, size=count, replace=False))
        perturbation = rng.standard_t(df=2.5, size=(count, len(channels), x.shape[2]))
        perturbation *= (1.0 + 3.5 * severity) * scale[channels][None, :, :]
        # np.ix_ keeps the channel and band axes independent.
        x[np.ix_(burst_windows, channels, np.arange(x.shape[2]))] += perturbation
        mask[np.ix_(burst_windows, channels)] = True
        quality[np.ix_(burst_windows, channels)] = max(0.02, 0.35 - 0.30 * severity)
    else:  # pragma: no cover - guarded by the Literal type, retained for runtime callers.
        raise ValueError(f"unsupported corruption kind: {spec.kind}")

    if not np.all(np.isfinite(x)):
        raise RuntimeError("corruption produced a non-finite feature")
    metadata = {
        "kind": spec.kind,
        "severity": severity,
        "channels": list(spec.channels),
        "start": start,
        "end": end,
        "seed": int(seed),
        "training_allowed": spec.kind in TRAINING_KINDS,
        "quality_semantics": "synthetic 0=unusable, 1=nominal",
    }
    return CorruptionResult(x, quality, mask, metadata)


def sample_training_corruption(
    features: np.ndarray,
    *,
    seed: int,
    max_channels: int = 3,
) -> CorruptionResult:
    """Sample one reproducible training episode from the allowed corruption set."""
    x = np.asarray(features)
    if x.ndim != 3:
        raise ValueError("features must have shape (windows, channels, bands)")
    if max_channels < 1:
        raise ValueError("max_channels must be positive")
    rng = np.random.default_rng(seed)
    count = int(rng.integers(1, min(max_channels, x.shape[1]) + 1))
    channels = tuple(sorted(int(value) for value in rng.choice(x.shape[1], count, replace=False)))
    length_low = max(1, int(np.ceil(0.10 * x.shape[0])))
    length_high = max(length_low, int(np.ceil(0.40 * x.shape[0])))
    length = int(rng.integers(length_low, length_high + 1))
    start = int(rng.integers(0, x.shape[0] - length + 1))
    kind = TRAINING_KINDS[int(rng.integers(0, len(TRAINING_KINDS)))]
    severity = float(rng.uniform(0.2, 1.0))
    # Use an independent seed so changing the sampling policy does not silently
    # change a selected corruption's noise realization.
    corruption_seed = int(rng.integers(0, np.iinfo(np.uint32).max, dtype=np.uint32))
    return apply_feature_corruption(
        x,
        CorruptionSpec(kind, severity, channels, start, length),
        seed=corruption_seed,
    )
