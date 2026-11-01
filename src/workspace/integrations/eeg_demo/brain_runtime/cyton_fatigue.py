"""Board-local four-channel SEED-VIG fatigue candidate for the fixed Cyton cap.

CH5–CH8 are T7, T8, O1, O2. The other four physical channels are never
renamed or silently imputed. Filtering and HGB inference run on Z15 ARM.
"""

import json
import math
from pathlib import Path

import numpy as np
from scipy.signal import butter, sosfilt


BANDS = (("delta", 1.0, 4.0), ("theta", 4.0, 8.0),
         ("alpha", 8.0, 14.0), ("beta", 14.0, 31.0),
         ("gamma", 31.0, 50.0))
CHANNELS = ("T7", "T8", "O1", "O2")
PHYSICAL_INDICES = (4, 5, 6, 7)
RATE_HZ = 250
WINDOW_SAMPLES = 2000


class FourChannelDEStream:
    """Filter only newly arrived samples; never replay an overlapping window."""

    def __init__(self):
        self.sos = [butter(4, (low, high), btype="bandpass", fs=RATE_HZ,
                           output="sos") for _, low, high in BANDS]
        self.reset()

    def reset(self):
        self.zi = [np.zeros((len(sos), 2, 4), dtype=np.float64) for sos in self.sos]
        self.ring = np.zeros((WINDOW_SAMPLES, 4, len(BANDS)), dtype=np.float64)
        self.offset = 0
        self.seen = 0

    def append(self, filtered_uv):
        values = np.asarray(filtered_uv, dtype=np.float64)
        if values.ndim != 2 or values.shape[1] != 8 or not np.all(np.isfinite(values)):
            raise ValueError("Expected finite sample-by-eight filtered EEG")
        count = len(values)
        if count < 1 or count > WINDOW_SAMPLES:
            raise ValueError("Invalid DE stream chunk")
        selected = values[:, PHYSICAL_INDICES]
        outputs = []
        for index, sos in enumerate(self.sos):
            filtered, self.zi[index] = sosfilt(sos, selected, axis=0, zi=self.zi[index])
            outputs.append(filtered)
        stacked = np.stack(outputs, axis=-1)
        positions = (np.arange(count) + self.offset) % WINDOW_SAMPLES
        self.ring[positions] = stacked
        self.offset = (self.offset + count) % WINDOW_SAMPLES
        self.seen += count

    def features(self):
        if self.seen < WINDOW_SAMPLES:
            return None
        variance = np.var(self.ring, axis=0)
        output = 0.5 * np.log(2.0 * np.pi * np.e * np.maximum(variance, 1e-12))
        return output.reshape(-1)


class FourChannelFatigue:
    def __init__(self, model_path):
        self.path = Path(model_path)
        model = json.loads(self.path.read_text(encoding="utf-8"))
        if (model.get("format") != "cyton_fatigue_hgb_v1" or
            tuple(model.get("channels", ())) != CHANNELS or
            tuple(model.get("physical_indices", ())) != PHYSICAL_INDICES or
            tuple(tuple(band) for band in model.get("bands_hz", ())) != BANDS or
            int(model.get("window_seconds", 0)) != 8 or
            int(model.get("hop_seconds", 0)) != 8):
            raise ValueError("Fatigue model feature/montage contract mismatch")
        self.model = model
        self.stream = FourChannelDEStream()
        self.reset()

    def reset(self):
        self.baseline = []
        self.mean = None
        self.scale = None
        self.window = 0
        self.reset_stream()

    def reset_stream(self):
        """Discard interrupted samples and predictions, retaining accepted calibration."""
        self.stream.reset()
        self.ema = None
        self.diagnostics = None

    def append(self, filtered_uv):
        self.stream.append(filtered_uv)

    def _predict(self, values):
        estimate = float(self.model["baseline_prediction"])
        for tree in self.model["trees"]:
            index = 0
            while not tree[index][6]:
                node = tree[index]
                feature = float(values[int(node[1])])
                left = bool(node[5]) if math.isnan(feature) else feature <= float(node[2])
                index = int(node[3] if left else node[4])
            estimate += float(tree[index][0])
        return min(1.0, max(0.0, estimate))

    def process_window(self, quality_ok, transport_ok):
        self.diagnostics = None
        self.window += 1
        result = {"window": self.window, "valid": False, "state": "INVALID",
                  "calibration_current": len(self.baseline),
                  "calibration_total": int(self.model["calibration_windows"]),
                  "fatigue_model_channels": list(CHANNELS),
                  "fatigue_feature_backend": "Z15_ARM_continuous_DE"}
        features = self.stream.features()
        if features is None:
            result["reason"] = "FEATURE_WARMUP"
            return result
        if not transport_ok:
            result["reason"] = "TRANSPORT"
            return result
        if not quality_ok:
            result["reason"] = "REQUIRED_CHANNEL_QUALITY"
            return result
        self.diagnostics = {'kind':'differential_entropy','shape':[4,5],
                            'bands_hz':[list(band[1:]) for band in BANDS],
                            'channels':list(CHANNELS),'values':features.tolist()}
        if self.mean is None:
            self.baseline.append(features)
            result.update(valid=True, state="CALIBRATING",
                          calibration_current=len(self.baseline))
            if len(self.baseline) == int(self.model["calibration_windows"]):
                baseline = np.stack(self.baseline)
                self.mean = baseline.mean(axis=0)
                self.scale = baseline.std(axis=0)
                self.scale[self.scale < 1e-6] = 1.0
                result["calibration_ready"] = True
            return result
        calibrated = (features - self.mean) / self.scale
        alpha = float(self.model["ema_alpha"])
        self.ema = (calibrated.copy() if self.ema is None else
                    alpha * calibrated + (1.0 - alpha) * self.ema)
        perclos = self._predict(self.ema)
        lower, upper = self.model["thresholds"]
        level = 0 if perclos < lower else 1 if perclos < upper else 2
        result.update(valid=True, state=("NORMAL", "MILD", "SEVERE")[level],
                      level=level, perclos=perclos, smoothed_perclos=perclos,
                      calibration_current=len(self.baseline))
        return result
