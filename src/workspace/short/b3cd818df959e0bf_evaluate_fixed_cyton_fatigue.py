"""Audit a four-channel SEED-VIG fallback for the fixed Cyton montage.

Only T7/T8/O1/O2 overlap the available 17-channel SEED-VIG cache and the
physical F3/F4/C3/C4/T7/T8/O1/O2 cap. This is exploratory; no channel names
are substituted and no board model is deployed by this script.
"""

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import scipy
import sklearn
from sklearn.metrics import mean_squared_error
from threadpoolctl import threadpool_limits


HERE = Path(__file__).resolve().parent
REFERENCE = Path(r"D:\ican\ican_fpga_project\software\pc_fatigue_reference")
sys.path.insert(0, str(REFERENCE))
from train_seedvig_8ch_calibrated_loso import (
    CALIBRATION_WINDOWS, MODEL_PARAMETERS, calibrate_recording, make_model,
    smooth_features,
)


CYTON_CHANNELS = ("F3", "F4", "C3", "C4", "T7", "T8", "O1", "O2")
OVERLAP = ("T7", "T8", "O1", "O2")
BENCHMARK = ("FT7", "FT8", "CP1", "CP2", "P1", "P2", "O1", "O2")


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def metrics(y, prediction):
    y = np.asarray(y, dtype=np.float64)
    p = np.clip(np.asarray(prediction, dtype=np.float64), 0, 1)
    covariance = float(np.mean((y - y.mean()) * (p - p.mean())))
    denominator = float(np.sqrt(y.var() * p.var()))
    ccc_denominator = float(y.var() + p.var() + (y.mean() - p.mean()) ** 2)
    return {
        "pcc": covariance / denominator if denominator > 0 else None,
        "ccc": 2 * covariance / ccc_denominator if ccc_denominator > 0 else None,
        "rmse": float(np.sqrt(mean_squared_error(y, p))),
    }


def load(cache_dir):
    paths = sorted(cache_dir.glob("*.npz"))
    if len(paths) < 2:
        raise ValueError("SEED-VIG cache is unavailable or incomplete")
    recordings = {}
    manifest = []
    for path in paths:
        with np.load(path, allow_pickle=False) as item:
            channel_names = tuple(str(value).upper() for value in item["channels"])
            if len(set(channel_names)) != len(channel_names):
                raise ValueError(f"duplicate channels in {path}")
            if not set(OVERLAP + BENCHMARK).issubset(channel_names):
                raise ValueError(f"required benchmark channels missing in {path}")
            source = np.asarray(item["features"], dtype=np.float64)
            y = np.asarray(item["perclos"], dtype=np.float64)
            if source.shape != (len(y), len(channel_names) * 5):
                raise ValueError(f"feature shape mismatch in {path}")
            features = {}
            for name, channels in (("overlap4", OVERLAP), ("benchmark8", BENCHMARK)):
                columns = [channel_names.index(ch) * 5 + band
                           for ch in channels for band in range(5)]
                calibrated, _, _ = calibrate_recording(source[:, columns])
                features[name] = smooth_features(calibrated[CALIBRATION_WINDOWS:])
            recordings[path.stem] = {
                "participant": path.stem.split("_", 1)[0],
                "target": y[CALIBRATION_WINDOWS:], "features": features,
            }
            manifest.append({"recording": path.stem, "sha256": sha256(path),
                             "windows": len(y), "channels": channel_names})
    return recordings, manifest


def evaluate(recordings, name, output_dir):
    subjects = sorted({item["participant"] for item in recordings.values()}, key=int)
    predictions = []
    folds = []
    with threadpool_limits(limits=1):
        for number, held_out in enumerate(subjects, 1):
            training = [item for item in recordings.values() if item["participant"] != held_out]
            testing = [(recording, item) for recording, item in recordings.items()
                       if item["participant"] == held_out]
            x_train = np.concatenate([item["features"][name] for item in training])
            y_train = np.concatenate([item["target"] for item in training])
            model = make_model().fit(x_train, y_train)
            constant = float(y_train.mean())
            targets, estimates, constants = [], [], []
            for recording, item in testing:
                actual = item["target"]
                predicted = np.clip(model.predict(item["features"][name]), 0, 1)
                targets.append(actual)
                estimates.append(predicted)
                constants.append(np.full(len(actual), constant))
                predictions.extend((held_out, recording, window + CALIBRATION_WINDOWS,
                                    float(y), float(p), constant)
                                   for window, (y, p) in enumerate(zip(actual, predicted)))
            score = metrics(np.concatenate(targets), np.concatenate(estimates))
            score["constant_mean"] = metrics(np.concatenate(targets), np.concatenate(constants))
            score["participant"] = held_out
            folds.append(score)
            print(f"{name} fold {number}/{len(subjects)} participant={held_out} "
                  f"pcc={score['pcc']:.3f} rmse={score['rmse']:.3f}", flush=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / f"predictions_{name}.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(("participant", "recording", "window", "perclos", "predicted", "train_mean"))
        writer.writerows(predictions)
    matrix = np.asarray([[row[3], row[4], row[5]] for row in predictions])
    pooled = metrics(matrix[:, 0], matrix[:, 1])
    baseline = metrics(matrix[:, 0], matrix[:, 2])
    mean_subject = {key: float(np.mean([fold[key] for fold in folds]))
                    for key in ("pcc", "ccc", "rmse")}
    return {"channels": OVERLAP if name == "overlap4" else BENCHMARK,
            "folds": folds, "pooled": pooled, "mean_subject": mean_subject,
            "constant_mean_pooled": baseline,
            "predictions_sha256": sha256(output_dir / f"predictions_{name}.csv")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=HERE / "cache_all17")
    parser.add_argument("--output", type=Path, default=HERE / "output" / "fixed_cyton_fatigue_v1")
    args = parser.parse_args()
    recordings, manifest = load(args.cache)
    args.output.mkdir(parents=True, exist_ok=True)
    protocol = {
        "hypothesis": "Four physically shared channels retain useful cross-subject PERCLOS information",
        "falsification": "Mean participant PCC is not positive or RMSE fails to improve over a train-mean constant",
        "status": "exploratory, not a Cyton accuracy claim",
        "target": "SEED-VIG PERCLOS regression",
        "physical_cyton_montage": CYTON_CHANNELS,
        "available_overlap": OVERLAP,
        "benchmark_channels": BENCHMARK,
        "calibration": "first 15 eight-second windows per recording, excluded from scoring",
        "split": "participant-grouped leave-one-subject-out; complete recordings stay within a fold",
        "model": "fixed HistGradientBoostingRegressor",
        "parameters": MODEL_PARAMETERS,
        "primary_metrics": ("mean_participant_pcc", "mean_participant_rmse", "mean_participant_ccc"),
        "source_sha256": sha256(Path(__file__)),
        "numpy": np.__version__, "scipy": scipy.__version__, "sklearn": sklearn.__version__,
        "cache_manifest": manifest,
    }
    (args.output / "protocol.json").write_text(json.dumps(protocol, indent=2), encoding="utf-8")
    results = {name: evaluate(recordings, name, args.output)
               for name in ("overlap4", "benchmark8")}
    (args.output / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps({key: value["mean_subject"] for key, value in results.items()}, indent=2))
    if results["overlap4"]["mean_subject"]["pcc"] <= 0:
        return
    x = np.concatenate([item["features"]["overlap4"] for item in recordings.values()])
    y = np.concatenate([item["target"] for item in recordings.values()])
    with threadpool_limits(limits=1):
        model = make_model().fit(x, y)
    joblib.dump(model, args.output / "overlap4_deployment_candidate.joblib")
    print("saved exploratory four-channel offline candidate", flush=True)


if __name__ == "__main__":
    main()
