#!/usr/bin/env python3
"""Leakage-safe, frozen participant split for a Cyton-compatible MI candidate."""

import argparse
import hashlib
import json
import sys
from fractions import Fraction
from pathlib import Path

import mne
import numpy as np
from scipy import signal
from sklearn import __version__ as sklearn_version
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score, f1_score
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "pynq_guardianloop"))
from cyton_sqi import CausalEEGFilter  # noqa: E402
from mi_features import CHANNELS, RATE_HZ, WINDOW_SAMPLES, feature, relative_feature  # noqa: E402


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_trials(path, subject, run, start_seconds, *, variant="absolute"):
    raw = mne.io.read_raw_edf(path, preload=False, verbose="ERROR")
    source_rate_hz = raw.info["sfreq"]
    if source_rate_hz not in (128.0, 160.0):
        raise ValueError(f"unexpected sample rate: {path}")
    cleaned_names = [name.rstrip(".").upper() for name in raw.ch_names]
    if len(cleaned_names) != len(set(cleaned_names)) or not set(CHANNELS).issubset(cleaned_names):
        raise ValueError(f"missing or duplicate fixed channels: {path}")
    picks = [cleaned_names.index(name) for name in CHANNELS]
    eeg_uv = raw.get_data(picks=picks).T * 1e6
    ratio = Fraction(RATE_HZ, int(source_rate_hz))
    resampled = signal.resample_poly(eeg_uv, ratio.numerator, ratio.denominator, axis=0)
    conditioned = CausalEEGFilter(sample_rate_hz=RATE_HZ).process(resampled)
    rows, labels, meta = [], [], []
    for annotation in raw.annotations:
        if annotation["description"] not in ("T1", "T2"):
            continue
        if annotation["duration"] < start_seconds + WINDOW_SAMPLES / RATE_HZ:
            continue
        start = int(round((annotation["onset"] + start_seconds) * RATE_HZ))
        window = conditioned[start:start + WINDOW_SAMPLES]
        if window.shape[0] != WINDOW_SAMPLES:
            continue
        if variant == "absolute":
            vector = feature(window)
        elif variant == "rest_relative":
            baseline_start = int(round((annotation["onset"] - 3.5) * RATE_HZ))
            baseline = conditioned[baseline_start:baseline_start + WINDOW_SAMPLES]
            if baseline.shape != window.shape:
                continue
            vector = relative_feature(window, baseline)
        else:
            raise ValueError(f"unknown feature variant: {variant}")
        rows.append(vector)
        labels.append(0 if annotation["description"] == "T1" else 1)
        meta.append({"subject": subject, "run": run, "onset_seconds": float(annotation["onset"]),
                     "source_rate_hz": source_rate_hz,
                     "label": annotation["description"], "file": str(path)})
    if not rows:
        raise ValueError(f"no valid imagined left/right events: {path}")
    return rows, labels, meta


def subject_metrics(y_true, y_pred, subjects):
    result = []
    for subject in sorted(set(subjects)):
        mask = subjects == subject
        if set(y_true[mask]) != {0, 1}:
            raise ValueError(f"both task classes required for subject {subject}")
        result.append({"subject": int(subject), "trials": int(mask.sum()),
                       "balanced_accuracy": float(balanced_accuracy_score(y_true[mask], y_pred[mask])),
                       "macro_f1": float(f1_score(y_true[mask], y_pred[mask], average="macro"))})
    return result


def train_model(x, y, columns):
    scaler = StandardScaler().fit(x[:, columns])
    estimator = LogisticRegression(C=1.0, class_weight="balanced", max_iter=2000,
                                   random_state=20260930).fit(scaler.transform(x[:, columns]), y)
    return scaler, estimator


def evaluate_model(x_train, y_train, x_eval, y_eval, subjects_eval, columns):
    scaler, estimator = train_model(x_train, y_train, columns)
    prediction = estimator.predict(scaler.transform(x_eval[:, columns]))
    details = subject_metrics(y_eval, prediction, subjects_eval)
    return details, prediction, scaler, estimator


def bootstrap_ci(values, seed):
    rng = np.random.default_rng(seed)
    sample = np.asarray(values)
    draws = rng.choice(sample, size=(10000, len(sample)), replace=True).mean(axis=1)
    return [float(v) for v in np.quantile(draws, [0.025, 0.975])]


def run(args):
    protocol_path = HERE / "mi_physionet_protocol.json"
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    if args.last_subject != 109 or args.first_subject != 1:
        raise ValueError("confirmatory experiment requires frozen subjects 1..109")
    all_features, all_labels, all_subjects, metadata = [], [], [], []
    source_hashes = {}
    for subject in range(1, 110):
        for run_number in protocol["runs"]:
            name = f"S{subject:03d}/S{subject:03d}R{run_number:02d}.edf"
            path = args.data_root / name
            if not path.is_file():
                raise FileNotFoundError(f"missing {path}; run mi_physionet_download.py")
            rows, labels, trials = load_trials(
                path, subject, run_number, protocol["epoch_start_seconds_after_cue"])
            all_features.extend(rows)
            all_labels.extend(labels)
            all_subjects.extend([subject] * len(labels))
            metadata.extend(trials)
            source_hashes[name] = file_hash(path)
        if subject % 10 == 0 or subject == 109:
            print(f"features {subject}/109 subjects", flush=True)
    x = np.asarray(all_features)
    y = np.asarray(all_labels)
    subjects = np.asarray(all_subjects)
    training = subjects <= 70
    validation = (subjects >= 71) & (subjects <= 89)
    testing = subjects >= 90
    if not (set(subjects[training]) & set(subjects[validation]) == set()
            and set(subjects[testing]) & set(subjects[validation]) == set()):
        raise AssertionError("subject leakage")
    baseline = [band * 8 + index for band in range(2) for index in (2, 3)]
    options = {"C3_C4": baseline, "FIXED_EIGHT": list(range(16))}
    validation_results = {}
    for name, columns in options.items():
        folds, _, _, _ = evaluate_model(x[training], y[training], x[validation],
                                        y[validation], subjects[validation], columns)
        validation_results[name] = {"per_subject": folds,
                                    "mean_balanced_accuracy": float(np.mean([
                                        row["balanced_accuracy"] for row in folds]))}
    selected = max(options, key=lambda name: validation_results[name]["mean_balanced_accuracy"])
    train_final = ~testing
    test_rows, predictions, scaler, estimator = evaluate_model(
        x[train_final], y[train_final], x[testing], y[testing], subjects[testing], options[selected])
    standardized = (x[testing][:, options[selected]] - scaler.mean_) / scaler.scale_
    portable_scores = standardized @ estimator.coef_[0] + estimator.intercept_[0]
    sklearn_scores = estimator.decision_function(scaler.transform(x[testing][:, options[selected]]))
    max_portable_error = float(np.max(np.abs(portable_scores - sklearn_scores)))
    if max_portable_error > 1e-10 or not np.array_equal(portable_scores >= 0, predictions == 1):
        raise AssertionError("NumPy ARM score is inconsistent with sklearn")
    test_ba = [row["balanced_accuracy"] for row in test_rows]
    ci = bootstrap_ci(test_ba, protocol["seed"])
    passed = bool(np.mean(test_ba) >= .60 and ci[0] > .50)
    args.output.mkdir(parents=True, exist_ok=True)
    trial_predictions = []
    for record, prediction in zip(np.asarray(metadata, dtype=object)[testing], predictions):
        trial_predictions.append({**record, "prediction": "T1" if prediction == 0 else "T2"})
    report = {
        "protocol_sha256": file_hash(protocol_path), "source": protocol["source"],
        "source_sha256": source_hashes, "channels": list(CHANNELS),
        "software": {"mne": mne.__version__, "sklearn": sklearn_version,
                     "numpy": np.__version__},
        "split_subject_counts": {"train": 70, "validation": 19, "test": 20},
        "split_trial_counts": {"train": int(training.sum()),
                               "validation": int(validation.sum()), "test": int(testing.sum())},
        "validation": validation_results, "selected": selected,
        "test_mean_subject_balanced_accuracy": float(np.mean(test_ba)),
        "test_mean_subject_macro_f1": float(np.mean([row["macro_f1"] for row in test_rows])),
        "test_subject_bootstrap_95_ci": ci,
        "portable_score_max_abs_error": max_portable_error,
        "test_per_subject": test_rows, "test_trial_predictions": trial_predictions,
        "promotion_gate_passed": passed,
        "limitations": ["public-data cue-locked trials, not Cyton accuracy",
                        "dataset has a different hardware reference from Cyton",
                        "no no-cue false-trigger test or live control validation"]
    }
    (args.output / "evaluation.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    model_info = {"channels": list(CHANNELS), "selected": selected,
                  "selected_channels": ["C3", "C4"] if selected == "C3_C4" else list(CHANNELS),
                  "source_rate_hz": RATE_HZ, "window_samples": WINDOW_SAMPLES,
                  "feature": protocol["features"], "protocol_sha256": report["protocol_sha256"],
                  "promotion_gate_passed": passed,
                  "control_enabled": False}
    np.savez_compressed(args.output / "model_offline_candidate.npz",
                        mean=scaler.mean_, scale=scaler.scale_, coef=estimator.coef_[0],
                        intercept=estimator.intercept_[0],
                        columns=np.asarray(options[selected], dtype=np.int64),
                        metadata=json.dumps(model_info, ensure_ascii=False))
    print(json.dumps({key: report[key] for key in (
        "selected", "test_mean_subject_balanced_accuracy",
        "test_subject_bootstrap_95_ci", "promotion_gate_passed")}, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path(r"D:\ican\datasets\EEGMMIDB"))
    parser.add_argument("--output", type=Path, default=HERE / "output" / "mi_physionet_fixed8_v1")
    parser.add_argument("--first-subject", type=int, default=1)
    parser.add_argument("--last-subject", type=int, default=109)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
