"""Replay an official SEED-VIG recording through the real Z15 PL pipeline.

The dataset is 200 Hz; each non-overlapping eight-second window is resampled
to the 250 Hz / 2000-sample contract used by GuardianLoop.  Values are treated
as microvolts and converted to signed int16 at 0.01 uV/LSB.  Out-of-range
windows are marked transport-invalid and are never silently clipped.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
from scipy.signal import resample_poly


REFERENCE_DIR = Path(r"D:\ican\ican_fpga_project\software\pc_fatigue_reference")
if str(REFERENCE_DIR) not in sys.path:
    sys.path.insert(0, str(REFERENCE_DIR))

from fatigue_reference import DEFAULT_CHANNEL_NAMES_8, channel_indices, load_seedvig_subject
from validate_seedvig_loso import DEFAULT_DATASET_ROOT, discover_pairs
from lsl_to_pynq import send_window


def select_recording(dataset_root: Path, requested: str):
    pairs = discover_pairs(dataset_root)
    if not requested:
        return pairs[0]
    for item in pairs:
        if item[0] == requested:
            return item
    names = ", ".join(item[0] for item in pairs)
    raise SystemExit(f"Unknown recording {requested!r}. Available: {names}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, default=DEFAULT_DATASET_ROOT)
    parser.add_argument("--recording", default="1_20151124_noon_2")
    parser.add_argument("--url", default="http://192.168.2.99:9101")
    parser.add_argument("--start-window", type=int, default=0)
    parser.add_argument("--windows", type=int, default=24)
    parser.add_argument("--pace-seconds", type=float, default=0.4,
                        help="delay between windows; 0 sends as fast as the board accepts")
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()
    if args.start_window < 0 or args.windows <= 0 or args.pace_seconds < 0:
        raise SystemExit("Invalid window or pace argument")
    token = os.environ.get("GL_PYNQ_TOKEN", "")
    if len(token) < 16:
        raise SystemExit("Set GL_PYNQ_TOKEN to the same private value as window_server.py")

    name, raw_path, label_path = select_recording(args.dataset_root, args.recording)
    subject = load_seedvig_subject(raw_path, label_path)
    indices = channel_indices(subject.channel_names, DEFAULT_CHANNEL_NAMES_8)
    eeg = subject.eeg[:, indices]
    samples_per_window = subject.sample_rate_hz * subject.window_seconds
    available = min(len(subject.perclos), len(eeg) // samples_per_window)
    stop = min(available, args.start_window + args.windows)
    if args.start_window >= stop:
        raise SystemExit(f"Recording has only {available} complete windows")

    # Match the live sender's initial DC centering without modifying each later
    # window independently.
    first = eeg[args.start_window * samples_per_window:(args.start_window + 1) * samples_per_window]
    first_250 = resample_poly(first, 5, 4, axis=0)
    offsets = first_250[:25].mean(axis=0)
    print(f"SEEDVIG_REPLAY: recording={name} source_rate={subject.sample_rate_hz} "
          f"target_rate=250 channels={','.join(DEFAULT_CHANNEL_NAMES_8)}")
    print("CENTER_OFFSETS_UV: " + ", ".join(f"{value:.3f}" for value in offsets))

    sent = valid_transport = predictions = 0
    for window_index in range(args.start_window, stop):
        source = eeg[window_index * samples_per_window:(window_index + 1) * samples_per_window]
        target = resample_poly(source, 5, 4, axis=0)
        if target.shape != (2000, 8):
            raise RuntimeError(f"Unexpected resampled shape {target.shape}")
        units = np.rint((target - offsets) * 100.0)
        transport_ok = bool(np.all(np.isfinite(units)) and
                            np.all(units >= -32768) and np.all(units <= 32767))
        payload = units.astype(np.int16) if transport_ok else np.zeros((2000, 8), dtype=np.int16)
        reference = float(subject.perclos[window_index])
        result = send_window(args.url, token, payload, transport_ok, args.timeout,
                             source="seedvig_replay", reference_perclos=reference)
        sent += 1
        valid_transport += int(transport_ok)
        predictions += int(str(result.get("state", "")).upper() in ("NORMAL", "MILD", "SEVERE"))
        print("REPLAY_RESULT: " + json.dumps({
            "dataset_window": window_index,
            "reference_perclos": round(reference, 6),
            "transport_ok": transport_ok,
            "board": result,
        }, ensure_ascii=False, sort_keys=True), flush=True)
        if args.pace_seconds:
            time.sleep(args.pace_seconds)

    print(f"SEEDVIG_REPLAY_COMPLETE: sent={sent} transport_valid={valid_transport} "
          f"predictions={predictions}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
