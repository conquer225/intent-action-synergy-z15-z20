"""Isolated ARM/PC replay benchmark. No serial device, service, PL or web writes."""

import argparse
import json
import platform
import time
from pathlib import Path

import numpy as np
import scipy
from scipy import signal

from cyton_covariance import log_covariance
from cyton_sqi import CausalEEGFilter

BANDS = ((1, 4), (4, 8), (8, 14), (14, 31), (31, 45))


class CausalResampler:
    """4/5 rational conversion; 50ms FIR delay, no future samples or end padding."""
    def __init__(self):
        self.h = 4 * signal.firwin(101, .2, window=("kaiser", 5))
        self.reset()

    def reset(self):
        self.zi = np.zeros((100, 8))
        self.count = 0

    def process(self, x):
        up = np.zeros((len(x) * 4, 8))
        up[::4] = x
        filtered, self.zi = signal.lfilter(self.h, [1.], up, axis=0, zi=self.zi)
        start = (-self.count) % 5
        self.count += len(up)
        return filtered[start::5]


class FeatureStream:
    def __init__(self):
        self.sos = [signal.butter(4, b, fs=200, btype="bandpass", output="sos") for b in BANDS]
        self.reset()

    def reset(self):
        self.zi = [np.zeros((len(s), 2, 8)) for s in self.sos]
        self.pending = np.empty((5, 0, 8))
        self.warmup = 400

    def process(self, x):
        if not len(x):
            return []
        bands = []
        for i, sos in enumerate(self.sos):
            filtered, self.zi[i] = signal.sosfilt(sos, x, axis=0, zi=self.zi[i])
            bands.append(filtered)
        filtered = np.stack(bands)
        discard = min(self.warmup, len(x))
        self.warmup -= discard
        self.pending = np.concatenate((self.pending, filtered[:, discard:]), axis=1)
        output = []
        while self.pending.shape[1] >= 2400:
            output.append(np.concatenate([log_covariance(b[:2400]) for b in self.pending]))
            self.pending = self.pending[:, 2400:]
        return output


def replay(values, weights, rate, conditioned=False, chunks=250):
    resampler = CausalResampler() if rate == 250 else None
    prefilter = CausalEEGFilter() if conditioned else None
    stream = FeatureStream()
    features, scores, timings = [], [], []
    mean = np.zeros(180)
    count = 0
    for start in range(0, len(values), chunks):
        stamp = time.perf_counter()
        x = values[start:start + chunks]
        if prefilter is not None:
            x = prefilter.process(x)
        if resampler is not None:
            x = resampler.process(x)
        for feature in stream.process(x):
            features.append(feature)
            if count >= 5:
                scores.append(weights["weight"] @ (feature - mean) + weights["bias"])
            mean += (feature - mean) / (count + 1)
            count += 1
        timings.append(time.perf_counter() - stamp)
    return np.asarray(features), np.asarray(scores).reshape(-1, 3), np.asarray(timings)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--weights", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    data = dict(np.load(args.input, allow_pickle=False))
    weights = dict(np.load(args.weights, allow_pickle=False))
    arrays, reports = {}, {}
    for name, rate, conditioned in [("seed", 200, False), ("cyton", 250, False), ("conditioned", 250, True)]:
        values = data["seed"] if name == "seed" else data["cyton"]
        runs = []
        for iteration in range(4):
            feature, scores, timing = replay(values, weights, rate, conditioned)
            if iteration:
                runs.extend(timing.tolist())
        arrays[name + "_features"] = feature
        arrays[name + "_scores"] = scores
        arrays[name + "_classes"] = weights["classes"][scores.argmax(axis=1)] if len(scores) else np.array([], dtype=int)
        reports[name] = {"windows": len(feature), "score_windows": len(scores),
            "timed_runs": 3, "warmup_runs": 1, "chunk_samples": 250,
            "chunk_ms_median": float(np.median(runs)*1000), "chunk_ms_p95": float(np.quantile(runs, .95)*1000),
            "chunk_ms_max": float(np.max(runs)*1000), "replay_seconds_mean": float(sum(runs)/3),
            "input_seconds": len(values)/rate}
    np.savez(output / "arrays.npz", **arrays)
    report = {"platform": platform.platform(), "numpy": np.__version__, "scipy": scipy.__version__,
        "cases": reports, "scope": "ARM preprocessing+features+adaptation+linear scores; excludes acquisition wait, SQI, web, DMA and PL",
        "warning": "Existing unlabelled recording, longest packet-contiguous segment only; scores are diagnostic not validated emotion",
        "resampler": "101-tap causal FIR, up4/down5, delay50ms; unlike zero-phase resample_poly"}
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
