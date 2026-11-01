#!/usr/bin/env python3
"""Compare clean, augmented, oracle-gated, and predicted-quality HGB models.

All augmentation and quality-estimator fitting happens inside each LOSO fold.
The held-out participant is never used for preprocessing, augmentation fitting,
quality-model fitting, fatigue-model fitting, or threshold selection.
"""

from __future__ import annotations

import argparse
import csv
import json
import platform
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import scipy
import sklearn
from scipy.stats import pearsonr, spearmanr
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import accuracy_score, f1_score, mean_absolute_error, mean_squared_error

from corruptions import CorruptionSpec, TRAINING_KINDS, apply_feature_corruption
from evaluate_hgb_channel_count_sweep import CHANNEL_COUNTS, SweepCondition, all_conditions
from evaluate_hgb_robustness import (
    BANDS_PER_CHANNEL,
    CALIBRATION_WINDOWS,
    CHANNELS,
    EPISODE_FRACTIONS,
    FEATURE_EMA_ALPHA,
    HERE,
    MODEL_PARAMETERS,
    PROJECT_ROOT,
    REFERENCE_DIR,
    SEVERITY_LEVELS,
    concordance_correlation,
    load_recordings,
    make_model,
    participant_id,
    perclos_to_class,
    ratio_to_class,
    sha256_file,
    smooth_features,
    stable_seed,
    tune_ratio_thresholds,
    write_csv,
)


METHODS = (
    "clean_hgb",
    "random_mask_aug",
    "structured_aug",
    "oracle_gate",
    "predicted_gate",
)
TRAIN_AUGMENTATION_SEEDS = (31415, 27182, 16180)
QUALITY_THRESHOLD = 0.90
QUALITY_MODEL_PARAMETERS = {
    "learning_rate": 0.06,
    "max_iter": 80,
    "max_leaf_nodes": 15,
    "l2_regularization": 1.0,
    "random_state": 0,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=PROJECT_ROOT / "viformer_z15" / "cache_all17")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=HERE / "results" / "quality_aware_hgb_v1",
    )
    parser.add_argument("--seeds", type=int, nargs="+", default=[20260920, 20260921, 20260922])
    parser.add_argument("--max-folds", type=int, default=None, help="Smoke test only.")
    return parser.parse_args()


def rolling_std(values: np.ndarray, width: int = 5) -> np.ndarray:
    """Causal rolling standard deviation for (windows, channels, bands)."""
    result = np.empty_like(values, dtype=np.float64)
    for index in range(len(values)):
        start = max(0, index - width + 1)
        result[index] = values[start : index + 1].std(axis=0)
    return result


def quality_features(values: np.ndarray) -> np.ndarray:
    """Return per-window/per-channel SQI features without using fatigue labels."""
    shaped = np.asarray(values, dtype=np.float64).reshape(-1, len(CHANNELS), BANDS_PER_CHANNEL)
    difference = np.empty_like(shaped)
    difference[0] = 0.0
    difference[1:] = np.abs(np.diff(shaped, axis=0))
    local_std = rolling_std(shaped, width=5)
    spatial_residual = np.abs(shaped - np.median(shaped, axis=1, keepdims=True))
    combined = np.concatenate((shaped, difference, local_std, spatial_residual), axis=2)
    return combined.reshape(-1, combined.shape[2])


def gate_features(values: np.ndarray, quality: np.ndarray) -> np.ndarray:
    """Apply soft channel gating before EMA and append EMA-smoothed quality."""
    shaped = np.asarray(values, dtype=np.float64).reshape(-1, len(CHANNELS), BANDS_PER_CHANNEL)
    q = np.clip(np.asarray(quality, dtype=np.float64), 0.0, 1.0)
    if q.shape != shaped.shape[:2]:
        raise ValueError(f"quality shape {q.shape} does not match {shaped.shape[:2]}")
    gated = shaped * q[:, :, None]
    return np.concatenate(
        (smooth_features(gated.reshape(len(gated), -1)), smooth_features(q)),
        axis=1,
    )


def build_corruption(
    values: np.ndarray,
    *,
    kind: str,
    severity: float,
    channel_count: int,
    fraction: float,
    design_seed: int,
    noise_seed: int,
) -> object:
    windows = len(values)
    rng = np.random.default_rng(design_seed)
    channel_order = rng.permutation(len(CHANNELS))
    channels = tuple(sorted(int(value) for value in channel_order[:channel_count]))
    length = max(1, min(windows, int(round(windows * fraction))))
    start = int(rng.integers(0, windows - length + 1))
    shaped = values.reshape(windows, len(CHANNELS), BANDS_PER_CHANNEL)
    return apply_feature_corruption(
        shaped,
        CorruptionSpec(kind, severity, channels, start, length),
        seed=noise_seed,
    )


def test_corruption(values: np.ndarray, recording: str, condition: SweepCondition) -> object | None:
    if condition.kind is None or condition.severity is None or condition.seed is None:
        return None
    design_seed = stable_seed("count-sweep-design", recording, condition.severity, condition.seed)
    noise_seed = stable_seed(
        "count-sweep-noise",
        recording,
        condition.kind,
        condition.severity,
        condition.channel_count,
        condition.seed,
    )
    return build_corruption(
        values,
        kind=condition.kind,
        severity=condition.severity,
        channel_count=condition.channel_count,
        fraction=EPISODE_FRACTIONS[condition.severity],
        design_seed=design_seed,
        noise_seed=noise_seed,
    )


def training_corruption(values: np.ndarray, recording: str, kind: str, seed: int) -> object:
    design_seed = stable_seed("train-structured-design", recording, kind, seed)
    rng = np.random.default_rng(design_seed)
    severity = float(rng.uniform(0.20, 1.0))
    channel_count = int(rng.integers(1, 5))
    fraction = float(rng.uniform(0.10, 0.40))
    return build_corruption(
        values,
        kind=kind,
        severity=severity,
        channel_count=channel_count,
        fraction=fraction,
        design_seed=design_seed,
        noise_seed=stable_seed("train-structured-noise", recording, kind, seed),
    )


def random_mask_corruption(values: np.ndarray, recording: str, seed: int) -> object:
    design_seed = stable_seed("train-random-mask-design", recording, seed)
    rng = np.random.default_rng(design_seed)
    return build_corruption(
        values,
        kind="dropout",
        severity=1.0,
        channel_count=int(rng.integers(1, 5)),
        fraction=float(rng.uniform(0.10, 0.40)),
        design_seed=design_seed,
        noise_seed=stable_seed("train-random-mask-noise", recording, seed),
    )


def prepare_fold_training(recordings: dict[str, dict], train_names: list[str]) -> dict[str, np.ndarray]:
    clean_x = np.concatenate([recordings[name]["clean"] for name in train_names])
    clean_y = np.concatenate([recordings[name]["target"] for name in train_names])
    # Keep EMA state independent between recordings, matching deployment and
    # the clean 40-feature baseline.
    clean_gate = np.concatenate([
        gate_features(
            recordings[name]["raw_post_calibration"],
            np.ones((len(recordings[name]["target"]), len(CHANNELS))),
        )
        for name in train_names
    ])

    random_x_parts: list[np.ndarray] = []
    random_y_parts: list[np.ndarray] = []
    structured_x_parts: list[np.ndarray] = []
    structured_y_parts: list[np.ndarray] = []
    gated_x_parts: list[np.ndarray] = []
    gated_y_parts: list[np.ndarray] = []
    quality_x_parts: list[np.ndarray] = []
    quality_y_parts: list[np.ndarray] = []

    for name in train_names:
        values = recordings[name]["raw_post_calibration"]
        target = recordings[name]["target"]
        for seed in TRAIN_AUGMENTATION_SEEDS:
            result = random_mask_corruption(values, name, seed)
            affected = result.corruption_mask.any(axis=1)
            random_x_parts.append(smooth_features(result.features.reshape(len(values), -1))[affected])
            random_y_parts.append(target[affected])

        for kind_index, kind in enumerate(TRAINING_KINDS):
            seed = TRAIN_AUGMENTATION_SEEDS[kind_index % len(TRAIN_AUGMENTATION_SEEDS)]
            result = training_corruption(values, name, kind, seed)
            affected_windows = result.corruption_mask.any(axis=1)
            smoothed = smooth_features(result.features.reshape(len(values), -1))
            structured_x_parts.append(smoothed[affected_windows])
            structured_y_parts.append(target[affected_windows])
            gated = gate_features(result.features.reshape(len(values), -1), result.quality)
            gated_x_parts.append(gated[affected_windows])
            gated_y_parts.append(target[affected_windows])

            sqi = quality_features(result.features.reshape(len(values), -1))
            quality_target = result.quality.reshape(-1).astype(np.float64)
            bad_indices = np.flatnonzero(result.corruption_mask.reshape(-1))
            good_indices = np.flatnonzero(~result.corruption_mask.reshape(-1))
            rng = np.random.default_rng(stable_seed("quality-balance", name, kind, seed))
            good_count = min(len(good_indices), max(len(bad_indices), 1))
            selected_good = rng.choice(good_indices, size=good_count, replace=False)
            selected = np.concatenate((bad_indices, selected_good))
            quality_x_parts.append(sqi[selected])
            quality_y_parts.append(quality_target[selected])

    return {
        "clean_x": clean_x,
        "clean_y": clean_y,
        "clean_gate": clean_gate,
        "random_x": np.concatenate((clean_x, *random_x_parts)),
        "random_y": np.concatenate((clean_y, *random_y_parts)),
        "structured_x": np.concatenate((clean_x, *structured_x_parts)),
        "structured_y": np.concatenate((clean_y, *structured_y_parts)),
        "gated_x": np.concatenate((clean_gate, *gated_x_parts)),
        "gated_y": np.concatenate((clean_y, *gated_y_parts)),
        "quality_x": np.concatenate(quality_x_parts),
        "quality_y": np.concatenate(quality_y_parts),
    }


def calculate_metrics(reference: np.ndarray, prediction: np.ndarray, predicted_class: np.ndarray) -> dict:
    clipped = np.clip(prediction, 0.0, 1.0)
    true_class = perclos_to_class(reference)
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


def quality_metrics(target: np.ndarray, prediction: np.ndarray, mask: np.ndarray) -> dict:
    target_flat = np.asarray(target).reshape(-1)
    prediction_flat = np.clip(np.asarray(prediction).reshape(-1), 0.0, 1.0)
    mask_flat = np.asarray(mask, dtype=bool).reshape(-1)
    predicted_bad = prediction_flat < QUALITY_THRESHOLD
    if mask_flat.any():
        precision_denominator = int(predicted_bad.sum())
        true_positive = int(np.sum(predicted_bad & mask_flat))
        precision = true_positive / precision_denominator if precision_denominator else 0.0
        recall = true_positive / int(mask_flat.sum())
        f1 = 2.0 * precision * recall / (precision + recall) if precision + recall else 0.0
    else:
        precision = recall = f1 = float("nan")
    return {
        "quality_mae": float(np.mean(np.abs(target_flat - prediction_flat))),
        "bad_precision": precision,
        "bad_recall": recall,
        "bad_f1": f1,
        "false_bad_rate": float(np.mean(predicted_bad & ~mask_flat)),
    }


def mean_std(values: list[float]) -> dict[str, float]:
    array = np.asarray(values, dtype=np.float64)
    return {
        "mean": float(np.nanmean(array)),
        "std": float(np.nanstd(array, ddof=1)) if np.sum(np.isfinite(array)) > 1 else 0.0,
    }


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
    reference_blocks: list[np.ndarray] = []
    prediction_blocks: list[np.ndarray] = []
    threshold_blocks: list[np.ndarray] = []
    fold_rows: list[dict] = []
    quality_rows: list[dict] = []
    fold_manifest: list[dict] = []

    for fold_index, held_out in enumerate(participant_ids, 1):
        train_names = [name for name in recordings if participant_id(name) != held_out]
        test_names = groups[held_out]
        training = prepare_fold_training(recordings, train_names)

        models = {
            "clean_hgb": make_model().fit(training["clean_x"], training["clean_y"]),
            "random_mask_aug": make_model().fit(training["random_x"], training["random_y"]),
            "structured_aug": make_model().fit(training["structured_x"], training["structured_y"]),
            "oracle_gate": make_model().fit(training["gated_x"], training["gated_y"]),
        }
        quality_model = HistGradientBoostingRegressor(**QUALITY_MODEL_PARAMETERS).fit(
            training["quality_x"], training["quality_y"]
        )
        models["predicted_gate"] = models["oracle_gate"]

        thresholds: dict[str, tuple[float, float]] = {}
        for method in METHODS:
            clean_input = training["clean_gate"] if method.endswith("gate") else training["clean_x"]
            development = np.clip(models[method].predict(clean_input), 0.0, 1.0)
            thresholds[method] = tune_ratio_thresholds(development, perclos_to_class(training["clean_y"]))

        test_y = np.concatenate([recordings[name]["target"] for name in test_names])
        fold_predictions = np.empty((len(test_y), len(METHODS), len(conditions)), dtype=np.float32)

        for condition_index, condition in enumerate(conditions):
            method_parts = {method: [] for method in METHODS}
            q_target_parts: list[np.ndarray] = []
            q_prediction_parts: list[np.ndarray] = []
            q_mask_parts: list[np.ndarray] = []
            for name in test_names:
                values = recordings[name]["raw_post_calibration"]
                result = test_corruption(values, name, condition)
                if result is None:
                    corrupted = values
                    oracle_quality = np.ones((len(values), len(CHANNELS)), dtype=np.float64)
                    corruption_mask = np.zeros_like(oracle_quality, dtype=bool)
                else:
                    corrupted = result.features.reshape(len(values), -1)
                    oracle_quality = result.quality.astype(np.float64)
                    corruption_mask = result.corruption_mask
                standard_input = smooth_features(corrupted)
                predicted_quality = np.clip(
                    quality_model.predict(quality_features(corrupted)).reshape(len(values), len(CHANNELS)),
                    0.0,
                    1.0,
                )
                oracle_input = gate_features(corrupted, oracle_quality)
                predicted_input = gate_features(corrupted, predicted_quality)
                for method in ("clean_hgb", "random_mask_aug", "structured_aug"):
                    method_parts[method].append(np.clip(models[method].predict(standard_input), 0.0, 1.0))
                method_parts["oracle_gate"].append(np.clip(models["oracle_gate"].predict(oracle_input), 0.0, 1.0))
                method_parts["predicted_gate"].append(
                    np.clip(models["predicted_gate"].predict(predicted_input), 0.0, 1.0)
                )
                q_target_parts.append(oracle_quality)
                q_prediction_parts.append(predicted_quality)
                q_mask_parts.append(corruption_mask)

            for method_index, method in enumerate(METHODS):
                prediction = np.concatenate(method_parts[method])
                fold_predictions[:, method_index, condition_index] = prediction.astype(np.float32)
                predicted_class = ratio_to_class(prediction, thresholds[method])
                fold_rows.append(
                    {
                        "participant": held_out,
                        "method": method,
                        "condition": condition.key,
                        "kind": condition.kind or "clean",
                        "severity": "" if condition.severity is None else condition.severity,
                        "channel_count": condition.channel_count,
                        "seed": "" if condition.seed is None else condition.seed,
                        "windows": len(test_y),
                        **calculate_metrics(test_y, prediction, predicted_class),
                    }
                )
            quality_rows.append(
                {
                    "participant": held_out,
                    "condition": condition.key,
                    "kind": condition.kind or "clean",
                    "severity": "" if condition.severity is None else condition.severity,
                    "channel_count": condition.channel_count,
                    "seed": "" if condition.seed is None else condition.seed,
                    **quality_metrics(
                        np.concatenate(q_target_parts),
                        np.concatenate(q_prediction_parts),
                        np.concatenate(q_mask_parts),
                    ),
                }
            )

        for name in test_names:
            count = len(recordings[name]["target"])
            sample_participant.extend([held_out] * count)
            sample_recording.extend([name] * count)
            sample_window.extend(range(CALIBRATION_WINDOWS, CALIBRATION_WINDOWS + count))
        reference_blocks.append(test_y)
        prediction_blocks.append(fold_predictions)
        threshold_blocks.append(
            np.tile(
                np.asarray([thresholds[method] for method in METHODS], dtype=np.float64)[None, :, :],
                (len(test_y), 1, 1),
            )
        )
        fold_manifest.append(
            {
                "participant": held_out,
                "train_recordings": train_names,
                "test_recordings": test_names,
                "thresholds": {method: list(thresholds[method]) for method in METHODS},
                "training_rows": {
                    key: int(len(training[key]))
                    for key in ("clean_x", "random_x", "structured_x", "gated_x", "quality_x")
                },
            }
        )
        print(f"fold {fold_index:02d}/{len(participant_ids):02d} participant={held_out} complete", flush=True)

    reference = np.concatenate(reference_blocks)
    predictions = np.concatenate(prediction_blocks, axis=0)
    sample_thresholds = np.concatenate(threshold_blocks, axis=0)
    true_class = perclos_to_class(reference)
    aggregate_rows: list[dict] = []
    for method_index, method in enumerate(METHODS):
        for condition_index, condition in enumerate(conditions):
            prediction = predictions[:, method_index, condition_index].astype(np.float64)
            predicted_class = np.empty_like(true_class)
            for sample_index, value in enumerate(prediction):
                predicted_class[sample_index] = ratio_to_class(
                    np.asarray([value]), tuple(sample_thresholds[sample_index, method_index])
                )[0]
            aggregate_rows.append(
                {
                    "method": method,
                    "condition": condition.key,
                    "kind": condition.kind or "clean",
                    "severity": "" if condition.severity is None else condition.severity,
                    "channel_count": condition.channel_count,
                    "seed": "" if condition.seed is None else condition.seed,
                    "windows": len(reference),
                    **calculate_metrics(reference, prediction, predicted_class),
                }
            )

    clean_by_method = {
        row["method"]: row for row in aggregate_rows if row["condition"] == "clean"
    }
    scenario_summary: list[dict] = []
    for method in METHODS:
        for kind in TRAINING_KINDS:
            for severity in SEVERITY_LEVELS:
                for channel_count in CHANNEL_COUNTS:
                    rows = [
                        row
                        for row in aggregate_rows
                        if row["method"] == method
                        and row["kind"] == kind
                        and row["severity"] == severity
                        and row["channel_count"] == channel_count
                    ]
                    baseline = clean_by_method[method]
                    clean_hgb_rows = [
                        row
                        for row in aggregate_rows
                        if row["method"] == "clean_hgb"
                        and row["kind"] == kind
                        and row["severity"] == severity
                        and row["channel_count"] == channel_count
                    ]
                    scenario_summary.append(
                        {
                            "method": method,
                            "kind": kind,
                            "severity": severity,
                            "channel_count": channel_count,
                            "replicates": len(rows),
                            "pcc": mean_std([float(row["pcc"]) for row in rows]),
                            "rmse": mean_std([float(row["rmse"]) for row in rows]),
                            "ccc": mean_std([float(row["ccc"]) for row in rows]),
                            "macro_f1": mean_std([float(row["macro_f1"]) for row in rows]),
                            "delta_ccc_from_own_clean": mean_std(
                                [float(row["ccc"]) - float(baseline["ccc"]) for row in rows]
                            ),
                            "ccc_gain_vs_clean_hgb": mean_std(
                                [float(row["ccc"]) - float(other["ccc"]) for row, other in zip(rows, clean_hgb_rows)]
                            ),
                            "rmse_gain_vs_clean_hgb": mean_std(
                                [float(other["rmse"]) - float(row["rmse"]) for row, other in zip(rows, clean_hgb_rows)]
                            ),
                        }
                    )

    source_files = [
        Path(__file__).resolve(),
        HERE / "evaluate_hgb_channel_count_sweep.py",
        HERE / "evaluate_hgb_robustness.py",
        HERE / "corruptions.py",
        REFERENCE_DIR / "train_seedvig_8ch_calibrated_loso.py",
    ]
    config = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "smoke_test" if args.max_folds is not None else "full",
        "hypothesis": "Quality-aware gating reduces CCC loss under 3-4 channel corruption without materially reducing clean performance.",
        "falsification": "Oracle gating fails to improve robustness, or predicted gating loses the oracle benefit because SQI estimation is inadequate.",
        "methods": list(METHODS),
        "channels": list(CHANNELS),
        "bands_per_channel": BANDS_PER_CHANNEL,
        "calibration_windows": CALIBRATION_WINDOWS,
        "feature_ema_alpha": FEATURE_EMA_ALPHA,
        "fatigue_model_parameters": MODEL_PARAMETERS,
        "quality_model_parameters": QUALITY_MODEL_PARAMETERS,
        "quality_features": ["five_de_bands", "absolute_first_difference", "causal_5_window_std", "absolute_spatial_median_residual"],
        "quality_threshold": QUALITY_THRESHOLD,
        "training_augmentation_seeds": list(TRAIN_AUGMENTATION_SEEDS),
        "test_seeds": args.seeds,
        "corruption_kinds": list(TRAINING_KINDS),
        "severity_levels": list(SEVERITY_LEVELS),
        "channel_counts": list(CHANNEL_COUNTS),
        "participants": participant_ids,
        "recordings": sorted(recordings),
        "source_hashes_sha256": {path.name: sha256_file(path) for path in source_files},
        "cache_hashes_sha256": {path.name: sha256_file(path) for path in cache_paths},
        "software": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "sklearn": sklearn.__version__,
        },
    }
    summary = {
        "protocol": "strict participant-grouped LOSO; augmentation and SQI model inside fold; identical held-out corruption matrix",
        "clean": {
            method: {key: clean_by_method[method][key] for key in ("pcc", "rmse", "ccc", "macro_f1")}
            for method in METHODS
        },
        "scenarios": scenario_summary,
    }

    write_csv(args.output_dir / "fold_metrics.csv", fold_rows)
    write_csv(args.output_dir / "condition_metrics.csv", aggregate_rows)
    write_csv(args.output_dir / "quality_metrics.csv", quality_rows)
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
        method=np.asarray(METHODS),
        condition=np.asarray([condition.key for condition in conditions]),
        prediction=predictions,
    )
    print(f"saved full evidence bundle: {args.output_dir.resolve()}")
    print(json.dumps(summary["clean"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
