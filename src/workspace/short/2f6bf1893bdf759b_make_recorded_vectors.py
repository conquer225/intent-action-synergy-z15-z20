"""Generate a 3000-sample RTL gold vector from the existing Cyton recording."""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from scipy import signal

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "pynq_guardianloop"))
from cyton_sqi import CausalEEGFilter  # noqa: E402

TRACE = ROOT / "eeg_apps_z15/output/pl_integrated_candidate_20260929/recorded_input.npz"


def main():
    with np.load(TRACE, allow_pickle=False) as source:
        raw = np.asarray(source["recorded"], dtype=np.float64)
    six = CausalEEGFilter().process(raw)[:, (0, 1, 4, 5, 6, 7)]
    band = signal.sosfilt(signal.butter(4, (1, 4), fs=250,
                                           btype="bandpass", output="sos"), six, axis=0)
    q = np.rint(band[:3000] * 4).astype(np.int64)
    if np.any(q < -32768) or np.any(q > 32767):
        raise ValueError("test vector overflow")
    words = [sum((int(sample[c]) & 0xFFFF) << (16*c) for c in range(6)) for sample in q]
    sums = q.sum(axis=0, dtype=np.int64)
    gram = q.T @ q
    golden = [int(value) for value in sums]
    golden += [int(gram[i, j]) for i in range(6) for j in range(i, 6)]
    (HERE / "test_vectors.hex").write_text(
        "".join(f"{word:024x}\n" for word in words), encoding="ascii")
    (HERE / "golden.hex").write_text(
        "".join(f"{value & ((1 << 48) - 1):012x}\n" for value in golden), encoding="ascii")
    (HERE / "recorded_vector_manifest.json").write_text(json.dumps({
        "source": str(TRACE), "source_sha256": hashlib.sha256(TRACE.read_bytes()).hexdigest(),
        "samples": len(q), "channels": ["F3", "F4", "T7", "T8", "O1", "O2"],
        "band_hz": [1, 4], "integer_lsb_uv": 0.25, "golden_elements": 27,
        "max_abs_quantized": int(np.max(np.abs(q))),
    }, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
