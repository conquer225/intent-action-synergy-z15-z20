"""Leakage-aware, deployable 8-channel SEED emotion baseline.

The bundled source contains one participant/session only.  Evaluation therefore
uses leave-one-complete-trial-out cross-validation and must not be reported as
cross-participant performance.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
from pathlib import Path

import numpy as np
import scipy
from scipy import signal
from scipy.io import loadmat
import sklearn
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.metrics import accuracy_score, balanced_accuracy_score, confusion_matrix, f1_score
from sklearn.model_selection import LeaveOneGroupOut, cross_val_predict
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


DEFAULT_DATA = Path(
    r"D:\ican\整理\2025计设\2025035201-02 素材与源码\素材与源码\素材与源码"
    r"\信号处理与主要功能代码\dateset\15_20131105.mat"
)
DEFAULT_LABELS = DEFAULT_DATA.with_name("label.mat")
DEFAULT_OUTPUT = Path(__file__).with_name("output") / "emotion_baseline"

SAMPLE_RATE_HZ = 200
WINDOW_SECONDS = 4
WINDOW_SAMPLES = SAMPLE_RATE_HZ * WINDOW_SECONDS
BANDS_HZ = ((1, 4), (4, 8), (8, 14), (14, 31), (31, 45))
CHANNELS_62 = (
    "FP1", "FPZ", "FP2", "AF3", "AF4", "F7", "F5", "F3", "F1", "FZ",
    "F2", "F4", "F6", "F8", "FT7", "FC5", "FC3", "FC1", "FCZ", "FC2",
    "FC4", "FC6", "FT8", "T7", "C5", "C3", "C1", "CZ", "C2", "C4",
    "C6", "T8", "TP7", "CP5", "CP3", "CP1", "CPZ", "CP2", "CP4", "CP6",
    "TP8", "P7", "P5", "P3", "P1", "PZ", "P2", "P4", "P6", "P8",
    "PO7", "PO5", "PO3", "POZ", "PO4", "PO6", "PO8", "CB1", "O1", "OZ",
    "O2", "CB2",
)
# Symmetric, eight-channel first prototype.  This is an engineering choice, not
# a claim that these are the optimal emotion channels.
CHANNELS_8 = ("F3", "F4", "F7", "F8", "T7", "T8", "P3", "P4")
LABEL_NAMES = {-1: "negative", 0: "neutral", 1: "positive"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def extract_features(data_path: Path, labels_path: Path):
    contents = loadmat(data_path, verify_compressed_data_integrity=False)
    labels = loadmat(labels_path, verify_compressed_data_integrity=False)["label"].ravel().astype(int)
    trials = sorted(
        (name for name in contents if "_eeg" in name),
        key=lambda name: int(name.rsplit("eeg", 1)[1]),
    )
    if len(trials) != len(labels):
        raise ValueError(f"found {len(trials)} trials but {len(labels)} labels")
    indexes = [CHANNELS_62.index(name) for name in CHANNELS_8]
    filters = [
        signal.butter(4, band, btype="bandpass", fs=SAMPLE_RATE_HZ, output="sos")
        for band in BANDS_HZ
    ]
    features, targets, groups, rows = [], [], [], []
    for trial_index, (trial_name, target) in enumerate(zip(trials, labels), 1):
        raw = np.asarray(contents[trial_name], dtype=np.float64)[indexes]
        filtered = [signal.sosfiltfilt(sos, raw, axis=1) for sos in filters]
        window_count = raw.shape[1] // WINDOW_SAMPLES
        for window_index in range(window_count):
            section = slice(window_index * WINDOW_SAMPLES, (window_index + 1) * WINDOW_SAMPLES)
            # Feature order is band-major, then channel order in CHANNELS_8.
            vector = np.concatenate(
                [np.log(np.var(band[:, section], axis=1) + 1e-12) for band in filtered]
            )
            features.append(vector)
            targets.append(int(target))
            groups.append(trial_index)
            rows.append((trial_index, trial_name, window_index))
    return (
        np.asarray(features, dtype=np.float64),
        np.asarray(targets, dtype=np.int64),
        np.asarray(groups, dtype=np.int64),
        rows,
    )


def build_model():
    return make_pipeline(
        StandardScaler(),
        LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto"),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    x, y, groups, rows = extract_features(args.data, args.labels)
    model = build_model()
    prediction = cross_val_predict(
        model, x, y, groups=groups, cv=LeaveOneGroupOut(), method="predict"
    )
    labels = (-1, 0, 1)
    per_trial = []
    for trial_id in np.unique(groups):
        selected = groups == trial_id
        per_trial.append(
            {
                "trial_id": int(trial_id),
                "label": int(y[selected][0]),
                "label_name": LABEL_NAMES[int(y[selected][0])],
                "windows": int(selected.sum()),
                "accuracy": float(accuracy_score(y[selected], prediction[selected])),
            }
        )
    report = {
        "scope": "single participant/session; leave-one-complete-trial-out; not cross-participant",
        "hypothesis": "8-channel five-band log-power LDA exceeds 3-class chance on unseen trials",
        "falsification": "balanced accuracy does not exceed chance meaningfully on untouched trials",
        "data": str(args.data),
        "data_sha256": sha256(args.data),
        "labels": str(args.labels),
        "labels_sha256": sha256(args.labels),
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "window_seconds": WINDOW_SECONDS,
        "overlap_seconds": 0,
        "channels": list(CHANNELS_8),
        "bands_hz": [list(item) for item in BANDS_HZ],
        "feature_order": "band-major then channel",
        "samples": int(len(y)),
        "trials": int(len(np.unique(groups))),
        "metrics": {
            "accuracy": float(accuracy_score(y, prediction)),
            "balanced_accuracy": float(balanced_accuracy_score(y, prediction)),
            "macro_f1": float(f1_score(y, prediction, labels=labels, average="macro")),
            "confusion_matrix_labels": list(labels),
            "confusion_matrix": confusion_matrix(y, prediction, labels=labels).tolist(),
        },
        "per_trial": per_trial,
        "versions": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "scikit_learn": sklearn.__version__,
        },
    }

    model.fit(x, y)
    scaler = model.named_steps["standardscaler"]
    lda = model.named_steps["lineardiscriminantanalysis"]
    # Verify that the plain NumPy formula intended for ARM deployment gives
    # exactly the same class decisions as scikit-learn.
    scaled = (x - scaler.mean_) / scaler.scale_
    deployed_scores = scaled @ lda.coef_.T + lda.intercept_
    deployed_prediction = lda.classes_[np.argmax(deployed_scores, axis=1)]
    export_agreement = float(np.mean(deployed_prediction == model.predict(x)))
    if export_agreement != 1.0:
        raise RuntimeError(f"exported inference mismatch: agreement={export_agreement}")
    report["export_validation"] = {
        "formula": "((x - scaler_mean) / scaler_scale) @ lda_coef.T + lda_intercept",
        "prediction_agreement": export_agreement,
    }
    exported_model = {
        "model": "standard_scaler_plus_linear_discriminant_analysis",
        "classes": lda.classes_.astype(int).tolist(),
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "window_seconds": WINDOW_SECONDS,
        "channels": list(CHANNELS_8),
        "bands_hz": [list(item) for item in BANDS_HZ],
        "feature_order": "band-major then channel",
        "scaler_mean": scaler.mean_.tolist(),
        "scaler_scale": scaler.scale_.tolist(),
        "lda_coef": lda.coef_.tolist(),
        "lda_intercept": lda.intercept_.tolist(),
    }
    with (args.output / "metrics.json").open("w", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    with (args.output / "model.json").open("w", encoding="utf-8") as stream:
        json.dump(exported_model, stream, ensure_ascii=False, indent=2)
    with (args.output / "predictions.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.writer(stream)
        writer.writerow(("trial_id", "trial_name", "window_index", "label", "prediction"))
        for row, target, predicted in zip(rows, y, prediction):
            writer.writerow((*row, int(target), int(predicted)))
    print(json.dumps(report["metrics"], ensure_ascii=False, indent=2))
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
