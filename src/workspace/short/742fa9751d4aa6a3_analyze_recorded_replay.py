"""Compare verified PL replay bytes with the board's ARM filter and downstream CPU path."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def signature(quality):
    return (quality["state"], quality["calibrated"], tuple(quality["bad_channels"]),
            tuple((channel["calibrated"], channel["usable"])
                  for channel in quality["channels"]))


def run(raw_path, output_path, runtime_dir, fatigue_model_path, report_path):
    sys.path.insert(0, str(runtime_dir.resolve()))
    from cyton_sqi import CausalEEGFilter, CytonSQIMonitor
    from cyton_covariance import CovarianceFeatureStream, CovarianceSVM
    from cyton_fatigue import FourChannelDEStream, FourChannelFatigue

    raw = np.load(raw_path)
    if raw.ndim != 2 or raw.shape[1] != 8 or len(raw) % 10:
        raise ValueError("Raw input must be whole 10x8 frames")
    pl_bytes = output_path.read_bytes()
    if len(pl_bytes) != raw.size * 8:
        raise ValueError("PL output length mismatch")
    pl_words = np.frombuffer(pl_bytes, dtype="<i8").reshape(raw.shape)
    pl = pl_words.astype(np.float64) / 65536.0
    arm_filter = CausalEEGFilter()
    arm = np.empty_like(raw)
    filter_times = []
    start_filter = time.perf_counter()
    for start in range(0, len(raw), 10):
        begin = time.perf_counter()
        arm[start : start + 10] = arm_filter.process(raw[start : start + 10])
        filter_times.append((time.perf_counter() - begin) * 1000)
    total_filter_ms = (time.perf_counter() - start_filter) * 1000
    differences = pl - arm
    streams = [CovarianceFeatureStream(("F3", "F4", "C3", "C4", "T7", "T8", "O1", "O2"))
               for _ in range(2)]
    fatigue = [FourChannelDEStream() for _ in range(2)]
    monitors = [CytonSQIMonitor() for _ in range(2)]
    models = [CovarianceSVM(runtime_dir / "gameemo_covariance_svm.npz") for _ in range(2)]
    fatigue_models = [FourChannelFatigue(fatigue_model_path) for _ in range(2)]
    quality_differences = []
    emotion_differences = []
    fatigue_differences = []
    max_cov_diff = max_de_diff = max_emotion_score_diff = 0.0
    diagnostic_emotion_count = 0
    valid_emotion_count = valid_fatigue_count = 0
    start_downstream = time.perf_counter()
    for start in range(0, len(raw), 250):
        end = min(start + 250, len(raw))
        for index, values in enumerate((arm, pl)):
            streams[index].append(values[start:end])
            fatigue[index].append(values[start:end])
            fatigue_models[index].append(values[start:end])
        if end % 2000 == 0:
            q = [monitors[i].process(values[end-2000:end])
                 for i, values in enumerate((arm, pl))]
            if signature(q[0]) != signature(q[1]):
                quality_differences.append(end)
            features = [stream.features() for stream in fatigue]
            max_de_diff = max(max_de_diff, float(np.max(np.abs(features[0]-features[1]))))
            required_ok = [all(q[i]["channels"][ch]["quality"] >= 0.5
                               for ch in (4, 5, 6, 7)) for i in range(2)]
            results = [fatigue_models[i].process_window(required_ok[i], True)
                       for i in range(2)]
            if (results[0]["valid"], results[0]["state"]) != (results[1]["valid"], results[1]["state"]):
                fatigue_differences.append(end)
            valid_fatigue_count += int(results[0]["valid"] and results[1]["valid"])
            valid_emotion_count += int(all(all(q[i]["quality"][ch] >= 0.5
                                               for ch in (0, 1, 4, 5, 6, 7))
                                           for i in range(2)))
        if streams[0].ready and end % 500 == 0:
            features = [stream.feature() for stream in streams]
            max_cov_diff = max(max_cov_diff, float(np.max(np.abs(features[0]-features[1]))))
            pred = [model.predict_feature(feature) for model, feature in zip(models, features)]
            diagnostic_emotion_count += 1
            max_emotion_score_diff = max(max_emotion_score_diff,
                                         float(np.max(np.abs(np.asarray(pred[0][2])-pred[1][2]))))
            if pred[0][0] != pred[1][0]:
                emotion_differences.append(end)
    downstream_ms = (time.perf_counter() - start_downstream) * 1000
    report = {
        "scope": "existing-record accelerated replay; no live Cyton, no labels/accuracy; "
                 "diagnostic classifier outputs include rejected windows",
        "samples": len(raw), "frames": len(raw) // 10,
        "source_sha256": sha256(raw_path), "verified_pl_output_sha256": sha256(output_path),
        "model_sha256": sha256(runtime_dir / "gameemo_covariance_svm.npz"),
        "fatigue_model_sha256": sha256(fatigue_model_path),
        "filter_max_abs_error_uv": float(np.max(np.abs(differences))),
        "filter_rms_error_uv": float(np.sqrt(np.mean(differences ** 2))),
        "arm_filter_wall_ms": total_filter_ms,
        "arm_filter_batch_median_ms": float(np.median(filter_times)),
        "arm_filter_batch_p95_ms": float(np.percentile(filter_times, 95)),
        "downstream_both_paths_wall_ms": downstream_ms,
        "quality_state_difference_end_samples": quality_differences,
        "fatigue_state_difference_end_samples": fatigue_differences,
        "diagnostic_emotion_class_difference_end_samples": emotion_differences,
        "diagnostic_emotion_window_count": diagnostic_emotion_count,
        "quality_usable_both_window_count": valid_emotion_count,
        "fatigue_valid_both_window_count": valid_fatigue_count,
        "max_cov_feature_abs_difference": max_cov_diff,
        "max_de_feature_abs_difference": max_de_diff,
        "max_emotion_score_abs_difference": max_emotion_score_diff,
    }
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--pl-output", type=Path, required=True)
    parser.add_argument("--runtime-dir", type=Path, required=True)
    parser.add_argument("--fatigue-model", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    run(args.raw, args.pl_output, args.runtime_dir,
        args.fatigue_model or args.runtime_dir / "cyton_fatigue_overlap4.json", args.report)
