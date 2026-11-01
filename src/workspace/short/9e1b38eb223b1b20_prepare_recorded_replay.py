"""Prepare continuous real-recording frames for the isolated DMA board check."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from fixed_sos import FixedSOS, quantize

APP = HERE.parents[1]
SOS = APP / "output/pl_primary_filter_q31_20260927/sos_float.npy"
COEFF = APP / "output/pl_filter_v2025_2_20260927/coeff.hex"
DEFAULT_INPUT = APP / "output/seed_recorded_replay_20260926/input.npz"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(source, output, key="cyton", limit_frames=2023):
    output.mkdir(parents=True, exist_ok=False)
    with np.load(source) as archive:
        raw = np.asarray(archive[key], dtype=np.float64)
    if raw.ndim != 2 or raw.shape[1] != 8 or not np.isfinite(raw).all():
        raise ValueError("Expected finite 8-channel EEG rows")
    frames = min(len(raw) // 10, limit_frames)
    if not 2 <= frames <= 10000:
        raise ValueError("Need 2..10000 complete 10x8 frames")
    raw = raw[: frames * 10]
    sos = np.load(SOS)
    model = FixedSOS(sos)
    encoded = [int(word, 16) for word in COEFF.read_text().split()]
    expected = [int(word) & ((1 << 34) - 1) for row in model.coeff for word in row]
    if encoded != expected:
        raise ValueError("SOS coefficients differ from the implemented candidate")
    tx = quantize(raw - raw[0], 16, 40)
    golden = model.process_quantized(tx)
    if model.saturations:
        raise ValueError("Recorded input caused fixed-point saturation")
    split = FixedSOS(sos)
    replay = np.concatenate([split.process_quantized(part) for part in np.split(tx, frames)])
    np.testing.assert_array_equal(golden, replay)
    vector_path = output / "recorded_frames.bin"
    with vector_path.open("xb") as fp:
        fp.write(struct.pack("<8sII", b"GLDMA001", 1, frames))
        for index in range(frames):
            start = index * 10
            fp.write(tx[start : start + 10].astype("<i8", copy=False).tobytes())
            fp.write(golden[start : start + 10].astype("<i8", copy=False).tobytes())
    raw_path = output / "raw_uv.npy"
    np.save(raw_path, raw)
    proxy_path = output / "fixed_proxy_not_physical.bin"
    proxy_path.write_bytes(golden.astype("<i8", copy=False).tobytes())
    manifest = {
        "scope": "existing Cyton recording; continuous fixed-cap 8-channel segment; no label/accuracy claim",
        "source": str(source.resolve()), "source_sha256": digest(source), "key": key,
        "frames": frames, "samples": len(raw), "rate_hz": 250,
        "channel_order_assumed": ["F3", "F4", "C3", "C4", "T7", "T8", "O1", "O2"],
        "record_channel_positions_proven_by_file": False,
        "sample_zero_origin_for_entire_stream": True,
        "fixed_saturations": model.saturations,
        "sha256": {name: digest(path) for name, path in {
            "vectors": vector_path, "raw_uv": raw_path, "fixed_proxy_not_physical": proxy_path,
            "sos": SOS, "coeff": COEFF
        }.items()},
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"status": "RECORDED_REPLAY_PREPARED", "frames": frames,
                      "samples": len(raw), "vector_sha256": digest(vector_path)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--key", default="cyton")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit-frames", type=int, default=2023)
    args = parser.parse_args()
    prepare(args.source, args.output, args.key, args.limit_frames)
