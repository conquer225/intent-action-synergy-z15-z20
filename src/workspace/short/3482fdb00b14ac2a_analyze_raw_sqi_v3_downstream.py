#!/usr/bin/env python3
"""Participant-level analysis for the frozen SQI-v3 downstream protocol."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.stats import wilcoxon


HERE = Path(__file__).resolve().parent
ROOT = HERE / "results" / "raw_sqi_v3_downstream_full_frozen"
KINDS = ("flatline", "broadband_noise", "mains_noise", "drift", "burst", "cable_motion")
METHODS = (
    "clean_no_gate", "augmented_no_gate", "oracle_hard_gate", "v3_hard_gate",
    "oracle_soft_gate", "v3_soft_gate",
)
METRICS = ("pcc", "rmse", "mae", "ccc", "episode_rmse", "episode_mae")
BOOTSTRAPS = 10_000


def holm_adjust(p_values: dict[str, float]) -> dict[str, float]:
    ordered = sorted(p_values, key=p_values.get)
    adjusted: dict[str, float] = {}
    running = 0.0
    count = len(ordered)
    for rank, name in enumerate(ordered):
        value = min(1.0, (count - rank) * p_values[name])
        running = max(running, value)
        adjusted[name] = running
    return adjusted


def bootstrap_mean_ci(values: np.ndarray, seed: int) -> list[float]:
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(values), size=(BOOTSTRAPS, len(values)))
    low, high = np.quantile(values[indices].mean(axis=1), (0.025, 0.975))
    return [float(low), float(high)]


def paired_test(improvements: np.ndarray, seed: int) -> dict[str, object]:
    if np.allclose(improvements, 0.0):
        statistic, p_value = 0.0, 1.0
    else:
        test = wilcoxon(improvements, alternative="two-sided", zero_method="wilcox")
        statistic, p_value = float(test.statistic), float(test.pvalue)
    return {
        "participants": int(len(improvements)),
        "mean_improvement": float(np.mean(improvements)),
        "median_improvement": float(np.median(improvements)),
        "participant_bootstrap_95_ci": bootstrap_mean_ci(improvements, seed),
        "wilcoxon_statistic": statistic,
        "wilcoxon_p_raw": p_value,
    }


def main() -> int:
    rows: list[dict[str, object]] = []
    for path in sorted(ROOT.glob("severity_*_seed_*/fold_metrics.csv")):
        with path.open(encoding="utf-8", newline="") as handle:
            for source in csv.DictReader(handle):
                row: dict[str, object] = dict(source)
                row["participant"] = int(source["participant"])
                row["severity"] = float(source["severity"]) if source["severity"] else None
                row["seed"] = int(source["seed"])
                for metric in METRICS:
                    row[metric] = float(source[metric]) if source[metric] else None
                rows.append(row)

    participants = sorted({int(row["participant"]) for row in rows})
    if len(participants) != 21:
        raise RuntimeError(f"Expected 21 participants, found {len(participants)}")

    values: dict[tuple[int, str, str, str], list[float]] = defaultdict(list)
    for row in rows:
        for metric in METRICS:
            value = row[metric]
            if value is not None:
                values[(int(row["participant"]), str(row["method"]), str(row["condition"]), metric)].append(float(value))

    participant_means: dict[tuple[int, str, str, str], float] = {
        key: float(np.mean(group)) for key, group in values.items()
    }

    summary_rows = []
    for method in METHODS:
        for condition in ("clean", *KINDS):
            selected = [row for row in rows if row["method"] == method and row["condition"] == condition]
            output: dict[str, object] = {"method": method, "condition": condition}
            for metric in METRICS:
                metric_values = [float(row[metric]) for row in selected if row[metric] is not None]
                output[metric] = float(np.mean(metric_values)) if metric_values else None
            summary_rows.append(output)
    with (ROOT / "participant_metric_summary.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["method", "condition", *METRICS])
        writer.writeheader()
        writer.writerows(summary_rows)

    practical = "v3_soft_gate"
    comparator = "augmented_no_gate"
    paired_rows = []
    family_stats: dict[str, dict[str, object]] = {}
    raw_p: dict[str, float] = {}
    for kind_index, kind in enumerate(KINDS):
        episode_improvements = []
        ccc_improvements = []
        rmse_improvements = []
        for participant in participants:
            base_episode = participant_means[(participant, comparator, kind, "episode_rmse")]
            cand_episode = participant_means[(participant, practical, kind, "episode_rmse")]
            base_ccc = participant_means[(participant, comparator, kind, "ccc")]
            cand_ccc = participant_means[(participant, practical, kind, "ccc")]
            base_rmse = participant_means[(participant, comparator, kind, "rmse")]
            cand_rmse = participant_means[(participant, practical, kind, "rmse")]
            episode_gain = base_episode - cand_episode
            ccc_gain = cand_ccc - base_ccc
            rmse_gain = base_rmse - cand_rmse
            episode_improvements.append(episode_gain)
            ccc_improvements.append(ccc_gain)
            rmse_improvements.append(rmse_gain)
            paired_rows.append({
                "participant": participant,
                "condition": kind,
                "augmented_no_gate_episode_rmse": base_episode,
                "v3_soft_gate_episode_rmse": cand_episode,
                "episode_rmse_improvement": episode_gain,
                "ccc_improvement": ccc_gain,
                "full_rmse_improvement": rmse_gain,
            })
        episode_array = np.asarray(episode_improvements)
        stats = paired_test(episode_array, 20260921 + kind_index)
        stats["augmented_no_gate_mean_episode_rmse"] = float(np.mean([
            participant_means[(participant, comparator, kind, "episode_rmse")] for participant in participants
        ]))
        stats["v3_soft_gate_mean_episode_rmse"] = float(np.mean([
            participant_means[(participant, practical, kind, "episode_rmse")] for participant in participants
        ]))
        stats["mean_ccc_improvement"] = float(np.mean(ccc_improvements))
        stats["mean_full_rmse_improvement"] = float(np.mean(rmse_improvements))
        family_stats[kind] = stats
        raw_p[kind] = float(stats["wilcoxon_p_raw"])
    adjusted = holm_adjust(raw_p)
    for kind in KINDS:
        family_stats[kind]["wilcoxon_p_holm"] = adjusted[kind]

    def pooled_improvements(candidate: str, baseline: str, metric: str, lower_is_better: bool, clean: bool = False) -> np.ndarray:
        results = []
        conditions = ("clean",) if clean else KINDS
        for participant in participants:
            cand = np.mean([participant_means[(participant, candidate, kind, metric)] for kind in conditions])
            base = np.mean([participant_means[(participant, baseline, kind, metric)] for kind in conditions])
            results.append(base - cand if lower_is_better else cand - base)
        return np.asarray(results)

    overall = {
        "augmented_no_gate_vs_clean_no_gate_episode_rmse": paired_test(
            pooled_improvements("augmented_no_gate", "clean_no_gate", "episode_rmse", True), 20261000
        ),
        "v3_soft_vs_augmented_no_gate_episode_rmse": paired_test(
            pooled_improvements(practical, comparator, "episode_rmse", True), 20261001
        ),
        "v3_soft_vs_augmented_no_gate_full_rmse": paired_test(
            pooled_improvements(practical, comparator, "rmse", True), 20261002
        ),
        "v3_soft_vs_augmented_no_gate_ccc": paired_test(
            pooled_improvements(practical, comparator, "ccc", False), 20261003
        ),
        "v3_soft_vs_clean_no_gate_episode_rmse": paired_test(
            pooled_improvements(practical, "clean_no_gate", "episode_rmse", True), 20261004
        ),
        "oracle_soft_vs_v3_soft_episode_rmse": paired_test(
            pooled_improvements("oracle_soft_gate", practical, "episode_rmse", True), 20261005
        ),
        "oracle_hard_vs_augmented_no_gate_episode_rmse": paired_test(
            pooled_improvements("oracle_hard_gate", comparator, "episode_rmse", True), 20261008
        ),
        "v3_hard_vs_augmented_no_gate_episode_rmse": paired_test(
            pooled_improvements("v3_hard_gate", comparator, "episode_rmse", True), 20261009
        ),
        "clean_v3_soft_vs_augmented_no_gate_rmse": paired_test(
            pooled_improvements(practical, comparator, "rmse", True, clean=True), 20261006
        ),
        "clean_v3_soft_vs_augmented_no_gate_ccc": paired_test(
            pooled_improvements(practical, comparator, "ccc", False, clean=True), 20261007
        ),
    }

    with (ROOT / "participant_paired_values.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(paired_rows[0]))
        writer.writeheader()
        writer.writerows(paired_rows)

    output = {
        "analysis_unit": "participant",
        "participant_count": len(participants),
        "runs_per_participant": 9,
        "primary_endpoint": "corrupted-episode RMSE; positive improvement means v3_soft_gate is better",
        "primary_comparator": "augmented_no_gate",
        "multiple_comparison_correction": "Holm across six corruption families for the primary endpoint",
        "bootstrap_resamples": BOOTSTRAPS,
        "overall_comparisons": overall,
        "per_corruption_primary_comparisons": family_stats,
    }
    (ROOT / "participant_statistics.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
