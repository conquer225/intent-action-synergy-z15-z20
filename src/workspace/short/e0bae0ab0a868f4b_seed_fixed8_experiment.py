"""Full-SEED fixed-cap, participant-disjoint baseline with traceable raw predictions."""

import argparse
import csv
import json
import platform
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import scipy
import sklearn
from scipy import signal
from scipy.io import loadmat, whosmat
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import accuracy_score, balanced_accuracy_score, confusion_matrix, f1_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .emotion_baseline import CHANNELS_62, sha256
from .fixed8_deap_preflight import CYTON_CHANNELS
from .fixed8_deap_experiment import matrix_log_vectors


HERE = Path(__file__).parent
PROTOCOL = HERE / "seed_fixed8_protocol.json"
INDICES = tuple(CHANNELS_62.index(c.upper()) for c in CYTON_CHANNELS)
BANDS = ((1, 4), (4, 8), (8, 14), (14, 31), (31, 45))
FS, WARMUP, WINDOW = 200, 400, 2400
CLASSES = (-1, 0, 1)
METHODS = ("power_lda", "logcov_lda", "power_hgb")


def trial_names(contents):
    names = [n for n in contents if re.fullmatch(r".+_eeg\d+", n)]
    names.sort(key=lambda n: int(n.rsplit("eeg", 1)[1]))
    if [int(n.rsplit("eeg", 1)[1]) for n in names] != list(range(1, 16)):
        raise ValueError("Expected exactly EEG trials 1-15")
    return names


def extract_trial(raw):
    if raw.ndim != 2 or raw.shape[0] != 8 or raw.shape[1] < WARMUP + WINDOW:
        raise ValueError("Unexpected trial shape")
    if not np.isfinite(raw).all():
        raise ValueError("Nonfinite fixed-channel EEG")
    count = (raw.shape[1] - WARMUP) // WINDOW
    power = np.empty((count, 40))
    covariance = np.empty((count, 5, 8, 8))
    for band_index, band in enumerate(BANDS):
        sos = signal.butter(4, band, fs=FS, btype="bandpass", output="sos")
        filtered = signal.sosfilt(sos, raw, axis=1)
        segments = filtered[:, WARMUP:WARMUP + count * WINDOW].reshape(8, count, WINDOW).transpose(1, 0, 2)
        centered = segments - segments.mean(axis=-1, keepdims=True)
        cov = centered @ centered.swapaxes(-1, -2) / (WINDOW - 1)
        trace = np.trace(cov, axis1=-2, axis2=-1)
        if np.any(trace <= 0):
            raise ValueError("Flat trial has no positive covariance")
        power[:, band_index * 8:(band_index + 1) * 8] = np.log(
            np.maximum(np.diagonal(cov, axis1=-2, axis2=-1), 1e-12))
        covariance[:, band_index] = cov + .05 * trace[:, None, None] / 8 * np.eye(8)
    return power, matrix_log_vectors(covariance)


def build_manifest(root):
    files = sorted(root.glob("*_*.mat"), key=lambda p: (int(p.stem.split("_")[0]), p.stem))
    subjects = Counter(int(p.stem.split("_")[0]) for p in files)
    if subjects != Counter({i: 3 for i in range(1, 16)}):
        raise ValueError(f"Expected 15 participants x3 sessions, got {subjects}")
    labels = loadmat(root / "label.mat")["label"].ravel()
    if labels.tolist() != [1, 0, -1, -1, 0, 1, -1, 0, 1, 1, 0, -1, 0, 1, -1]:
        raise ValueError("Unexpected SEED trial labels")
    records = []
    for path in files:
        structure = {name: shape for name, shape, _ in whosmat(path)}
        names = trial_names(structure)
        if any(structure[n][0] != 62 for n in names):
            raise ValueError(f"Unexpected channel count: {path}")
        records.append({"path": str(path), "subject": int(path.stem.split("_")[0]),
                        "session": path.stem.split("_")[1], "sha256": sha256(path),
                        "trials": {n: structure[n] for n in names}})
    return {"labels": labels.astype(int).tolist(), "labels_sha256": sha256(root / "label.mat"),
            "montage": CYTON_CHANNELS, "indices": INDICES, "records": records,
            "folds": [{"test": [s], "train": [t for t in range(1, 16) if t != s]} for s in range(1, 16)]}


def extract(manifest):
    powers, covariances, keys, labels = [], [], [], []
    for record in manifest["records"]:
        path = Path(record["path"])
        if sha256(path) != record["sha256"]:
            raise ValueError(f"Source changed: {path}")
        content = loadmat(path)
        for trial, name in enumerate(trial_names(content), 1):
            raw = np.asarray(content[name][list(INDICES)], dtype=np.float64)
            power, logcov = extract_trial(raw)
            powers.append(power)
            covariances.append(logcov)
            labels.extend([manifest["labels"][trial - 1]] * len(power))
            keys.extend((record["subject"], int(record["session"]), trial, window)
                        for window in range(len(power)))
        print(f"EXTRACTED {path.name}", flush=True)
    data = {"power": np.concatenate(powers), "logcov": np.concatenate(covariances),
            "keys": np.asarray(keys, dtype=np.int64), "targets": np.asarray(labels)}
    if len(set(map(tuple, data["keys"]))) != len(keys) or not all(np.isfinite(v).all() for v in data.values()):
        raise ValueError("Duplicate keys or nonfinite features")
    return data


def participant_masks(keys, subject):
    test = keys[:, 0] == subject
    return ~test, test


def evaluate(data, output):
    results = {}
    predictions_path = output / "predictions.csv"
    with predictions_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["method", "subject", "session", "trial", "window", "target", "prediction"])
        for method in METHODS:
            x = data["logcov"] if method == "logcov_lda" else data["power"]
            y = data["targets"]
            scores = []
            for subject in range(1, 16):
                train, test = participant_masks(data["keys"], subject)
                if set(y[train]) != set(CLASSES) or set(y[test]) != set(CLASSES):
                    raise ValueError("Missing fold class")
                started = time.perf_counter()
                if method.endswith("lda"):
                    model = make_pipeline(StandardScaler(), LinearDiscriminantAnalysis(
                        solver="lsqr", shrinkage="auto", priors=[1/3] * 3))
                    model.fit(x[train], y[train])
                else:
                    model = HistGradientBoostingClassifier(max_iter=100, max_leaf_nodes=15,
                        min_samples_leaf=30, l2_regularization=1, early_stopping=False, random_state=20260926)
                    count = Counter(y[train])
                    weight = np.array([train.sum() / (3 * count[v]) for v in y[train]])
                    model.fit(x[train], y[train], sample_weight=weight)
                guess = model.predict(x[test])
                scores.append({"subject": subject, "windows": int(test.sum()),
                    "accuracy": accuracy_score(y[test], guess),
                    "balanced_accuracy": balanced_accuracy_score(y[test], guess),
                    "macro_f1": f1_score(y[test], guess, labels=CLASSES, average="macro"),
                    "confusion_matrix": confusion_matrix(y[test], guess, labels=CLASSES).tolist(),
                    "fit_predict_seconds_pc": time.perf_counter() - started})
                writer.writerows((method, *map(int, key), int(label), int(prediction))
                                 for key, label, prediction in zip(data["keys"][test], y[test], guess))
                stream.flush()
                print(f"FOLD {method} subject={subject} BA={scores[-1]['balanced_accuracy']:.4f}", flush=True)
            results[method] = {"participants": scores}
            for metric in ("accuracy", "balanced_accuracy", "macro_f1"):
                values = np.array([s[metric] for s in scores])
                rng = np.random.default_rng(20260926)
                interval = np.quantile(values[rng.integers(0, 15, (20000, 15))].mean(axis=1), [.025, .975])
                results[method][metric] = {"mean_subject": values.mean(), "std_subject": values.std(ddof=1), "ci95": interval.tolist()}
            print(f"COMPLETE {method}: {results[method]['balanced_accuracy']}", flush=True)
    baseline = np.array([s["balanced_accuracy"] for s in results["power_lda"]["participants"]])
    for method in METHODS[1:]:
        difference = np.array([s["balanced_accuracy"] for s in results[method]["participants"]]) - baseline
        rng = np.random.default_rng(20260926)
        results[method]["paired_vs_power_lda"] = {"mean_gain": difference.mean(),
            "ci97_5": np.quantile(difference[rng.integers(0, 15, (20000, 15))].mean(axis=1), [.0125, .9875]).tolist()}
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path(r"D:\ican\datasets\SEED\SEED\Preprocessed_EEG"))
    parser.add_argument("--output", type=Path, default=HERE / "output/seed_fixed8_initial_20260926")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if (args.output / "results.json").exists():
        raise FileExistsError("Completed output already exists; choose another output directory")
    protocol = json.loads(PROTOCOL.read_text())
    if tuple(protocol["seed_zero_based_indices"]) != INDICES:
        raise ValueError("Montage differs from frozen protocol")
    started = datetime.now(timezone.utc).isoformat()
    (args.output / "protocol.json").write_text(json.dumps(protocol, indent=2), encoding="utf-8")
    manifest = build_manifest(args.data)
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    data = extract(manifest)
    np.savez_compressed(args.output / "features.npz", **data)
    results = evaluate(data, args.output)
    paths = [PROTOCOL, Path(__file__), HERE / "emotion_baseline.py", HERE / "fixed8_deap_preflight.py",
             HERE / "fixed8_deap_experiment.py", args.output / "manifest.json", args.output / "features.npz",
             args.output / "predictions.csv"]
    report = {"status": "complete exploratory LOSO baseline; no independent model-selection holdout or board deployment",
        "started_utc": started, "completed_utc": datetime.now(timezone.utc).isoformat(),
        "montage": CYTON_CHANNELS, "indices": INDICES, "participants": 15, "sessions": 45,
        "windows": len(data["targets"]), "class_window_counts": {str(c): int(sum(data["targets"] == c)) for c in CLASSES},
        "methods": results, "hashes": {str(p): sha256(p) for p in paths},
        "software": {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__,
                     "sklearn": sklearn.__version__, "machine": platform.machine()}}
    (args.output / "results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
