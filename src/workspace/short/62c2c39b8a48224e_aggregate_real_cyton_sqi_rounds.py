#!/usr/bin/env python3
"""Aggregate frozen SQI-v2 bench transfer at the placement level."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np


HERE = Path(__file__).resolve().parent
RESULT_ROOT = HERE / "results"
ROUND_FILES = {
    "R1": RESULT_ROOT / "real_cyton_sqi_v2_transfer" / "window_channel_scores.csv",
    "R2": RESULT_ROOT / "real_cyton_sqi_stage_b_round2" / "window_channel_scores.csv",
    "R3": RESULT_ROOT / "real_cyton_sqi_stage_b_round3" / "window_channel_scores.csv",
}
AFFECTED = {
    "stable_reference": set(),
    "single_open_CH1": {"CH1"},
    "multi_open_CH1_CH2_CH3": {"CH1", "CH2", "CH3"},
    "pre_static": set(),
    "CH4_motion": {"CH4"},
    "restored": set(),
}


def load_rows(path: Path, placement: str) -> list[dict]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        row["placement"] = placement
        row["bad"] = int(row["bad"])
    return rows


def counts(rows: list[dict], include: set[str] | None = None) -> dict[str, int | float]:
    tp = fn = tn = fp = 0
    for row in rows:
        condition = row["condition"]
        if condition not in AFFECTED or (include is not None and condition not in include):
            continue
        truth = row["channel"] in AFFECTED[condition]
        predicted = bool(row["bad"])
        if truth and predicted:
            tp += 1
        elif truth:
            fn += 1
        elif predicted:
            fp += 1
        else:
            tn += 1
    sensitivity = tp / (tp + fn) if tp + fn else float("nan")
    specificity = tn / (tn + fp) if tn + fp else float("nan")
    return {
        "tp": tp, "fn": fn, "tn": tn, "fp": fp,
        "sensitivity": sensitivity,
        "specificity": specificity,
        "balanced_accuracy": 0.5 * (sensitivity + specificity),
    }


def bootstrap(round_rows: dict[str, list[dict]], seed: int = 20260920, samples: int = 10000) -> dict:
    names = sorted(round_rows)
    rng = np.random.default_rng(seed)
    estimates = []
    for _ in range(samples):
        selected = rng.choice(names, size=len(names), replace=True)
        sample_rows = []
        for name in selected:
            sample_rows.extend(round_rows[str(name)])
        estimates.append(counts(sample_rows)["balanced_accuracy"])
    values = np.asarray(estimates, dtype=np.float64)
    return {
        "seed": seed,
        "resamples": samples,
        "placement_cluster_percentile_95_ci": [
            float(np.quantile(values, 0.025)), float(np.quantile(values, 0.975))
        ],
    }


def main() -> int:
    output = RESULT_ROOT / "real_cyton_sqi_three_placement_summary"
    output.mkdir(parents=True, exist_ok=True)
    round_rows = {name: load_rows(path, name) for name, path in ROUND_FILES.items()}
    all_rows = [row for rows in round_rows.values() for row in rows]
    per_placement = {name: counts(rows) for name, rows in round_rows.items()}
    aggregate = counts(all_rows)
    by_corruption = {
        "single_open": counts(all_rows, {"single_open_CH1"}),
        "multi_open": counts(all_rows, {"multi_open_CH1_CH2_CH3"}),
        "cable_motion": counts(all_rows, {"CH4_motion"}),
        "known_clean": counts(all_rows, {"stable_reference", "pre_static", "restored"}),
    }
    payload = {
        "hypothesis": "Frozen SQI-v2 transfers from public/synthetic training to controlled Cyton bench contact failures.",
        "falsification": "Affected-channel sensitivity or unaffected-channel specificity fails to exceed 0.80 across placements.",
        "inference_unit": "independent electrode re-placement (same device, operator, and day)",
        "placements": len(round_rows),
        "per_placement": per_placement,
        "pooled_descriptive": aggregate,
        "by_corruption": by_corruption,
        "bootstrap": bootstrap(round_rows),
        "limitations": [
            "Only three re-placements, all on one day with one device and operator.",
            "Wet-gauze phantom data are not physiological EEG.",
            "Window-level pooled counts are descriptive, not independent inferential samples.",
            "Cable-motion sensitivity is below the predeclared 0.80 criterion.",
        ],
    }
    (output / "summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
