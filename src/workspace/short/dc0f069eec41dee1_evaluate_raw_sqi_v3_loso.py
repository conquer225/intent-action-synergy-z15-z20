#!/usr/bin/env python3
"""Participant-grouped raw-domain SQI-v3 comparison against frozen features.

This script is initially used as a smoke test. The publishable run must use all
participants, all declared corruption families, three seeds, and severities.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor


HERE = Path(__file__).resolve().parent
REFERENCE_DIR = Path(r"D:\ican\ican_fpga_project\software\pc_fatigue_reference")
if str(REFERENCE_DIR) not in sys.path:
    sys.path.insert(0, str(REFERENCE_DIR))

from fatigue_reference import channel_indices, extract_band_de_features, load_seedvig_subject
from validate_seedvig_loso import DEFAULT_DATASET_ROOT, discover_pairs, participant_id

from evaluate_hgb_robustness import CHANNELS, stable_seed
from evaluate_quality_aware_hgb import QUALITY_MODEL_PARAMETERS, QUALITY_THRESHOLD, quality_features
from raw_corruptions import RAW_CORRUPTION_KINDS, RawCorruptionSpec, apply_raw_corruption
from raw_sqi_features import extract_raw_sqi_features


CALIBRATION_WINDOWS = 15
CONTEXT_WINDOWS = 4
DEFAULT_TRAIN_SEVERITIES = (0.25, 0.50, 0.75)
DEFAULT_TEST_SEVERITY = 0.75


@dataclass
class FeatureBlock:
    v2: np.ndarray
    v3: np.ndarray
    quality: np.ndarray
    mask: np.ndarray


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, default=DEFAULT_DATASET_ROOT)
    parser.add_argument("--output-dir", type=Path, default=HERE / "results" / "_smoke_raw_sqi_v3")
    parser.add_argument("--max-participants", type=int, default=4)
    parser.add_argument("--train-severities", type=float, nargs="+", default=list(DEFAULT_TRAIN_SEVERITIES))
    parser.add_argument("--test-severity", type=float, default=DEFAULT_TEST_SEVERITY)
    parser.add_argument("--experiment-seed", type=int, default=0)
    parser.add_argument(
        "--kinds", nargs="+", default=["flatline", "broadband_noise", "cable_motion"],
        choices=RAW_CORRUPTION_KINDS,
    )
    return parser.parse_args()


def calibrate(values: np.ndarray, baseline: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    mean = baseline.mean(axis=0)
    scale = baseline.std(axis=0)
    scale = np.where(scale < 1.0e-6, 1.0, scale)
    return (values - mean) / scale, mean, scale


def combine_features(de_values: np.ndarray, raw_values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    windows = len(de_values)
    v2 = quality_features(de_values).reshape(windows, len(CHANNELS), -1)
    if raw_values.shape[:2] != v2.shape[:2]:
        raise ValueError("DE and raw SQI feature shapes do not agree")
    return v2, np.concatenate((v2, raw_values), axis=2)


def episode_spec(
    recording: str,
    kind: str,
    windows: int,
    *,
    severity: float,
    train: bool,
    experiment_seed: int,
) -> tuple[RawCorruptionSpec, int]:
    seed = stable_seed(
        "raw-sqi-v3", experiment_seed, "train" if train else "test",
        recording, kind, severity,
    )
    rng = np.random.default_rng(seed)
    channel_count = int(rng.integers(1, 5)) if train else 2
    channels = tuple(sorted(int(value) for value in rng.choice(len(CHANNELS), channel_count, replace=False)))
    available = windows - CALIBRATION_WINDOWS - CONTEXT_WINDOWS
    length = max(5, min(20, int(round(available * (0.18 if train else 0.22)))))
    start = int(rng.integers(CALIBRATION_WINDOWS + CONTEXT_WINDOWS, windows - length + 1))
    return RawCorruptionSpec(kind, severity, channels, start, length), seed


def extract_recording(
    name: str,
    raw_path: Path,
    label_path: Path,
    kinds: list[str],
    train_severities: list[float],
    test_severity: float,
    experiment_seed: int,
) -> dict:
    subject = load_seedvig_subject(raw_path, label_path)
    indices = channel_indices(subject.channel_names, CHANNELS)
    eeg = np.asarray(subject.eeg[:, indices], dtype=np.float64)
    window_samples = subject.sample_rate_hz * subject.window_seconds
    de = extract_band_de_features(
        eeg, channel_names=CHANNELS, sample_rate_hz=subject.sample_rate_hz,
        window_samples=window_samples,
    ).values
    raw = extract_raw_sqi_features(
        eeg, channel_names=CHANNELS, sample_rate_hz=subject.sample_rate_hz,
        window_samples=window_samples,
    ).values
    de_cal, de_mean, de_scale = calibrate(de, de[:CALIBRATION_WINDOWS])
    raw_cal, raw_mean, raw_scale = calibrate(raw, raw[:CALIBRATION_WINDOWS])
    clean_v2, clean_v3 = combine_features(de_cal, raw_cal)
    clean = FeatureBlock(
        clean_v2[CALIBRATION_WINDOWS:], clean_v3[CALIBRATION_WINDOWS:],
        np.ones((len(de) - CALIBRATION_WINDOWS, len(CHANNELS))),
        np.zeros((len(de) - CALIBRATION_WINDOWS, len(CHANNELS)), dtype=bool),
    )

    episodes: dict[str, dict] = {"train": {}, "test": {}}
    for split in ("train", "test"):
        for kind in kinds:
            severities = train_severities if split == "train" else [test_severity]
            blocks = []
            for severity in severities:
                spec, seed = episode_spec(
                    name, kind, len(de), severity=severity, train=split == "train",
                    experiment_seed=experiment_seed,
                )
                context_start = spec.start_window - CONTEXT_WINDOWS
                segment_start = context_start * window_samples
                segment_stop = (spec.start_window + spec.length_windows) * window_samples
                segment = eeg[segment_start:segment_stop]
                local_spec = RawCorruptionSpec(
                    spec.kind, spec.severity, spec.channels, CONTEXT_WINDOWS, spec.length_windows
                )
                corrupted = apply_raw_corruption(
                    segment, local_spec, sample_rate_hz=subject.sample_rate_hz,
                    window_samples=window_samples, seed=seed,
                )
                corrupt_de = extract_band_de_features(
                    corrupted.values, channel_names=CHANNELS,
                    sample_rate_hz=subject.sample_rate_hz, window_samples=window_samples,
                ).values
                corrupt_raw = extract_raw_sqi_features(
                    corrupted.values, channel_names=CHANNELS,
                    sample_rate_hz=subject.sample_rate_hz, window_samples=window_samples,
                ).values
                corrupt_de = (corrupt_de - de_mean) / de_scale
                corrupt_raw = (corrupt_raw - raw_mean) / raw_scale
                v2, v3 = combine_features(corrupt_de, corrupt_raw)
                blocks.append(FeatureBlock(
                    v2[CONTEXT_WINDOWS:], v3[CONTEXT_WINDOWS:],
                    corrupted.quality[CONTEXT_WINDOWS:], corrupted.corruption_mask[CONTEXT_WINDOWS:],
                ))
            episodes[split][kind] = blocks if split == "train" else blocks[0]
    return {"clean": clean, "episodes": episodes, "participant": participant_id(name)}


def flatten(features: np.ndarray) -> np.ndarray:
    return features.reshape(-1, features.shape[-1])


def fit_model(recordings: dict[str, dict], names: list[str], method: str, kinds: list[str]):
    clean_parts = []
    x_parts = []
    y_parts = []
    for name in names:
        clean = recordings[name]["clean"]
        clean_x = flatten(getattr(clean, method))
        clean_parts.append(clean_x)
        x_parts.append(clean_x)
        y_parts.append(np.ones(len(clean_x)))
        for kind in kinds:
            for block in recordings[name]["episodes"]["train"][kind]:
                x = flatten(getattr(block, method))
                y = block.quality.reshape(-1)
                mask = block.mask.reshape(-1)
                x_parts.append(x[mask])
                y_parts.append(y[mask])
    model = HistGradientBoostingRegressor(**QUALITY_MODEL_PARAMETERS).fit(
        np.concatenate(x_parts), np.concatenate(y_parts)
    )
    clean_prediction = np.clip(model.predict(np.concatenate(clean_parts)), 0.0, 1.0)
    scale = max(float(np.quantile(clean_prediction, 0.10)), 1.0e-3)
    return model, scale


def classifier_training_data(
    recordings: dict[str, dict], names: list[str], kinds: list[str], experiment_seed: int
) -> tuple[np.ndarray, np.ndarray]:
    clean_parts = []
    bad_parts = []
    for name in names:
        clean_parts.append(flatten(recordings[name]["clean"].v3))
        for kind in kinds:
            for block in recordings[name]["episodes"]["train"][kind]:
                values = flatten(block.v3)
                mask = block.mask.reshape(-1)
                bad_parts.append(values[mask])
    clean_x = np.concatenate(clean_parts)
    bad_x = np.concatenate(bad_parts)
    rng = np.random.default_rng(
        stable_seed("raw-sqi-v3-balanced", experiment_seed, *sorted(names))
    )
    clean_count = min(len(clean_x), 2 * len(bad_x))
    clean_indices = rng.choice(len(clean_x), clean_count, replace=False)
    x = np.concatenate((clean_x[clean_indices], bad_x))
    y = np.concatenate((np.zeros(clean_count, dtype=np.int8), np.ones(len(bad_x), dtype=np.int8)))
    return x, y


def make_classifier(experiment_seed: int) -> HistGradientBoostingClassifier:
    parameters = {**QUALITY_MODEL_PARAMETERS, "random_state": experiment_seed}
    return HistGradientBoostingClassifier(**parameters)


def development_predictions(
    model: HistGradientBoostingClassifier,
    recordings: dict[str, dict],
    names: list[str],
    kinds: list[str],
) -> tuple[np.ndarray, np.ndarray]:
    prediction_parts = []
    target_parts = []
    for name in names:
        clean = recordings[name]["clean"]
        prediction_parts.append(model.predict_proba(flatten(clean.v3))[:, 1])
        target_parts.append(np.zeros(len(flatten(clean.v3)), dtype=bool))
        for kind in kinds:
            for block in recordings[name]["episodes"]["train"][kind]:
                prediction_parts.append(model.predict_proba(flatten(block.v3))[:, 1])
                target_parts.append(block.mask.reshape(-1))
    return np.concatenate(target_parts), np.concatenate(prediction_parts)


def tune_bad_probability_threshold(target: np.ndarray, probability: np.ndarray) -> float:
    best: tuple[float, float, float] | None = None
    for threshold in np.linspace(0.01, 0.99, 99):
        metrics = confusion(target, probability >= threshold)
        false_bad = 1.0 - float(metrics["specificity"])
        if false_bad > 0.15:
            continue
        candidate = (float(metrics["balanced_accuracy"]), float(metrics["specificity"]), float(threshold))
        if best is None or candidate > best:
            best = candidate
    if best is None:
        raise RuntimeError("no classifier threshold satisfies the clean false-bad constraint")
    return best[2]


def confusion(target_bad: np.ndarray, predicted_bad: np.ndarray) -> dict[str, float | int]:
    target = np.asarray(target_bad, dtype=bool)
    predicted = np.asarray(predicted_bad, dtype=bool)
    tp = int(np.sum(target & predicted))
    fn = int(np.sum(target & ~predicted))
    tn = int(np.sum(~target & ~predicted))
    fp = int(np.sum(~target & predicted))
    sensitivity = tp / (tp + fn) if tp + fn else float("nan")
    specificity = tn / (tn + fp) if tn + fp else float("nan")
    return {
        "tp": tp, "fn": fn, "tn": tn, "fp": fp,
        "sensitivity": sensitivity, "specificity": specificity,
        "balanced_accuracy": 0.5 * (sensitivity + specificity) if np.isfinite(sensitivity) else specificity,
    }


def main() -> int:
    args = parse_args()
    if any(not 0.0 < value <= 1.0 for value in args.train_severities) or not 0.0 < args.test_severity <= 1.0:
        raise SystemExit("severities must be in (0, 1]")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    pairs = discover_pairs(args.dataset_root)
    participant_ids = sorted({participant_id(name) for name, _, _ in pairs}, key=int)
    selected_participants = participant_ids[:args.max_participants]
    selected_pairs = [item for item in pairs if participant_id(item[0]) in selected_participants]
    recordings = {}
    for index, (name, raw_path, label_path) in enumerate(selected_pairs, 1):
        print(f"[{index}/{len(selected_pairs)}] extracting {name}", flush=True)
        recordings[name] = extract_recording(
            name,
            raw_path,
            label_path,
            args.kinds,
            args.train_severities,
            args.test_severity,
            args.experiment_seed,
        )

    rows = []
    for held_out in selected_participants:
        train_names = [name for name in recordings if recordings[name]["participant"] != held_out]
        test_names = [name for name in recordings if recordings[name]["participant"] == held_out]
        training_participants = sorted(
            {recordings[name]["participant"] for name in train_names}, key=int
        )
        development_participant = training_participants[-1]
        fit_names = [
            name for name in train_names
            if recordings[name]["participant"] != development_participant
        ]
        development_names = [
            name for name in train_names
            if recordings[name]["participant"] == development_participant
        ]
        for method in ("v2", "v3", "v3_classifier"):
            if method == "v3_classifier":
                fit_x, fit_y = classifier_training_data(
                    recordings, fit_names, args.kinds, args.experiment_seed
                )
                threshold_model = make_classifier(args.experiment_seed).fit(fit_x, fit_y)
                development_target, development_probability = development_predictions(
                    threshold_model, recordings, development_names, args.kinds
                )
                threshold = tune_bad_probability_threshold(
                    development_target, development_probability
                )
                all_x, all_y = classifier_training_data(
                    recordings, train_names, args.kinds, args.experiment_seed
                )
                model = make_classifier(args.experiment_seed).fit(all_x, all_y)
                scale = None
                feature_name = "v3"
            else:
                model, scale = fit_model(recordings, train_names, method, args.kinds)
                threshold = QUALITY_THRESHOLD
                feature_name = method
            clean_predictions = []
            for name in test_names:
                clean = recordings[name]["clean"]
                clean_x = flatten(getattr(clean, feature_name))
                if method == "v3_classifier":
                    prediction = model.predict_proba(clean_x)[:, 1]
                    clean_predictions.append(prediction >= threshold)
                else:
                    prediction = np.clip(model.predict(clean_x) / scale, 0.0, 1.0)
                    clean_predictions.append(prediction < threshold)
            clean_prediction = np.concatenate(clean_predictions)
            rows.append({
                "participant": held_out, "method": method, "condition": "clean",
                "threshold": threshold,
                "false_bad_rate": float(np.mean(clean_prediction)),
                "sensitivity": "", "specificity": float(np.mean(~clean_prediction)),
                "balanced_accuracy": "",
            })
            for kind in args.kinds:
                target_parts = []
                prediction_parts = []
                for name in test_names:
                    block = recordings[name]["episodes"]["test"][kind]
                    x = flatten(getattr(block, feature_name))
                    if method == "v3_classifier":
                        prediction_parts.append(model.predict_proba(x)[:, 1] >= threshold)
                    else:
                        prediction = np.clip(model.predict(x) / scale, 0.0, 1.0)
                        prediction_parts.append(prediction < threshold)
                    target_parts.append(block.mask.reshape(-1))
                metrics = confusion(np.concatenate(target_parts), np.concatenate(prediction_parts))
                rows.append({
                    "participant": held_out, "method": method, "condition": kind,
                    "threshold": threshold,
                    "false_bad_rate": metrics["fp"] / (metrics["tn"] + metrics["fp"]),
                    "sensitivity": metrics["sensitivity"], "specificity": metrics["specificity"],
                    "balanced_accuracy": metrics["balanced_accuracy"],
                })
            print(f"fold={held_out} method={method} complete", flush=True)

    with (args.output_dir / "fold_metrics.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = {}
    for method in ("v2", "v3", "v3_classifier"):
        summary[method] = {}
        for condition in ("clean", *args.kinds):
            selected = [row for row in rows if row["method"] == method and row["condition"] == condition]
            summary[method][condition] = {
                key: float(np.mean([float(row[key]) for row in selected if row[key] != ""]))
                for key in ("false_bad_rate", "sensitivity", "specificity", "balanced_accuracy")
                if any(row[key] != "" for row in selected)
            }
    payload = {
        "status": "smoke_test" if args.max_participants < 21 else "full_participant_run",
        "participants": selected_participants,
        "kinds": args.kinds,
        "train_severities": args.train_severities,
        "test_severity": args.test_severity,
        "experiment_seed": args.experiment_seed,
        "quality_threshold": QUALITY_THRESHOLD,
        "summary": summary,
    }
    (args.output_dir / "summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
