"""Export the trained six-channel sklearn SVM for NumPy-only ARM inference."""

import argparse
import hashlib
import json
from pathlib import Path

import joblib
import numpy as np


HERE = Path(__file__).resolve().parent
SOURCE = HERE / "output" / "gameemo_covariance_v1" / "six_channel_covariance_svm.joblib"
TARGET = HERE.parent / "pynq_guardianloop" / "gameemo_covariance_svm.npz"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--target", type=Path, default=TARGET)
    args = parser.parse_args()
    pipeline = joblib.load(args.source)
    scaler, svm = pipeline.steps[0][1], pipeline.steps[1][1]
    if (svm.kernel != "rbf" or svm.classes_.tolist() != [0, 1, 2, 3]
            or svm.support_vectors_.shape[1] != 105):
        raise ValueError("unexpected SVM model; export not supported")
    metadata = {
        "algorithm_version": "gameemo-6ch-covariance-rbfsvm-v1",
        "source_sha256": hashlib.sha256(args.source.read_bytes()).hexdigest(),
        "channels": ["F3", "F4", "T7", "T8", "O1", "O2"],
        "bands_hz": [[1, 4], [4, 8], [8, 13], [13, 30], [30, 43]],
        "window_seconds": 12,
        "class_names": ["boring", "calm", "horror", "funny"],
        "label_type": "GAMEEMO game condition, not self-reported emotion",
    }
    np.savez_compressed(args.target,
                        mean=scaler.mean_, scale=scaler.scale_,
                        support=svm.support_vectors_, dual=svm.dual_coef_,
                        intercept=svm.intercept_, counts=svm.n_support_,
                        classes=svm.classes_, gamma=np.float64(svm._gamma),
                        metadata=json.dumps(metadata, separators=(",", ":")))
    print(f"exported={args.target} sha256={hashlib.sha256(args.target.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    main()
