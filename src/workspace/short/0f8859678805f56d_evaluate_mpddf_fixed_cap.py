"""Participant-grouped MPD-DF comparison of physical four versus eight EEG channels."""

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import scipy
import sklearn
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score, confusion_matrix, f1_score
from threadpoolctl import threadpool_limits


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(Path(r"D:\ican\ican_fpga_project\software\pc_fatigue_reference")))
from train_seedvig_8ch_calibrated_loso import calibrate_recording, smooth_features
from prepare_mpddf_fixed_cap import CHANNELS, VERSION


FOUR = ("T7", "T8", "O1", "O2")
EXPECTED_IDS = tuple(f"{identifier:02d}" for identifier in range(1, 51))
SEED = 20260925


def sha256(path):
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def load(cache):
    records, manifest = {}, []
    for identifier in EXPECTED_IDS:
        path = cache / f"subject_{identifier}.npz"
        with np.load(path, allow_pickle=False) as item:
            if str(item["version"].item()) != VERSION or tuple(item["channels"]) != CHANNELS:
                raise ValueError(f"Wrong montage/preprocessing for {path}")
            source = np.asarray(item["features"], dtype=np.float64)
            original = np.asarray(item["labels"], dtype=np.int8)
            times = np.asarray(item["window_start_seconds"], dtype=np.int32)
            source_md5 = [str(value) for value in item["source_md5"]]
        if source.shape != (len(original), 40) or len(original) != len(times):
            raise ValueError(f"Invalid feature/label shape for {path}")
        selected = {}
        for name, channels in (("four", FOUR), ("eight", CHANNELS)):
            columns = [CHANNELS.index(channel) * 5 + band for channel in channels for band in range(5)]
            calibrated, _, _ = calibrate_recording(source[:, columns])
            selected[name] = smooth_features(calibrated[15:])
        mask = (original[15:] >= 0) & (original[15:] <= 4)
        records[identifier] = {
            "x": {key: value[mask] for key, value in selected.items()},
            "y": (original[15:][mask] > 0).astype(np.int8),
            "published_label": original[15:][mask],
            "window_index": np.flatnonzero(mask) + 15,
            "window_start_seconds": times[15:][mask],
        }
        if len(records[identifier]["y"]) == 0:
            raise ValueError(f"No valid scored windows for {identifier}")
        manifest.append({"participant": identifier, "feature_cache_sha256": sha256(path),
                         "source_md5": source_md5,
                         "n_scored": len(records[identifier]["y"]),
                         "class_counts": np.bincount(records[identifier]["y"], minlength=2).tolist()})
    return records, manifest


def score(y, prediction):
    result = {"macro_f1": float(f1_score(y, prediction, labels=[0, 1],
                                         average="macro", zero_division=0)),
              "accuracy": float(np.mean(y == prediction)),
              "support": np.bincount(y, minlength=2).tolist(),
              "confusion": confusion_matrix(y, prediction, labels=[0, 1]).tolist()}
    result["balanced_accuracy"] = (float(balanced_accuracy_score(y, prediction))
                                   if len(set(y)) == 2 else None)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path,
                        default=HERE / "output" / "mpddf_fixed_cap_v1" / "feature_cache")
    parser.add_argument("--output", type=Path,
                        default=HERE / "output" / "mpddf_fixed_cap_v1")
    args = parser.parse_args()
    records, manifest = load(args.cache)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "analysis_manifest.json").write_text(json.dumps({
        "protocol_sha256": sha256(HERE / "mpd_df_protocol.json"),
        "preparation_source_sha256": sha256(HERE / "prepare_mpddf_fixed_cap.py"),
        "evaluation_source_sha256": sha256(Path(__file__)),
        "numpy": np.__version__, "scipy": scipy.__version__,
        "sklearn": sklearn.__version__, "participant_manifest": manifest,
    }, indent=2), encoding="utf-8")
    folds = []
    rows = []
    for index, held_out in enumerate(EXPECTED_IDS, 1):
        training = [records[identifier] for identifier in EXPECTED_IDS if identifier != held_out]
        test = records[held_out]
        y_train = np.concatenate([item["y"] for item in training])
        majority = int(np.argmax(np.bincount(y_train, minlength=2)))
        predictions = {}
        with threadpool_limits(limits=1):
            for mode in ("four", "eight"):
                x_train = np.concatenate([item["x"][mode] for item in training])
                model = LogisticRegression(
                    C=0.3, class_weight="balanced", max_iter=400,
                    solver="lbfgs", random_state=0)
                model.fit(x_train, y_train)
                probabilities = model.predict_proba(test["x"][mode])[:, 1]
                predictions[mode] = (probabilities, (probabilities >= 0.5).astype(np.int8))
        fold = {"participant": held_out,
                "four": score(test["y"], predictions["four"][1]),
                "eight": score(test["y"], predictions["eight"][1]),
                "train_majority": score(test["y"], np.full(len(test["y"]), majority))}
        folds.append(fold)
        for j in range(len(test["y"])):
            rows.append((held_out, int(test["window_index"][j]),
                         int(test["window_start_seconds"][j]),
                         int(test["published_label"][j]), int(test["y"][j]),
                         float(predictions["four"][0][j]), int(predictions["four"][1][j]),
                         float(predictions["eight"][0][j]), int(predictions["eight"][1][j]),
                         majority))
        print(f"FOLD {index}/50 subject={held_out} n={len(test['y'])} "
              f"four_f1={fold['four']['macro_f1']:.3f} "
              f"eight_f1={fold['eight']['macro_f1']:.3f}", flush=True)
    predictions_path = args.output / "mpddf_loso_predictions.csv"
    with predictions_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(("participant", "window_index", "window_start_second_of_day",
                         "published_label", "binary_target", "four_probability",
                         "four_prediction", "eight_probability", "eight_prediction",
                         "training_majority_prediction"))
        writer.writerows(rows)
    array = np.asarray([[row[4], row[6], row[8], row[9]] for row in rows], dtype=np.int8)
    deltas = np.asarray([fold["eight"]["macro_f1"] - fold["four"]["macro_f1"]
                         for fold in folds])
    rng = np.random.default_rng(SEED)
    bootstrap = deltas[rng.integers(0, len(deltas), size=(10000, len(deltas)))].mean(axis=1)
    ci = np.quantile(bootstrap, (0.025, 0.975)).tolist()
    result = {
        "dataset": "MPD-DF", "target": "published 0 versus published 1-4",
        "folds": folds, "mean_participant_macro_f1": {
            name: float(np.mean([fold[name]["macro_f1"] for fold in folds]))
            for name in ("four", "eight", "train_majority")},
        "pooled": {name: score(array[:, 0], array[:, column])
                   for name, column in (("four", 1), ("eight", 2), ("train_majority", 3))},
        "paired_eight_minus_four_macro_f1": {
            "mean": float(deltas.mean()), "median": float(np.median(deltas)),
            "bootstrap_95_ci": ci, "bootstrap_seed": SEED,
            "positive_participants": int(np.sum(deltas > 0)),
            "negative_participants": int(np.sum(deltas < 0))},
        "deployment_rule_passed": bool(ci[0] > 0 and deltas.mean() >= 0.02),
        "predictions_sha256": sha256(predictions_path),
    }
    path = args.output / "results.json"
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({key: result[key] for key in (
        "mean_participant_macro_f1", "paired_eight_minus_four_macro_f1",
        "deployment_rule_passed")}, indent=2), flush=True)


if __name__ == "__main__":
    main()
