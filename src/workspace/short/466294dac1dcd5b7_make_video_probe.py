"""Generate synthetic H.264 samples with already installed Windows Media Foundation."""
import argparse
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np


def create(folder, width, height):
    path = folder / (str(height) + "p30_h264.mp4")
    if path.exists():
        raise FileExistsError(path)
    frames = 180
    writer = cv2.VideoWriter(str(path), cv2.CAP_MSMF, cv2.VideoWriter_fourcc(*"H264"), 30, (width, height))
    if not writer.isOpened():
        raise RuntimeError("Existing Windows H.264 encoder unavailable; no dependencies were installed")
    y, x = np.indices((height, width))
    rng = np.random.default_rng(32)
    texture = rng.integers(0, 256, (height // 6, width // 4, 3), dtype=np.uint8)
    frame = np.empty((height, width, 3), np.uint8)
    try:
        for i in range(frames):
            frame[..., 0] = (x + i * 4) % 256
            frame[..., 1] = (y + i * 3) % 256
            frame[..., 2] = ((x // 40 + y // 40 + i // 5) % 2) * 180 + 40
            # Translating a fixed texture exercises motion prediction, not random-noise bitrate.
            frame[height // 2:height // 2 + height // 6, :width // 4] = np.roll(texture, i % 32, axis=1)
            cv2.putText(frame, "SYNTHETIC VIDEO TEST " + str(i), (50, 80), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            writer.write(frame)
    finally:
        writer.release()
    cap = cv2.VideoCapture(str(path), cv2.CAP_FFMPEG)
    code = int(cap.get(cv2.CAP_PROP_FOURCC))
    fourcc = "".join(chr((code >> (8 * n)) & 255) for n in range(4))
    count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    if count != frames or fourcc.lower() not in {"avc1", "h264"}:
        raise RuntimeError("Generated sample is not the expected complete H.264 stream")
    return {"path": str(path), "resolution": [width, height], "fps": 30, "frames": frames,
            "fourcc": fourcc, "bytes": path.stat().st_size,
            "average_mbps": path.stat().st_size * 8 / (frames / 30) / 1e6,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "source": "synthetic gradient/checkerboard/moving texture, no phone capture"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()
    args.folder.mkdir(parents=True, exist_ok=False)
    results = [create(args.folder, width, height) for width, height in [(1280, 720), (1920, 1080)]]
    (args.folder / "samples.json").write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))
