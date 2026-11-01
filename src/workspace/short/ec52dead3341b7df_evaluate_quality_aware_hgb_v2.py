#!/usr/bin/env python3
"""Clean-aware, training-calibrated SQI ablation for quality-gated HGB.

This follow-up freezes the v1 fatigue-gating architecture and changes only the
quality estimator.  Two SQI feature sets are compared: DE bands alone and DE
bands plus temporal/spatial diagnostics.  Explicit clean examples are added,
weak mains-like perturbations are treated as non-actionable, and a conservative
scale calibration is fitted using clean training participants only.
"""

from __future__ import annotations

import argparse
import json
import platform
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import scipy
import sklearn
from sklearn.ensemble import HistGradientBoostingRegressor

from corruptions import TRAINING_KINDS
from evaluate_hgb_channel_count_sweep import CHANNEL_COUNTS, all_conditions
from evaluate_hgb_robustness import (
    BANDS_PER_CHANNEL,
    CALIBRATION_WINDOWS,
    CHANNELS,
    HERE,
    PROJECT_ROOT,
    REFERENCE_DIR,
    SEVERITY_LEVELS,
    load_recordings,
    participant_id,
    perclos_to_class,
    ratio_to_class,
    sha256_file,
    stable_seed,
    tune_ratio_thresholds,
    write_csv,
)
from evaluate_quality_aware_hgb import (
    QUALITY_MODEL_PARAMETERS,
    QUALITY_THRESHOLD,
    TRAIN_AUGMENTATION_SEEDS,
    calculate_metrics,
    gate_features,
    prepare_fold_training,
    quality_features,
    quality_metrics,
    test_corruption,
    training_corruption,
)


METHODS = ("predicted_gate_bands_v2", "predicted_gate_full_v2")
CLEAN_CALIBRATION_QUANTILE = 0.10
SUCCESS_FALSE_BAD_RATE = 0.15


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=PROJECT_ROOT / "viformer_z15" / "cache_all17")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=HERE / "results" / "quality_aware_hgb_v2",
    )
    parser.add_argument("--seeds", type=int, nargs="+", default=[20260920, 20260921, 20260922])
    parser.add_argument("--max-folds", type=int, default=None, help="Smoke test only.")
    return parser.parse_args()


def sqi_features(values: np.ndarray, feature_set: str) -> np.ndarray:
    if feature_set == "bands":
        return np.asarray(values, dtype=np.float64).reshape(-1, BANDS_PER_CHANNEL)
    if feature_set == "full":
        return quality_features(values)
    raise ValueError(feature_set)


def actionable_quality(kind: str, quality: np.ndarray) -> np.ndarray:
    # v1 showed no RMSE cost from the weak DE-domain mains approximation and
    # Oracle channel removal made CCC worse.  Its training target is therefore
    # "do not gate" rather than "electrically pristine".
    if kind == "mains_noise":
        return np.ones_like(quality, dtype=np.float64)
    return np.asarray(quality, dtype=np.float64)


def prepare_quality_training(
    recordings: dict[str, dict],
    train_names: list[str],
    feature_set: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    feature_parts: list[np.ndarray] = []
    target_parts: list[np.ndarray] = []
    clean_feature_parts: list[np.ndarray] = []
    for name in train_names:
        values = recordings[name]["raw_post_calibration"]
        clean_features = sqi_features(values, feature_set)
        clean_feature_parts.append(clean_features)
        feature_parts.append(clean_features)
        target_parts.append(np.ones(len(clean_features), dtype=np.float64))

        for kind_index, kind in enumerate(TRAINING_KINDS):
            seed = TRAIN_AUGMENTATION_SEEDS[kind_index % len(TRAIN_AUGMENTATION_SEEDS)]
            result = training_corruption(values, name, kind, seed)
            features = sqi_features(result.features.reshape(len(values), -1), feature_set)
            target = actionable_quality(kind, result.quality).reshape(-1)
            actionable_bad = target < 0.999
            bad_indices = np.flatnonzero(actionable_bad)
            if len(bad_indices):
                # Retain all actionable failures.  Clean examples are supplied
                # separately, so unaffected samples from a corrupted stream are
                # not duplicated as pseudo-clean observations.
                feature_parts.append(features[bad_indices])
                target_parts.append(target[bad_indices])
    return (
        np.concatenate(feature_parts),
        np.concatenate(target_parts),
        np.concatenate(clean_feature_parts),
    )


def calibrate_quality(raw: np.ndarray, clean_scale: float) -> np.ndarray:
    return np.clip(np.asarray(raw, dtype=np.float64) / clean_scale, 0.0, 1.0)


def v2_quality_metrics(
    target: np.ndarray,
    prediction: np.ndarray,
    actionable_mask: np.ndarray,
) -> dict:
    return quality_metrics(target, prediction, actionable_mask)


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
        # Rebuild the same oracle-gated fatigue model as v1.  Only the SQI
        # estimator differs in this experiment.
        fatigue_training = prepare_fold_training(recordings, train_names)
        fatigue_model = HistGradientBoostingRegressor(**{
            "learning_rate": 0.05,
            "max_iter": 120,
            "max_leaf_nodes": 15,
            "l2_regularization": 1.0,
            "random_state": 0,
        }).fit(fatigue_training["gated_x"], fatigue_training["gated_y"])

        quality_models: dict[str, HistGradientBoostingRegressor] = {}
        quality_scales: dict[str, float] = {}
        for feature_set in ("bands", "full"):
            quality_x, quality_y, clean_quality_x = prepare_quality_training(
                recordings, train_names, feature_set
            )
            model = HistGradientBoostingRegressor(**QUALITY_MODEL_PARAMETERS).fit(quality_x, quality_y)
            clean_prediction = np.clip(model.predict(clean_quality_x), 0.0, 1.0)
            scale = float(np.quantile(clean_prediction, CLEAN_CALIBRATION_QUANTILE))
            quality_models[feature_set] = model
            quality_scales[feature_set] = max(scale, 1.0e-3)

        thresholds: dict[str, tuple[float, float]] = {}
        for method in METHODS:
            development = np.clip(fatigue_model.predict(fatigue_training["clean_gate"]), 0.0, 1.0)
            thresholds[method] = tune_ratio_thresholds(
                development, perclos_to_class(fatigue_training["clean_y"])
            )

        test_y = np.concatenate([recordings[name]["target"] for name in test_names])
        fold_predictions = np.empty((len(test_y), len(METHODS), len(conditions)), dtype=np.float32)
        for condition_index, condition in enumerate(conditions):
            method_parts = {method: [] for method in METHODS}
            diagnostics = {
                method: {"target": [], "prediction": [], "mask": []} for method in METHODS
            }
            for name in test_names:
                values = recordings[name]["raw_post_calibration"]
                result = test_corruption(values, name, condition)
                if result is None:
                    corrupted = values
                    electrical_quality = np.ones((len(values), len(CHANNELS)), dtype=np.float64)
                    corruption_mask = np.zeros_like(electrical_quality, dtype=bool)
                else:
                    corrupted = result.features.reshape(len(values), -1)
                    electrical_quality = result.quality.astype(np.float64)
                    corruption_mask = result.corruption_mask
                kind = condition.kind or "clean"
                target_quality = actionable_quality(kind, electrical_quality)
                actionable_mask = corruption_mask if kind != "mains_noise" else np.zeros_like(corruption_mask)
                for method_index, method in enumerate(METHODS):
                    feature_set = "bands" if "bands" in method else "full"
                    raw_quality = quality_models[feature_set].predict(
                        sqi_features(corrupted, feature_set)
                    ).reshape(len(values), len(CHANNELS))
                    predicted_quality = calibrate_quality(raw_quality, quality_scales[feature_set])
                    gated_input = gate_features(corrupted, predicted_quality)
                    method_parts[method].append(
                        np.clip(fatigue_model.predict(gated_input), 0.0, 1.0)
                    )
                    diagnostics[method]["target"].append(target_quality)
                    diagnostics[method]["prediction"].append(predicted_quality)
                    diagnostics[method]["mask"].append(actionable_mask)

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
                        "method": method,
                        "condition": condition.key,
                        "kind": condition.kind or "clean",
                        "severity": "" if condition.severity is None else condition.severity,
                        "channel_count": condition.channel_count,
                        "seed": "" if condition.seed is None else condition.seed,
                        **v2_quality_metrics(
                            np.concatenate(diagnostics[method]["target"]),
                            np.concatenate(diagnostics[method]["prediction"]),
                            np.concatenate(diagnostics[method]["mask"]),
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
                "quality_clean_scales": quality_scales,
                "thresholds": {method: list(thresholds[method]) for method in METHODS},
            }
        )
        print(f"fold {fold_index:02d}/{len(participant_ids):02d} participant={held_out} complete", flush=True)

    reference = np.concatenate(reference_blocks)
    predictions = np.concatenate(prediction_blocks, axis=0)
    sample_thresholds = np.concatenate(threshold_blocks, axis=0)
    aggregate_rows: list[dict] = []
    true_class = perclos_to_class(reference)
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

    clean = {
        method: next(row for row in aggregate_rows if row["method"] == method and row["condition"] == "clean")
        for method in METHODS
    }
    config = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "smoke_test" if args.max_folds is not None else "full",
        "hypothesis": "Clean-aware training and training-only SQI calibration reduce clean false-bad rate below 15% while preserving or improving corruption robustness.",
        "falsification": "Clean false-bad rate remains at least 15%, or no predicted-gating variant gives participant-stable robustness benefit without more than 0.01 clean CCC loss.",
        "methods": list(METHODS),
        "channels": list(CHANNELS),
        "quality_feature_sets": {
            "bands": ["five_de_bands"],
            "full": ["five_de_bands", "absolute_first_difference", "causal_5_window_std", "absolute_spatial_median_residual"],
        },
        "clean_calibration_quantile": CLEAN_CALIBRATION_QUANTILE,
        "diagnostic_quality_threshold": QUALITY_THRESHOLD,
        "mains_policy": "non-actionable quality target=1 because v1 Oracle gating harmed the weak DE-domain approximation",
        "training_augmentation_seeds": list(TRAIN_AUGMENTATION_SEEDS),
        "test_seeds": args.seeds,
        "severity_levels": list(SEVERITY_LEVELS),
        "channel_counts": list(CHANNEL_COUNTS),
        "participants": participant_ids,
        "source_hashes_sha256": {
            path.name: sha256_file(path)
            for path in (
                Path(__file__).resolve(),
                HERE / "evaluate_quality_aware_hgb.py",
                HERE / "evaluate_hgb_channel_count_sweep.py",
                HERE / "corruptions.py",
                REFERENCE_DIR / "train_seedvig_8ch_calibrated_loso.py",
            )
        },
        "cache_hashes_sha256": {path.name: sha256_file(path) for path in cache_paths},
        "software": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "sklearn": sklearn.__version__,
        },
    }
    summary = {
        "protocol": "strict participant-grouped LOSO; clean-aware SQI fitting and calibration inside fold; identical v1 test manifest",
        "clean": {
            method: {key: clean[method][key] for key in ("pcc", "rmse", "ccc", "macro_f1")}
            for method in METHODS
        },
    }
    write_csv(args.output_dir / "fold_metrics.csv", fold_rows)
    write_csv(args.output_dir / "condition_metrics.csv", aggregate_rows)
    write_csv(args.output_dir / "quality_metrics.csv", quality_rows)
    (args.output_dir / "config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.output_dir / "split_manifest.json").write_text(json.dumps({"folds": fold_manifest}, ensure_ascii=False, indent=2), encoding="utf-8")
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
