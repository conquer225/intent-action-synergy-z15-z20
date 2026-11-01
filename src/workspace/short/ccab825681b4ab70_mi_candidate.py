"""Portable, non-control motor-imagery candidate for a cued 3-second EEG trial."""

import json
from pathlib import Path

import numpy as np

from mi_features import CHANNELS, WINDOW_SAMPLES, feature


class MotorImageryCandidate:
    def __init__(self, model_path):
        with np.load(Path(model_path), allow_pickle=False) as model:
            self.mean = model["mean"].astype(np.float64)
            self.scale = model["scale"].astype(np.float64)
            self.coef = model["coef"].astype(np.float64)
            self.intercept = float(model["intercept"])
            self.columns = model["columns"].astype(np.int64)
            self.metadata = json.loads(str(model["metadata"].item()))
        width = len(self.columns)
        if (tuple(self.metadata["channels"]) != CHANNELS
                or self.metadata["window_samples"] != WINDOW_SAMPLES
                or self.metadata["source_rate_hz"] != 250
                or self.metadata["control_enabled"] is not False
                or not self.metadata["promotion_gate_passed"]
                or not np.array_equal(self.columns, sorted(set(self.columns)))
                or np.any((self.columns < 0) | (self.columns >= 16))
                or self.mean.shape != (width,) or self.scale.shape != (width,)
                or self.coef.shape != (width,) or np.any(self.scale <= 0)
                or not np.isfinite(self.mean).all() or not np.isfinite(self.scale).all()
                or not np.isfinite(self.coef).all() or not np.isfinite(self.intercept)):
            raise ValueError("invalid or unpromoted fixed-cap MI artifact")
        self.required_indices = tuple(sorted(set(int(column % 8) for column in self.columns)))

    def predict(self, conditioned_window_uv, quality, *, cue_active, transport_ok):
        if not cue_active:
            return {"valid": False, "state": "cue_required", "control_enabled": False}
        if not transport_ok:
            return {"valid": False, "state": "transport_invalid", "control_enabled": False}
        q = np.asarray(quality, dtype=np.float64)
        if q.shape != (8,) or not np.isfinite(q).all() or np.any(q[list(self.required_indices)] < .5):
            return {"valid": False, "state": "signal_invalid", "control_enabled": False}
        vector = feature(conditioned_window_uv)[self.columns]
        score = float(self.coef @ ((vector - self.mean) / self.scale) + self.intercept)
        return {"valid": True, "state": "candidate_only",
                "label": "right_fist_imagery" if score >= 0 else "left_fist_imagery",
                "decision_score": score, "model_channels": [CHANNELS[i] for i in self.required_indices],
                "control_enabled": False,
                "note": "Cue-locked public-data candidate; Cyton accuracy and false-trigger rate unverified"}
