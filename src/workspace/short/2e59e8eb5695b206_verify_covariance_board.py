"""Offline synthetic ARM check: stream parity, model label and processing time."""

import json
import time
from pathlib import Path

import numpy as np
from scipy import signal

from cyton_covariance import BANDS, CovarianceFeatureStream, CovarianceSVM, log_covariance
from cyton_sqi import CausalEEGFilter


def main():
    rng = np.random.default_rng(20260925)
    raw = rng.normal(0, 12, (4200, 8))
    raw[:, 6] += 3 * np.sin(2 * np.pi * 10 * np.arange(4200) / 250)
    conditioned = CausalEEGFilter().process(raw)
    stream = CovarianceFeatureStream(("F3", "F4", "C3", "C4", "T7", "T8", "O1", "O2"))
    start = time.perf_counter()
    for start_index in range(0, len(conditioned), 125):
        stream.append(conditioned[start_index:start_index + 125])
    stream_seconds = time.perf_counter() - start
    start = time.perf_counter()
    feature = stream.feature()
    feature_seconds = time.perf_counter() - start
    expected = np.concatenate([
        log_covariance(signal.sosfilt(
            signal.butter(4, band, fs=250, btype="bandpass", output="sos"),
            conditioned[:, stream.indexes], axis=0)[-3000:])
        for band in BANDS])
    error = float(np.max(np.abs(feature - expected)))
    model = CovarianceSVM(Path(__file__).with_name("gameemo_covariance_svm.npz"))
    start = time.perf_counter()
    label, votes, _ = model.predict_feature(feature)
    prediction_seconds = time.perf_counter() - start
    print(json.dumps({"stream_seconds_for_4200_samples": stream_seconds,
                      "feature_seconds": feature_seconds,
                      "prediction_seconds": prediction_seconds,
                      "feature_max_abs_error": error,
                      "feature_sum": float(feature.sum()),
                      "label": label, "votes": votes}, sort_keys=True))
    if error > 1e-8:
        raise SystemExit("streaming feature mismatch")


if __name__ == "__main__":
    main()
