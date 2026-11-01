#!/usr/bin/env python3
"""Run and aggregate the frozen multi-severity, multi-seed SQI-v3 protocol."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path

import numpy as np


HERE = Path(__file__).resolve().parent
DEFAULT_SEVERITIES = (0.25, 0.50, 0.75)
DEFAULT_SEEDS = (0, 1, 2)
DEFAULT_KINDS = (
    "flatline", "broadband_noise", "mains_noise", "drift", "burst", "cable_motion"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=HERE / "results" / "raw_sqi_v3_full")
    parser.add_argument("--max-participants", type=int, default=21)
    parser.add_argument("--severities", type=float, nargs="+", default=list(DEFAULT_SEVERITIES))
    parser.add_argument("--seeds", type=int, nargs="+", default=list(DEFAULT_SEEDS))
    parser.add_argument("--kinds", nargs="+", default=list(DEFAULT_KINDS))
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    summaries = []
    for severity in args.severities:
        for seed in args.seeds:
            run_dir = args.output_dir / f"severity_{severity:.2f}_seed_{seed}"
            summary_path = run_dir / "summary.json"
            if args.force or not summary_path.exists():
                command = [
                    sys.executable, str(HERE / "evaluate_raw_sqi_v3_loso.py"),
                    "--max-participants", str(args.max_participants),
                    "--test-severity", str(severity),
                    "--experiment-seed", str(seed),
                    "--output-dir", str(run_dir),
                    "--kinds", *args.kinds,
                ]
                print(f"RUN severity={severity:.2f} seed={seed}", flush=True)
                subprocess.run(command, cwd=HERE, check=True)
            payload = json.loads(summary_path.read_text(encoding="utf-8"))
            summaries.append(payload)

    rows = []
    for payload in summaries:
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
        "severity", "seed", "method", "condition", "false_bad_rate",
        "sensitivity", "specificity", "balanced_accuracy",
    ]
    with (args.output_dir / "all_run_metrics.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    aggregate: dict[str, dict] = {}
    for method in sorted({row["method"] for row in rows}):
        aggregate[method] = {}
        for condition in sorted({row["condition"] for row in rows}):
            selected = [row for row in rows if row["method"] == method and row["condition"] == condition]
            if not selected:
                continue
            aggregate[method][condition] = {}
            for metric in ("false_bad_rate", "sensitivity", "specificity", "balanced_accuracy"):
                values = [float(row[metric]) for row in selected if metric in row]
                if values:
                    aggregate[method][condition][metric] = {
                        "mean": float(np.mean(values)),
                        "std_across_runs": float(np.std(values, ddof=1)) if len(values) > 1 else 0.0,
                        "min": float(np.min(values)),
                        "max": float(np.max(values)),
                    }
    output = {
        "participants": args.max_participants,
        "severities": args.severities,
        "seeds": args.seeds,
        "kinds": args.kinds,
        "runs": len(summaries),
        "aggregate": aggregate,
    }
    (args.output_dir / "aggregate_summary.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
