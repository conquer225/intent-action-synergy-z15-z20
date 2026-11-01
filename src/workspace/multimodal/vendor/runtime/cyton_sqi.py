"""ARM-side Cyton signal-quality monitoring and quality-gated emotion inference."""

import json
from functools import lru_cache
from pathlib import Path

import numpy as np
from scipy import signal


SQI_NAMES = ("robust_scale", "p99_abs", "flat_ratio", "clip_ratio",
             "mains_ratio", "hf_ratio", "step_ratio")
TRANSPORT_LIMIT_UV = 327.67
EPS = 1e-12


class CausalEEGFilter:
    """Filter the continuous Cyton stream before the narrow PL transport."""

    def __init__(self, sample_rate_hz=250):
        notch_b, notch_a = signal.iirnotch(50.0, 5.0, sample_rate_hz)
        notch = signal.tf2sos(notch_b, notch_a)
        band = signal.butter(4, (1.0, 45.0), btype="bandpass",
                             fs=sample_rate_hz, output="sos")
        self.sos = np.vstack((notch, band))
        self.zi = np.zeros((len(self.sos), 2, 8), dtype=np.float64)
        self.origin = None

    def process(self, samples_uv):
        values = np.asarray(samples_uv, dtype=np.float64)
        if values.ndim != 2 or values.shape[1] != 8:
            raise ValueError("filter expects samples x 8 channels")
        if not len(values):
            return values.copy()
        if self.origin is None:
            self.origin = values[0].copy()
        filtered, self.zi = signal.sosfilt(
            self.sos, values - self.origin, axis=0, zi=self.zi)
        return filtered


@lru_cache(maxsize=8)
def _sqi_spectral_constants(samples, sample_rate_hz):
    frequency = np.fft.rfftfreq(samples, 1 / sample_rate_hz)
    constants = (np.hanning(samples), (frequency >= 1) & (frequency <= 55),
                 (frequency >= 49) & (frequency <= 51),
                 (frequency >= 30) & (frequency <= 45))
    for value in constants:
        value.setflags(write=False)
    return constants


def channel_sqi(samples_uv, sample_rate_hz=250, channel_indices=None):
    values = np.asarray(samples_uv, dtype=np.float64)
    if values.ndim != 2 or values.shape[1] != 8:
        raise ValueError("SQI expects samples x 8 channels")
    if channel_indices is not None:
        values = values[:, channel_indices]
    values = values.T
    centered = values - np.median(values, axis=-1, keepdims=True)
    absolute = np.abs(centered)
    differences = np.diff(values, axis=-1)
    mad = 1.4826 * np.median(absolute, axis=-1) + EPS
    p99 = np.quantile(absolute, 0.99, axis=-1)
    flat = np.mean(np.abs(differences) <= 1e-3, axis=-1)
    # The Cyton/ADS1299 raw stream carries a large DC electrode offset. The
    # PL transport is centered per window, so test the same centered signal.
    clipped = np.mean(absolute >= TRANSPORT_LIMIT_UV - 0.01, axis=-1)
    step = np.max(np.abs(differences), axis=-1) / mad
    taper, total_band, mains_band, high_band = _sqi_spectral_constants(values.shape[-1], sample_rate_hz)
    power = np.abs(np.fft.rfft(centered * taper, axis=-1)) ** 2
    total = np.sum(power[:, total_band], axis=-1) + EPS
    mains = np.sum(power[:, mains_band], axis=-1) / total
    high = np.sum(power[:, high_band], axis=-1) / total
    return np.stack((mad, p99, flat, clipped, mains, high, step), axis=-1)


def _transform(sqi):
    output = sqi.copy()
    for index in (0, 1, 4, 5, 6):
        output[..., index] = np.log(output[..., index] + EPS)
    return output


class CytonSQIMonitor:
    def __init__(self, calibration_windows=15, segment_seconds=2, sample_rate_hz=250):
        self.calibration_windows = calibration_windows
        self.segment_samples = segment_seconds * sample_rate_hz
        self.sample_rate_hz = sample_rate_hz
        self.reference = [[] for _ in range(8)]
        self.center = np.zeros((8, len(SQI_NAMES)))
        self.scale = np.ones((8, len(SQI_NAMES)))
        self.threshold = np.full(8, 6.0)
        self.calibrated_channels = np.zeros(8, dtype=bool)

    def _heuristic_quality(self, sqi):
        p99, flat, clipped, mains, high, step = (sqi[..., i] for i in (1, 2, 3, 4, 5, 6))
        penalties = np.maximum.reduce((
            np.clip((p99 - 80) / 250, 0, 1), np.clip(flat / 0.95, 0, 1),
            np.clip(clipped / 0.01, 0, 1), np.clip((mains - 0.10) / 0.40, 0, 1),
            np.clip((high - 0.45) / 0.45, 0, 1), np.clip((step - 20) / 80, 0, 1),
        ))
        return 1.0 - penalties

    def process(self, samples_uv, transport_ok=True):
        values = np.asarray(samples_uv, dtype=np.float64)
        if values.ndim != 2 or values.shape[1] != 8 or len(values) < self.segment_samples:
            raise ValueError("SQI requires at least one complete 8-channel segment")
        transport = np.asarray(transport_ok, dtype=bool)
        if transport.ndim == 0:
            transport = np.full(8, bool(transport))
        if transport.shape != (8,):
            raise ValueError("transport_ok must be a bool or eight channel flags")
        count = values.shape[0] // self.segment_samples
        segments = values[:count * self.segment_samples].reshape(count, self.segment_samples, 8)
        descriptors = np.stack([channel_sqi(segment, self.sample_rate_hz) for segment in segments])
        heuristic = self._heuristic_quality(descriptors)
        hard_bad = (descriptors[..., 2] >= 0.95) | (descriptors[..., 3] > 0.001)
        for index in range(8):
            candidate = (transport[index] and not self.calibrated_channels[index]
                         and not np.any(hard_bad[:, index])
                         and np.min(heuristic[:, index]) >= 0.5)
            if not candidate:
                continue
            self.reference[index].extend(descriptors[:, index])
            if len(self.reference[index]) < self.calibration_windows * count:
                continue
            reference = _transform(np.asarray(self.reference[index]))
            self.center[index] = np.median(reference, axis=0)
            self.scale[index] = np.maximum(
                1.4826 * np.median(np.abs(reference - self.center[index]), axis=0), 0.10)
            worst = np.max(np.abs((reference - self.center[index]) / self.scale[index]), axis=-1)
            self.threshold[index] = max(6.0, float(np.quantile(worst, 0.995)))
            self.calibrated_channels[index] = True
        segment_quality = heuristic.copy()
        for index in np.flatnonzero(self.calibrated_channels):
            worst = np.max(np.abs(
                (_transform(descriptors[:, index]) - self.center[index]) / self.scale[index]),
                axis=-1)
            adaptive = 1 / (1 + np.exp(np.clip(
                (worst - self.threshold[index]) / 1.5, -40, 40)))
            segment_quality[:, index] = np.minimum(adaptive, heuristic[:, index])
        segment_quality[hard_bad] = 0.0
        segment_quality[:, ~transport] = 0.0
        calibrated = int(np.sum(self.calibrated_channels)) >= 6
        if calibrated:
            segment_quality[:, ~self.calibrated_channels] = 0.0
        quality = np.min(segment_quality, axis=0)
        usable = (quality >= 0.5) & (self.calibrated_channels if calibrated else True)
        latest = descriptors[-1]
        channels = []
        for index in range(8):
            reasons = []
            if np.max(descriptors[:, index, 3]) > 0.001: reasons.append("clipping")
            if np.max(descriptors[:, index, 2]) >= 0.95: reasons.append("flatline")
            if np.max(descriptors[:, index, 1]) > 100: reasons.append("amplitude")
            if np.max(descriptors[:, index, 4]) > 0.20: reasons.append("mains")
            if np.max(descriptors[:, index, 5]) > 0.55: reasons.append("high_frequency")
            if np.max(descriptors[:, index, 6]) > 40: reasons.append("step")
            if not transport[index]: reasons.append("transport")
            if calibrated and not self.calibrated_channels[index]: reasons.append("not_calibrated")
            if not usable[index] and not reasons: reasons.append("adaptive_outlier")
            channels.append({
                "index": index + 1, "quality": round(float(quality[index]), 4),
                "usable": bool(usable[index]), "downweighted": bool(not usable[index]),
                "calibrated": bool(self.calibrated_channels[index]),
                "calibration_current": min(self.calibration_windows,
                                           len(self.reference[index]) // count),
                "reasons": reasons,
                **{name: round(float(latest[index, j]), 6) for j, name in enumerate(SQI_NAMES)},
            })
        usable_count = int(np.sum(usable))
        state = "good" if usable_count == 8 else ("degraded" if usable_count >= 6 else "invalid")
        return {
            "version": "cyton-sqi-v2", "state": state,
            "calibrated": calibrated,
            "calibrated_channels": int(np.sum(self.calibrated_channels)),
            "calibration_current": sorted(
                (min(self.calibration_windows, len(items) // count) for items in self.reference),
                reverse=True)[5],
            "calibration_total": self.calibration_windows,
            "overall_quality": round(float(np.mean(quality)), 4),
            "usable_channels": usable_count, "bad_channels": [int(i) + 1 for i in np.flatnonzero(~usable)],
            "quality": [round(float(item), 4) for item in quality], "channels": channels,
        }


def emotion_features(samples_uv, source_rate_hz=250, sample_rate_hz=128,
                     window_seconds=4, bands=((4, 8), (8, 13), (13, 30), (30, 43))):
    """Band-major log variance of a prefiltered window, shared with training."""
    values = np.asarray(samples_uv, dtype=np.float64)
    needed = int(source_rate_hz * window_seconds)
    if values.ndim != 2 or len(values) < needed or not np.all(np.isfinite(values)):
        raise ValueError("emotion features require a finite, complete samples x channels window")
    resampled = signal.resample_poly(values[-needed:], sample_rate_hz, source_rate_hz, axis=0)
    resampled = resampled[:int(sample_rate_hz * window_seconds)].T
    return np.concatenate([
        np.log(np.var(signal.sosfiltfilt(
            signal.butter(4, band, btype="bandpass", fs=sample_rate_hz, output="sos"),
            resampled, axis=-1), axis=-1) + EPS) for band in bands
    ])


class GameemoEmotionRecognizer:
    def __init__(self, model_path):
        model = json.loads(Path(model_path).read_text(encoding="utf-8"))
        self.model = model
        self.sample_rate = int(model["sample_rate_hz"])
        self.window_samples = self.sample_rate * int(model["window_seconds"])
        self.bands = tuple(tuple(item) for item in model["bands_hz"])
        self.feature_median = np.asarray(model["feature_median"])
        self.mean = np.asarray(model["scaler_mean"])
        self.scale = np.asarray(model["scaler_scale"])
        self.coef = np.asarray(model["lda_coef"])
        self.intercept = np.asarray(model["lda_intercept"])
        self.classes = model["classes"]
        self.names = model["class_names"]
        self.channels = tuple(str(ch).upper() for ch in model["channels"])
        self.minimum_usable = int(model.get("minimum_usable_channels", 6))
        feature_count = len(self.channels) * len(self.bands)
        if (len(set(self.channels)) != len(self.channels)
                or not 1 <= self.minimum_usable <= len(self.channels)
                or self.mean.shape != (feature_count,)
                or self.scale.shape != (feature_count,)
                or self.feature_median.shape != (feature_count,)
                or self.coef.shape != (len(self.classes), feature_count)
                or self.intercept.shape != (len(self.classes),)
                or np.any(self.scale <= 0)):
            raise ValueError("inconsistent emotion model schema")

    def channel_indices(self, source_channel_map):
        names = tuple(str(ch).upper() for ch in source_channel_map)
        if len(set(names)) != len(names) or not set(self.channels).issubset(names):
            raise ValueError("emotion model channels missing or duplicated in acquisition map")
        return [names.index(channel) for channel in self.channels]

    def predict(self, samples_uv, quality, source_rate_hz=250, source_channel_map=None):
        values = np.asarray(samples_uv, dtype=np.float64)
        q = np.asarray(quality, dtype=np.float64)
        if values.ndim != 2 or q.shape != (values.shape[1],):
            raise ValueError("emotion quality must match input channels")
        if source_channel_map is not None:
            if len(source_channel_map) != values.shape[1]:
                raise ValueError("channel map must match input width")
            indexes = self.channel_indices(source_channel_map)
            values, q = values[:, indexes], q[indexes]
        elif values.shape[1] != len(self.channels):
            raise ValueError("explicit source channel map required")
        if not np.all(np.isfinite(q)) or np.any((q < 0) | (q > 1)):
            raise ValueError("quality weights must lie in [0,1]")
        features = emotion_features(values, source_rate_hz, self.sample_rate,
                                    self.model["window_seconds"], self.bands)
        for band in range(len(self.bands)):
            columns = slice(band * len(self.channels), (band + 1) * len(self.channels))
            features[columns] = q * features[columns] + (1 - q) * self.feature_median[columns]
        scores = ((features - self.mean) / self.scale) @ self.coef.T + self.intercept
        probabilities = np.exp(scores - np.max(scores)); probabilities /= np.sum(probabilities)
        choice = int(np.argmax(probabilities))
        usable = int(np.sum(q >= 0.5))
        valid = usable >= self.minimum_usable
        return {
            "valid": valid, "state": "prediction" if valid else "insufficient_signal",
            "class_id": int(self.classes[choice]), "label": self.names[choice],
            "confidence": round(float(probabilities[choice]), 4),
            "probabilities": {name: round(float(value), 4) for name, value in zip(self.names, probabilities)},
            "usable_channels": usable, "model_channels": list(self.channels),
            "minimum_usable_channels": self.minimum_usable,
            "algorithm_version": self.model.get("algorithm_version", "gameemo-maskaug-lda-v1"),
            "label_scope": "GAMEEMO game condition, not self-reported emotion",
            "deployment_status": self.model["deployment_status"],
        }
