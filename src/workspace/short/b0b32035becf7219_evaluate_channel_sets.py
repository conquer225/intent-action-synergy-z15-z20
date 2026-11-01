"""Compare practical 8-channel layouts on all SEED-VIG recordings.

Evaluation is participant-grouped LOSO.  The first 120 seconds of every
recording are used for unlabeled per-channel calibration and excluded from
scoring, matching the current GuardianLoop deployment protocol.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
from scipy.stats import pearsonr, spearmanr
from sklearn.metrics import accuracy_score, f1_score, mean_absolute_error, mean_squared_error


REFERENCE_DIR = Path(r"D:\ican\ican_fpga_project\software\pc_fatigue_reference")
if str(REFERENCE_DIR) not in sys.path:
    sys.path.insert(0, str(REFERENCE_DIR))

from fatigue_reference import SOURCE_CHANNEL_ORDER_17, perclos_to_class, ratio_to_class, tune_ratio_thresholds
from train_seedvig_8ch_calibrated_loso import (
    CALIBRATION_WINDOWS,
    calibrate_recording,
    make_model,
    smooth_features,
)
from train_seedvig_8ch_de_regression_loso import load_or_extract
from validate_seedvig_loso import DEFAULT_DATASET_ROOT, discover_pairs, participant_id


CHANNEL_SETS = {
    "current_asymmetric": ("FT7", "FT8", "CP1", "CP2", "P1", "PZ", "PO3", "O1"),
    "balanced_parietal_occipital": ("FT7", "FT8", "CP1", "CP2", "P1", "P2", "O1", "O2"),
    "posterior_only": ("CP1", "CP2", "P1", "P2", "PO3", "PO4", "O1", "O2"),
    "literature_critical": ("TP7", "TP8", "CP1", "CP2", "POZ", "O1", "OZ", "O2"),
    "temporal_occipital": ("FT7", "FT8", "TP7", "TP8", "PO3", "PO4", "O1", "O2"),
}


def score(y_true: np.ndarray, y_pred: np.ndarray, y_class: np.ndarray) -> dict:
    return {
        "pearson": float(pearsonr(y_true, y_pred).statistic),
        "spearman": float(spearmanr(y_true, y_pred).statistic),
        "rmse": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "accuracy": float(accuracy_score(perclos_to_class(y_true), y_class)),
        "macro_f1": float(f1_score(perclos_to_class(y_true), y_class, labels=[0, 1, 2], average="macro", zero_division=0)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", type=Path, default=DEFAULT_DATASET_ROOT)
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("channel_set_loso.json"))
    parser.add_argument("--cache", type=Path, default=Path(__file__).with_name("cache_all17"))
    args = parser.parse_args()

    pairs = discover_pairs(args.dataset_root)
    groups: dict[str, list[str]] = {}
    full = {}
    all_channels = list(SOURCE_CHANNEL_ORDER_17)
    for index, (name, raw_path, label_path) in enumerate(pairs, 1):
        print(f"[{index:02d}/{len(pairs):02d}] all-channel DE: {name}", flush=True)
        groups.setdefault(participant_id(name), []).append(name)
        full[name] = load_or_extract(name, raw_path, label_path, all_channels, args.cache, True)

    results = {}
    for set_name, channels in CHANNEL_SETS.items():
        print(f"\n=== {set_name}: {', '.join(channels)} ===", flush=True)
        column_indices = []
        for channel in channels:
            channel_index = all_channels.index(channel)
            column_indices.extend(range(channel_index * 5, channel_index * 5 + 5))

        recordings = {}
        for name, item in full.items():
            selected = np.asarray(item["features"])[:, column_indices]
            calibrated, _, _ = calibrate_recording(selected)
            recordings[name] = {
                "x": smooth_features(calibrated[CALIBRATION_WINDOWS:]),
                "y": np.asarray(item["perclos"])[CALIBRATION_WINDOWS:],
            }

        references, predictions, class_predictions = [], [], []
        folds = []
        for fold_number, held_out in enumerate(sorted(groups, key=int), 1):
            train_names = [name for name in recordings if participant_id(name) != held_out]
            test_names = groups[held_out]
            train_x = np.concatenate([recordings[name]["x"] for name in train_names])
            train_y = np.concatenate([recordings[name]["y"] for name in train_names])
            test_x = np.concatenate([recordings[name]["x"] for name in test_names])
            test_y = np.concatenate([recordings[name]["y"] for name in test_names])
            model = make_model().fit(train_x, train_y)
            development = np.clip(model.predict(train_x), 0.0, 1.0)
            thresholds = tune_ratio_thresholds(development, perclos_to_class(train_y))
            prediction = np.clip(model.predict(test_x), 0.0, 1.0)
            predicted_class = ratio_to_class(prediction, thresholds)
            fold_score = score(test_y, prediction, predicted_class)
            fold_score["participant"] = held_out
            folds.append(fold_score)
            references.append(test_y)
            predictions.append(prediction)
            class_predictions.append(predicted_class)
            print(f"  fold {fold_number:02d}/{len(groups):02d} p={held_out} f1={fold_score['macro_f1']:.3f}", flush=True)

        y_true = np.concatenate(references)
        y_pred = np.concatenate(predictions)
        y_class = np.concatenate(class_predictions)
        aggregate = score(y_true, y_pred, y_class)
        results[set_name] = {"channels": list(channels), "aggregate": aggregate, "folds": folds}
        print(f"  aggregate: {aggregate}", flush=True)

    ranking = sorted(results, key=lambda name: results[name]["aggregate"]["macro_f1"], reverse=True)
    payload = {
        "protocol": "21 participant-grouped LOSO; 120 s unlabeled per-recording calibration excluded from scoring; identical 5-band DE/HGB pipeline",
        "recordings": len(pairs),
        "participants": len(groups),
        "ranking_by_macro_f1": ranking,
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
