"""Leakage-safe GAMEEMO 14-to-8-channel emotion baseline.

Evaluation is leave-one-participant-out (LOSO).  All windows from a participant
remain together, and scaling plus LDA fitting happen inside each training fold.
The final eight-channel model is exported as plain JSON for later ARM inference.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import re
from pathlib import Path

import numpy as np
import scipy
from scipy import signal
from scipy.io import loadmat, whosmat
import sklearn
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.metrics import accuracy_score, balanced_accuracy_score, confusion_matrix, f1_score
from sklearn.model_selection import LeaveOneGroupOut, cross_val_predict
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


DEFAULT_DATA = Path(r"D:\ican\datasets\GAMEEMO\data")
DEFAULT_ARCHIVE = DEFAULT_DATA.parent / "GAMEEMO_v3.zip"
DEFAULT_OUTPUT = Path(__file__).with_name("output") / "gameemo_8ch"

SAMPLE_RATE_HZ = 128
WINDOW_SECONDS = 4
WINDOW_SAMPLES = SAMPLE_RATE_HZ * WINDOW_SECONDS
BANDS_HZ = ((4, 8), (8, 13), (13, 30), (30, 43))
CHANNELS_14 = (
    "AF3", "AF4", "F3", "F4", "F7", "F8", "FC5", "FC6",
    "O1", "O2", "P7", "P8", "T7", "T8",
)
# Fixed before evaluation: symmetric frontal, temporal and occipital coverage.
CHANNELS_8 = ("AF3", "AF4", "F3", "F4", "T7", "T8", "O1", "O2")
GAME_LABELS = {
    1: {"class_id": 0, "name": "boring", "valence": "negative", "arousal": "low"},
    2: {"class_id": 1, "name": "calm", "valence": "positive", "arousal": "low"},
    3: {"class_id": 2, "name": "horror", "valence": "negative", "arousal": "high"},
    4: {"class_id": 3, "name": "funny", "valence": "positive", "arousal": "high"},
}
SOURCE_URL = "https://data.mendeley.com/datasets/b3pn4kwpmn/3"
SOURCE_DOI = "10.17632/b3pn4kwpmn.3"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def discover_records(data_root: Path):
    records = []
    for subject_dir in sorted(data_root.iterdir()):
        match = re.fullmatch(r"\(S(\d{2})\)", subject_dir.name)
        if not match or not subject_dir.is_dir():
            continue
        subject = int(match.group(1))
        mat_dir = subject_dir / "Preprocessed EEG Data" / ".mat format"
        files = sorted(mat_dir.glob("*AllChannels.mat"))
        if len(files) != 4:
            raise ValueError(f"{subject_dir}: expected 4 preprocessed MAT files, found {len(files)}")
        for path in files:
            game_match = re.fullmatch(rf"S{subject:02d}G([1-4])AllChannels\.mat", path.name)
            if not game_match:
                raise ValueError(f"unexpected filename: {path}")
            game = int(game_match.group(1))
            records.append(
                {
                    "subject": subject,
                    "game": game,
                    "class_id": GAME_LABELS[game]["class_id"],
                    "class_name": GAME_LABELS[game]["name"],
                    "path": path,
                }
            )
    if len(records) != 112:
        raise ValueError(f"expected 28 subjects x 4 games = 112 records, found {len(records)}")
    return records


def create_manifest(records, data_root: Path, archive: Path):
    manifest = {
        "dataset": "GAMEEMO version 3",
        "source_url": SOURCE_URL,
        "source_doi": SOURCE_DOI,
        "license": "CC BY 4.0",
        "source_archive": str(archive),
        "source_archive_bytes": archive.stat().st_size,
        "source_archive_sha256": sha256(archive),
        "data_root": str(data_root),
        "known_archive_anomaly": (
            "The official archive contains a duplicate nested S26 tree under S28; "
            "only direct top-level subject directories S01-S28 are used."
        ),
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "records": [
            {
                "subject": item["subject"],
                "game": item["game"],
                "class_id": item["class_id"],
                "class_name": item["class_name"],
                "relative_path": item["path"].relative_to(data_root).as_posix(),
                "bytes": item["path"].stat().st_size,
            }
            for item in records
        ],
    }
    encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    manifest["manifest_sha256"] = hashlib.sha256(encoded).hexdigest()
    return manifest


def extract_features(records):
    filters = [
        signal.butter(4, band, btype="bandpass", fs=SAMPLE_RATE_HZ, output="sos")
        for band in BANDS_HZ
    ]
    features, targets, groups, rows = [], [], [], []
    expected_keys = set(CHANNELS_14)
    for record in records:
        metadata = {name: shape for name, shape, _ in whosmat(record["path"])}
        if set(metadata) != expected_keys:
            raise ValueError(f"channel mismatch in {record['path']}: {sorted(metadata)}")
        lengths = {metadata[channel][0] for channel in CHANNELS_14}
        if len(lengths) != 1:
            raise ValueError(f"unequal channel lengths in {record['path']}")
        contents = loadmat(record["path"], variable_names=list(CHANNELS_14))
        raw = np.vstack([np.asarray(contents[channel]).ravel() for channel in CHANNELS_14])
        filtered = [signal.sosfiltfilt(sos, raw, axis=1) for sos in filters]
        window_count = raw.shape[1] // WINDOW_SAMPLES
        for window_index in range(window_count):
            section = slice(window_index * WINDOW_SAMPLES, (window_index + 1) * WINDOW_SAMPLES)
            vector = np.concatenate(
                [np.log(np.var(band[:, section], axis=1) + 1e-12) for band in filtered]
            )
            features.append(vector)
            targets.append(record["class_id"])
            groups.append(record["subject"])
            rows.append((record["subject"], record["game"], window_index))
    return (
        np.asarray(features, dtype=np.float64),
        np.asarray(targets, dtype=np.int64),
        np.asarray(groups, dtype=np.int64),
        rows,
    )


def select_channels(features: np.ndarray, channels):
    indexes = [CHANNELS_14.index(channel) for channel in channels]
    columns = [band_index * len(CHANNELS_14) + index for band_index in range(len(BANDS_HZ)) for index in indexes]
    return features[:, columns]


def build_model():
    return make_pipeline(
        StandardScaler(),
        LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto"),
    )


def evaluate(features, targets, groups, channels):
    x = select_channels(features, channels)
    prediction = cross_val_predict(
        build_model(), x, targets, groups=groups, cv=LeaveOneGroupOut(), method="predict"
    )
    labels = tuple(range(4))
    return x, prediction, {
        "channels": list(channels),
        "feature_count": int(x.shape[1]),
        "accuracy": float(accuracy_score(targets, prediction)),
        "balanced_accuracy": float(balanced_accuracy_score(targets, prediction)),
        "macro_f1": float(f1_score(targets, prediction, labels=labels, average="macro")),
        "confusion_matrix_labels": [GAME_LABELS[index + 1]["name"] for index in labels],
        "confusion_matrix": confusion_matrix(targets, prediction, labels=labels).tolist(),
        "per_subject": [
            {
                "subject": int(subject),
                "windows": int(np.sum(groups == subject)),
                "accuracy": float(accuracy_score(targets[groups == subject], prediction[groups == subject])),
                "balanced_accuracy": float(
                    balanced_accuracy_score(targets[groups == subject], prediction[groups == subject])
                ),
            }
            for subject in np.unique(groups)
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    records = discover_records(args.data)
    manifest = create_manifest(records, args.data, args.archive)
    features, targets, groups, rows = extract_features(records)
    x14, prediction14, metrics14 = evaluate(features, targets, groups, CHANNELS_14)
    x8, prediction8, metrics8 = evaluate(features, targets, groups, CHANNELS_8)

    retained = metrics8["balanced_accuracy"] / metrics14["balanced_accuracy"]
    report = {
        "scope": "GAMEEMO four-class participant-independent LOSO",
        "hypothesis": "fixed 8-channel montage retains at least 90% of 14-channel balanced accuracy",
        "falsification": "8-channel/14-channel balanced-accuracy ratio is below 0.90",
        "split_rule": "leave one complete participant out; preprocessing fit on training participants only",
        "window_seconds": WINDOW_SECONDS,
        "overlap_seconds": 0,
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "bands_hz": [list(band) for band in BANDS_HZ],
        "feature_order": "band-major then channel",
        "class_mapping": GAME_LABELS,
        "windows": int(len(targets)),
        "subjects": int(len(np.unique(groups))),
        "records": len(records),
        "manifest_sha256": manifest["manifest_sha256"],
        "metrics_14ch": metrics14,
        "metrics_8ch": metrics8,
        "balanced_accuracy_retained_ratio": float(retained),
        "hypothesis_passed": bool(retained >= 0.90),
        "versions": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "scikit_learn": sklearn.__version__,
        },
    }

    model = build_model().fit(x8, targets)
    scaler = model.named_steps["standardscaler"]
    lda = model.named_steps["lineardiscriminantanalysis"]
    deployed_scores = ((x8 - scaler.mean_) / scaler.scale_) @ lda.coef_.T + lda.intercept_
    deployed_prediction = lda.classes_[np.argmax(deployed_scores, axis=1)]
    agreement = float(np.mean(deployed_prediction == model.predict(x8)))
    if agreement != 1.0:
        raise RuntimeError(f"exported inference mismatch: agreement={agreement}")
    report["export_validation"] = {"prediction_agreement": agreement}
    exported_model = {
        "model": "standard_scaler_plus_linear_discriminant_analysis",
        "deployment_status": "prototype; requires Cyton domain validation/calibration",
        "classes": lda.classes_.astype(int).tolist(),
        "class_names": [GAME_LABELS[index + 1]["name"] for index in lda.classes_],
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "window_seconds": WINDOW_SECONDS,
        "channels": list(CHANNELS_8),
        "bands_hz": [list(band) for band in BANDS_HZ],
        "feature_order": "band-major then channel",
        "scaler_mean": scaler.mean_.tolist(),
        "scaler_scale": scaler.scale_.tolist(),
        "lda_coef": lda.coef_.tolist(),
        "lda_intercept": lda.intercept_.tolist(),
        "manifest_sha256": manifest["manifest_sha256"],
    }

    for filename, payload in (
        ("data_manifest.json", manifest),
        ("metrics.json", report),
        ("model_8ch.json", exported_model),
    ):
        with (args.output / filename).open("w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
    with (args.output / "predictions.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.writer(stream)
        writer.writerow(("subject", "game", "window", "target", "prediction_14ch", "prediction_8ch"))
        for row, target, pred14, pred8 in zip(rows, targets, prediction14, prediction8):
            writer.writerow((*row, int(target), int(pred14), int(pred8)))

    print(json.dumps({"14ch": metrics14, "8ch": metrics8, "retained_ratio": retained}, indent=2))
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
