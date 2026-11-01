"""Separate online-feasible prefix alignment from full-session diagnostics."""

import csv
import json
from pathlib import Path

import numpy as np
from sklearn.metrics import balanced_accuracy_score, f1_score
from threadpoolctl import threadpool_limits

from .emotion_baseline import sha256
from .fixed8_deap_experiment import matrix_log_vectors
from .seed_covariance_diagnosis import INITIAL, model_for

OUTPUT = Path(__file__).parent / "output/seed_prefix_alignment_20260926"


def covariance_from_logs(features):
    values = features.reshape(-1, 5, 36).copy()
    rows, cols = np.triu_indices(8)
    values[..., rows != cols] /= np.sqrt(2)
    matrix = np.zeros((len(values), 5, 8, 8))
    matrix[..., rows, cols] = values
    matrix[..., cols, rows] = values
    eigenvalues, vectors = np.linalg.eigh(matrix)
    return (vectors * np.exp(eigenvalues)[..., None, :]) @ vectors.swapaxes(-1, -2)


def align_session(features, mode, prefix=5):
    if mode == "prefix_center":
        return features - features[:prefix].mean(axis=0)
    if mode == "session_center_diagnostic":
        return features - features.mean(axis=0)
    if mode != "prefix_ea":
        raise ValueError(mode)
    cov = covariance_from_logs(features)
    reference = cov[:prefix].mean(axis=0)
    values, vectors = np.linalg.eigh(reference)
    whitening = (vectors * values[..., None, :]**-.5) @ vectors.swapaxes(-1, -2)
    return matrix_log_vectors(whitening @ cov @ whitening)


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    if (OUTPUT / "results.json").exists():
        raise FileExistsError("Experiment already complete")
    original = json.loads((INITIAL / "results.json").read_text())
    feature_path = INITIAL / "features.npz"
    assert sha256(feature_path) == original["hashes"][str(feature_path)]
    data = dict(np.load(feature_path, allow_pickle=False))
    x, keys, y = data["logcov"], data["keys"], data["targets"]
    modes = ["prefix_center", "prefix_ea", "session_center_diagnostic"]
    protocol = {"montage": original["montage"], "modes": modes,
        "reference": "first five complete 12-second windows of each session, no labels; fixed thereafter",
        "timing": "60 seconds retained signal following 2-second trial filter warmup",
        "comparison": "raw LDA and all adaptations exclude identical first five windows per session, source and target",
        "model": "StandardScaler training-only + equal-prior auto-shrinkage LDA",
        "split": "15-person LOSO, all three sessions held out together",
        "diagnostic_only": "session_center_diagnostic reads future unlabeled EEG; ineligible for deployment",
        "confound": "first film has positive label, identical film order across people; prefix is not neutral rest",
        "acceptance": "prefix methods gain >=.02 and Bonferroni two-comparison participant-bootstrap lower >0",
        "limitations": "exploratory reused cohort; upstream SEED preprocessing offline; no independent wearer evidence"}
    (OUTPUT / "protocol.json").write_text(json.dumps(protocol, indent=2), encoding="utf-8")
    transformed = {mode: np.empty_like(x) for mode in modes}
    eligible = np.ones(len(x), dtype=bool)
    for subject, session in np.unique(keys[:, :2], axis=0):
        indices = np.flatnonzero((keys[:, 0] == subject) & (keys[:, 1] == session))
        indices = indices[np.lexsort((keys[indices, 3], keys[indices, 2]))]
        eligible[indices[:5]] = False
        for mode in modes:
            transformed[mode][indices] = align_session(x[indices], mode)
    methods = {"raw_matched": x, **transformed}
    results = {}
    draws = np.random.default_rng(20260926).integers(0, 15, (20000, 15))
    with (OUTPUT / "predictions.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["method", "subject", "session", "trial", "window", "target", "prediction"])
        for mode, features in methods.items():
            scores = []
            for subject in range(1, 16):
                train = eligible & (keys[:, 0] != subject)
                test = eligible & (keys[:, 0] == subject)
                with threadpool_limits(limits=2):
                    prediction = model_for("lda").fit(features[train], y[train]).predict(features[test])
                scores.append({"subject": subject, "balanced_accuracy": float(balanced_accuracy_score(y[test], prediction)),
                               "macro_f1": float(f1_score(y[test], prediction, average="macro"))})
                for key, target, pred in zip(keys[test], y[test], prediction):
                    writer.writerow([mode, *key, target, pred])
            values = np.array([s["balanced_accuracy"] for s in scores])
            results[mode] = {"participants": scores, "mean_balanced_accuracy": float(values.mean())}
            if mode == "raw_matched":
                baseline_values = values
            else:
                difference = values - baseline_values
                interval = np.quantile(difference[draws].mean(axis=1), [.0125, .9875])
                results[mode].update(paired_gain=float(difference.mean()), paired_ci975=interval.tolist(),
                    accept_exploratory=bool(mode != "session_center_diagnostic" and difference.mean() >= .02 and interval[0] > 0))
            print(mode, results[mode]["mean_balanced_accuracy"], flush=True)
    (OUTPUT / "results.json").write_text(json.dumps({"methods": results,
        "windows": int(eligible.sum()), "deployment": "unchanged", "hashes": {str(p): sha256(p)
        for p in [Path(__file__), feature_path, OUTPUT / "protocol.json", OUTPUT / "predictions.csv"]}}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
