"""Parity checks for the fixed-montage board fatigue inference path."""

import json
import sys
from pathlib import Path

import joblib
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "viformer_z15"))
sys.path.insert(0, str(Path(r"D:\ican\ican_fpga_project\software\pc_fatigue_reference")))

from cyton_fatigue import FourChannelDEStream, FourChannelFatigue
from fatigue_reference import channel_indices, load_seedvig_subject
from train_cyton_montage_fatigue import CHANNELS, preprocess


def main():
    output = ROOT / "viformer_z15" / "output" / "cyton_montage_fatigue_v2"
    portable = FourChannelFatigue(output / "cyton_fatigue_overlap4.json")
    sklearn = joblib.load(output / "overlap4_deployment_candidate.joblib")
    rng = np.random.default_rng(42)
    values = rng.normal(size=(200, 20))
    actual = np.asarray([portable._predict(row) for row in values])
    expected = np.clip(sklearn.predict(values), 0, 1)
    if not np.allclose(actual, expected, rtol=0, atol=1e-11):
        raise AssertionError("Board HGB predictor differs from sklearn")

    name = "1_20151124_noon_2"
    dataset = Path(r"D:\ican\seed-vig.zip\seed-vig")
    subject = load_seedvig_subject(dataset / "Raw_Data" / f"{name}.mat",
                                   dataset / "perclos_labels" / f"{name}.mat")
    filtered = preprocess(subject.eeg[:, channel_indices(subject.channel_names, CHANNELS)],
                          subject.sample_rate_hz)
    stream = FourChannelDEStream()
    cached = np.load(output / "feature_cache" / f"{name}.npz", allow_pickle=False)["features"]
    deviations = []
    for window in range(20):
        block = filtered[window * 2000:(window + 1) * 2000]
        # The stream accepts all eight physical positions; only four overlap.
        eight = np.zeros((2000, 8), dtype=np.float64)
        eight[:, 4:] = block
        for start in range(0, 2000, 125):
            stream.append(eight[start:start + 125])
        deviations.append(float(np.max(np.abs(stream.features() - cached[window]))))
    maximum = max(deviations)
    if maximum > 1e-8:
        raise AssertionError(f"Streaming DE differs from training: {maximum}")
    print(json.dumps({"HGB_max_abs": float(np.max(np.abs(actual - expected))),
                      "DE_max_abs": maximum, "windows": len(deviations)}))


if __name__ == "__main__":
    main()
