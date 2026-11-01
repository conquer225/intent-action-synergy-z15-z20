"""Prepare immutable recorded-data replay and causal chunking checks."""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from scipy.io import loadmat

from .seed_fixed8_experiment import INDICES, extract_trial, trial_names

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "eeg_apps_z15/output/seed_recorded_replay_20260926"
sys.path.insert(0, str(ROOT / "pynq_guardianloop"))
from seed_replay_check import CausalResampler, FeatureStream, replay


def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    raw_path = Path(r"C:\Users\lenovo\Documents\OpenBCI_GUI\Recordings\OpenBCISession_2026-09-23_18-57-41\OpenBCI-RAW-2026-09-23_18-59-07.txt")
    seed_path = Path(r"D:\ican\datasets\SEED\SEED\Preprocessed_EEG\1_20131027.mat")
    raw = np.loadtxt(raw_path, delimiter=",", skiprows=5, usecols=range(9))
    steps = np.diff(raw[:, 0].astype(int)) % 256
    boundaries = np.r_[0, np.flatnonzero(steps != 1) + 1, len(raw)]
    chosen = int(np.argmax(np.diff(boundaries)))
    begin, end = int(boundaries[chosen]), int(boundaries[chosen + 1])
    cyton = raw[begin:end, 1:9]
    mat = loadmat(seed_path)
    name = trial_names(mat)[0]
    seed = mat[name][list(INDICES), :16000].T.astype(float)
    assert np.isfinite(cyton).all() and np.isfinite(seed).all()
    np.savez(OUTPUT / "input.npz", cyton=cyton, seed=seed)
    expected = extract_trial(seed.T)[1]
    stream = FeatureStream()
    collected = []
    for start in range(0, len(seed), 37):
        collected.extend(stream.process(seed[start:start+37]))
    error = float(np.max(np.abs(np.asarray(collected)-expected)))
    np.testing.assert_allclose(collected, expected, atol=1e-9, rtol=1e-9)
    batch = CausalResampler().process(cyton)
    resampler = CausalResampler()
    chunked = np.concatenate([resampler.process(cyton[i:i+37]) for i in range(0,len(cyton),37)])
    np.testing.assert_allclose(batch, chunked, atol=1e-9, rtol=1e-9)
    prefix = CausalResampler().process(cyton[:1000])
    np.testing.assert_allclose(batch[:len(prefix)], prefix, atol=1e-12)
    weights = dict(np.load(ROOT / "eeg_apps_z15/output/seed_causal_candidate_20260926/linear_weights.npz"))
    features, _, _ = replay(cyton, weights, 250, chunks=37)
    reference, _, _ = replay(cyton, weights, 250, chunks=250)
    np.testing.assert_allclose(features, reference, atol=1e-8, rtol=1e-8)
    manifest = {"source": str(raw_path), "source_hash": digest(raw_path),
        "seed_source": str(seed_path), "seed_hash": digest(seed_path), "seed_trial": name,
        "input_hash": digest(OUTPUT / "input.npz"), "sample_rate_header_hz": 250,
        "source_samples": len(raw), "gap_events": int(sum(steps != 1)),
        "estimated_missing_modulo256": int(np.sum((steps[steps != 1]-1)%256)),
        "selected_row_start": begin, "selected_row_end_exclusive": end,
        "selected_contiguous_seconds": len(cyton)/250,
        "montage": "F3 F4 C3 C4 T7 T8 O1 O2 (user-declared; recording header contains CH indices only)",
        "reference": "current code configures SRB2 on; physical historical reference cannot be proven from TXT",
        "seed_stream_vs_training_max_abs": error,
        "resample_chunk_invariance_max_abs": float(np.max(np.abs(batch-chunked))),
        "cyton_feature_chunk_invariance_max_abs": float(np.max(np.abs(features-reference))),
        "claims": "engineering parity only; no labels, no quality-gated emotion output"}
    (OUTPUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
