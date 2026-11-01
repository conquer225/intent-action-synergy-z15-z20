#!/usr/bin/env python3
"""Development-only evaluation of rest-relative MI features; never reads test subjects."""

import json
from pathlib import Path

import numpy as np

from mi_physionet_evaluate import bootstrap_ci, evaluate_model, load_trials


DATA = Path(r"D:\ican\datasets\EEGMMIDB")
OUT = Path(__file__).resolve().parent / "output" / "mi_physionet_erd_dev_v2"


def main():
    features, labels, subjects = [], [], []
    for subject in range(1, 90):
        for run in (4, 8, 12):
            path = DATA / f"S{subject:03d}" / f"S{subject:03d}R{run:02d}.edf"
            x, y, _ = load_trials(path, subject, run, .5, variant="rest_relative")
            features.extend(x)
            labels.extend(y)
            subjects.extend([subject] * len(y))
    x = np.asarray(features)
    y = np.asarray(labels)
    group = np.asarray(subjects)
    train, validation = group <= 70, group >= 71
    results = {}
    for name, columns in {"C3_C4": [2, 3, 10, 11], "FIXED_EIGHT": list(range(16))}.items():
        per_subject, _, _, _ = evaluate_model(x[train], y[train], x[validation],
                                               y[validation], group[validation], columns)
        ba = [row["balanced_accuracy"] for row in per_subject]
        results[name] = {"mean_subject_balanced_accuracy": float(np.mean(ba)),
                         "subject_bootstrap_95_ci": bootstrap_ci(ba, 20260930),
                         "per_subject": per_subject}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "development_only.json").write_text(
        json.dumps({"feature": "task 0.5..3.5s minus preceding rest -3.5..-0.5s log Welch power",
                    "train_subjects": [1, 70], "validation_subjects": [71, 89],
                    "test_subjects_touched": False, "results": results},
                   indent=2, ensure_ascii=False), encoding="utf-8")
    print({name: row["mean_subject_balanced_accuracy"] for name, row in results.items()})


if __name__ == "__main__":
    main()
