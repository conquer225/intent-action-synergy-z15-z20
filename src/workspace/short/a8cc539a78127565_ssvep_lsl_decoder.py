"""Read an OpenBCI LSL EEG stream and log five-target CCA decisions."""

from __future__ import annotations

import argparse
import json
import time
from collections import deque
from pathlib import Path

import numpy as np
from pylsl import StreamInlet, resolve_byprop
from scipy import signal

from ssvep_core import DEFAULT_FREQUENCIES, classify


def parse_channels(value: str) -> tuple[int, ...]:
    channels = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    if not channels or min(channels) < 0 or len(set(channels)) != len(channels):
        raise argparse.ArgumentTypeError("channels must be unique zero-based indexes")
    return channels


def filter_window(values: np.ndarray, sample_rate_hz: float) -> np.ndarray:
    notch_b, notch_a = signal.iirnotch(50.0, 30.0, fs=sample_rate_hz)
    band_sos = signal.butter(4, (5.0, 45.0), btype="bandpass", fs=sample_rate_hz, output="sos")
    filtered = signal.filtfilt(notch_b, notch_a, values, axis=1)
    return signal.sosfiltfilt(band_sos, filtered, axis=1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--channels", type=parse_channels, default=parse_channels("0,1,2,3,4,5,6,7"))
    parser.add_argument("--sample-rate", type=float, default=250.0)
    parser.add_argument("--window-seconds", type=float, default=1.0)
    parser.add_argument("--step-seconds", type=float, default=0.25)
    parser.add_argument("--minimum-score", type=float, default=0.0)
    parser.add_argument("--minimum-margin", type=float, default=0.0)
    parser.add_argument("--output", type=Path, default=Path("output/ssvep_cca_log.jsonl"))
    args = parser.parse_args()
    window_samples = int(round(args.sample_rate * args.window_seconds))
    step_samples = int(round(args.sample_rate * args.step_seconds))
    if window_samples < 32 or step_samples < 1:
        parser.error("window/step is too short")

    print("Waiting for an LSL stream with type=EEG ...", flush=True)
    streams = resolve_byprop("type", "EEG", timeout=10.0)
    if not streams:
        raise RuntimeError("No LSL EEG stream found")
    inlet = StreamInlet(streams[0], max_buflen=10)
    info = inlet.info()
    if info.channel_count() <= max(args.channels):
        raise RuntimeError(
            f"stream has {info.channel_count()} channels, requested index {max(args.channels)}"
        )
    print(
        f"Connected name={info.name()!r} nominal_srate={info.nominal_srate()} "
        f"channels={info.channel_count()}",
        flush=True,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    buffers = [deque(maxlen=window_samples) for _ in args.channels]
    since_decision = 0
    with args.output.open("a", encoding="utf-8") as log:
        while True:
            chunk, timestamps = inlet.pull_chunk(timeout=1.0, max_samples=step_samples * 2)
            if not chunk:
                continue
            array = np.asarray(chunk, dtype=np.float64)
            for position, channel in enumerate(args.channels):
                buffers[position].extend(array[:, channel].tolist())
            since_decision += len(chunk)
            if min(map(len, buffers)) < window_samples or since_decision < step_samples:
                continue
            since_decision = 0
            raw = np.asarray([tuple(buffer) for buffer in buffers], dtype=np.float64)
            filtered = filter_window(raw, args.sample_rate)
            result = classify(
                filtered,
                frequencies=DEFAULT_FREQUENCIES,
                sample_rate_hz=args.sample_rate,
                minimum_score=args.minimum_score,
                minimum_margin=args.minimum_margin,
            )
            record = {
                "wall_time": time.time(),
                "lsl_time": float(timestamps[-1]),
                "frequency_hz": result.frequency_hz,
                "target": result.target_index + 1,
                "score": result.score,
                "margin": result.margin,
                "accepted": result.accepted,
                "scores": result.scores.tolist(),
                "channels": list(args.channels),
                "window_samples": window_samples,
            }
            line = json.dumps(record, ensure_ascii=False)
            print(line, flush=True)
            log.write(line + "\n")
            log.flush()


if __name__ == "__main__":
    raise SystemExit(main())
