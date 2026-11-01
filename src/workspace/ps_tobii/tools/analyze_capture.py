"""Summarize actual probe CSV, including sample gaps hidden by USB error counts."""
import argparse
import csv
import json
from pathlib import Path
import statistics


def summarize(path, duration):
    with path.open(newline="") as file:
        rows = list(csv.DictReader(file))
    if len(rows) < 2 or duration <= 0:
        raise ValueError("At least two actual samples and a positive duration are required")
    timestamps = [int(r["timestamp_us"]) for r in rows]
    counters = [int(r["frame_counter"]) for r in rows]
    host = [float(r["elapsed_ms"]) for r in rows]
    dt = [b-a for a, b in zip(timestamps, timestamps[1:])]
    gaps = [b-a for a, b in zip(counters, counters[1:])]
    return {
        "run": path.stem, "samples": len(rows), "requested_seconds": duration,
        "gaze_hz": len(rows) / duration, "last_host_ms": host[-1],
        "timestamps_strictly_increasing": all(v > 0 for v in dt),
        "device_interval_us_median": statistics.median(dt),
        "device_interval_us_max": max(dt),
        "frame_counter_gap_events": sum(v > 1 for v in gaps),
        "frame_counter_missing_samples": sum(v - 1 for v in gaps if v > 1),
        "frame_counter_non_increasing": sum(v <= 0 for v in gaps),
        "host_interval_ms_max": max(b-a for a, b in zip(host, host[1:])),
        "combined_valid_count": sum(r["gaze_valid"] == "1" for r in rows),
        "left_detected_count": sum(r["eye_present_l"] == "1" for r in rows),
        "right_detected_count": sum(r["eye_present_r"] == "1" for r in rows),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path)
    parser.add_argument("--seconds", type=float, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = json.dumps(summarize(args.csv, args.seconds), indent=2) + "\n"
    if args.output:
        args.output.write_text(result, encoding="utf-8")
    print(result, end="")


if __name__ == "__main__":
    main()
