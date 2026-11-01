#!/usr/bin/env python3
"""Exploratory within-person, later-run test after one cued calibration run."""

import json
from pathlib import Path

import numpy as np
from sklearn.metrics import balanced_accuracy_score, f1_score

from mi_physionet_evaluate import bootstrap_ci, load_trials, train_model


ROOT = Path(r"D:\ican\datasets\EEGMMIDB")
OUT = Path(__file__).resolve().parent / "output" / "mi_physionet_personal_dev"


def main():
    methods = {"C3_C4": [2, 3, 10, 11], "FIXED_EIGHT": list(range(16))}
    report = {}
    for variant in ("absolute", "rest_relative"):
        candidate = {name: [] for name in methods}
        for subject in range(1, 90):
            trials = {}
            for run in (4, 8, 12):
                path = ROOT / f"S{subject:03d}" / f"S{subject:03d}R{run:02d}.edf"
                x, y, _ = load_trials(path, subject, run, .5, variant=variant)
                trials[run] = (np.asarray(x), np.asarray(y))
            x_train, y_train = trials[4]
            x_test = np.vstack([trials[8][0], trials[12][0]])
            y_test = np.r_[trials[8][1], trials[12][1]]
            if set(y_train) != {0, 1} or set(y_test) != {0, 1}:
                raise ValueError(f"both classes required for subject {subject}")
            for name, columns in methods.items():
                scaler, model = train_model(x_train, y_train, columns)
                predicted = model.predict(scaler.transform(x_test[:, columns]))
                candidate[name].append({"subject": subject,
                                        "calibration_trials": len(y_train),
                                        "future_trials": len(y_test),
                                        "balanced_accuracy": float(balanced_accuracy_score(y_test, predicted)),
                                        "macro_f1": float(f1_score(y_test, predicted, average="macro"))})
        for name, per_subject in candidate.items():
            values = [row["balanced_accuracy"] for row in per_subject]
            report[f"{variant}_{name}"] = {
                "mean_subject_balanced_accuracy": float(np.mean(values)),
                "subject_bootstrap_95_ci": bootstrap_ci(values, 20260930),
                "per_subject": per_subject,
            }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "development_only.json").write_text(json.dumps({
        "claim": "exploratory within-person calibration, not subject-independent accuracy",
        "subjects": [1, 89], "calibration_run": 4, "future_test_runs": [8, 12],
        "final_held_out_subjects_touched": False, "methods": report,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print({key: value["mean_subject_balanced_accuracy"] for key, value in report.items()})


if __name__ == "__main__":
    main()
