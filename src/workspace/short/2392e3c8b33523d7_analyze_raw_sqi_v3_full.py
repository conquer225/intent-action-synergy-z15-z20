#!/usr/bin/env python3
"""Participant-level statistical analysis for the frozen SQI-v3 protocol."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.stats import wilcoxon


HERE = Path(__file__).resolve().parent
ROOT = HERE / "results" / "raw_sqi_v3_full_frozen"
KINDS = ("flatline", "broadband_noise", "mains_noise", "drift", "burst", "cable_motion")
METHODS = ("v2", "v3", "v3_classifier")
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


def bootstrap_mean_ci(values: np.ndarray, seed: int) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(values), size=(BOOTSTRAPS, len(values)))
    means = values[indices].mean(axis=1)
    low, high = np.quantile(means, (0.025, 0.975))
    return float(low), float(high)


def main() -> int:
    rows = []
    for path in sorted(ROOT.glob("severity_*_seed_*/fold_metrics.csv")):
        run_name = path.parent.name
        parts = run_name.split("_")
        severity = float(parts[1])
        seed = int(parts[3])
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                row["severity"] = severity
                row["seed"] = seed
                row["participant"] = int(row["participant"])
                for key in ("false_bad_rate", "sensitivity", "specificity", "balanced_accuracy"):
                    row[key] = float(row[key]) if row[key] else None
                rows.append(row)

    severity_rows = []
    for severity in sorted({row["severity"] for row in rows}):
        for method in METHODS:
            for condition in ("clean", *KINDS):
                selected = [
                    row for row in rows
                    if row["severity"] == severity and row["method"] == method
                    and row["condition"] == condition
                ]
                result = {"severity": severity, "method": method, "condition": condition}
                for metric in ("false_bad_rate", "sensitivity", "specificity", "balanced_accuracy"):
                    values = [row[metric] for row in selected if row[metric] is not None]
                    result[metric] = float(np.mean(values)) if values else None
                severity_rows.append(result)

    with (ROOT / "severity_summary.csv").open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "severity", "method", "condition", "false_bad_rate",
            "sensitivity", "specificity", "balanced_accuracy",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(severity_rows)

    participant_values: dict[tuple[int, str, str], list[float]] = defaultdict(list)
    for row in rows:
        if row["balanced_accuracy"] is not None:
            participant_values[(row["participant"], row["method"], row["condition"])].append(
                row["balanced_accuracy"]
            )

    raw_p = {}
    comparisons = {}
    participant_rows = []
    for kind_index, kind in enumerate(KINDS):
        baseline = []
        candidate = []
        for participant in range(1, 22):
            base = float(np.mean(participant_values[(participant, "v2", kind)]))
            cand = float(np.mean(participant_values[(participant, "v3_classifier", kind)]))
            baseline.append(base)
            candidate.append(cand)
            participant_rows.append({
                "participant": participant,
                "condition": kind,
                "v2_balanced_accuracy": base,
                "v3_classifier_balanced_accuracy": cand,
                "difference": cand - base,
            })
        difference = np.asarray(candidate) - np.asarray(baseline)
        test = wilcoxon(difference, alternative="two-sided", zero_method="wilcox")
        raw_p[kind] = float(test.pvalue)
        ci_low, ci_high = bootstrap_mean_ci(difference, seed=20260921 + kind_index)
        comparisons[kind] = {
            "participants": 21,
            "v2_mean_balanced_accuracy": float(np.mean(baseline)),
            "v3_classifier_mean_balanced_accuracy": float(np.mean(candidate)),
            "mean_paired_difference": float(np.mean(difference)),
            "participant_bootstrap_95_ci": [ci_low, ci_high],
            "wilcoxon_statistic": float(test.statistic),
            "wilcoxon_p_raw": float(test.pvalue),
        }
    adjusted = holm_adjust(raw_p)
    for kind in KINDS:
        comparisons[kind]["wilcoxon_p_holm"] = adjusted[kind]

    with (ROOT / "participant_paired_values.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(participant_rows[0]))
        writer.writeheader()
        writer.writerows(participant_rows)

    output = {
        "analysis_unit": "participant",
        "participant_count": 21,
        "runs_per_participant": 9,
        "comparison": "v3_classifier minus DE-only v2 regression baseline",
        "multiple_comparison_correction": "Holm across six corruption families",
        "bootstrap_resamples": BOOTSTRAPS,
        "comparisons": comparisons,
    }
    (ROOT / "participant_statistics.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
