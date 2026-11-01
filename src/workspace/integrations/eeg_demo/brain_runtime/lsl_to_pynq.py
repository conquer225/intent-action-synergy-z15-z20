"""Forward eight-channel LSL EEG windows to the Z15 PYNQ GuardianLoop server.

The source-to-microvolt scale is explicit. Out-of-range samples quarantine the
whole window as INVALID; they are never silently clipped or sent to PL.
"""

import argparse
import json
import math
import os
from collections import deque
from urllib.request import Request, urlopen

import numpy as np


CHANNELS = 8
WINDOW_SAMPLES = 2000
FIRST_FRAME_SAMPLES = 25


def send_window(url, token, samples, transport_ok, timeout, source="lsl",
                reference_perclos=None):
    payload = np.asarray(samples, dtype="<i2").tobytes(order="C")
    if len(payload) != 32000:
        raise RuntimeError("Wrong window size before POST")
    headers = {"Content-Type": "application/octet-stream",
               "X-GuardianLoop-Token": token,
               "X-Transport-OK": "1" if transport_ok else "0",
               "X-GuardianLoop-Source": source}
    if reference_perclos is not None:
        headers["X-Reference-PERCLOS"] = f"{float(reference_perclos):.9f}"
    request = Request(url.rstrip("/") + "/window", data=payload, method="POST",
                      headers=headers)
    with urlopen(request, timeout=timeout) as reply:
        return json.load(reply)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://192.168.2.99:9101")
    parser.add_argument("--stream-name", default="obci_eeg1")
    parser.add_argument("--input-scale", type=float, required=True,
                        help="LSL value to microvolt multiplier, e.g. the existing 0.02")
    parser.add_argument("--center-first-frame", action="store_true")
    parser.add_argument("--windows", type=int, default=0,
                        help="0 means continue until Ctrl+C")
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()
    token = os.environ.get("GL_PYNQ_TOKEN", "")
    if len(token) < 16:
        raise SystemExit("Set GL_PYNQ_TOKEN to the same private value as on the Z15")
    if not math.isfinite(args.input_scale) or args.input_scale <= 0:
        raise SystemExit("--input-scale must be finite and positive")
    if args.windows < 0 or args.timeout <= 0:
        raise SystemExit("--windows must be >=0 and --timeout must be >0")

    from pylsl import StreamInlet, resolve_byprop

    streams = resolve_byprop("name", args.stream_name, timeout=5.0)
    if not streams:
        raise RuntimeError(f"LSL stream {args.stream_name!r} not found")
    info = streams[0]
    if info.channel_count() < CHANNELS or abs(info.nominal_srate() - 250.0) > 0.01:
        raise RuntimeError("Need at least 8 channels at nominal 250 Hz")
    inlet = StreamInlet(info, max_chunklen=25)
    print(f"LSL_CONNECTED: name={info.name()} channels={info.channel_count()} rate={info.nominal_srate()}")

    raw_first = []
    offsets = None
    rows = deque(maxlen=WINDOW_SAMPLES)
    bad_timestamps = deque(maxlen=WINDOW_SAMPLES)
    previous_timestamp = None
    new_samples = 0
    windows_sent = 0
    calibration_ready = False
    out_of_range_rows = 0
    timestamp_gaps = 0
    try:
        while args.windows == 0 or windows_sent < args.windows:
            sample, timestamp = inlet.pull_sample(timeout=1.0)
            if sample is None:
                continue
            if len(sample) < CHANNELS:
                raise RuntimeError("Short LSL sample; channel mapping changed")
            raw = np.asarray(sample[:CHANNELS], dtype=np.float64)
            if offsets is None and not np.all(np.isfinite(raw)):
                raw_first = []  # Need 25 consecutive finite samples for DC centering.
                continue
            if offsets is None:
                raw_first.append(raw)
                if len(raw_first) < FIRST_FRAME_SAMPLES:
                    continue
                offsets = np.stack(raw_first).mean(axis=0) if args.center_first_frame else np.zeros(CHANNELS)
                print("FIRST_FRAME_OFFSETS: " + ", ".join(f"{v:.3f}" for v in offsets))
                first_rows = raw_first
                raw_first = []
            else:
                first_rows = [raw]

            for raw_row in first_rows:
                microvolts = (raw_row - offsets) * args.input_scale
                units = np.rint(microvolts * 100.0)
                outside = bool(not np.all(np.isfinite(units)) or
                               np.any(units < -32768) or np.any(units > 32767))
                if outside:
                    # Placeholder is never processed: transport_ok=False skips DMA.
                    rows.append(np.zeros(CHANNELS, dtype=np.int16))
                    out_of_range_rows += 1
                else:
                    rows.append(units.astype(np.int16))
                gap = (previous_timestamp is not None and
                       float(timestamp) - previous_timestamp > 0.05)
                bad_timestamps.append(bool(gap or outside))
                if gap:
                    timestamp_gaps += 1
                previous_timestamp = float(timestamp)
                new_samples += 1
                hop = 500 if calibration_ready else WINDOW_SAMPLES
                if len(rows) < WINDOW_SAMPLES or new_samples < hop:
                    continue
                result = send_window(args.url, token, np.stack(rows),
                                     transport_ok=not any(bad_timestamps),
                                     timeout=args.timeout)
                windows_sent += 1
                new_samples = 0
                calibration_ready = bool(result.get("calibration_ready")) or calibration_ready
                if result.get("reason") == "TRANSPORT":
                    print(f"WINDOW_INPUT_INVALID: bad_rows_in_window={sum(bad_timestamps)} "
                          f"new_out_of_range_rows={out_of_range_rows} "
                          f"new_timestamp_gaps={timestamp_gaps}; no clipping/PL inference",
                          flush=True)
                out_of_range_rows = 0
                timestamp_gaps = 0
                print(f"PYNQ_RESULT: {json.dumps(result, sort_keys=True)}", flush=True)
    except KeyboardInterrupt:
        print("STOPPED_BY_USER")
    print(f"LSL_TO_PYNQ_COMPLETE: windows={windows_sent}")


if __name__ == "__main__":
    main()
