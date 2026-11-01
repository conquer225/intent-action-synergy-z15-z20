"""Decode to BGR memory only. No HDMI output or timing claims for display."""
import argparse
import json
from pathlib import Path
import resource
import time

import cv2
import numpy as np


def test(path):
    cap = cv2.VideoCapture(str(path), cv2.CAP_FFMPEG)
    if not cap.isOpened():
        raise RuntimeError("FFmpeg backend could not open " + str(path))
    metadata = {"width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                "source_fps": cap.get(cv2.CAP_PROP_FPS),
                "expected_frames": int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
                "fourcc": "".join(chr((int(cap.get(cv2.CAP_PROP_FOURCC)) >> (8 * n)) & 255) for n in range(4))}
    samples = []
    cpu_start = time.process_time()
    start = time.perf_counter()
    checksum = 0
    try:
        while True:
            if time.perf_counter() - start > 20:
                break
            a = time.perf_counter()
            ok, frame = cap.read()
            elapsed = time.perf_counter() - a
            if not ok:
                break
            if frame.shape != (metadata["height"], metadata["width"], 3):
                raise RuntimeError("Unexpected decoded frame shape")
            checksum += int(frame[0, 0, 0])
            samples.append(elapsed * 1000)
    finally:
        cap.release()
    wall = time.perf_counter() - start
    cpu = time.process_time() - cpu_start
    frames = len(samples)
    if not frames:
        raise RuntimeError("No frames decoded")
    return dict(metadata, path=str(path), frames=frames, wall_s=wall, cpu_s=cpu,
                complete=frames == metadata["expected_frames"],
                decoded_fps=frames / wall, frame_p50_ms=float(np.percentile(samples, 50)),
                frame_p95_ms=float(np.percentile(samples, 95)),
                frame_max_ms=max(samples), frames_over_33ms=sum(x > 1000 / 30 for x in samples),
                process_cpu_percent=cpu / wall * 100,
                peak_rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
                checksum=checksum, output="BGR memory, not HDMI", opencv_threads=cv2.getNumThreads())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", type=Path, nargs="+")
    args = parser.parse_args()
    for path in args.files:
        print(json.dumps(test(path), ensure_ascii=False), flush=True)
