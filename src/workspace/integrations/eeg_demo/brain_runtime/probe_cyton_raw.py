#!/usr/bin/env python3
"""Briefly measure Cyton serial framing and raw channel amplitudes."""

import argparse
import json
import os
import select
import termios
import time

import numpy as np
from scipy import signal

from cyton_guardianloop import configure_serial, decode_eeg_counts, write_command


def read_for(fd, seconds):
    end = time.monotonic() + seconds
    data = bytearray()
    while time.monotonic() < end:
        ready, _, _ = select.select([fd], [], [], min(0.25, end - time.monotonic()))
        if ready:
            data.extend(os.read(fd, 8192))
    return data


def parse_frames(data):
    frames = []
    index = 0
    skipped = 0
    while index + 33 <= len(data):
        if data[index] == 0xA0 and (data[index + 32] & 0xF0) == 0xC0:
            frames.append(data[index:index + 33])
            index += 33
        else:
            index += 1
            skipped += 1
    return frames, skipped


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="/dev/ttyUSB0")
    parser.add_argument("--seconds", type=float, default=8.0)
    parser.add_argument("--save-npz", default=None,
                        help="optional path for the unmodified sample counters and EEG counts")
    args = parser.parse_args()
    fd = os.open(args.port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    try:
        configure_serial(fd)
        write_command(fd, b"s")
        time.sleep(0.2)
        termios.tcflush(fd, termios.TCIFLUSH)
        write_command(fd, b"v")
        version = read_for(fd, 1.5).decode("ascii", errors="replace")
        termios.tcflush(fd, termios.TCIFLUSH)
        write_command(fd, b"?")
        settings = read_for(fd, 1.5).decode("ascii", errors="replace")
        termios.tcflush(fd, termios.TCIFLUSH)
        write_command(fd, b"b")
        read_for(fd, 1.0)
        raw = read_for(fd, args.seconds)
        write_command(fd, b"s")
    finally:
        os.close(fd)
    frames, skipped = parse_frames(raw)
    if not frames:
        print(json.dumps({"bytes": len(raw), "frames": 0, "version": version[-400:],
                          "settings": settings[-800:]}))
        return
    sequence = np.fromiter((frame[1] for frame in frames), dtype=np.int16)
    delta = (np.diff(sequence) & 0xFF)
    counts = np.stack([decode_eeg_counts(frame) for frame in frames]).astype(np.float64)
    if args.save_npz:
        np.savez_compressed(args.save_npz, sequence=sequence,
                            counts=counts.astype(np.int32), sample_rate_hz=250)
    uv = counts * (4_500_000.0 / 24.0 / (2**23 - 1))
    centered = uv - np.median(uv, axis=0)
    breaks = np.flatnonzero(delta != 1) + 1
    boundaries = np.r_[0, breaks, len(frames)]
    run = int(np.argmax(np.diff(boundaries)))
    continuous = uv[boundaries[run]:boundaries[run + 1]].copy()
    continuous -= np.median(continuous, axis=0)
    notch_b, notch_a = signal.iirnotch(50.0, 30.0, 250.0)
    filtered = signal.filtfilt(notch_b, notch_a, continuous, axis=0)
    band_sos = signal.butter(4, (1.0, 45.0), btype="bandpass", fs=250.0, output="sos")
    filtered = signal.sosfiltfilt(band_sos, filtered, axis=0)
    summary = {
        "duration_s": args.seconds,
        "bytes": len(raw),
        "frames": len(frames),
        "frames_per_second": round(len(frames) / args.seconds, 2),
        "skipped_bytes": skipped,
        "sequential_pairs": int(np.count_nonzero(delta == 1)),
        "gap_pairs": int(np.count_nonzero(delta > 1)),
        "duplicate_pairs": int(np.count_nonzero(delta == 0)),
        "sum_gap_sizes": int(np.sum(np.maximum(delta - 1, 0))),
        "longest_contiguous_frames": int(len(continuous)),
        "counter_first_last": [int(sequence[0]), int(sequence[-1])],
        "median_uv": np.round(np.median(uv, axis=0), 1).tolist(),
        "p99_centered_uv": np.round(np.quantile(np.abs(centered), 0.99, axis=0), 1).tolist(),
        "p99_gui_like_filtered_uv": np.round(np.quantile(np.abs(filtered), 0.99, axis=0), 1).tolist(),
        "version": version[-400:],
        "settings": settings[-1200:],
    }
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
