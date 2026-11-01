"""Participant-held-out evaluation and export for the six Cyton/GAMEEMO sites."""

import argparse
import csv
import hashlib
import json
import platform
import sys
import time
from pathlib import Path

import numpy as np
import scipy
from scipy import signal
from scipy.io import loadmat
import sklearn
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.metrics import accuracy_score, balanced_accuracy_score, f1_score
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from gameemo_8ch_baseline import (
    BANDS_HZ, CHANNELS_8, DEFAULT_DATA, DEFAULT_ARCHIVE, GAME_LABELS,
    create_manifest, discover_records, sha256,
)
from gameemo_contact_robustness import gate_features, mask_augment

BOARD_CODE = Path(__file__).parents[1] / "pynq_guardianloop"
sys.path.insert(0, str(BOARD_CODE))
from cyton_sqi import CausalEEGFilter, GameemoEmotionRecognizer, emotion_features

CHANNELS = ("F3", "F4", "T7", "T8", "O1", "O2")
LIVE_CHANNELS = ("F3", "F4", "C3", "C4", "T7", "T8", "O1", "O2")
SEEDS = (13, 37, 73)
DEFAULT_OUTPUT = Path(__file__).with_name("output") / "gameemo_6ch_live"


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def prepare(records):
    features, labels, subjects, rows = [], [], [], []
    fixture = None
    for number, record in enumerate(records):
        data = loadmat(record["path"], variable_names=list(CHANNELS_8))
        raw = np.column_stack([np.asarray(data[ch]).ravel() for ch in CHANNELS_8])
        # Mirror Cyton's 250 Hz conditioning and window-wise feature extraction.
        # GAMEEMO inputs have already undergone the vendor preprocessing.
        conditioned = CausalEEGFilter().process(signal.resample_poly(raw, 125, 64, axis=0))
        for index in range(1, len(conditioned) // 1000):
            window = conditioned[index * 1000:(index + 1) * 1000]
            features.append(emotion_features(window))
            labels.append(record["class_id"])
            subjects.append(record["subject"])
            rows.append((record["subject"], record["game"], index))
            if fixture is None:
                fixture = np.zeros((1000, 8))
                for ch in CHANNELS:
                    fixture[:, LIVE_CHANNELS.index(ch)] = window[:, CHANNELS_8.index(ch)]
        if (number + 1) % 8 == 0:
            print(f"features: {number + 1}/{len(records)} records", flush=True)
    return np.asarray(features), np.asarray(labels), np.asarray(subjects), rows, fixture


def fit_model(x, y, seed=None):
    median = np.median(x, axis=0)
    scaler = StandardScaler().fit(x)
    ax, ay = (x, y) if seed is None else mask_augment(x, y, median, seed)
    classifier = LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto")
    classifier.fit(scaler.transform(ax), ay)
    return scaler, classifier, median


def metrics(y, prediction, groups):
    per_subject = []
    for subject in np.unique(groups):
        mask = groups == subject
        per_subject.append({"subject": int(subject),
                            "balanced_accuracy": float(balanced_accuracy_score(y[mask], prediction[mask])),
                            "macro_f1": float(f1_score(y[mask], prediction[mask], average="macro", zero_division=0))})
    scores = [row["balanced_accuracy"] for row in per_subject]
    return {"accuracy": float(accuracy_score(y, prediction)),
            "balanced_accuracy": float(balanced_accuracy_score(y, prediction)),
            "macro_f1": float(f1_score(y, prediction, average="macro", zero_division=0)),
            "subject_ba_mean": float(np.mean(scores)), "subject_ba_std": float(np.std(scores)),
            "per_subject": per_subject}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    started = time.time()
    records = discover_records(args.data)
    manifest = create_manifest(records, args.data, args.archive)
    for item, record in zip(manifest["records"], records):
        item["sha256"] = sha256(record["path"])
    manifest.pop("manifest_sha256", None)
    manifest["manifest_sha256"] = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    save_json(args.output / "data_manifest.json", manifest)
    protocol = {
        "hypothesis": "six shared channels retain at least 90% of eight-channel plain LOSO balanced accuracy",
        "falsification": "six/eight plain LOSO BA ratio below 0.90",
        "primary_metrics": ["balanced_accuracy", "macro_f1"],
        "channels": CHANNELS, "acquisition_channels": LIVE_CHANNELS,
        "seeds": SEEDS, "deployment_seed": SEEDS[0], "minimum_usable_channels": 5,
        "window_seconds": 4, "overlap_seconds": 0, "warmup_excluded_seconds_per_record": 4,
        "preprocessing": "128->250Hz resample; continuous notch50 Q5 and Butterworth4 1-45Hz; shared window feature code",
        "conditions": ["clean", "each_of_six_channels_masked_individually"],
        "label_basis": "four game conditions; not individual self-report emotion labels",
        "folds": [{"test_subject": s, "train_subjects": [i for i in range(1, 29) if i != s]} for s in range(1, 29)],
        "versions": {"python": platform.python_version(), "numpy": np.__version__,
                     "scipy": scipy.__version__, "sklearn": sklearn.__version__},
        "source_hashes": {str(path): sha256(path) for path in
                          (Path(__file__), BOARD_CODE / "cyton_sqi.py", Path(__file__).with_name("gameemo_contact_robustness.py"))},
    }
    save_json(args.output / "protocol.json", protocol)
    all_x, y, groups, rows, fixture = prepare(records)
    columns = [band * 8 + CHANNELS_8.index(ch) for band in range(len(BANDS_HZ)) for ch in CHANNELS]
    x6 = all_x[:, columns]
    results = {}
    with threadpool_limits(limits=1), (args.output / "predictions.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(("method", "seed", "condition", "subject", "game", "window", "target", "prediction"))
        for name, x, seeds in (("plain8", all_x, (None,)), ("plain6", x6, (None,)), ("maskaug6", x6, SEEDS)):
            for seed in seeds:
                conditions = ["clean"] + ([f"missing_{ch}" for ch in CHANNELS] if name != "plain8" else [])
                predictions = {condition: np.empty_like(y) for condition in conditions}
                for subject in np.unique(groups):
                    train, test = groups != subject, groups == subject
                    scaler, classifier, median = fit_model(x[train], y[train], seed)
                    for condition in conditions:
                        xt = x[test]
                        if condition != "clean":
                            q = np.ones((len(xt), len(CHANNELS)))
                            q[:, CHANNELS.index(condition[8:])] = 0
                            xt = gate_features(xt, q, median)
                        predictions[condition][test] = classifier.predict(scaler.transform(xt))
                key = name if seed is None else f"{name}_seed{seed}"
                results[key] = {}
                for condition, prediction in predictions.items():
                    results[key][condition] = metrics(y, prediction, groups)
                    writer.writerows((name, seed, condition, *row, int(target), int(pred))
                                     for row, target, pred in zip(rows, y, prediction))
                print(key, results[key]["clean"]["balanced_accuracy"], flush=True)
        scaler, classifier, median = fit_model(x6, y, SEEDS[0])
    seed_scores = [results[f"maskaug6_seed{seed}"]["clean"]["balanced_accuracy"] for seed in SEEDS]
    ratio = results["plain6"]["clean"]["balanced_accuracy"] / results["plain8"]["clean"]["balanced_accuracy"]
    report = {"windows": len(y), "participants": len(np.unique(groups)), "results": results,
              "six_to_eight_ba_ratio": ratio, "retention_hypothesis_passed": ratio >= 0.90,
              "maskaug6_ba_seed_mean": float(np.mean(seed_scores)),
              "maskaug6_ba_seed_std": float(np.std(seed_scores)),
              "duration_seconds": time.time() - started,
              "protocol_sha256": sha256(args.output / "protocol.json"),
              "manifest_sha256": sha256(args.output / "data_manifest.json")}
    save_json(args.output / "metrics.json", report)
    scores = scaler.transform(x6) @ classifier.coef_.T + classifier.intercept_
    agreement = float(np.mean(classifier.classes_[scores.argmax(axis=1)] == classifier.predict(scaler.transform(x6))))
    if agreement != 1.0 or np.mean(seed_scores) <= 0.25:
        raise RuntimeError("export gate failed: classifier agreement or mean LOSO BA <= chance")
    payload = {
        "model": "GAMEEMO_maskaug_scaler_LDA", "algorithm_version": "gameemo-6ch-maskaug-lda-v2",
        "deployment_status": "experimental game-condition classifier; Cyton emotion accuracy unvalidated",
        "sample_rate_hz": 128, "window_seconds": 4, "channels": list(CHANNELS),
        "minimum_usable_channels": 5, "bands_hz": BANDS_HZ,
        "classes": classifier.classes_.astype(int).tolist(),
        "class_names": [GAME_LABELS[int(index) + 1]["name"] for index in classifier.classes_],
        "feature_median": median.tolist(), "scaler_mean": scaler.mean_.tolist(),
        "scaler_scale": scaler.scale_.tolist(), "lda_coef": classifier.coef_.tolist(),
        "lda_intercept": classifier.intercept_.tolist(), "export_agreement": agreement,
        "training_windows": len(y), "training_participants": 28, "training_seed": SEEDS[0],
        "loso_balanced_accuracy": float(np.mean(seed_scores)),
        "metrics_sha256": sha256(args.output / "metrics.json"),
        "preprocessing": protocol["preprocessing"], "label_basis": protocol["label_basis"],
    }
    model_path = args.output / "model_6ch.json"
    save_json(model_path, payload)
    runtime = GameemoEmotionRecognizer(model_path)
    expected = runtime.predict(fixture, np.ones(8), source_channel_map=LIVE_CHANNELS)
    pc_probabilities = np.exp(scores[0] - np.max(scores[0]))
    pc_probabilities /= pc_probabilities.sum()
    np.testing.assert_allclose(list(expected["probabilities"].values()), pc_probabilities, atol=5.1e-5, rtol=0)
    np.savez(args.output / "runtime_fixture.npz", samples_uv=fixture)
    save_json(args.output / "runtime_expected.json", expected)
    print(json.dumps({"output": str(args.output), "windows": len(y), "maskaug6_ba_mean": np.mean(seed_scores),
                      "retention_ratio": ratio, "export_agreement": agreement}), flush=True)


if __name__ == "__main__":
    main()
