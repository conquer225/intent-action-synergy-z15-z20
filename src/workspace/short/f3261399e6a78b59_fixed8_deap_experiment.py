"""Participant-independent development comparison for the fixed Z15 montage.

Requires the signed-license DEAP preprocessed Python files. This script never
uses s25-s32 for fitting, model selection, or development scores. Its output is
offline evidence only, not a Cyton or PL deployment artifact.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import pickle
import platform
from pathlib import Path

import numpy as np
import scipy
import sklearn
from scipy import signal
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score, f1_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

from .fixed8_deap_preflight import (
    CYTON_CHANNELS, DEAP_INDICES, DEV_SUBJECTS, EXPECTED_DATA_SHAPE,
    EXPECTED_LABEL_SHAPE, TASK_COLUMNS, audit, subject_paths,
)


SAMPLE_RATE = 128
BANDS_HZ = ((4, 8), (8, 13), (13, 30), (30, 43))
SECONDS_PER_WINDOW = 12
BASELINE_SAMPLES = 3 * SAMPLE_RATE
WINDOW_SAMPLES = SECONDS_PER_WINDOW * SAMPLE_RATE
WINDOWS_PER_TRIAL = 5
METHODS = ("power_linear", "logcov_rbf", "tangent_linear")
PROTOCOL_PATH = Path(__file__).with_name("fixed8_protocol.json")


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def matrix_log_vectors(covariances: np.ndarray) -> np.ndarray:
    """Upper-triangle matrix-log vectors, with sqrt(2) off-diagonal scaling."""
    eigenvalues, vectors = np.linalg.eigh(covariances)
    if np.any(eigenvalues <= 0):
        raise ValueError("covariance must be positive definite")
    matrix_logs = (vectors * np.log(eigenvalues)[..., None, :]) @ np.swapaxes(vectors, -1, -2)
    n_channels = covariances.shape[-1]
    upper = np.triu_indices(n_channels)
    features = matrix_logs[..., upper[0], upper[1]].copy()
    features[..., upper[0] != upper[1]] *= np.sqrt(2)
    return features.reshape(len(features), -1)


def tangent_vectors(covariances: np.ndarray, training_covariances: np.ndarray) -> np.ndarray:
    """Affine-invariant tangent mapping at a train-only arithmetic SPD reference."""
    reference = training_covariances.mean(axis=0)
    eigenvalues, vectors = np.linalg.eigh(reference)
    if np.any(eigenvalues <= 0):
        raise ValueError("training reference must be positive definite")
    inv_sqrt = (vectors * (eigenvalues ** -0.5)[..., None, :]) @ np.swapaxes(vectors, -1, -2)
    whitened = np.einsum("bij,nbjk,bkl->nbil", inv_sqrt, covariances, inv_sqrt,
                         optimize=True)
    return matrix_log_vectors(whitened)


def trial_features(trial: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return five non-overlapping windows; channels are in fixed Cyton order."""
    if trial.shape != (len(CYTON_CHANNELS), 63 * SAMPLE_RATE):
        raise ValueError(f"unexpected trial shape: {trial.shape}")
    power = np.empty((WINDOWS_PER_TRIAL, len(BANDS_HZ) * len(CYTON_CHANNELS)))
    covariances = np.empty((WINDOWS_PER_TRIAL, len(BANDS_HZ),
                            len(CYTON_CHANNELS), len(CYTON_CHANNELS)))
    for band_index, band in enumerate(BANDS_HZ):
        sos = signal.butter(4, band, fs=SAMPLE_RATE, btype="bandpass", output="sos")
        # The three-second pre-stimulus segment warms up the causal filter.
        filtered = signal.sosfilt(sos, trial, axis=1)
        for window_index in range(WINDOWS_PER_TRIAL):
            start = BASELINE_SAMPLES + window_index * WINDOW_SAMPLES
            section = filtered[:, start:start + WINDOW_SAMPLES]
            covariance = np.cov(section)
            covariance += 0.05 * np.trace(covariance) / len(CYTON_CHANNELS) * np.eye(len(CYTON_CHANNELS))
            covariances[window_index, band_index] = covariance
            left = band_index * len(CYTON_CHANNELS)
            power[window_index, left:left + len(CYTON_CHANNELS)] = np.log(
                np.maximum(np.var(section, axis=1, ddof=1), 1e-12))
    return power, covariances


def extract_development(data_dir: Path, manifest: dict) -> dict[str, np.ndarray]:
    """Extract s01-s24 only; holdout files are audited, never opened here."""
    expected_hashes = {row["subject"]: row["sha256"] for row in manifest["records"]}
    power_rows, covariance_rows, rating_rows, row_keys = [], [], [], []
    for path in subject_paths(data_dir):
        subject = int(path.stem[1:])
        if subject not in DEV_SUBJECTS:
            continue
        if file_hash(path) != expected_hashes[subject]:
            raise ValueError(f"dataset file changed since audit: {path}")
        # Only open trusted official DEAP pickles obtained under the license.
        with path.open("rb") as stream:
            payload = pickle.load(stream, encoding="latin1")
        data, labels = np.asarray(payload["data"]), np.asarray(payload["labels"])
        if data.shape != EXPECTED_DATA_SHAPE or labels.shape != EXPECTED_LABEL_SHAPE:
            raise ValueError(f"unexpected DEAP shapes in {path}")
        for trial_index in range(40):
            trial = data[trial_index, DEAP_INDICES, :]
            powers, covariances = trial_features(trial)
            power_rows.extend(powers)
            covariance_rows.extend(covariances)
            rating_rows.extend([labels[trial_index, :2]] * WINDOWS_PER_TRIAL)
            row_keys.extend((subject, trial_index, window_index)
                            for window_index in range(WINDOWS_PER_TRIAL))
        print(f"EXTRACTED subject={subject:02d}", flush=True)
    keys = np.asarray(row_keys, dtype=np.int16)
    if len(keys) != len(DEV_SUBJECTS) * 40 * WINDOWS_PER_TRIAL or len(set(map(tuple, keys))) != len(keys):
        raise ValueError("missing or duplicate subject/trial/window keys")
    result = {"power": np.asarray(power_rows),
              "covariances": np.asarray(covariance_rows),
              "ratings": np.asarray(rating_rows), "keys": keys}
    if not all(np.isfinite(value).all() for value in result.values()):
        raise ValueError("non-finite extracted features or ratings")
    return result


def model_for(method: str):
    classifier = (SVC(kernel="rbf", C=1, class_weight="balanced")
                  if method == "logcov_rbf" else
                  LogisticRegression(C=1, class_weight="balanced", max_iter=1000))
    return make_pipeline(StandardScaler(), classifier)


def fold_features(method: str, data: dict[str, np.ndarray],
                  train: np.ndarray, test: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    if method == "power_linear":
        return data["power"][train], data["power"][test]
    if method == "logcov_rbf":
        return (matrix_log_vectors(data["covariances"][train]),
                matrix_log_vectors(data["covariances"][test]))
    if method == "tangent_linear":
        reference = data["covariances"][train]
        return (tangent_vectors(reference, reference),
                tangent_vectors(data["covariances"][test], reference))
    raise ValueError(f"unknown method: {method}")


def evaluate_development(data: dict[str, np.ndarray]) -> tuple[dict, list[tuple]]:
    keys, ratings = data["keys"], data["ratings"]
    groups = keys[:, 0]
    summaries, predictions = {}, []
    for task, column in TASK_COLUMNS.items():
        eligible = ratings[:, column] != 5
        targets = (ratings[:, column] > 5).astype(np.int8)
        summaries[task] = {}
        for method in METHODS:
            participant_scores = []
            for subject in DEV_SUBJECTS:
                train, test = eligible & (groups != subject), eligible & (groups == subject)
                if set(np.unique(targets[train])) != {0, 1} or set(np.unique(targets[test])) != {0, 1}:
                    raise ValueError(f"both classes required in {task} fold for subject {subject}")
                train_x, test_x = fold_features(method, data, train, test)
                predicted = model_for(method).fit(train_x, targets[train]).predict(test_x)
                truth = targets[test]
                score = {"subject": subject,
                         "balanced_accuracy": float(balanced_accuracy_score(truth, predicted)),
                         "macro_f1": float(f1_score(truth, predicted, average="macro")),
                         "windows": int(test.sum())}
                participant_scores.append(score)
                for key, actual, guess in zip(keys[test], truth, predicted):
                    predictions.append((task, method, *map(int, key), int(actual), int(guess)))
            summaries[task][method] = {
                "mean_subject_balanced_accuracy": float(np.mean(
                    [row["balanced_accuracy"] for row in participant_scores])),
                "participants": participant_scores,
            }
            print(f"DEV {task} {method}: "
                  f"{summaries[task][method]['mean_subject_balanced_accuracy']:.4f}", flush=True)
    return summaries, predictions


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_dir", type=Path)
    parser.add_argument("--output", type=Path,
                        default=Path(__file__).with_name("output") / "deap_fixed8")
    args = parser.parse_args()
    manifest = audit(args.data_dir)
    args.output.mkdir(parents=True, exist_ok=True)
    manifest_path = args.output / "data_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    data = extract_development(args.data_dir, manifest)
    feature_path = args.output / "development_features.npz"
    np.savez_compressed(feature_path, **data)
    summaries, predictions = evaluate_development(data)
    predictions_path = args.output / "development_predictions.csv"
    with predictions_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(("task", "method", "subject", "trial", "window", "target", "prediction"))
        writer.writerows(predictions)
    report = {"status": "development only; no untouched holdout or Cyton evaluation",
              "protocol_sha256": file_hash(PROTOCOL_PATH),
              "source_sha256": file_hash(Path(__file__)),
              "manifest_sha256": file_hash(manifest_path),
              "features_sha256": file_hash(feature_path),
              "predictions_sha256": file_hash(predictions_path),
              "software": {"python": platform.python_version(),
                           "numpy": np.__version__, "scipy": scipy.__version__,
                           "scikit_learn": sklearn.__version__},
              "montage": CYTON_CHANNELS, "bands_hz": BANDS_HZ,
              "methods": METHODS, "tasks": summaries}
    (args.output / "development_results.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8")
    print("DEAP_FIXED8_DEVELOPMENT_COMPLETE; holdout remains untouched", flush=True)


if __name__ == "__main__":
    main()
