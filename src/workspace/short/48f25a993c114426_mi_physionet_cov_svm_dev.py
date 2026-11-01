#!/usr/bin/env python3
"""One exploratory nonlinear spatial-covariance baseline; development subjects only."""

import json
from pathlib import Path

import numpy as np
from sklearn.svm import SVC
from sklearn.preprocessing import StandardScaler

from mi_physionet_cov_dev import trial_features
from mi_physionet_evaluate import bootstrap_ci, subject_metrics


ROOT = Path(r"D:\ican\datasets\EEGMMIDB")
OUT = Path(__file__).resolve().parent / "output" / "mi_physionet_cov_svm_dev_v4"


def main():
    features = {"C3_C4": [], "FIXED_EIGHT": []}
    labels, subjects = [], []
    for subject in range(1, 90):
        for run in (4, 8, 12):
            path = ROOT / f"S{subject:03d}" / f"S{subject:03d}R{run:02d}.edf"
            trial_vectors, run_labels = trial_features(path)
            for name in features:
                features[name].extend(trial_vectors[name])
            labels.extend(run_labels)
            subjects.extend([subject] * len(run_labels))
    group = np.asarray(subjects)
    y = np.asarray(labels)
    train, validation = group <= 70, group >= 71
    report = {}
    for name, vectors in features.items():
        x = np.asarray(vectors)
        scaler = StandardScaler().fit(x[train])
        model = SVC(C=1.0, kernel="rbf", gamma="scale", class_weight="balanced").fit(
            scaler.transform(x[train]), y[train])
        predicted = model.predict(scaler.transform(x[validation]))
        folds = subject_metrics(y[validation], predicted, group[validation])
        ba = [row["balanced_accuracy"] for row in folds]
        report[name] = {"mean_subject_balanced_accuracy": float(np.mean(ba)),
                        "subject_bootstrap_95_ci": bootstrap_ci(ba, 20260930),
                        "support_vector_count": int(model.n_support_.sum()),
                        "per_subject": folds}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "development_only.json").write_text(json.dumps({
        "claim": "exploratory; not a fresh held-out confirmation",
        "classifier": "standardized RBF SVC C=1 gamma=scale class_weight=balanced",
        "train_subjects": [1, 70], "validation_subjects": [71, 89],
        "test_subjects_touched": False, "results": report,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print({name: (row["mean_subject_balanced_accuracy"], row["support_vector_count"])
           for name, row in report.items()})


if __name__ == "__main__":
    main()
