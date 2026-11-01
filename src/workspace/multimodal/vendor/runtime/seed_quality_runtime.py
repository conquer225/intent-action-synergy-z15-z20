"""Offline-candidate eight-channel runtime. Does not open hardware or publish results."""
from copy import deepcopy

import numpy as np

from cyton_sqi import CausalEEGFilter, CytonSQIMonitor, channel_sqi
from seed_replay_check import CausalResampler, FeatureStream

CHANNELS = ("F3", "F4", "C3", "C4", "T7", "T8", "O1", "O2")


class SeedQualityRuntime:
    def __init__(self, weights, channel_map=CHANNELS):
        if tuple(channel_map) != CHANNELS:
            raise ValueError("Fixed channel order is required")
        self.weight = np.asarray(weights["weight"], dtype=float)
        self.bias = np.asarray(weights["bias"], dtype=float)
        self.classes = np.asarray(weights["classes"])
        if (self.weight.shape != (3, 180) or self.bias.shape != (3,)
                or not np.array_equal(self.classes, [-1, 0, 1])
                or not np.isfinite(self.weight).all() or not np.isfinite(self.bias).all()):
            raise ValueError("Invalid SEED linear artifact")
        self.epoch = -1
        self.reset()

    def _reset_signal(self):
        self.prefilter = CausalEEGFilter()
        self.resampler = CausalResampler()
        self.features = FeatureStream()
        self.warming = True
        self.last_prediction = None

    def reset(self):
        self.epoch += 1
        self.mean = np.zeros(180)
        self.accepted_windows = 0
        self.pending = np.empty((0, 8))
        self.raw_mains_ratio = None
        # Fixed 2s segments: 60 accepted segments correspond to 120s SQI calibration.
        self.sqi = CytonSQIMonitor(calibration_windows=60)
        self._reset_signal()

    def disconnect(self, reason="disconnect"):
        self.reset()
        return self._event("reset", reason=reason)

    def _event(self, state, **fields):
        return {"state": state, "valid": state == "prediction", "epoch": self.epoch,
                "accepted_windows": self.accepted_windows, "raw_mains_ratio": self.raw_mains_ratio, **fields}

    def _accept_feature(self, feature):
        if np.asarray(feature).shape != (180,) or not np.isfinite(feature).all():
            self._reset_signal()
            return self._event("rejected", reason="invalid_feature")
        scores = None
        if self.accepted_windows >= 5:
            scores = self.weight @ (feature - self.mean) + self.bias
        # Only accepted complete windows reach this update; score uses preceding mean.
        self.mean += (feature - self.mean) / (self.accepted_windows + 1)
        self.accepted_windows += 1
        if scores is None:
            return self._event("calibrating")
        self.last_prediction = int(self.classes[np.argmax(scores)])
        return self._event("prediction", class_id=self.last_prediction, scores=scores.tolist(),
                           label_scope="SEED film condition; wearer accuracy unvalidated")

    def append(self, samples_uv, transport_ok=True):
        """Caller verifies counters/timeouts; false transport discards the whole supplied batch."""
        values = np.asarray(samples_uv, dtype=float)
        if values.ndim != 2 or values.shape[1] != 8:
            raise ValueError("Expected samples x 8")
        if not transport_ok:
            return [self.disconnect("transport_gap")]
        if not np.isfinite(values).all():
            return [self.disconnect("nonfinite_input")]
        self.pending = np.concatenate((self.pending, values))
        events = []
        while len(self.pending) >= 500:
            raw, self.pending = self.pending[:500], self.pending[500:]
            raw_sqi = channel_sqi(raw)
            self.raw_mains_ratio = raw_sqi[:, 4].tolist()
            raw_bad = (raw_sqi[:, 2] >= .95) | (np.mean(np.abs(raw) >= .95*187500, axis=0) > .001)
            if raw_bad.any():
                self._reset_signal()
                events.append(self._event("rejected", reason="raw_flat_or_adc_rail", bad_channels=(np.flatnonzero(raw_bad)+1).tolist()))
                continue
            filtered = self.prefilter.process(raw)
            resampled = self.resampler.process(filtered)
            if self.warming:
                self.features.process(resampled)
                self.warming = False
                events.append(self._event("warming"))
                continue
            # SQI calibration is transactional too: rejected segments cannot modify it.
            proposal = deepcopy(self.sqi)
            quality = proposal.process(filtered)
            if quality["usable_channels"] != 8:
                self._reset_signal()
                events.append(self._event("rejected", reason="sqi", bad_channels=quality["bad_channels"],
                    quality=quality["quality"], raw_mains_ratio=raw_sqi[:, 4].tolist()))
                continue
            self.sqi = proposal
            emitted = self.features.process(resampled)
            if not emitted:
                events.append(self._event("collecting"))
            for feature in emitted:
                events.append(self._accept_feature(feature))
        return events
