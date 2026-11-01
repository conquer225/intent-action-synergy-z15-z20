#!/usr/bin/env python3
"""Audit an OpenBCI GUI RAW file for bench SQI transfer experiments.

The parser tolerates a file that is still being written by ignoring incomplete
trailing records. It reports transport continuity separately from signal
railing and amplitude so poor electrode contact is not mislabeled packet loss.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("raw_file", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--sample-rate", type=float, default=250.0)
    parser.add_argument("--skip-seconds", type=float, default=0.0)
    parser.add_argument("--duration-seconds", type=float)
    parser.add_argument("--tail-seconds", type=float)
    return parser.parse_args()


def read_complete_rows(path: Path) -> tuple[np.ndarray, np.ndarray, int]:
    sample_ids: list[int] = []
    channels: list[list[float]] = []
    malformed = 0
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.reader(handle)
        for row in reader:
            if not row or row[0].startswith("%") or row[0].strip() == "Sample Index":
                continue
            if len(row) < 9:
                malformed += 1
                continue
            try:
                sid = int(float(row[0]))
                values = [float(value) for value in row[1:9]]
            except ValueError:
                malformed += 1
                continue
            sample_ids.append(sid)
            channels.append(values)
    if not channels:
        raise RuntimeError(f"No complete 8-channel samples found in {path}")
    return np.asarray(sample_ids, dtype=np.int16), np.asarray(channels), malformed


def summarize(
    path: Path,
    sample_rate: float,
    skip_seconds: float = 0.0,
    duration_seconds: float | None = None,
    tail_seconds: float | None = None,
) -> dict:
    sample_ids, values, malformed = read_complete_rows(path)
    skip_samples = max(0, int(round(skip_seconds * sample_rate)))
    if skip_samples:
        sample_ids = sample_ids[skip_samples:]
        values = values[skip_samples:]
    if duration_seconds is not None:
        duration_samples = max(1, int(round(duration_seconds * sample_rate)))
        sample_ids = sample_ids[:duration_samples]
        values = values[:duration_samples]
    if tail_seconds is not None:
        tail_samples = max(1, int(round(tail_seconds * sample_rate)))
        sample_ids = sample_ids[-tail_samples:]
        values = values[-tail_samples:]
    if not len(sample_ids):
        raise RuntimeError("The requested analysis window contains no complete samples")
    deltas = (sample_ids[1:].astype(int) - sample_ids[:-1].astype(int)) % 256
    duplicates = int(np.sum(deltas == 0))
    jumps = deltas[(deltas > 1) & (deltas < 128)]
    estimated_missing = int(np.sum(jumps - 1))
    continuity_denominator = len(sample_ids) + estimated_missing
    packet_loss_fraction = (
        estimated_missing / continuity_denominator if continuity_denominator else 0.0
    )

    med = np.median(values, axis=0)
    centered = values - med
    mad = np.median(np.abs(centered), axis=0)
    p95_abs_centered = np.percentile(np.abs(centered), 95, axis=0)
    rail_fraction = np.mean(np.abs(values) >= 187_499.0, axis=0)
    flat_fraction = np.mean(np.abs(np.diff(values, axis=0)) < 1e-9, axis=0)

    channel_summary = []
    for idx in range(8):
        channel_summary.append(
            {
                "channel": f"CH{idx + 1}",
                "median_uv": float(med[idx]),
                "mad_uv": float(mad[idx]),
                "p95_abs_centered_uv": float(p95_abs_centered[idx]),
                "rail_fraction": float(rail_fraction[idx]),
                "flat_step_fraction": float(flat_fraction[idx]),
            }
        )

    return {
        "source_file": str(path.resolve()),
        "sample_rate_hz": sample_rate,
        "analysis_window": {
            "skip_seconds": skip_seconds,
            "duration_seconds": duration_seconds,
            "tail_seconds": tail_seconds,
        },
        "complete_samples": int(len(sample_ids)),
        "duration_seconds": float(len(sample_ids) / sample_rate),
        "incomplete_or_malformed_rows": malformed,
        "transport": {
            "estimated_missing_packets": estimated_missing,
            "duplicate_sample_ids": duplicates,
            "estimated_packet_loss_fraction": float(packet_loss_fraction),
            "note": "Derived from modulo-256 OpenBCI sample-index continuity; signal railing is independent.",
        },
        "channels": channel_summary,
    }


def main() -> None:
    args = parse_args()
    result = summarize(
        args.raw_file,
        args.sample_rate,
        skip_seconds=args.skip_seconds,
        duration_seconds=args.duration_seconds,
        tail_seconds=args.tail_seconds,
    )
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
