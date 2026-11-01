#!/usr/bin/env python3
"""Sweep 1-4 corrupted EEG channels under strict participant-grouped LOSO.

This is the preregistered dose-response follow-up to hgb_symmetric_v1.  It
reuses the exact clean model, calibration, preprocessing, and split logic but
evaluates nested channel subsets of size 1, 2, 3, and 4.  Channel swap is not
included because it is a distinct identity-error test requiring pairs.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import scipy
import sklearn
from scipy.stats import pearsonr, spearmanr
from sklearn.metrics import accuracy_score, f1_score, mean_absolute_error, mean_squared_error

from corruptions import CorruptionSpec, TRAINING_KINDS, apply_feature_corruption
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


CHANNEL_COUNTS = (1, 2, 3, 4)


@dataclass(frozen=True)
class SweepCondition:
    key: str
    kind: str | None
    severity: float | None
    channel_count: int
    seed: int | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=PROJECT_ROOT / "viformer_z15" / "cache_all17")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=HERE / "results" / "hgb_channel_count_sweep_v1",
    )
    parser.add_argument("--seeds", type=int, nargs="+", default=[20260920, 20260921, 20260922])
    parser.add_argument("--max-folds", type=int, default=None, help="Smoke test only.")
    return parser.parse_args()


def all_conditions(seeds: list[int]) -> list[SweepCondition]:
    conditions = [SweepCondition("clean", None, None, 0, None)]
    for kind in TRAINING_KINDS:
        for severity in SEVERITY_LEVELS:
            severity_label = f"{int(round(severity * 100)):03d}"
            for channel_count in CHANNEL_COUNTS:
                for seed in seeds:
                    key = f"{kind}_s{severity_label}_c{channel_count}_seed{seed}"
                    conditions.append(SweepCondition(key, kind, severity, channel_count, seed))
    return conditions


def corrupted_recording(values: np.ndarray, recording: str, condition: SweepCondition) -> np.ndarray:
    if condition.kind is None or condition.severity is None or condition.seed is None:
        return smooth_features(values)
    windows = len(values)
    # The permutation and episode start deliberately exclude corruption kind
    # and channel count.  Thus c1 is nested in c2/c3/c4, and corruption-family
    # comparisons use the same channels and temporal support.
    design_seed = stable_seed("count-sweep-design", recording, condition.severity, condition.seed)
    rng = np.random.default_rng(design_seed)
    channel_order = rng.permutation(len(CHANNELS))
    channels = tuple(sorted(int(value) for value in channel_order[: condition.channel_count]))
    fraction = EPISODE_FRACTIONS[condition.severity]
    length = max(1, min(windows, int(round(windows * fraction))))
    start = int(rng.integers(0, windows - length + 1))
    corruption_seed = stable_seed(
        "count-sweep-noise",
        recording,
        condition.kind,
        condition.severity,
        condition.channel_count,
        condition.seed,
    )
    shaped = values.reshape(windows, len(CHANNELS), BANDS_PER_CHANNEL)
    result = apply_feature_corruption(
        shaped,
        CorruptionSpec(condition.kind, condition.severity, channels, start, length),
        seed=corruption_seed,
    )
    return smooth_features(result.features.reshape(windows, -1))


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


def mean_std(values: list[float]) -> dict[str, float]:
    array = np.asarray(values, dtype=np.float64)
    return {
        "mean": float(array.mean()),
        "std": float(array.std(ddof=1)) if len(array) > 1 else 0.0,
    }


def normalized_auc(values: list[float]) -> float:
    return float(np.trapezoid(np.asarray(values, dtype=np.float64), x=np.asarray((0, 1, 2, 3, 4))) / 4.0)


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
                if condition.kind is None:
                    features = recordings[name]["clean"]
                else:
                    features = corrupted_recording(
                        recordings[name]["raw_post_calibration"], name, condition
                    )
                parts.append(np.clip(model.predict(features), 0.0, 1.0))
            prediction = np.concatenate(parts)
            predicted_class = ratio_to_class(prediction, thresholds)
            fold_predictions[:, condition_index] = prediction.astype(np.float32)
            fold_rows.append(
                {
                    "participant": held_out,
                    "condition": condition.key,
                    "kind": condition.kind or "clean",
                    "severity": "" if condition.severity is None else condition.severity,
                    "channel_count": condition.channel_count,
                    "seed": "" if condition.seed is None else condition.seed,
                    "windows": len(test_y),
                    **calculate_metrics(test_y, prediction, predicted_class),
                }
            )

        for name in test_names:
            count = len(recordings[name]["target"])
            sample_participant.extend([held_out] * count)
            sample_recording.extend([name] * count)
            sample_window.extend(range(CALIBRATION_WINDOWS, CALIBRATION_WINDOWS + count))
        reference_blocks.append(test_y)
        prediction_blocks.append(fold_predictions)
        threshold_blocks.append(np.tile(np.asarray(thresholds, dtype=np.float64), (len(test_y), 1)))
        fold_manifest.append(
            {
                "participant": held_out,
                "train_recordings": train_names,
                "test_recordings": test_names,
                "thresholds": [float(value) for value in thresholds],
            }
        )
        clean_row = fold_rows[-len(conditions)]
        print(
            f"fold {fold_index:02d}/{len(participant_ids):02d} participant={held_out} "
            f"clean PCC={clean_row['pcc']:.4f} RMSE={clean_row['rmse']:.4f} CCC={clean_row['ccc']:.4f}",
            flush=True,
        )

    reference = np.concatenate(reference_blocks)
    predictions = np.concatenate(prediction_blocks, axis=0)
    sample_thresholds = np.concatenate(threshold_blocks, axis=0)
    true_class = perclos_to_class(reference)

    aggregate_rows: list[dict] = []
    for condition_index, condition in enumerate(conditions):
        prediction = predictions[:, condition_index].astype(np.float64)
        predicted_class = np.empty_like(true_class)
        for sample_index, value in enumerate(prediction):
            predicted_class[sample_index] = ratio_to_class(
                np.asarray([value]), tuple(sample_thresholds[sample_index])
            )[0]
        aggregate_rows.append(
            {
                "condition": condition.key,
                "kind": condition.kind or "clean",
                "severity": "" if condition.severity is None else condition.severity,
                "channel_count": condition.channel_count,
                "seed": "" if condition.seed is None else condition.seed,
                "windows": len(reference),
                **calculate_metrics(reference, prediction, predicted_class),
            }
        )

    clean = aggregate_rows[0]
    scenario_summary: list[dict] = []
    for kind in TRAINING_KINDS:
        for severity in SEVERITY_LEVELS:
            for channel_count in CHANNEL_COUNTS:
                rows = [
                    row
                    for row in aggregate_rows
                    if row["kind"] == kind
                    and row["severity"] == severity
                    and row["channel_count"] == channel_count
                ]
                scenario_summary.append(
                    {
                        "kind": kind,
                        "severity": severity,
                        "channel_count": channel_count,
                        "episode_fraction": EPISODE_FRACTIONS[severity],
                        "replicates": len(rows),
                        "pcc": mean_std([float(row["pcc"]) for row in rows]),
                        "rmse": mean_std([float(row["rmse"]) for row in rows]),
                        "ccc": mean_std([float(row["ccc"]) for row in rows]),
                        "macro_f1": mean_std([float(row["macro_f1"]) for row in rows]),
                        "delta_pcc": mean_std([float(row["pcc"]) - float(clean["pcc"]) for row in rows]),
                        "delta_rmse": mean_std([float(row["rmse"]) - float(clean["rmse"]) for row in rows]),
                        "delta_ccc": mean_std([float(row["ccc"]) - float(clean["ccc"]) for row in rows]),
                    }
                )

    dose_summary: list[dict] = []
    for kind in TRAINING_KINDS:
        for severity in SEVERITY_LEVELS:
            seed_rows = []
            for seed in args.seeds:
                rows = sorted(
                    [
                        row
                        for row in aggregate_rows
                        if row["kind"] == kind and row["severity"] == severity and row["seed"] == seed
                    ],
                    key=lambda row: int(row["channel_count"]),
                )
                ccc_values = [float(clean["ccc"])] + [float(row["ccc"]) for row in rows]
                pcc_values = [float(clean["pcc"])] + [float(row["pcc"]) for row in rows]
                rmse_values = [float(clean["rmse"])] + [float(row["rmse"]) for row in rows]
                seed_rows.append(
                    {
                        "ccc_auc": normalized_auc(ccc_values),
                        "pcc_auc": normalized_auc(pcc_values),
                        "rmse_auc": normalized_auc(rmse_values),
                        "ccc_monotonic_steps": int(sum(b <= a for a, b in zip(ccc_values, ccc_values[1:]))),
                        "rmse_monotonic_steps": int(sum(b >= a for a, b in zip(rmse_values, rmse_values[1:]))),
                    }
                )
            dose_summary.append(
                {
                    "kind": kind,
                    "severity": severity,
                    "ccc_auc": mean_std([row["ccc_auc"] for row in seed_rows]),
                    "pcc_auc": mean_std([row["pcc_auc"] for row in seed_rows]),
                    "rmse_auc": mean_std([row["rmse_auc"] for row in seed_rows]),
                    "ccc_monotonic_steps_mean_of_4": float(np.mean([row["ccc_monotonic_steps"] for row in seed_rows])),
                    "rmse_monotonic_steps_mean_of_4": float(np.mean([row["rmse_monotonic_steps"] for row in seed_rows])),
                }
            )

    source_files = [
        Path(__file__).resolve(),
        HERE / "evaluate_hgb_robustness.py",
        HERE / "corruptions.py",
        REFERENCE_DIR / "train_seedvig_8ch_calibrated_loso.py",
    ]
    config = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "smoke_test" if args.max_folds is not None else "full",
        "hypothesis": "PCC and CCC decrease and RMSE increases as affected channels rise from one to four, especially for broadband noise, dropout, and flatline.",
        "falsification": "Most corruption families lack a consistent dose trend or participant-level effect directions are highly unstable.",
        "channels": list(CHANNELS),
        "bands_per_channel": BANDS_PER_CHANNEL,
        "calibration_windows": CALIBRATION_WINDOWS,
        "calibration_seconds": CALIBRATION_WINDOWS * 8,
        "feature_ema_alpha": FEATURE_EMA_ALPHA,
        "model": "sklearn HistGradientBoostingRegressor",
        "model_parameters": MODEL_PARAMETERS,
        "corruption_stage": "held-out post-calibration DE, before causal EMA",
        "corruption_kinds": list(TRAINING_KINDS),
        "channel_counts": list(CHANNEL_COUNTS),
        "nested_channel_subsets": True,
        "severity_levels": list(SEVERITY_LEVELS),
        "episode_fractions": {str(key): value for key, value in EPISODE_FRACTIONS.items()},
        "seeds": args.seeds,
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
        "protocol": "participant-grouped LOSO; clean training only; nested 1/2/3/4-channel held-out corruption; fixed fold model and thresholds",
        "clean": {key: clean[key] for key in ("pcc", "rmse", "ccc", "macro_f1")},
        "scenarios": scenario_summary,
        "dose_response": dose_summary,
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
    print(f"clean metrics: {summary['clean']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
