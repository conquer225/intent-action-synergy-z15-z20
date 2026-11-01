#!/usr/bin/env python3
"""Evaluate whether frozen SQI-v3 gating improves downstream vigilance estimates."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np
from scipy.stats import pearsonr
from sklearn.metrics import mean_absolute_error, mean_squared_error

from evaluate_hgb_robustness import (
    CHANNELS,
    concordance_correlation,
    make_model,
    smooth_features,
)
from evaluate_quality_aware_hgb import gate_features
from evaluate_raw_sqi_v3_loso import (
    CALIBRATION_WINDOWS,
    RAW_CORRUPTION_KINDS,
    classifier_training_data,
    development_predictions,
    episode_spec,
    extract_recording,
    make_classifier,
    participant_id,
    tune_bad_probability_threshold,
)

from fatigue_reference import load_seedvig_subject
from validate_seedvig_loso import DEFAULT_DATASET_ROOT, discover_pairs


HERE = Path(__file__).resolve().parent
METHODS = (
    "clean_no_gate", "augmented_no_gate",
    "oracle_hard_gate", "v3_hard_gate",
    "oracle_soft_gate", "v3_soft_gate",
)
TRAIN_SEVERITIES = (0.25, 0.50, 0.75)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, default=DEFAULT_DATASET_ROOT)
    parser.add_argument("--output-dir", type=Path, default=HERE / "results" / "_smoke_sqi_v3_downstream")
    parser.add_argument("--max-participants", type=int, default=4)
    parser.add_argument("--test-severity", type=float, default=0.25)
    parser.add_argument("--experiment-seed", type=int, default=0)
    parser.add_argument("--kinds", nargs="+", default=list(RAW_CORRUPTION_KINDS), choices=RAW_CORRUPTION_KINDS)
    return parser.parse_args()


def de_from_quality_block(block) -> np.ndarray:
    return np.asarray(block.v2[:, :, :5], dtype=np.float64)


def episode_target(recording: dict, name: str, kind: str, severity: float, train: bool, seed: int) -> np.ndarray:
    spec, _ = episode_spec(
        name, kind, len(recording["all_target"]), severity=severity,
        train=train, experiment_seed=seed,
    )
    return recording["all_target"][spec.start_window:spec.start_window + spec.length_windows]


def episode_bounds(recording: dict, name: str, kind: str, severity: float, train: bool, seed: int) -> tuple[int, int]:
    spec, _ = episode_spec(
        name, kind, len(recording["all_target"]), severity=severity,
        train=train, experiment_seed=seed,
    )
    start = spec.start_window - CALIBRATION_WINDOWS
    return start, start + spec.length_windows


def continuous_metrics(reference: np.ndarray, prediction: np.ndarray) -> dict[str, float]:
    predicted = np.clip(np.asarray(prediction, dtype=np.float64), 0.0, 1.0)
    target = np.asarray(reference, dtype=np.float64)
    pcc = float("nan") if np.std(target) == 0.0 or np.std(predicted) == 0.0 else float(
        pearsonr(target, predicted).statistic
    )
    return {
        "pcc": pcc,
        "rmse": float(np.sqrt(mean_squared_error(target, predicted))),
        "mae": float(mean_absolute_error(target, predicted)),
        "ccc": concordance_correlation(target, predicted),
    }


def prepare_fatigue_training(recordings: dict[str, dict], names: list[str], kinds: list[str], seed: int):
    clean_standard_x = []
    clean_gate_x = []
    clean_y = []
    augmented_x = []
    augmented_y = []
    oracle_x = []
    oracle_y = []
    soft_oracle_x = []
    soft_oracle_y = []
    for name in names:
        recording = recordings[name]
        clean_de = de_from_quality_block(recording["clean"])
        clean_flat = clean_de.reshape(len(clean_de), -1)
        target = recording["all_target"][CALIBRATION_WINDOWS:]
        clean_standard_x.append(smooth_features(clean_flat))
        clean_gate_x.append(gate_features(clean_flat, np.ones(clean_de.shape[:2])))
        clean_y.append(target)
        for kind in kinds:
            for severity, block in zip(TRAIN_SEVERITIES, recording["episodes"]["train"][kind]):
                start, stop = episode_bounds(recording, name, kind, severity, True, seed)
                corrupted_de = clean_de.copy()
                corrupted_de[start:stop] = de_from_quality_block(block)
                full_mask = np.zeros(clean_de.shape[:2], dtype=bool)
                full_mask[start:stop] = block.mask
                affected = full_mask.any(axis=1)
                hard_quality = (~full_mask).astype(np.float64)
                soft_quality = np.ones(clean_de.shape[:2], dtype=np.float64)
                soft_quality[start:stop] = block.quality
                augmented_x.append(smooth_features(corrupted_de.reshape(len(corrupted_de), -1))[affected])
                augmented_y.append(target[affected])
                oracle_x.append(
                    gate_features(corrupted_de.reshape(len(corrupted_de), -1), hard_quality)[affected]
                )
                oracle_y.append(target[affected])
                soft_oracle_x.append(
                    gate_features(corrupted_de.reshape(len(corrupted_de), -1), soft_quality)[affected]
                )
                soft_oracle_y.append(target[affected])
    clean_standard = np.concatenate(clean_standard_x)
    clean_gate = np.concatenate(clean_gate_x)
    target = np.concatenate(clean_y)
    return {
        "clean_standard_x": clean_standard,
        "clean_gate_x": clean_gate,
        "clean_y": target,
        "augmented_x": np.concatenate((clean_standard, *augmented_x)),
        "augmented_y": np.concatenate((target, *augmented_y)),
        "oracle_x": np.concatenate((clean_gate, *oracle_x)),
        "oracle_y": np.concatenate((target, *oracle_y)),
        "soft_oracle_x": np.concatenate((clean_gate, *soft_oracle_x)),
        "soft_oracle_y": np.concatenate((target, *soft_oracle_y)),
    }


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    pairs = discover_pairs(args.dataset_root)
    participant_ids = sorted({participant_id(name) for name, _, _ in pairs}, key=int)
    selected_participants = participant_ids[:args.max_participants]
    selected_pairs = [item for item in pairs if participant_id(item[0]) in selected_participants]
    recordings = {}
    for index, (name, raw_path, label_path) in enumerate(selected_pairs, 1):
        print(f"[{index}/{len(selected_pairs)}] extracting {name}", flush=True)
        recording = extract_recording(
            name, raw_path, label_path, args.kinds, list(TRAIN_SEVERITIES),
            args.test_severity, args.experiment_seed,
        )
        recording["all_target"] = np.asarray(
            load_seedvig_subject(raw_path, label_path).perclos, dtype=np.float64
        )
        recordings[name] = recording

    rows = []
    for held_out in selected_participants:
        train_names = [name for name in recordings if recordings[name]["participant"] != held_out]
        test_names = [name for name in recordings if recordings[name]["participant"] == held_out]
        training_participants = sorted({recordings[name]["participant"] for name in train_names}, key=int)
        development_participant = training_participants[-1]
        fit_names = [name for name in train_names if recordings[name]["participant"] != development_participant]
        development_names = [name for name in train_names if recordings[name]["participant"] == development_participant]

        fit_x, fit_y = classifier_training_data(recordings, fit_names, args.kinds, args.experiment_seed)
        threshold_model = make_classifier(args.experiment_seed).fit(fit_x, fit_y)
        dev_target, dev_probability = development_predictions(
            threshold_model, recordings, development_names, args.kinds
        )
        quality_threshold = tune_bad_probability_threshold(dev_target, dev_probability)
        all_x, all_y = classifier_training_data(recordings, train_names, args.kinds, args.experiment_seed)
        quality_model = make_classifier(args.experiment_seed).fit(all_x, all_y)

        fatigue_training = prepare_fatigue_training(recordings, train_names, args.kinds, args.experiment_seed)
        clean_model = make_model().fit(fatigue_training["clean_standard_x"], fatigue_training["clean_y"])
        augmented_model = make_model().fit(fatigue_training["augmented_x"], fatigue_training["augmented_y"])
        gated_model = make_model().fit(fatigue_training["oracle_x"], fatigue_training["oracle_y"])
        soft_gated_model = make_model().fit(
            fatigue_training["soft_oracle_x"], fatigue_training["soft_oracle_y"]
        )

        clean_targets = []
        clean_predictions = {method: [] for method in METHODS}
        for name in test_names:
            recording = recordings[name]
            de = de_from_quality_block(recording["clean"])
            flat = de.reshape(len(de), -1)
            target = recording["all_target"][CALIBRATION_WINDOWS:]
            clean_targets.append(target)
            clean_predictions["clean_no_gate"].append(clean_model.predict(smooth_features(flat)))
            clean_predictions["augmented_no_gate"].append(augmented_model.predict(smooth_features(flat)))
            all_good = np.ones(de.shape[:2])
            clean_predictions["oracle_hard_gate"].append(gated_model.predict(gate_features(flat, all_good)))
            clean_predictions["v3_hard_gate"].append(gated_model.predict(gate_features(flat, all_good)))
            clean_predictions["oracle_soft_gate"].append(
                soft_gated_model.predict(gate_features(flat, all_good))
            )
            clean_predictions["v3_soft_gate"].append(
                soft_gated_model.predict(gate_features(flat, all_good))
            )
        clean_target = np.concatenate(clean_targets)
        for method in METHODS:
            rows.append({
                "participant": held_out, "method": method, "condition": "clean",
                "severity": "", "seed": args.experiment_seed,
                "episode_rmse": "", "episode_mae": "",
                **continuous_metrics(clean_target, np.concatenate(clean_predictions[method])),
            })

        for kind in args.kinds:
            targets = []
            predictions = {method: [] for method in METHODS}
            for name in test_names:
                recording = recordings[name]
                block = recording["episodes"]["test"][kind]
                clean_de = de_from_quality_block(recording["clean"])
                start, stop = episode_bounds(
                    recording, name, kind, args.test_severity, False, args.experiment_seed
                )
                corrupted_de = clean_de.copy()
                corrupted_de[start:stop] = de_from_quality_block(block)
                flat = corrupted_de.reshape(len(corrupted_de), -1)
                target = recording["all_target"][CALIBRATION_WINDOWS:]
                probability = quality_model.predict_proba(block.v3.reshape(-1, block.v3.shape[-1]))[:, 1]
                predicted_bad = probability.reshape(block.mask.shape) >= quality_threshold
                predicted_quality = np.ones(clean_de.shape[:2], dtype=np.float64)
                predicted_quality[start:stop] = (~predicted_bad).astype(np.float64)
                predicted_soft_quality = np.ones(clean_de.shape[:2], dtype=np.float64)
                predicted_soft_quality[start:stop] = 1.0 - probability.reshape(block.mask.shape)
                oracle_quality = np.ones(clean_de.shape[:2], dtype=np.float64)
                oracle_quality[start:stop] = (~block.mask).astype(np.float64)
                oracle_soft_quality = np.ones(clean_de.shape[:2], dtype=np.float64)
                oracle_soft_quality[start:stop] = block.quality
                targets.append(target)
                predictions["clean_no_gate"].append(clean_model.predict(smooth_features(flat)))
                predictions["augmented_no_gate"].append(augmented_model.predict(smooth_features(flat)))
                predictions["oracle_hard_gate"].append(
                    gated_model.predict(gate_features(flat, oracle_quality))
                )
                predictions["v3_hard_gate"].append(
                    gated_model.predict(gate_features(flat, predicted_quality))
                )
                predictions["oracle_soft_gate"].append(
                    soft_gated_model.predict(gate_features(flat, oracle_soft_quality))
                )
                predictions["v3_soft_gate"].append(
                    soft_gated_model.predict(gate_features(flat, predicted_soft_quality))
                )
            target = np.concatenate(targets)
            for method in METHODS:
                prediction = np.concatenate(predictions[method])
                episode_target_parts = []
                episode_prediction_parts = []
                offset = 0
                for name in test_names:
                    length = len(recordings[name]["all_target"]) - CALIBRATION_WINDOWS
                    start, stop = episode_bounds(
                        recordings[name], name, kind, args.test_severity, False,
                        args.experiment_seed,
                    )
                    episode_target_parts.append(target[offset + start:offset + stop])
                    episode_prediction_parts.append(prediction[offset + start:offset + stop])
                    offset += length
                event_target = np.concatenate(episode_target_parts)
                event_prediction = np.clip(np.concatenate(episode_prediction_parts), 0.0, 1.0)
                rows.append({
                    "participant": held_out, "method": method, "condition": kind,
                    "severity": args.test_severity, "seed": args.experiment_seed,
                    "episode_rmse": float(np.sqrt(mean_squared_error(event_target, event_prediction))),
                    "episode_mae": float(mean_absolute_error(event_target, event_prediction)),
                    **continuous_metrics(target, prediction),
                })
        print(f"fold={held_out} complete", flush=True)

    with (args.output_dir / "fold_metrics.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = {}
    for method in METHODS:
        summary[method] = {}
        for condition in ("clean", *args.kinds):
            selected = [row for row in rows if row["method"] == method and row["condition"] == condition]
            summary[method][condition] = {
                metric: float(np.nanmean([row[metric] for row in selected]))
                for metric in ("pcc", "rmse", "mae", "ccc", "episode_rmse", "episode_mae")
                if any(row[metric] != "" for row in selected)
            }
    payload = {
        "status": "smoke_test" if args.max_participants < 21 else "full_participant_run",
        "participants": selected_participants,
        "test_severity": args.test_severity,
        "experiment_seed": args.experiment_seed,
        "kinds": args.kinds,
        "methods": list(METHODS),
        "summary": summary,
    }
    (args.output_dir / "summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
