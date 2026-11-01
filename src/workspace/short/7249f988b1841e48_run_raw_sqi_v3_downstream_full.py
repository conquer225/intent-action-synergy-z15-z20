#!/usr/bin/env python3
"""Run the frozen downstream SQI-v3 gating experiment with resume support."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path

import numpy as np


HERE = Path(__file__).resolve().parent
SEVERITIES = (0.25, 0.50, 0.75)
SEEDS = (0, 1, 2)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir", type=Path,
        default=HERE / "results" / "raw_sqi_v3_downstream_full_frozen",
    )
    parser.add_argument("--max-participants", type=int, default=21)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    payloads = []
    for severity in SEVERITIES:
        for seed in SEEDS:
            run_dir = args.output_dir / f"severity_{severity:.2f}_seed_{seed}"
            summary_path = run_dir / "summary.json"
            if args.force or not summary_path.exists():
                command = [
                    sys.executable, str(HERE / "evaluate_raw_sqi_v3_downstream.py"),
                    "--max-participants", str(args.max_participants),
                    "--test-severity", str(severity),
                    "--experiment-seed", str(seed),
                    "--output-dir", str(run_dir),
                ]
                print(f"RUN severity={severity:.2f} seed={seed}", flush=True)
                subprocess.run(command, cwd=HERE, check=True)
            payloads.append(json.loads(summary_path.read_text(encoding="utf-8")))

    rows = []
    for payload in payloads:
        for method, conditions in payload["summary"].items():
            for condition, metrics in conditions.items():
                rows.append({
                    "severity": payload["test_severity"],
                    "seed": payload["experiment_seed"],
                    "method": method,
                    "condition": condition,
                    **metrics,
                })
    fieldnames = [
        "severity", "seed", "method", "condition", "pcc", "rmse", "mae", "ccc",
        "episode_rmse", "episode_mae",
    ]
    with (args.output_dir / "all_run_metrics.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    aggregate = {}
    for method in sorted({row["method"] for row in rows}):
        aggregate[method] = {}
        for condition in sorted({row["condition"] for row in rows}):
            selected = [row for row in rows if row["method"] == method and row["condition"] == condition]
            aggregate[method][condition] = {}
            for metric in ("pcc", "rmse", "mae", "ccc", "episode_rmse", "episode_mae"):
                values = [float(row[metric]) for row in selected if metric in row]
                if values:
                    aggregate[method][condition][metric] = {
                        "mean": float(np.nanmean(values)),
                        "std_across_runs": float(np.nanstd(values, ddof=1)),
                        "min": float(np.nanmin(values)),
                        "max": float(np.nanmax(values)),
                    }
    output = {
        "participants": args.max_participants,
        "severities": list(SEVERITIES),
        "seeds": list(SEEDS),
        "runs": len(payloads),
        "aggregate": aggregate,
    }
    (args.output_dir / "aggregate_summary.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
