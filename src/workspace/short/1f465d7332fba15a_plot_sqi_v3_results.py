#!/usr/bin/env python3
"""Create paper-ready summary figures for the frozen SQI-v3 experiments."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


HERE = Path(__file__).resolve().parent
DETECTION = HERE / "results" / "raw_sqi_v3_full_frozen"
DOWNSTREAM = HERE / "results" / "raw_sqi_v3_downstream_full_frozen"
KINDS = ("flatline", "broadband_noise", "mains_noise", "drift", "burst", "cable_motion")
LABELS = ("Flatline", "Broadband", "Mains", "Drift", "Burst", "Cable motion")


def main() -> int:
    detection = json.loads((DETECTION / "participant_statistics.json").read_text(encoding="utf-8"))
    with (DOWNSTREAM / "participant_metric_summary.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    baseline_ba = [detection["comparisons"][kind]["v2_mean_balanced_accuracy"] for kind in KINDS]
    classifier_ba = [detection["comparisons"][kind]["v3_classifier_mean_balanced_accuracy"] for kind in KINDS]
    methods = ("clean_no_gate", "augmented_no_gate", "v3_hard_gate", "v3_soft_gate")
    method_labels = ("Clean only", "Corruption aug.", "SQI-v3 hard", "SQI-v3 soft")
    episode_rmse = {
        method: [float(next(row["episode_rmse"] for row in rows if row["method"] == method and row["condition"] == kind)) for kind in KINDS]
        for method in methods
    }

    plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False})
    fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.1), constrained_layout=True)
    x = np.arange(len(KINDS))
    width = 0.36
    axes[0].bar(x - width / 2, baseline_ba, width, label="DE-only baseline", color="#9CA3AF")
    axes[0].bar(x + width / 2, classifier_ba, width, label="SQI-v3 classifier", color="#2563EB")
    axes[0].axhline(0.5, color="black", linewidth=0.8, linestyle="--")
    axes[0].set_ylabel("Balanced accuracy")
    axes[0].set_ylim(0.45, 1.02)
    axes[0].set_xticks(x, LABELS, rotation=28, ha="right")
    axes[0].set_title("(a) Corruption detection")
    axes[0].legend(frameon=False, loc="lower left")

    colors = ("#9CA3AF", "#059669", "#7C3AED", "#DC2626")
    offsets = np.linspace(-0.30, 0.30, len(methods))
    bar_width = 0.19
    for method, label, color, offset in zip(methods, method_labels, colors, offsets):
        axes[1].bar(x + offset, episode_rmse[method], bar_width, label=label, color=color)
    axes[1].set_ylabel("Corrupted-episode RMSE (lower is better)")
    axes[1].set_ylim(0.14, 0.215)
    axes[1].set_xticks(x, LABELS, rotation=28, ha="right")
    axes[1].set_title("(b) Downstream vigilance estimation")
    axes[1].legend(frameon=False, fontsize=8, ncol=2, loc="upper right")

    output_dir = DOWNSTREAM / "figures"
    output_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_dir / "sqi_v3_detection_and_downstream.png", dpi=300)
    fig.savefig(output_dir / "sqi_v3_detection_and_downstream.pdf")
    plt.close(fig)
    print(output_dir / "sqi_v3_detection_and_downstream.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
