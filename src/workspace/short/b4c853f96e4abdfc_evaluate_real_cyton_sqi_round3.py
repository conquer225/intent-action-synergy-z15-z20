#!/usr/bin/env python3
"""Score Cyton Stage-B round 3 with the already frozen SQI-v2 model."""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np

from analyze_cyton_bench import read_complete_rows, summarize
from evaluate_real_cyton_sqi_transfer import (
    CALIBRATION_WINDOWS,
    QUALITY_THRESHOLD,
    SAMPLE_RATE_HZ,
    WINDOW_SAMPLES,
    detection_metrics,
    extract_de,
    grouped_summary,
    score_segment,
    select_samples,
    sha256_file,
    write_csv,
)
from train_seedvig_8ch_calibrated_loso import calibrate_recording


HERE = Path(__file__).resolve().parent
SESSION = Path(r"C:\Users\lenovo\Documents\OpenBCI_GUI\Recordings\OpenBCISession_2026-09-20_20-48-08")
FILES = {
    "R3_B1": SESSION / "OpenBCI-RAW-2026-09-20_21-10-58.txt",
    "R3_B3": SESSION / "OpenBCI-RAW-2026-09-20_21-14-14.txt",
    "R3_B2": SESSION / "OpenBCI-RAW-2026-09-20_21-16-12.txt",
    "R3_B4": SESSION / "OpenBCI-RAW-2026-09-20_21-17-53.txt",
    "R3_B5": SESSION / "OpenBCI-RAW-2026-09-20_21-19-32.txt",
}


def main() -> int:
    output = HERE / "results" / "real_cyton_sqi_stage_b_round3"
    output.mkdir(parents=True, exist_ok=True)
    frozen = HERE / "results" / "real_cyton_sqi_v2_transfer"
    model = joblib.load(frozen / "sqi_v2_public_final.joblib")
    with np.load(frozen / "b1r_de_calibration.npz") as item:
        clean_scale = float(item["quality_clean_scale"])

    values = {}
    transport = {}
    for stage, path in FILES.items():
        _, values[stage], malformed = read_complete_rows(path)
        report = summarize(path, SAMPLE_RATE_HZ)
        transport[stage] = {
            "duration_seconds": report["duration_seconds"],
            "estimated_packet_loss_fraction": report["transport"]["estimated_packet_loss_fraction"],
            "estimated_missing_packets": report["transport"]["estimated_missing_packets"],
            "malformed_rows": malformed,
        }

    b1_de = extract_de(select_samples(values["R3_B1"], 0.0, None))
    _, mean, scale = calibrate_recording(b1_de)
    scale = np.asarray(scale, dtype=np.float64)
    rows = []
    b1_post = values["R3_B1"][CALIBRATION_WINDOWS * WINDOW_SAMPLES:]
    b1_post = b1_post[: len(b1_post) // WINDOW_SAMPLES * WINDOW_SAMPLES]
    rows += score_segment("R3_B1", "stable_reference", b1_post, mean, scale, model, clean_scale, 120.0)
    rows += score_segment(
        "R3_B3", "multi_open_CH1_CH2_CH3", select_samples(values["R3_B3"], 0.0, 64.0),
        mean, scale, model, clean_scale, 0.0,
    )
    rows += score_segment(
        "R3_B2", "single_open_CH1", select_samples(values["R3_B2"], 0.0, 64.0),
        mean, scale, model, clean_scale, 0.0,
    )
    b4_rows = score_segment(
        "R3_B4", "temporary", select_samples(values["R3_B4"], 0.0, 80.0),
        mean, scale, model, clean_scale, 0.0,
    )
    for row in b4_rows:
        center = 0.5 * (float(row["window_start_s"]) + float(row["window_end_s"]))
        row["condition"] = "pre_static" if center < 16.0 else ("CH4_motion" if center < 56.0 else "recovery")
    rows += b4_rows
    rows += score_segment(
        "R3_B5", "restored", select_samples(values["R3_B5"], 0.0, 120.0),
        mean, scale, model, clean_scale, 0.0,
    )

    channel_summary = grouped_summary(rows, ("stage", "condition", "channel"))
    condition_summary = grouped_summary(rows, ("stage", "condition"))
    detection = detection_metrics(rows)
    write_csv(output / "window_channel_scores.csv", rows)
    write_csv(output / "channel_summary.csv", channel_summary)
    write_csv(output / "condition_summary.csv", condition_summary)
    manifest = {
        "round": 3,
        "model_frozen_before_round": True,
        "real_data_used_for_fit_or_threshold": False,
        "quality_threshold": QUALITY_THRESHOLD,
        "calibration": "First 120 s of R3-B1; all other conditions share this calibration.",
        "condition_order": ["R3_B1", "R3_B3", "R3_B2", "R3_B4", "R3_B5"],
        "files": {stage: {"path": str(path), "sha256": sha256_file(path), **transport[stage]} for stage, path in FILES.items()},
        "detection": detection,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"condition_summary": condition_summary, "detection": detection, "transport": transport}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
