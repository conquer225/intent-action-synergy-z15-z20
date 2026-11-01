"""Participant-independent GAMEEMO contact-corruption stress test.

Corruptions are generated only after selecting the held-out participant. Every
fold fits its classifier, feature replacement values and SQI reference only on
training participants. Clipped samples are detected/downweighted, not claimed
to be recoverable.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
from collections import defaultdict
from pathlib import Path

import numpy as np
import scipy
from scipy import signal
from scipy.io import loadmat
import sklearn
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.metrics import accuracy_score, balanced_accuracy_score, f1_score
from sklearn.preprocessing import StandardScaler

from gameemo_8ch_baseline import (
    BANDS_HZ, CHANNELS_8, DEFAULT_DATA, SAMPLE_RATE_HZ, WINDOW_SAMPLES,
    WINDOW_SECONDS, create_manifest, discover_records,
)

DEFAULT_ARCHIVE = DEFAULT_DATA.parent / "GAMEEMO_v3.zip"
DEFAULT_OUTPUT = Path(__file__).with_name("output") / "gameemo_contact_robustness"
SEEDS = (13, 37, 73)
SEVERITIES = ("low", "medium", "high")
CORRUPTIONS = (
    "dropout", "flatline", "broadband_noise", "mains_noise", "drift",
    "burst", "clipping", "contact_composite", "channel_swap",
)
METHODS = (
    "plain", "amplitude_gate", "adaptive_sqi",
    "maskaug_plain", "maskaug_adaptive", "maskaug_oracle",
)
TRANSPORT_LIMIT_UV = 327.67
AMPLITUDE_GATE_UV = 100.0
EPS = 1e-12

FILTERS = tuple(
    signal.butter(4, band, btype="bandpass", fs=SAMPLE_RATE_HZ, output="sos")
    for band in BANDS_HZ
)
SQI_NAMES = (
    "robust_scale", "p99_abs", "flat_ratio", "clip_ratio", "mains_ratio",
    "hf_ratio", "step_ratio",
)


def load_windows(records):
    windows, targets, groups, rows = [], [], [], []
    for record in records:
        data = loadmat(record["path"], variable_names=list(CHANNELS_8))
        raw = np.vstack([np.asarray(data[ch], dtype=np.float64).ravel() for ch in CHANNELS_8])
        count = raw.shape[1] // WINDOW_SAMPLES
        raw = raw[:, : count * WINDOW_SAMPLES].reshape(len(CHANNELS_8), count, WINDOW_SAMPLES)
        windows.append(np.transpose(raw, (1, 0, 2)))
        targets.extend([record["class_id"]] * count)
        groups.extend([record["subject"]] * count)
        rows.extend((record["subject"], record["game"], index) for index in range(count))
    return (
        np.concatenate(windows), np.asarray(targets, dtype=np.int64),
        np.asarray(groups, dtype=np.int64), rows,
    )


def extract_features(windows):
    return np.concatenate([
        np.log(np.var(signal.sosfiltfilt(sos, windows, axis=-1), axis=-1) + EPS)
        for sos in FILTERS
    ], axis=1)


def compute_sqi(windows):
    centered = windows - np.median(windows, axis=-1, keepdims=True)
    absolute = np.abs(centered)
    differences = np.diff(windows, axis=-1)
    mad = 1.4826 * np.median(absolute, axis=-1) + EPS
    p99 = np.quantile(absolute, 0.99, axis=-1)
    flat_ratio = np.mean(np.abs(differences) <= 1e-3, axis=-1)
    clip_ratio = np.mean(np.abs(windows) >= TRANSPORT_LIMIT_UV - 0.01, axis=-1)
    step_ratio = np.max(np.abs(differences), axis=-1) / mad
    power = np.abs(np.fft.rfft(centered * np.hanning(windows.shape[-1]), axis=-1)) ** 2
    frequency = np.fft.rfftfreq(windows.shape[-1], 1 / SAMPLE_RATE_HZ)
    total = np.sum(power[..., (frequency >= 1) & (frequency <= 55)], axis=-1) + EPS
    mains = np.sum(power[..., (frequency >= 49) & (frequency <= 51)], axis=-1) / total
    high = np.sum(power[..., (frequency >= 30) & (frequency <= 45)], axis=-1) / total
    return np.stack((mad, p99, flat_ratio, clip_ratio, mains, high, step_ratio), axis=-1)


def transform_sqi(sqi):
    output = sqi.copy()
    for index in (0, 1, 4, 5, 6):
        output[..., index] = np.log(output[..., index] + EPS)
    return output


def fit_sqi_reference(train_sqi):
    values = transform_sqi(train_sqi)
    center = np.median(values, axis=0)
    scale = 1.4826 * np.median(np.abs(values - center), axis=0) + 1e-6
    worst = np.max(np.abs((values - center) / scale), axis=-1)
    # Training-only calibration: cap the expected clean rejection rate for each
    # channel instead of applying one hardware-independent fixed z threshold.
    threshold = np.quantile(worst, 0.995, axis=0)
    return center, scale, threshold


def adaptive_quality(sqi, center, scale, threshold):
    z = np.abs((transform_sqi(sqi) - center) / scale)
    worst = np.max(z, axis=-1)
    quality = 1 / (1 + np.exp(np.clip((worst - threshold) / 1.5, -40, 40)))
    quality = np.where((sqi[..., 2] >= 0.95) | (sqi[..., 3] > 0.001), 0.0, quality)
    return quality


def amplitude_quality(sqi):
    return ((sqi[..., 1] <= AMPLITUDE_GATE_UV) & (sqi[..., 3] <= 0.001)).astype(float)


def gate_features(features, quality, train_median):
    output = features.copy()
    channel_count = quality.shape[1]
    for band in range(len(BANDS_HZ)):
        columns = slice(band * channel_count, (band + 1) * channel_count)
        output[:, columns] = quality * output[:, columns] + (1 - quality) * train_median[columns]
    return output


def mask_augment(features, target, train_median, seed):
    """Two training-only masked copies; no held-out samples enter augmentation."""
    rng = np.random.default_rng(seed)
    copies = [features]
    labels = [target]
    for channel_count in (1, 2):
        quality = np.ones((len(features), features.shape[1] // len(BANDS_HZ)), dtype=float)
        order = np.argsort(rng.random(quality.shape), axis=1)
        for row in range(len(features)):
            quality[row, order[row, :channel_count]] = 0.0
        copies.append(gate_features(features, quality, train_median))
        labels.append(target)
    return np.concatenate(copies), np.concatenate(labels)


def stable_seed(name, subject, seed):
    digest = hashlib.sha256(f"{name}:{subject}:{seed}".encode()).digest()
    return int.from_bytes(digest[:8], "little")


def corruption_plan(count, name, severity, subject, seed):
    rank = SEVERITIES.index(severity)
    rng = np.random.default_rng(stable_seed(name, subject, seed))
    active = rng.random(count) < (0.25, 0.50, 0.75)[rank]
    order = np.argsort(rng.random((count, len(CHANNELS_8))), axis=1)
    mask = np.zeros((count, len(CHANNELS_8)), dtype=bool)
    for row in np.flatnonzero(active):
        mask[row, order[row, : (1, 1, 2)[rank]]] = True
    return rng, mask, rank


def corrupt(windows, name, severity, subject, seed):
    rng, mask, rank = corruption_plan(len(windows), name, severity, subject, seed)
    result = windows.copy()
    time = np.arange(windows.shape[-1]) / SAMPLE_RATE_HZ
    scales = (1.0, 2.5, 6.0)
    amplitudes = (60.0, 180.0, 500.0)
    for row, channel in zip(*np.where(mask)):
        baseline = result[row, channel]
        robust_scale = max(1.4826 * np.median(np.abs(baseline - np.median(baseline))), 2.0)
        if name == "dropout":
            length = (64, 192, 384)[rank]
            start = int(rng.integers(0, WINDOW_SAMPLES - length + 1))
            result[row, channel, start:start + length] = 0
        elif name == "flatline":
            length = (128, 256, 512)[rank]
            start = int(rng.integers(0, WINDOW_SAMPLES - length + 1))
            result[row, channel, start:start + length] = np.median(baseline)
        elif name == "broadband_noise":
            result[row, channel] += rng.normal(0, robust_scale * scales[rank], WINDOW_SAMPLES)
        elif name == "mains_noise":
            phase = rng.uniform(0, 2 * np.pi)
            result[row, channel] += amplitudes[rank] * np.sin(2 * np.pi * 50 * time + phase)
        elif name == "drift":
            phase = rng.uniform(0, 2 * np.pi)
            result[row, channel] += amplitudes[rank] * np.sin(2 * np.pi * 0.25 * time + phase)
        elif name == "burst":
            length = (32, 96, 192)[rank]
            start = int(rng.integers(0, WINDOW_SAMPLES - length + 1))
            result[row, channel, start:start + length] += rng.normal(
                amplitudes[rank], amplitudes[rank] * 0.5, length)
        elif name == "clipping":
            phase = rng.uniform(0, 2 * np.pi)
            result[row, channel] += (180, 420, 900)[rank] * np.sin(2 * np.pi * 1.2 * time + phase)
            result[row, channel] = np.clip(result[row, channel], -TRANSPORT_LIMIT_UV, TRANSPORT_LIMIT_UV)
        elif name == "contact_composite":
            phase = rng.uniform(0, 2 * np.pi)
            result[row, channel] += amplitudes[rank] * np.sin(2 * np.pi * 0.25 * time + phase)
            result[row, channel] += 0.5 * amplitudes[rank] * np.sin(2 * np.pi * 50 * time + phase)
            length = (32, 96, 192)[rank]
            start = int(rng.integers(0, WINDOW_SAMPLES - length + 1))
            result[row, channel, start:start + length] += rng.normal(0, robust_scale * scales[rank], length)
            result[row, channel] = np.clip(result[row, channel], -TRANSPORT_LIMIT_UV, TRANSPORT_LIMIT_UV)
        elif name == "channel_swap":
            pass
        else:
            raise ValueError(name)
    if name == "channel_swap":
        for row in np.flatnonzero(np.any(mask, axis=1)):
            first = int(np.flatnonzero(mask[row])[0])
            second = (first + 4) % len(CHANNELS_8)
            result[row, [first, second]] = result[row, [second, first]]
            mask[row, second] = True
    if not np.all(np.isfinite(result)):
        raise RuntimeError(f"non-finite output: {name}/{severity}")
    return result, mask


def metric_record(target, prediction, groups, condition, method, seed):
    return {
        "condition": condition, "method": method, "seed": seed,
        "accuracy": float(accuracy_score(target, prediction)),
        "balanced_accuracy": float(balanced_accuracy_score(target, prediction)),
        "macro_f1": float(f1_score(target, prediction, average="macro")),
        "per_subject": [{
            "subject": int(subject),
            "balanced_accuracy": float(balanced_accuracy_score(
                target[groups == subject], prediction[groups == subject])),
        } for subject in np.unique(groups)],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--seeds", type=int, nargs="+", default=list(SEEDS))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    records = discover_records(args.data)
    manifest = create_manifest(records, args.data, args.archive)
    windows, target, groups, rows = load_windows(records)
    clean_features, clean_sqi = extract_features(windows), compute_sqi(windows)
    subjects = np.unique(groups)
    conditions = ["clean"] + [f"{name}/{level}" for name in CORRUPTIONS for level in SEVERITIES]
    predictions = defaultdict(lambda: np.empty(len(target), dtype=np.int64))
    quality_audit = []

    for seed in args.seeds:
        for subject in subjects:
            train, test = groups != subject, groups == subject
            scaler = StandardScaler().fit(clean_features[train])
            classifier = LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto")
            classifier.fit(scaler.transform(clean_features[train]), target[train])
            feature_median = np.median(clean_features[train], axis=0)
            augmented_x, augmented_y = mask_augment(
                clean_features[train], target[train], feature_median,
                stable_seed("mask_augmentation", int(subject), seed),
            )
            augmented_classifier = LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto")
            augmented_classifier.fit(scaler.transform(augmented_x), augmented_y)
            sqi_center, sqi_scale, sqi_threshold = fit_sqi_reference(clean_sqi[train])
            clean_prediction = classifier.predict(scaler.transform(clean_features[test]))
            augmented_clean_prediction = augmented_classifier.predict(scaler.transform(clean_features[test]))
            for method in ("plain", "amplitude_gate", "adaptive_sqi"):
                predictions[(seed, "clean", method)][test] = clean_prediction
            for method in ("maskaug_plain", "maskaug_adaptive", "maskaug_oracle"):
                predictions[(seed, "clean", method)][test] = augmented_clean_prediction
            for name in CORRUPTIONS:
                for severity in SEVERITIES:
                    condition = f"{name}/{severity}"
                    corrupted, known_mask = corrupt(windows[test], name, severity, int(subject), seed)
                    features, sqi = extract_features(corrupted), compute_sqi(corrupted)
                    qualities = {
                        "plain": np.ones_like(known_mask, dtype=float),
                        "amplitude_gate": amplitude_quality(sqi),
                        "adaptive_sqi": adaptive_quality(sqi, sqi_center, sqi_scale, sqi_threshold),
                        "maskaug_plain": np.ones_like(known_mask, dtype=float),
                        "maskaug_adaptive": adaptive_quality(sqi, sqi_center, sqi_scale, sqi_threshold),
                        "maskaug_oracle": (~known_mask).astype(float),
                    }
                    for method, quality in qualities.items():
                        prepared = gate_features(features, quality, feature_median)
                        active_classifier = augmented_classifier if method.startswith("maskaug_") else classifier
                        predictions[(seed, condition, method)][test] = active_classifier.predict(
                            scaler.transform(prepared))
                    quality_audit.append({
                        "seed": seed, "subject": int(subject), "condition": condition,
                        "known_corrupt_fraction": float(np.mean(known_mask)),
                        "amplitude_rejected_fraction": float(np.mean(qualities["amplitude_gate"] < 0.5)),
                        "adaptive_rejected_fraction": float(np.mean(qualities["adaptive_sqi"] < 0.5)),
                    })
            print(f"completed seed={seed} subject={int(subject):02d}", flush=True)

    metrics = [metric_record(target, predictions[(seed, condition, method)], groups, condition, method, seed)
               for seed in args.seeds for condition in conditions for method in METHODS]
    clean = {method: float(np.mean([m["balanced_accuracy"] for m in metrics
                                   if m["condition"] == "clean" and m["method"] == method]))
             for method in METHODS}
    summary = []
    for condition in conditions:
        for method in METHODS:
            values = [m["balanced_accuracy"] for m in metrics
                      if m["condition"] == condition and m["method"] == method]
            summary.append({
                "condition": condition, "method": method,
                "balanced_accuracy_mean": float(np.mean(values)),
                "balanced_accuracy_sd": float(np.std(values, ddof=1)) if len(values) > 1 else 0.0,
                "drop_from_clean": float(clean[method] - np.mean(values)),
            })
    report = {
        "scope": "GAMEEMO 8-channel participant-independent contact-corruption stress test",
        "hypothesis": "adaptive SQI gating reduces corruption loss without harming clean performance",
        "falsification": "no mean corrupted improvement, or clean balanced accuracy falls by >0.02",
        "limitations": ["synthetic corruption is not real Cyton validation",
                        "clipped samples cannot be reconstructed",
                        "GAMEEMO-to-Cyton domain shift still requires calibration"],
        "split_rule": "LOSO; fitting and SQI calibration use training participants only",
        "corruption_timing": "after held-out participant selection",
        "channels": list(CHANNELS_8), "sample_rate_hz": SAMPLE_RATE_HZ,
        "window_seconds": WINDOW_SECONDS, "sqi_features": list(SQI_NAMES),
        "amplitude_gate_uv": AMPLITUDE_GATE_UV, "transport_limit_uv": TRANSPORT_LIMIT_UV,
        "seeds": args.seeds, "manifest_sha256": manifest["manifest_sha256"],
        "versions": {"python": platform.python_version(), "numpy": np.__version__,
                     "scipy": scipy.__version__, "scikit_learn": sklearn.__version__},
        "summary": summary, "metrics": metrics, "quality_audit": quality_audit,
    }
    with (args.output / "robustness_metrics.json").open("w", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    with (args.output / "robustness_summary.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=summary[0].keys()); writer.writeheader(); writer.writerows(summary)
    with (args.output / "predictions.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.writer(stream)
        writer.writerow(("seed", "condition", "method", "subject", "game", "window", "target", "prediction"))
        for seed in args.seeds:
            for condition in conditions:
                for method in METHODS:
                    for row, truth, prediction in zip(rows, target, predictions[(seed, condition, method)]):
                        writer.writerow((seed, condition, method, *row, int(truth), int(prediction)))
    print(json.dumps({"clean": clean, "output": str(args.output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
