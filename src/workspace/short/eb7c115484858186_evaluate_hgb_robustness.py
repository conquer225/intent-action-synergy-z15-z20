#!/usr/bin/env python3
"""Strict participant-grouped HGB robustness evaluation on cached SEED-VIG DE.

The experiment keeps the clean HGB training protocol unchanged and corrupts
only held-out, post-calibration feature sequences.  Corruption is applied
before the deployment-compatible causal EMA.  This models a contact/noise
episode that starts after the two-minute personal calibration period.

Primary outputs are PCC, RMSE, and CCC.  Classification metrics are retained
as secondary deployment-facing outcomes.  Every prediction is stored in a
compressed matrix so that statistical tests and paper figures can be rebuilt
without rerunning the models.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import scipy
import sklearn
from scipy.stats import pearsonr, spearmanr
from sklearn.metrics import accuracy_score, f1_score, mean_absolute_error, mean_squared_error


HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent.parent
REFERENCE_DIR = Path(r"D:\ican\ican_fpga_project\software\pc_fatigue_reference")
if str(REFERENCE_DIR) not in sys.path:
    sys.path.insert(0, str(REFERENCE_DIR))

from fatigue_reference import perclos_to_class, ratio_to_class, tune_ratio_thresholds
from train_seedvig_8ch_calibrated_loso import (
    CALIBRATION_WINDOWS,
    FEATURE_EMA_ALPHA,
    MODEL_PARAMETERS,
    calibrate_recording,
    make_model,
    smooth_features,
)

from corruptions import CorruptionSpec, apply_feature_corruption


CHANNELS = ("FT7", "FT8", "CP1", "CP2", "P1", "P2", "O1", "O2")
BANDS_PER_CHANNEL = 5
CORRUPTION_KINDS = (
    "dropout",
    "flatline",
    "broadband_noise",
    "mains_noise",
    "drift",
    "burst",
    "channel_swap",
)
SEVERITY_LEVELS = (0.33, 0.66, 1.0)
EPISODE_FRACTIONS = {0.33: 0.10, 0.66: 0.25, 1.0: 0.40}


@dataclass(frozen=True)
class Condition:
    key: str
    kind: str | None
    severity: float | None
    seed: int | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache",
        type=Path,
        default=PROJECT_ROOT / "viformer_z15" / "cache_all17",
        help="Directory containing all-channel cached .npz recordings.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=HERE / "results" / "hgb_symmetric_v1",
    )
    parser.add_argument("--seeds", type=int, nargs="+", default=[20260920, 20260921, 20260922])
    parser.add_argument(
        "--max-folds",
        type=int,
        default=None,
        help="Development smoke test only; omit for the publishable full run.",
    )
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_seed(*parts: object) -> int:
    payload = "|".join(str(part) for part in parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:4], "little")


def participant_id(recording: str) -> str:
    prefix = recording.split("_", 1)[0]
    if not prefix.isdigit():
        raise ValueError(f"cannot infer participant id from recording: {recording}")
    return prefix


def concordance_correlation(reference: np.ndarray, predicted: np.ndarray) -> float:
    x = np.asarray(reference, dtype=np.float64)
    y = np.asarray(predicted, dtype=np.float64)
    covariance = float(np.mean((x - x.mean()) * (y - y.mean())))
    denominator = float(x.var() + y.var() + (x.mean() - y.mean()) ** 2)
    return float(2.0 * covariance / denominator) if denominator > 0.0 else float("nan")


def metrics(
    reference: np.ndarray,
    predicted: np.ndarray,
    thresholds: tuple[float, float],
) -> dict[str, float]:
    clipped = np.clip(np.asarray(predicted, dtype=np.float64), 0.0, 1.0)
    true_class = perclos_to_class(reference)
    predicted_class = ratio_to_class(clipped, thresholds)
    return {
        "pcc": float(pearsonr(reference, clipped).statistic),
        "spearman": float(spearmanr(reference, clipped).statistic),
        "rmse": float(np.sqrt(mean_squared_error(reference, clipped))),
        "mae": float(mean_absolute_error(reference, clipped)),
        "ccc": concordance_correlation(reference, clipped),
        "accuracy": float(accuracy_score(true_class, predicted_class)),
        "macro_f1": float(
            f1_score(true_class, predicted_class, labels=[0, 1, 2], average="macro", zero_division=0)
        ),
    }


def select_channel_columns(all_channels: list[str]) -> list[int]:
    normalized = [str(value).strip().upper() for value in all_channels]
    columns: list[int] = []
    for channel in CHANNELS:
        index = normalized.index(channel)
        columns.extend(range(index * BANDS_PER_CHANNEL, (index + 1) * BANDS_PER_CHANNEL))
    return columns


def load_recordings(cache: Path) -> tuple[dict[str, dict], dict[str, list[str]], list[Path]]:
    paths = sorted(cache.glob("*.npz"), key=lambda path: path.stem)
    if not paths:
        raise FileNotFoundError(f"no .npz recordings found in {cache}")
    recordings: dict[str, dict] = {}
    groups: dict[str, list[str]] = {}
    for path in paths:
        with np.load(path, allow_pickle=False) as item:
            columns = select_channel_columns(item["channels"].tolist())
            selected = np.asarray(item["features"], dtype=np.float64)[:, columns]
            calibrated, _, _ = calibrate_recording(selected)
            post_calibration = calibrated[CALIBRATION_WINDOWS:]
            target = np.asarray(item["perclos"], dtype=np.float64)[CALIBRATION_WINDOWS:]
        name = path.stem
        pid = participant_id(name)
        recordings[name] = {
            "raw_post_calibration": post_calibration,
            "clean": smooth_features(post_calibration),
            "target": target,
        }
        groups.setdefault(pid, []).append(name)
    return recordings, groups, paths


def all_conditions(seeds: list[int]) -> list[Condition]:
    conditions = [Condition("clean", None, None, None)]
    for kind in CORRUPTION_KINDS:
        for severity in SEVERITY_LEVELS:
            label = f"{int(round(severity * 100)):03d}"
            for seed in seeds:
                conditions.append(Condition(f"{kind}_s{label}_seed{seed}", kind, severity, seed))
    return conditions


def corrupted_recording(values: np.ndarray, recording: str, condition: Condition) -> np.ndarray:
    if condition.kind is None or condition.severity is None or condition.seed is None:
        return smooth_features(values)
    windows = len(values)
    design_seed = stable_seed("design", recording, condition.severity, condition.seed)
    rng = np.random.default_rng(design_seed)
    channels = tuple(sorted(int(value) for value in rng.choice(len(CHANNELS), 2, replace=False)))
    fraction = EPISODE_FRACTIONS[condition.severity]
    length = max(1, min(windows, int(round(windows * fraction))))
    start = int(rng.integers(0, windows - length + 1))
    corruption_seed = stable_seed("noise", recording, condition.kind, condition.severity, condition.seed)
    shaped = values.reshape(windows, len(CHANNELS), BANDS_PER_CHANNEL)
    result = apply_feature_corruption(
        shaped,
        CorruptionSpec(condition.kind, condition.severity, channels, start, length),
        seed=corruption_seed,
    )
    return smooth_features(result.features.reshape(windows, -1))


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def mean_std(values: list[float]) -> dict[str, float]:
    array = np.asarray(values, dtype=np.float64)
    return {"mean": float(array.mean()), "std": float(array.std(ddof=1)) if len(array) > 1 else 0.0}


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    recordings, groups, cache_paths = load_recordings(args.cache)
    participant_ids = sorted(groups, key=int)
    if args.max_folds is not None:
        participant_ids = participant_ids[: args.max_folds]
    conditions = all_conditions(args.seeds)

    sample_participant: list[str] = []
    sample_recording: list[str] = []
    sample_window: list[int] = []
    all_reference: list[np.ndarray] = []
    prediction_blocks: list[np.ndarray] = []
    fold_rows: list[dict] = []
    fold_manifest: list[dict] = []

    for fold_index, held_out in enumerate(participant_ids, 1):
        train_names = [name for name in recordings if participant_id(name) != held_out]
        test_names = groups[held_out]
        train_x = np.concatenate([recordings[name]["clean"] for name in train_names])
        train_y = np.concatenate([recordings[name]["target"] for name in train_names])
        test_y = np.concatenate([recordings[name]["target"] for name in test_names])

        model = make_model().fit(train_x, train_y)
        development_prediction = np.clip(model.predict(train_x), 0.0, 1.0)
        thresholds = tune_ratio_thresholds(development_prediction, perclos_to_class(train_y))
        fold_predictions = np.empty((len(test_y), len(conditions)), dtype=np.float32)

        for condition_index, condition in enumerate(conditions):
            parts = []
            for name in test_names:
                values = recordings[name]["raw_post_calibration"]
                features = recordings[name]["clean"] if condition.kind is None else corrupted_recording(values, name, condition)
                parts.append(np.clip(model.predict(features), 0.0, 1.0))
            prediction = np.concatenate(parts)
            fold_predictions[:, condition_index] = prediction.astype(np.float32)
            row = {
                "participant": held_out,
                "condition": condition.key,
                "kind": condition.kind or "clean",
                "severity": "" if condition.severity is None else condition.severity,
                "seed": "" if condition.seed is None else condition.seed,
                "windows": len(test_y),
                **metrics(test_y, prediction, thresholds),
            }
            fold_rows.append(row)

        offset = 0
        for name in test_names:
            count = len(recordings[name]["target"])
            sample_participant.extend([held_out] * count)
            sample_recording.extend([name] * count)
            sample_window.extend(range(CALIBRATION_WINDOWS, CALIBRATION_WINDOWS + count))
            offset += count
        all_reference.append(test_y)
        prediction_blocks.append(fold_predictions)
        fold_manifest.append(
            {
                "participant": held_out,
                "train_recordings": train_names,
                "test_recordings": test_names,
                "thresholds": [float(value) for value in thresholds],
            }
        )
        clean = fold_rows[-len(conditions)]
        print(
            f"fold {fold_index:02d}/{len(participant_ids):02d} participant={held_out} "
            f"clean PCC={clean['pcc']:.4f} RMSE={clean['rmse']:.4f} CCC={clean['ccc']:.4f}",
            flush=True,
        )

    reference = np.concatenate(all_reference)
    predictions = np.concatenate(prediction_blocks, axis=0)
    thresholds_by_sample = []
    for fold in fold_manifest:
        count = sum(len(recordings[name]["target"]) for name in fold["test_recordings"])
        thresholds_by_sample.extend([fold["thresholds"]] * count)
    thresholds_array = np.asarray(thresholds_by_sample, dtype=np.float64)

    aggregate_rows: list[dict] = []
    for index, condition in enumerate(conditions):
        prediction = predictions[:, index].astype(np.float64)
        true_class = perclos_to_class(reference)
        predicted_class = np.empty_like(true_class)
        for sample_index, value in enumerate(prediction):
            predicted_class[sample_index] = ratio_to_class(
                np.asarray([value]), tuple(thresholds_array[sample_index])
            )[0]
        aggregate_rows.append(
            {
                "condition": condition.key,
                "kind": condition.kind or "clean",
                "severity": "" if condition.severity is None else condition.severity,
                "seed": "" if condition.seed is None else condition.seed,
                "windows": len(reference),
                "pcc": float(pearsonr(reference, prediction).statistic),
                "spearman": float(spearmanr(reference, prediction).statistic),
                "rmse": float(np.sqrt(mean_squared_error(reference, prediction))),
                "mae": float(mean_absolute_error(reference, prediction)),
                "ccc": concordance_correlation(reference, prediction),
                "accuracy": float(accuracy_score(true_class, predicted_class)),
                "macro_f1": float(
                    f1_score(true_class, predicted_class, labels=[0, 1, 2], average="macro", zero_division=0)
                ),
            }
        )

    clean_metrics = {key: aggregate_rows[0][key] for key in ("pcc", "rmse", "ccc", "macro_f1")}
    summary_conditions: list[dict] = []
    for kind in CORRUPTION_KINDS:
        for severity in SEVERITY_LEVELS:
            rows = [row for row in aggregate_rows if row["kind"] == kind and row["severity"] == severity]
            summary_conditions.append(
                {
                    "kind": kind,
                    "severity": severity,
                    "episode_fraction": EPISODE_FRACTIONS[severity],
                    "replicates": len(rows),
                    "pcc": mean_std([float(row["pcc"]) for row in rows]),
                    "rmse": mean_std([float(row["rmse"]) for row in rows]),
                    "ccc": mean_std([float(row["ccc"]) for row in rows]),
                    "macro_f1": mean_std([float(row["macro_f1"]) for row in rows]),
                    "delta_pcc": mean_std([float(row["pcc"]) - clean_metrics["pcc"] for row in rows]),
                    "delta_rmse": mean_std([float(row["rmse"]) - clean_metrics["rmse"] for row in rows]),
                    "delta_ccc": mean_std([float(row["ccc"]) - clean_metrics["ccc"] for row in rows]),
                }
            )

    script_path = Path(__file__).resolve()
    source_files = [script_path, HERE / "corruptions.py", REFERENCE_DIR / "train_seedvig_8ch_calibrated_loso.py"]
    cache_hashes = {path.name: sha256_file(path) for path in cache_paths}
    config = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "smoke_test" if args.max_folds is not None else "full",
        "hypothesis": "Structured channel corruption degrades the clean HGB baseline and produces reproducible failure-mode rankings across held-out participants.",
        "falsification": "Little clean-to-corrupted degradation or no reproducible ordering across seeds and participants.",
        "channels": list(CHANNELS),
        "bands_per_channel": BANDS_PER_CHANNEL,
        "calibration_windows": CALIBRATION_WINDOWS,
        "calibration_seconds": CALIBRATION_WINDOWS * 8,
        "feature_ema_alpha": FEATURE_EMA_ALPHA,
        "model": "sklearn HistGradientBoostingRegressor",
        "model_parameters": MODEL_PARAMETERS,
        "corruption_stage": "held-out post-calibration DE, before causal EMA",
        "affected_channels_per_episode": 2,
        "severity_levels": list(SEVERITY_LEVELS),
        "episode_fractions": {str(key): value for key, value in EPISODE_FRACTIONS.items()},
        "seeds": args.seeds,
        "participants": participant_ids,
        "recordings": sorted(recordings),
        "source_hashes_sha256": {path.name: sha256_file(path) for path in source_files},
        "cache_hashes_sha256": cache_hashes,
        "software": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "sklearn": sklearn.__version__,
        },
    }
    summary = {
        "protocol": "participant-grouped LOSO; clean training only; 120 s calibration excluded; held-out corruption only; fixed fold model and thresholds",
        "clean": clean_metrics,
        "conditions": summary_conditions,
    }

    write_csv(args.output_dir / "fold_metrics.csv", fold_rows)
    write_csv(args.output_dir / "condition_metrics.csv", aggregate_rows)
    (args.output_dir / "config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.output_dir / "split_manifest.json").write_text(
        json.dumps({"folds": fold_manifest}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (args.output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    np.savez_compressed(
        args.output_dir / "predictions.npz",
        participant=np.asarray(sample_participant),
        recording=np.asarray(sample_recording),
        window=np.asarray(sample_window, dtype=np.int32),
        reference=reference.astype(np.float32),
        condition=np.asarray([condition.key for condition in conditions]),
        prediction=predictions,
    )
    print(f"saved full evidence bundle: {args.output_dir.resolve()}")
    print(f"clean metrics: {clean_metrics}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
