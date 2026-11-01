"""Fit and export the mask-augmented GAMEEMO model used by the Z15 ARM service."""

import argparse
import json
from pathlib import Path

import numpy as np
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.preprocessing import StandardScaler

from gameemo_8ch_baseline import CHANNELS_8, DEFAULT_DATA, GAME_LABELS, discover_records
from gameemo_contact_robustness import (
    BANDS_HZ, SAMPLE_RATE_HZ, WINDOW_SECONDS, extract_features, load_windows,
    mask_augment,
)

DEFAULT_OUTPUT = Path(__file__).parents[1] / "pynq_guardianloop" / "gameemo_emotion_model.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    records = discover_records(args.data)
    windows, target, _, _ = load_windows(records)
    features = extract_features(windows)
    feature_median = np.median(features, axis=0)
    augmented_x, augmented_y = mask_augment(features, target, feature_median, 20260922)
    scaler = StandardScaler().fit(features)
    classifier = LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto")
    classifier.fit(scaler.transform(augmented_x), augmented_y)
    score = scaler.transform(features) @ classifier.coef_.T + classifier.intercept_
    exported_prediction = classifier.classes_[np.argmax(score, axis=1)]
    agreement = float(np.mean(exported_prediction == classifier.predict(scaler.transform(features))))
    if agreement != 1.0:
        raise RuntimeError(f"export formula mismatch: {agreement}")
    payload = {
        "model": "GAMEEMO_maskaug_scaler_LDA",
        "deployment_status": "cross-dataset prototype; requires Cyton personal calibration",
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "window_seconds": WINDOW_SECONDS,
        "channels": list(CHANNELS_8),
        "bands_hz": [list(item) for item in BANDS_HZ],
        "classes": classifier.classes_.astype(int).tolist(),
        "class_names": [GAME_LABELS[index + 1]["name"] for index in classifier.classes_],
        "feature_median": feature_median.tolist(),
        "scaler_mean": scaler.mean_.tolist(),
        "scaler_scale": scaler.scale_.tolist(),
        "lda_coef": classifier.coef_.tolist(),
        "lda_intercept": classifier.intercept_.tolist(),
        "export_agreement": agreement,
        "training_windows": int(len(features)),
        "training_participants": 28,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote={args.output} agreement={agreement}")


if __name__ == "__main__":
    main()
