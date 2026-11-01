"""Recorded-data numerical gate for the isolated six-channel moment reducer.

This is an offline fixed-point emulation, not a measured PL or board speedup.
Run from any directory with Python, NumPy, and SciPy available.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from scipy import signal


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pynq_guardianloop"))
from cyton_covariance import BANDS, CovarianceSVM, log_covariance  # noqa: E402
from cyton_sqi import CausalEEGFilter  # noqa: E402

TRACE = ROOT / "eeg_apps_z15/output/pl_integrated_candidate_20260929/recorded_input.npz"
MODEL = ROOT / "pynq_guardianloop/gameemo_covariance_svm.npz"
MAP = (0, 1, 4, 5, 6, 7)  # F3,F4,T7,T8,O1,O2 in the fixed eight-cap order.
WINDOW = 3000
HOP = 2000


def fixed_feature(section, scale):
    quantized = np.rint(section * scale)
    overflowing = int(np.count_nonzero((quantized < -32768) | (quantized > 32767)))
    if overflowing:
        return None, overflowing
    q = quantized.astype(np.int64)
    sums = q.sum(axis=0, dtype=np.int64)
    gram = q.T @ q
    # Same ddof=1 covariance as np.cov; division stays on ARM.
    cov = (gram.astype(np.float64) - np.outer(sums, sums) / len(q)) / (len(q) - 1)
    cov /= scale * scale
    cov += 0.05 * np.trace(cov) / 6 * np.eye(6)
    eigenvalues, vectors = np.linalg.eigh(cov)
    matrix_log = (vectors * np.log(np.maximum(eigenvalues, 1e-12))) @ vectors.T
    upper = np.triu_indices(6)
    feature = matrix_log[upper]
    feature[upper[0] != upper[1]] *= np.sqrt(2)
    return feature, 0


def evaluate(trace_path, model_path):
    with np.load(trace_path, allow_pickle=False) as trace:
        raw = np.asarray(trace["recorded"], dtype=np.float64)
    conditioned = CausalEEGFilter().process(raw)[:, MAP]
    bands = [signal.sosfilt(signal.butter(4, band, fs=250,
                                      btype="bandpass", output="sos"),
                            conditioned, axis=0)
             for band in BANDS]
    model = CovarianceSVM(model_path)
    modes = {"q4": [], "q16": [], "q64": [], "adaptive_exploratory": []}
    for end in range(WINDOW, len(raw) + 1, HOP):
        sections = [band[end - WINDOW:end] for band in bands]
        reference = np.concatenate([log_covariance(section) for section in sections])
        reference_label, _, reference_scores = model.predict_feature(reference)
        for name in modes:
            parts, overflow_count, scales = [], 0, []
            for section in sections:
                if name == "adaptive_exploratory":
                    maximum = float(np.max(np.abs(section)))
                    scale = min(1024, 2 ** int(np.floor(np.log2(32767 / maximum)))) if maximum else 1024
                else:
                    scale = int(name[1:])
                feature, overflow = fixed_feature(section, scale)
                overflow_count += overflow
                scales.append(int(scale))
                if feature is not None:
                    parts.append(feature)
            result = {"end_sample": end, "overflow_samples": overflow_count,
                      "scales": scales}
            if overflow_count == 0:
                feature = np.concatenate(parts)
                label, _, scores = model.predict_feature(feature)
                result.update(feature_max_abs_error=float(np.max(np.abs(feature - reference))),
                              pair_score_max_abs_error=float(np.max(np.abs(
                                  np.asarray(scores) - np.asarray(reference_scores)))),
                              label_match=bool(label == reference_label))
            modes[name].append(result)
    summary = {}
    for name, windows in modes.items():
        valid = [w for w in windows if w["overflow_samples"] == 0]
        summary[name] = {
            "total_windows": len(windows), "nonoverflow_windows": len(valid),
            "overflow_samples_total": sum(w["overflow_samples"] for w in windows),
            "feature_max_abs_error": max((w["feature_max_abs_error"] for w in valid), default=None),
            "pair_score_max_abs_error": max((w["pair_score_max_abs_error"] for w in valid), default=None),
            "label_mismatches": sum(not w["label_match"] for w in valid),
            "window_details": windows,
        }
    return {
        "scope": "offline fixed-point emulation on a recorded, not necessarily SQI-accepted trace",
        "trace": str(trace_path),
        "trace_sha256": hashlib.sha256(trace_path.read_bytes()).hexdigest(),
        "model_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
        "channels": ["F3", "F4", "T7", "T8", "O1", "O2"],
        "bands_hz": BANDS, "window_samples": WINDOW, "hop_samples": HOP,
        "quantization": "signed 16-bit round-to-nearest; no silent clipping; 48-bit PL accumulators",
        "modes": summary,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", type=Path, default=TRACE)
    parser.add_argument("--model", type=Path, default=MODEL)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate(args.trace, args.model)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({name: {k: v for k, v in item.items() if k != "window_details"}
                      for name, item in result["modes"].items()}, indent=2))


if __name__ == "__main__":
    main()
