"""Isolated, raw-microvolt SSVEP candidate; never emits actuator commands.

Pass eight-channel samples in the declared cap order, BEFORE the production
emotion/fatigue prefilter or PL quantization. Filter state persists across batches.
Packet parsing and wall-clock timeout detection belong to the caller; call
disconnect on a timeout and pass an unwrapped acquisition sample index to push.
"""
from __future__ import annotations

import os
import time
import numpy as np
from scipy.signal import sosfilt

from ssvep_core import CachedCCA, reference_bank


class SSVEPStream:
    def __init__(self, config: dict, sos: np.ndarray):
        self.config = config
        self.sos = np.asarray(sos, dtype=np.float64).copy()
        if self.sos.ndim != 2 or self.sos.shape[1] != 6 or not np.isfinite(self.sos).all():
            raise ValueError("Expected finite SOS coefficients")
        self.channels = config["selected_cap_indices"]
        self.window = config["window_samples"]
        self.hop = config["hop_samples"]
        self.warmup = config["warmup_samples"]
        if self.window < 4 or self.hop < 1 or self.warmup < 0:
            raise ValueError("Invalid window, hop or warmup")
        self.references = reference_bank(config["frequencies_hz"],
                                         sample_rate_hz=config["sample_rate_hz"],
                                         samples=self.window, harmonics=config["harmonics"])
        self.cca = CachedCCA(self.references)
        self.filter_seconds = 0.0
        self.decode_seconds = 0.0
        self.reset("startup")

    def reset(self, reason: str):
        self.zi = np.zeros((len(self.sos), 2, len(self.channels)), dtype=np.float64)
        self.origin = None
        self.buffer = np.empty((0, len(self.channels)), dtype=np.float64)
        self.last_filtered = self.buffer.copy()
        self.expected_index = None
        self.seen = 0
        self.next_emit = self.warmup + self.window
        self.latest = None
        self.status = "no_data"
        self.reset_reason = reason

    def disconnect(self):
        self.reset("disconnect")

    def _decision(self, end_index: int) -> dict:
        began = time.perf_counter()
        x = self.buffer.T
        centered = x - x.mean(axis=1, keepdims=True)
        singular = np.linalg.svd(centered, compute_uv=False)
        valid = bool(singular[0] > 0 and singular[-1] > singular[0] * 1e-8)
        event = {"status": "candidate_only" if valid else "signal_invalid",
                 "window_start_index": int(end_index - self.window),
                 "window_end_index_exclusive": int(end_index),
                 "control_enabled": False, "source": "replay_candidate"}
        if valid:
            scores = (self.cca.scores_rank2(x)
                      if os.environ.get('GUARDIANLOOP_EXPERIMENTAL_RANK2_CCA') == '1'
                      else self.cca.scores(x))
            order = np.argsort(scores)
            winner = int(order[-1])
            event.update(target_index=winner, frequency_hz=self.config["frequencies_hz"][winner],
                         scores=scores.tolist(), margin=float(scores[winner] - scores[order[-2]]))
        else:
            event.update(target_index=None, frequency_hz=None, scores=None, margin=None)
        self.latest = event
        self.status = event["status"]
        self.decode_seconds += time.perf_counter() - began
        return event

    def push(self, samples_uv: np.ndarray, first_index: int) -> list:
        values = np.asarray(samples_uv, dtype=np.float64)
        if values.ndim != 2 or values.shape[1] != len(self.config["fixed_cap"]):
            raise ValueError("Expected samples x eight fixed-cap channels")
        if not isinstance(first_index, (int, np.integer)) or first_index < 0:
            raise ValueError("first_index must be an unwrapped nonnegative integer")
        if not len(values):
            self.last_filtered = np.empty((0, len(self.channels)))
            return []
        if self.expected_index is not None and first_index != self.expected_index:
            self.reset("sample_discontinuity")
        selected = values[:, self.channels]
        if not np.isfinite(selected).all():
            self.reset("nonfinite_selected_input")
            self.status = "signal_invalid"
            return []
        if self.origin is None:
            self.origin = selected[0].copy()
        began = time.perf_counter()
        filtered, self.zi = sosfilt(self.sos, selected - self.origin, axis=0, zi=self.zi)
        self.filter_seconds += time.perf_counter() - began
        if not np.isfinite(filtered).all():
            self.reset("nonfinite_filter_output")
            self.status = "signal_invalid"
            return []
        self.last_filtered = filtered
        events = []
        offset = 0
        while offset < len(filtered):
            take = min(len(filtered) - offset, self.next_emit - self.seen)
            self.buffer = np.concatenate((self.buffer, filtered[offset:offset + take]))[-self.window:]
            self.seen += take
            offset += take
            if self.seen == self.next_emit:
                events.append(self._decision(first_index + offset))
                self.next_emit += self.hop
        self.expected_index = int(first_index + len(values))
        if self.seen < self.warmup + self.window:
            self.status = "warmup"
        return events
