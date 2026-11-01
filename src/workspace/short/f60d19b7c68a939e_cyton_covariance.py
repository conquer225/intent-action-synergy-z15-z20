"""Streaming GAMEEMO six-channel covariance features and NumPy SVM inference.

The input is the continuous 250 Hz output of CausalEEGFilter. This module
does not use PL and does not repair bad electrodes or infer true emotion labels.
"""

import json
from collections import deque
from pathlib import Path

import numpy as np
from scipy import signal


CHANNELS = ("F3", "F4", "T7", "T8", "O1", "O2")
BANDS = ((1, 4), (4, 8), (8, 13), (13, 30), (30, 43))
RATE_HZ = 250
WINDOW_SAMPLES = 12 * RATE_HZ


def log_covariance(section):
    covariance = np.cov(section, rowvar=False)
    dimension = covariance.shape[0]
    covariance += 0.05 * (np.trace(covariance) / dimension) * np.eye(dimension)
    eigenvalues, vectors = np.linalg.eigh(covariance)
    matrix_log = (vectors * np.log(np.maximum(eigenvalues, 1e-12))) @ vectors.T
    upper = np.triu_indices(dimension)
    features = matrix_log[upper]
    features[upper[0] != upper[1]] *= np.sqrt(2)
    return features


class CovarianceFeatureStream:
    def __init__(self, channel_map, *, storage="deque"):
        if storage not in ("deque", "array"):
            raise ValueError("unknown covariance storage")
        self.storage = storage
        names = tuple(str(name).upper() for name in channel_map)
        if len(names) != 8 or len(set(names)) != 8 or not set(CHANNELS).issubset(names):
            raise ValueError("six model channels missing or duplicated in acquisition map")
        self.indexes = [names.index(name) for name in CHANNELS]
        self.sos = [signal.butter(4, band, fs=RATE_HZ, btype="bandpass", output="sos")
                    for band in BANDS]
        self.reset()

    def reset(self):
        self.zi = [np.zeros((len(sos), 2, 6), dtype=np.float64) for sos in self.sos]
        if self.storage == "deque":
            self.rows = [deque(maxlen=WINDOW_SAMPLES) for _ in BANDS]
        else:
            self.ring = np.zeros((len(BANDS), WINDOW_SAMPLES, 6), dtype=np.float64)
            self.offset = 0
            self.seen = 0

    def append(self, conditioned_samples):
        values = np.asarray(conditioned_samples, dtype=np.float64)
        if values.ndim != 2 or values.shape[1] != 8 or not np.isfinite(values).all():
            raise ValueError("expected finite samples x 8 conditioned EEG")
        selected = values[:, self.indexes]
        if not len(values):
            return
        for band_index, sos in enumerate(self.sos):
            filtered, self.zi[band_index] = signal.sosfilt(
                sos, selected, axis=0, zi=self.zi[band_index])
            if self.storage == "deque":
                self.rows[band_index].extend(filtered)
            else:
                kept = filtered[-WINDOW_SAMPLES:]
                end = (self.offset + len(values)) % WINDOW_SAMPLES
                start = (end - len(kept)) % WINDOW_SAMPLES
                first = min(len(kept), WINDOW_SAMPLES - start)
                self.ring[band_index, start:start+first] = kept[:first]
                self.ring[band_index, :len(kept)-first] = kept[first:]
        if self.storage == "array":
            self.offset = (self.offset + len(values)) % WINDOW_SAMPLES
            self.seen += len(values)

    @property
    def ready(self):
        return (self.seen >= WINDOW_SAMPLES if self.storage == "array"
                else len(self.rows[0]) == WINDOW_SAMPLES)

    def feature(self):
        if not self.ready:
            raise ValueError("12 seconds of continuous EEG are required")
        if self.storage == "deque":
            sections = [np.asarray(rows) for rows in self.rows]
        else:
            # Keep chronological order, including the covariance reduction order.
            sections = [np.concatenate((band[self.offset:], band[:self.offset]))
                        if self.offset else band for band in self.ring]
        return np.concatenate([log_covariance(section) for section in sections])


class CovarianceSVM:
    def __init__(self, model_path):
        path = Path(model_path)
        with np.load(path, allow_pickle=False) as model:
            self.mean = model["mean"].astype(np.float64)
            self.scale = model["scale"].astype(np.float64)
            self.support = model["support"].astype(np.float64)
            self.dual = model["dual"].astype(np.float64)
            self.intercept = model["intercept"].astype(np.float64)
            self.counts = model["counts"].astype(np.int64)
            self.classes = model["classes"].astype(np.int64)
            self.gamma = float(model["gamma"])
            self.metadata = json.loads(str(model["metadata"].item()))
        if (tuple(self.metadata["channels"]) != CHANNELS
                or tuple(map(tuple, self.metadata["bands_hz"])) != BANDS
                or self.metadata["window_seconds"] != 12
                or self.support.ndim != 2 or self.support.shape[1] != 105
                or self.mean.shape != (105,) or self.scale.shape != (105,)
                or np.any(self.scale <= 0)
                or self.dual.shape != (3, len(self.support))
                or self.counts.shape != (4,) or self.counts.sum() != len(self.support)
                or self.intercept.shape != (6,) or self.classes.shape != (4,)):
            raise ValueError("inconsistent covariance SVM artifact")
        self.support_norm = np.einsum("ij,ij->i", self.support, self.support)
        self.starts = np.r_[0, np.cumsum(self.counts)]

    def predict_feature(self, feature):
        vector = np.asarray(feature, dtype=np.float64)
        if vector.shape != (105,) or not np.isfinite(vector).all():
            raise ValueError("expected finite 105-element covariance feature")
        x = (vector - self.mean) / self.scale
        distance = np.maximum(self.support_norm + x @ x - 2 * (self.support @ x), 0)
        kernel = np.exp(-self.gamma * distance)
        votes = np.zeros(4, dtype=np.int64)
        pair_scores = []
        pair = 0
        for i in range(4):
            for j in range(i + 1, 4):
                left = slice(self.starts[i], self.starts[i + 1])
                right = slice(self.starts[j], self.starts[j + 1])
                score = (kernel[left] @ self.dual[j - 1, left]
                         + kernel[right] @ self.dual[i, right]
                         + self.intercept[pair])
                votes[i if score > 0 else j] += 1
                pair_scores.append(float(score))
                pair += 1
        choice = int(np.argmax(votes))
        return int(self.classes[choice]), votes.tolist(), pair_scores

    def predict(self, stream, quality):
        q = np.asarray(quality, dtype=np.float64)
        if q.shape != (6,) or not np.isfinite(q).all():
            raise ValueError("expected six channel quality values")
        usable = int(np.count_nonzero(q >= 0.5))
        if not stream.ready:
            return {"valid": False, "state": "collecting_12s", "usable_channels": usable}
        if usable < 6:
            return {"valid": False, "state": "insufficient_signal", "usable_channels": usable}
        label, votes, pair_scores = self.predict_feature(stream.feature())
        names = self.metadata["class_names"]
        return {"valid": True, "state": "prediction", "class_id": label,
                "label": names[label], "confidence": None,
                "label_scope": self.metadata["label_type"],
                "votes": votes, "pair_scores": pair_scores,
                "usable_channels": usable, "model_channels": list(CHANNELS),
                "minimum_usable_channels": 6,
                "algorithm_version": self.metadata["algorithm_version"],
                "deployment_status": "GAMEEMO game-condition candidate; Cyton accuracy unvalidated"}
