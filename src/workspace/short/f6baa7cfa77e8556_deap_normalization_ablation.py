"""Bounded development-only ablation; no fitting on a held-out person's future data."""

import csv
import json
import pickle
from pathlib import Path

import numpy as np
from scipy import signal
from sklearn.metrics import balanced_accuracy_score, f1_score

from .fixed8_deap_experiment import (
    BANDS_HZ, SAMPLE_RATE, BASELINE_SAMPLES, matrix_log_vectors, model_for, file_hash,
)
from .fixed8_deap_preflight import CYTON_CHANNELS, DEAP_INDICES, DEV_SUBJECTS, TASK_COLUMNS


HERE = Path(__file__).parent
INITIAL = HERE / "output/deap_fixed8_initial_20260926"
OUTPUT = HERE / "output/deap_normalization_20260926"
DATA = Path(r"D:\ican\datasets\DEAP\data_preprocessed_python")


def baseline_statistics(trial):
    """Use only the pre-stimulus three seconds; discard first second of filter settling."""
    powers, covariances = [], []
    for band in BANDS_HZ:
        sos = signal.butter(4, band, fs=SAMPLE_RATE, btype="bandpass", output="sos")
        baseline = signal.sosfilt(sos, trial[:, :BASELINE_SAMPLES], axis=1)[:, SAMPLE_RATE:]
        covariance = np.cov(baseline)
        covariance += .05 * np.trace(covariance) / 8 * np.eye(8)
        powers.extend(np.log(np.maximum(np.var(baseline, axis=1, ddof=1), 1e-12)))
        covariances.append(covariance)
    return np.array(powers), np.array(covariances)


def relative_power(power):
    values = power.reshape(-1, 4, 8)
    return (values - np.logaddexp.reduce(values, axis=1)[:, None, :]).reshape(-1, 32)


def baseline_whiten(covariance, baseline):
    eigenvalues, vectors = np.linalg.eigh(baseline)
    if np.any(eigenvalues <= 0):
        raise ValueError("Non-positive baseline covariance")
    transform = (vectors * eigenvalues[..., None, :] ** -.5) @ vectors.swapaxes(-1, -2)
    return transform @ covariance @ transform


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    protocol = {
        "montage": CYTON_CHANNELS, "development": DEV_SUBJECTS, "holdout": "s25-s32 unopened",
        "hypothesis": "Removing baseline/amplitude differences improves cross-person balanced accuracy",
        "variants": ["relative_power_linear", "baseline_power_linear", "baseline_logcov_rbf"],
        "calibration": "per-trial three-second pre-stimulus segment, no labels or future data; last two seconds used",
        "deployment_limit": "per-trial baselines are not equivalent to one calibration for continuous Cyton use",
        "budget": "three variants, C=1 fixed; no repeated tuning; both tasks, 24 LOSO folds",
        "decision": "continue a variant only if mean paired gain >=.02 and Bonferroni bootstrap interval excludes zero; otherwise change method family",
        "interval": "participant bootstrap 20000 draws, seed 20260926, six comparisons, 99.1667% intervals; exploratory",
    }
    (OUTPUT / "protocol.json").write_text(json.dumps(protocol, indent=2), encoding="utf-8")
    original = json.loads((INITIAL / "development_results.json").read_text())
    feature_path = INITIAL / "development_features.npz"
    assert file_hash(feature_path) == original["features_sha256"]
    data = dict(np.load(feature_path, allow_pickle=False))
    manifest = json.loads((INITIAL / "data_manifest.json").read_text())
    hashes = {r["subject"]: r["sha256"] for r in manifest["records"]}
    baseline_power = np.empty_like(data["power"])
    baseline_cov = np.empty_like(data["covariances"])
    for subject in DEV_SUBJECTS:
        path = DATA / f"s{subject:02d}.dat"
        assert file_hash(path) == hashes[subject]
        with path.open("rb") as stream:
            payload = pickle.load(stream, encoding="latin1")
        for trial in range(40):
            power, covariance = baseline_statistics(payload["data"][trial, DEAP_INDICES, :BASELINE_SAMPLES])
            mask = (data["keys"][:, 0] == subject) & (data["keys"][:, 1] == trial)
            baseline_power[mask], baseline_cov[mask] = power, covariance
        print(f"BASELINE subject={subject}", flush=True)
    features = {
        "relative_power_linear": relative_power(data["power"]),
        "baseline_power_linear": data["power"] - baseline_power,
        "baseline_logcov_rbf": matrix_log_vectors(baseline_whiten(data["covariances"], baseline_cov)),
    }
    np.savez_compressed(OUTPUT / "features.npz", **features)
    results, predictions = {}, []
    rng = np.random.default_rng(20260926)
    for task, column in TASK_COLUMNS.items():
        results[task] = {}
        eligible = data["ratings"][:, column] != 5
        target = (data["ratings"][:, column] > 5).astype(int)
        for name, x in features.items():
            scores = []
            parent = "logcov_rbf" if name.endswith("rbf") else "power_linear"
            for subject in DEV_SUBJECTS:
                test = eligible & (data["keys"][:, 0] == subject)
                train = eligible & (data["keys"][:, 0] != subject)
                predicted = model_for(parent).fit(x[train], target[train]).predict(x[test])
                scores.append({"subject": subject, "balanced_accuracy": balanced_accuracy_score(target[test], predicted),
                               "macro_f1": f1_score(target[test], predicted, average="macro")})
                predictions.extend((task, name, *map(int, key), int(y), int(p))
                                   for key, y, p in zip(data["keys"][test], target[test], predicted))
            values = np.array([s["balanced_accuracy"] for s in scores])
            old = np.array([s["balanced_accuracy"] for s in original["tasks"][task][parent]["participants"]])
            difference = values - old
            interval = np.quantile(difference[rng.integers(0, 24, (20000, 24))].mean(axis=1), [.05/12, 1-.05/12])
            results[task][name] = {"mean_subject_balanced_accuracy": values.mean(), "participants": scores,
                "paired_parent": parent, "gain": difference.mean(), "adjusted_interval": interval.tolist(),
                "continue": bool(difference.mean() >= .02 and interval[0] > 0)}
            print(task, name, results[task][name]["mean_subject_balanced_accuracy"], "continue", results[task][name]["continue"], flush=True)
    with (OUTPUT / "predictions.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["task", "method", "subject", "trial", "window", "target", "prediction"])
        writer.writerows(predictions)
    report = {"tasks": results, "software": original["software"], "status": "development only",
              "hashes": {str(p): file_hash(p) for p in [Path(__file__), INITIAL / "data_manifest.json",
                  feature_path, OUTPUT / "protocol.json", OUTPUT / "features.npz", OUTPUT / "predictions.csv"]}}
    (OUTPUT / "results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
