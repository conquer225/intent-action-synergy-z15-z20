#!/usr/bin/env python3
"""Evaluate the frozen SQI-v2 estimator on the Stage-A Cyton bench recordings.

The SQI model and its 0.90 decision threshold are learned only from the public
SEED-VIG cache and synthetic corruptions.  The real bench recordings are never
used for fitting or threshold selection.  B1-R supplies the deployment-style
120 s unlabeled DE calibration shared by all Stage-A conditions.
"""

from __future__ import annotations

import csv
import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import scipy
import sklearn
import joblib
from sklearn.ensemble import HistGradientBoostingRegressor


HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent.parent
REFERENCE_DIR = Path(r"D:\ican\ican_fpga_project\software\pc_fatigue_reference")
if str(REFERENCE_DIR) not in sys.path:
    sys.path.insert(0, str(REFERENCE_DIR))
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from fatigue_reference import DEPLOYMENT_DE_BANDS, extract_band_de_features
from train_seedvig_8ch_calibrated_loso import CALIBRATION_WINDOWS, calibrate_recording

from analyze_cyton_bench import read_complete_rows
from evaluate_hgb_robustness import CHANNELS, load_recordings
from evaluate_quality_aware_hgb import QUALITY_MODEL_PARAMETERS, QUALITY_THRESHOLD, quality_features
from evaluate_quality_aware_hgb_v2 import (
    CLEAN_CALIBRATION_QUANTILE,
    calibrate_quality,
    prepare_quality_training,
)


SAMPLE_RATE_HZ = 250
WINDOW_SECONDS = 8
WINDOW_SAMPLES = SAMPLE_RATE_HZ * WINDOW_SECONDS
CHANNEL_LABELS = tuple(f"CH{index}" for index in range(1, 9))

RAW_FILES = {
    "B1R": Path(r"C:\Users\lenovo\Documents\OpenBCI_GUI\Recordings\OpenBCISession_2026-09-20_17-19-47\OpenBCI-RAW-2026-09-20_17-30-25.txt"),
    "B2": Path(r"C:\Users\lenovo\Documents\OpenBCI_GUI\Recordings\OpenBCISession_2026-09-20_17-36-34\OpenBCI-RAW-2026-09-20_17-37-43.txt"),
    "B3": Path(r"C:\Users\lenovo\Documents\OpenBCI_GUI\Recordings\OpenBCISession_2026-09-20_17-44-18\OpenBCI-RAW-2026-09-20_17-45-37.txt"),
    "B4": Path(r"C:\Users\lenovo\Documents\OpenBCI_GUI\Recordings\OpenBCISession_2026-09-20_17-51-46\OpenBCI-RAW-2026-09-20_17-52-22.txt"),
    "B5": Path(r"C:\Users\lenovo\Documents\OpenBCI_GUI\Recordings\OpenBCISession_2026-09-20_17-55-35\OpenBCI-RAW-2026-09-20_17-57-05.txt"),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def select_samples(values: np.ndarray, skip_s: float, duration_s: float | None) -> np.ndarray:
    start = int(round(skip_s * SAMPLE_RATE_HZ))
    stop = len(values) if duration_s is None else start + int(round(duration_s * SAMPLE_RATE_HZ))
    selected = np.asarray(values[start:stop], dtype=np.float64)
    complete = (len(selected) // WINDOW_SAMPLES) * WINDOW_SAMPLES
    if complete < WINDOW_SAMPLES:
        raise ValueError(f"segment has fewer than {WINDOW_SECONDS} seconds")
    return selected[:complete]


def extract_de(values: np.ndarray) -> np.ndarray:
    return extract_band_de_features(
        values,
        channel_names=CHANNELS,
        sample_rate_hz=SAMPLE_RATE_HZ,
        window_samples=WINDOW_SAMPLES,
    ).values


def score_segment(
    stage: str,
    condition: str,
    values: np.ndarray,
    calibration_mean: np.ndarray,
    calibration_scale: np.ndarray,
    model: HistGradientBoostingRegressor,
    clean_scale: float,
    start_seconds: float,
) -> list[dict]:
    de = extract_de(values)
    calibrated = (de - calibration_mean) / calibration_scale
    raw_quality = model.predict(quality_features(calibrated)).reshape(len(calibrated), 8)
    quality = calibrate_quality(raw_quality, clean_scale)
    rows: list[dict] = []
    for window_index in range(len(quality)):
        window_start = start_seconds + window_index * WINDOW_SECONDS
        for channel_index, score in enumerate(quality[window_index]):
            rows.append(
                {
                    "stage": stage,
                    "condition": condition,
                    "window_index": window_index,
                    "window_start_s": window_start,
                    "window_end_s": window_start + WINDOW_SECONDS,
                    "channel": CHANNEL_LABELS[channel_index],
                    "sqi": float(score),
                    "bad": int(score < QUALITY_THRESHOLD),
                }
            )
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def grouped_summary(rows: list[dict], keys: tuple[str, ...]) -> list[dict]:
    groups: dict[tuple, list[float]] = {}
    for row in rows:
        key = tuple(row[name] for name in keys)
        groups.setdefault(key, []).append(float(row["sqi"]))
    result = []
    for key, scores in sorted(groups.items()):
        values = np.asarray(scores)
        result.append(
            {
                **dict(zip(keys, key)),
                "observations": len(values),
                "median_sqi": float(np.median(values)),
                "mean_sqi": float(values.mean()),
                "p10_sqi": float(np.quantile(values, 0.10)),
                "bad_fraction": float(np.mean(values < QUALITY_THRESHOLD)),
            }
        )
    return result


def median_for(rows: list[dict], condition: str, channels: set[str] | None = None) -> float:
    values = [
        float(row["sqi"])
        for row in rows
        if row["condition"] == condition and (channels is None or row["channel"] in channels)
    ]
    return float(np.median(values)) if values else float("nan")


def detection_metrics(rows: list[dict]) -> dict[str, float | int]:
    """Score only conditions with an unambiguous bench ground truth."""
    affected = {
        "stable_reference": set(),
        "single_open_CH1": {"CH1"},
        "multi_open_CH1_CH2_CH3": {"CH1", "CH2", "CH3"},
        "pre_static": set(),
        "CH4_motion": {"CH4"},
        "restored": set(),
    }
    tp = fp = tn = fn = 0
    for row in rows:
        condition = str(row["condition"])
        if condition not in affected:
            continue
        truth = str(row["channel"]) in affected[condition]
        predicted = bool(row["bad"])
        if truth and predicted:
            tp += 1
        elif truth:
            fn += 1
        elif predicted:
            fp += 1
        else:
            tn += 1
    return {
        "true_positive": tp,
        "false_negative": fn,
        "true_negative": tn,
        "false_positive": fp,
        "sensitivity": tp / (tp + fn) if tp + fn else float("nan"),
        "specificity": tn / (tn + fp) if tn + fp else float("nan"),
        "balanced_accuracy": 0.5 * (
            tp / (tp + fn) + tn / (tn + fp)
        ) if tp + fn and tn + fp else float("nan"),
    }


def main() -> int:
    output_dir = HERE / "results" / "real_cyton_sqi_v2_transfer"
    output_dir.mkdir(parents=True, exist_ok=True)
    for path in RAW_FILES.values():
        if not path.exists():
            raise FileNotFoundError(path)

    print("Loading public-data DE cache...", flush=True)
    recordings, _, cache_paths = load_recordings(PROJECT_ROOT / "viformer_z15" / "cache_all17")
    train_names = sorted(recordings)
    print("Building frozen SQI-v2 training matrix...", flush=True)
    quality_x, quality_y, clean_quality_x = prepare_quality_training(recordings, train_names, "full")
    print(f"Fitting final public-data SQI-v2 model on {len(quality_x):,} channel-windows...", flush=True)
    model = HistGradientBoostingRegressor(**QUALITY_MODEL_PARAMETERS).fit(quality_x, quality_y)
    clean_prediction = np.clip(model.predict(clean_quality_x), 0.0, 1.0)
    clean_scale = max(float(np.quantile(clean_prediction, CLEAN_CALIBRATION_QUANTILE)), 1.0e-3)

    raw_values: dict[str, np.ndarray] = {}
    malformed_rows: dict[str, int] = {}
    for stage, path in RAW_FILES.items():
        _, values, malformed = read_complete_rows(path)
        raw_values[stage] = values
        malformed_rows[stage] = malformed

    # B1-R is the fixed deployment-style calibration source.  It is not used
    # to fit the SQI model or threshold.
    b1r_de = extract_de(select_samples(raw_values["B1R"], 0.0, None))
    calibrated_b1r, calibration_mean, calibration_scale = calibrate_recording(b1r_de)
    calibration_scale = np.asarray(calibration_scale, dtype=np.float64)

    rows: list[dict] = []
    b1r_post = raw_values["B1R"][CALIBRATION_WINDOWS * WINDOW_SAMPLES :]
    b1r_post = b1r_post[: (len(b1r_post) // WINDOW_SAMPLES) * WINDOW_SAMPLES]
    rows += score_segment(
        "B1R", "stable_reference", b1r_post, calibration_mean, calibration_scale,
        model, clean_scale, CALIBRATION_WINDOWS * WINDOW_SECONDS,
    )
    rows += score_segment(
        "B2", "single_open_CH1", select_samples(raw_values["B2"], 10.0, 60.0),
        calibration_mean, calibration_scale, model, clean_scale, 10.0,
    )
    rows += score_segment(
        "B3", "multi_open_CH1_CH2_CH3", select_samples(raw_values["B3"], 10.0, 60.0),
        calibration_mean, calibration_scale, model, clean_scale, 10.0,
    )

    b4_rows = score_segment(
        "B4", "temporary", select_samples(raw_values["B4"], 0.0, 60.0),
        calibration_mean, calibration_scale, model, clean_scale, 0.0,
    )
    for row in b4_rows:
        center = (float(row["window_start_s"]) + float(row["window_end_s"])) / 2.0
        row["condition"] = "pre_static" if center < 10.0 else ("CH4_motion" if center < 50.0 else "recovery")
    rows += b4_rows
    rows += score_segment(
        "B5", "restored", select_samples(raw_values["B5"], 10.0, 120.0),
        calibration_mean, calibration_scale, model, clean_scale, 10.0,
    )

    channel_summary = grouped_summary(rows, ("stage", "condition", "channel"))
    condition_summary = grouped_summary(rows, ("stage", "condition"))
    write_csv(output_dir / "window_channel_scores.csv", rows)
    write_csv(output_dir / "channel_summary.csv", channel_summary)
    write_csv(output_dir / "condition_summary.csv", condition_summary)

    checks = {
        "B2_CH1_below_unaffected": median_for(rows, "single_open_CH1", {"CH1"})
        < median_for(rows, "single_open_CH1", set(CHANNEL_LABELS[1:])),
        "B3_open_channels_below_unaffected": median_for(
            rows, "multi_open_CH1_CH2_CH3", {"CH1", "CH2", "CH3"}
        ) < median_for(rows, "multi_open_CH1_CH2_CH3", set(CHANNEL_LABELS[3:])),
        "B4_CH4_motion_below_pre": median_for(rows, "CH4_motion", {"CH4"})
        < median_for(rows, "pre_static", {"CH4"}),
        "B5_bad_fraction_below_B3": float(next(
            item["bad_fraction"] for item in condition_summary if item["condition"] == "restored"
        )) < float(next(
            item["bad_fraction"] for item in condition_summary
            if item["condition"] == "multi_open_CH1_CH2_CH3"
        )),
    }
    detection = detection_metrics(rows)

    config = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "Frozen SQI-v2 transfer test; not fatigue-accuracy validation.",
        "fit_data": "Public SEED-VIG cached DE plus synthetic corruptions only.",
        "real_data_used_for_fit_or_threshold": False,
        "quality_threshold": QUALITY_THRESHOLD,
        "quality_model_parameters": QUALITY_MODEL_PARAMETERS,
        "clean_calibration_quantile": CLEAN_CALIBRATION_QUANTILE,
        "clean_prediction_scale": clean_scale,
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "window_seconds": WINDOW_SECONDS,
        "calibration": "First 15 non-overlapping 8 s windows of B1-R; shared across Stage-A files.",
        "bands_hz": [list(item) for item in DEPLOYMENT_DE_BANDS],
        "channels": list(CHANNELS),
        "raw_files": {key: {"path": str(path), "sha256": sha256_file(path), "malformed_rows": malformed_rows[key]} for key, path in RAW_FILES.items()},
        "public_cache_files": len(cache_paths),
        "software": {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__, "sklearn": sklearn.__version__},
        "predeclared_directional_checks": checks,
        "unambiguous_condition_detection": detection,
    }
    (output_dir / "config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    joblib.dump(model, output_dir / "sqi_v2_public_final.joblib")
    np.savez_compressed(
        output_dir / "b1r_de_calibration.npz",
        mean=calibration_mean,
        scale=calibration_scale,
        quality_clean_scale=np.asarray(clean_scale),
        quality_threshold=np.asarray(QUALITY_THRESHOLD),
    )

    labels = [item["condition"] for item in condition_summary]
    medians = [item["median_sqi"] for item in condition_summary]
    p10 = [item["p10_sqi"] for item in condition_summary]
    figure, axis = plt.subplots(figsize=(10, 4.8))
    x = np.arange(len(labels))
    axis.bar(x, medians, color="#377eb8", label="median SQI")
    axis.scatter(x, p10, color="#e41a1c", marker="v", label="10th percentile")
    axis.axhline(QUALITY_THRESHOLD, color="black", linestyle="--", linewidth=1.2, label="fixed bad threshold")
    axis.set_ylim(0.0, 1.05)
    axis.set_ylabel("Frozen SQI-v2 score")
    axis.set_xticks(x, labels, rotation=25, ha="right")
    axis.legend(loc="lower right")
    axis.grid(axis="y", alpha=0.25)
    figure.tight_layout()
    figure.savefig(output_dir / "condition_sqi.png", dpi=180)
    plt.close(figure)

    heatmap_conditions = [
        "stable_reference", "single_open_CH1", "multi_open_CH1_CH2_CH3",
        "pre_static", "CH4_motion", "recovery", "restored",
    ]
    summary_lookup = {
        (item["condition"], item["channel"]): float(item["median_sqi"])
        for item in channel_summary
    }
    matrix = np.asarray([
        [summary_lookup[(condition, channel)] for condition in heatmap_conditions]
        for channel in CHANNEL_LABELS
    ])
    figure, axis = plt.subplots(figsize=(11.5, 4.8))
    image = axis.imshow(matrix, vmin=0.0, vmax=1.0, cmap="RdYlGn", aspect="auto")
    for channel_index in range(matrix.shape[0]):
        for condition_index in range(matrix.shape[1]):
            value = matrix[channel_index, condition_index]
            axis.text(condition_index, channel_index, f"{value:.2f}", ha="center", va="center", fontsize=8)
    axis.set_yticks(np.arange(8), CHANNEL_LABELS)
    axis.set_xticks(np.arange(len(heatmap_conditions)), heatmap_conditions, rotation=25, ha="right")
    axis.set_title("Frozen SQI-v2 median by channel and bench condition")
    figure.colorbar(image, ax=axis, label="SQI (fixed bad threshold = 0.90)")
    figure.tight_layout()
    figure.savefig(output_dir / "channel_condition_heatmap.png", dpi=180)
    plt.close(figure)

    print(json.dumps(
        {"condition_summary": condition_summary, "checks": checks, "detection": detection},
        ensure_ascii=False,
        indent=2,
    ))
    print(f"Saved results to {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
