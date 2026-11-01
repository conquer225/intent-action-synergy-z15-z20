#!/usr/bin/env python3
"""Diagnose why frozen SQI-v2 detects cable motion inconsistently."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
from scipy.signal import welch

from analyze_cyton_bench import read_complete_rows


HERE = Path(__file__).resolve().parent
FS = 250.0
ROUNDS = {
    "R1": {
        "path": Path(r"C:\Users\lenovo\Documents\OpenBCI_GUI\Recordings\OpenBCISession_2026-09-20_17-51-46\OpenBCI-RAW-2026-09-20_17-52-22.txt"),
        "phases": {"pre_static": (0, 10), "motion": (10, 50), "recovery": (50, 60)},
        "scores": HERE / "results" / "real_cyton_sqi_v2_transfer" / "window_channel_scores.csv",
    },
    "R2": {
        "path": Path(r"C:\Users\lenovo\Documents\OpenBCI_GUI\Recordings\OpenBCISession_2026-09-20_20-48-08\OpenBCI-RAW-2026-09-20_20-56-37.txt"),
        "phases": {"pre_static": (0, 16), "motion": (16, 56), "recovery": (56, 80)},
        "scores": HERE / "results" / "real_cyton_sqi_stage_b_round2" / "window_channel_scores.csv",
    },
    "R3": {
        "path": Path(r"C:\Users\lenovo\Documents\OpenBCI_GUI\Recordings\OpenBCISession_2026-09-20_20-48-08\OpenBCI-RAW-2026-09-20_21-17-53.txt"),
        "phases": {"pre_static": (0, 16), "motion": (16, 56), "recovery": (56, 80)},
        "scores": HERE / "results" / "real_cyton_sqi_stage_b_round3" / "window_channel_scores.csv",
    },
}


def band_power(frequencies: np.ndarray, psd: np.ndarray, low: float, high: float) -> float:
    mask = (frequencies >= low) & (frequencies <= high)
    return float(np.trapezoid(psd[mask], frequencies[mask]))


def descriptors(values: np.ndarray, channel: int) -> dict[str, float]:
    signal = np.asarray(values[:, channel], dtype=np.float64)
    centered = signal - np.median(signal)
    frequencies, psd = welch(centered, fs=FS, nperseg=min(int(FS * 2), len(centered)), noverlap=min(int(FS), max(0, len(centered) // 2 - 1)))
    total = max(band_power(frequencies, psd, 1.0, 50.0), 1.0e-12)
    spatial_median = np.median(values, axis=1)
    return {
        "mad_uv": float(np.median(np.abs(centered))),
        "p95_abs_uv": float(np.percentile(np.abs(centered), 95)),
        "derivative_mad_uv": float(np.median(np.abs(np.diff(signal) - np.median(np.diff(signal))))),
        "low_1_4_ratio": band_power(frequencies, psd, 1.0, 4.0) / total,
        "high_31_50_ratio": band_power(frequencies, psd, 31.0, 50.0) / total,
        "mains_48_50_ratio": band_power(frequencies, psd, 48.0, 50.0) / total,
        "spatial_residual_mad_uv": float(np.median(np.abs(signal - spatial_median))),
    }


def bad_fraction(score_path: Path, condition: str, channel: str) -> float:
    with score_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    aliases = {"motion": "CH4_motion"}
    wanted = aliases.get(condition, condition)
    selected = [int(row["bad"]) for row in rows if row["condition"] == wanted and row["channel"] == channel]
    return float(np.mean(selected)) if selected else float("nan")


def main() -> int:
    output = HERE / "results" / "real_cyton_motion_diagnosis"
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    for round_name, spec in ROUNDS.items():
        _, values, _ = read_complete_rows(spec["path"])
        for phase, (start_s, stop_s) in spec["phases"].items():
            segment = values[int(start_s * FS):int(stop_s * FS)]
            for channel in range(8):
                rows.append({
                    "round": round_name,
                    "phase": phase,
                    "channel": f"CH{channel + 1}",
                    "seconds": stop_s - start_s,
                    **descriptors(segment, channel),
                    "sqi_bad_fraction": bad_fraction(spec["scores"], phase, f"CH{channel + 1}"),
                })
    with (output / "motion_descriptors.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    ch4 = [row for row in rows if row["channel"] == "CH4"]
    round_summary = {}
    for round_name in ROUNDS:
        lookup = {row["phase"]: row for row in ch4 if row["round"] == round_name}
        pre = lookup["pre_static"]
        motion = lookup["motion"]
        round_summary[round_name] = {
            "motion_to_pre_mad_ratio": motion["mad_uv"] / max(pre["mad_uv"], 1.0e-12),
            "motion_to_pre_p95_ratio": motion["p95_abs_uv"] / max(pre["p95_abs_uv"], 1.0e-12),
            "motion_to_pre_derivative_mad_ratio": motion["derivative_mad_uv"] / max(pre["derivative_mad_uv"], 1.0e-12),
            "motion_high_31_50_ratio": motion["high_31_50_ratio"],
            "motion_spatial_residual_mad_uv": motion["spatial_residual_mad_uv"],
            "ch4_motion_bad_fraction": motion["sqi_bad_fraction"],
        }
    (output / "summary.json").write_text(json.dumps(round_summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(round_summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
