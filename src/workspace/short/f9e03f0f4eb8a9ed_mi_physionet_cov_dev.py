#!/usr/bin/env python3
"""Development-only frequency-band spatial-covariance MI baseline (subjects 1..89)."""

import json
import sys
from fractions import Fraction
from pathlib import Path

import mne
import numpy as np
from scipy import signal

from mi_physionet_evaluate import bootstrap_ci, evaluate_model


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "pynq_guardianloop"))
from cyton_covariance import log_covariance  # noqa: E402
from cyton_sqi import CausalEEGFilter  # noqa: E402
from mi_features import CHANNELS, RATE_HZ, WINDOW_SAMPLES  # noqa: E402


DATA = Path(r"D:\ican\datasets\EEGMMIDB")
OUT = HERE / "output" / "mi_physionet_cov_dev_v3"
BANDS = ((8, 12), (18, 26))


def trial_features(path):
    raw = mne.io.read_raw_edf(path, preload=False, verbose="ERROR")
    original_rate = int(raw.info["sfreq"])
    if original_rate not in (128, 160):
        raise ValueError(f"unexpected rate: {path}")
    names = [name.rstrip(".").upper() for name in raw.ch_names]
    picks = [names.index(name) for name in CHANNELS]
    ratio = Fraction(RATE_HZ, original_rate)
    input_uv = signal.resample_poly(raw.get_data(picks=picks).T * 1e6,
                                    ratio.numerator, ratio.denominator, axis=0)
    conditioned = CausalEEGFilter(sample_rate_hz=RATE_HZ).process(input_uv)
    filtered = [signal.sosfilt(signal.butter(4, band, fs=RATE_HZ,
                                              btype="bandpass", output="sos"),
                               conditioned, axis=0) for band in BANDS]
    all_features = {"C3_C4": [], "FIXED_EIGHT": []}
    labels = []
    for annotation in raw.annotations:
        if annotation["description"] not in ("T1", "T2") or annotation["duration"] < 3.5:
            continue
        start = int(round((annotation["onset"] + .5) * RATE_HZ))
        segments = [band[start:start + WINDOW_SAMPLES] for band in filtered]
        if any(len(segment) != WINDOW_SAMPLES for segment in segments):
            continue
        all_features["C3_C4"].append(np.concatenate([
            log_covariance(segment[:, [2, 3]]) for segment in segments]))
        all_features["FIXED_EIGHT"].append(np.concatenate([
            log_covariance(segment) for segment in segments]))
        labels.append(0 if annotation["description"] == "T1" else 1)
    if not labels:
        raise ValueError(f"no trials: {path}")
    return all_features, labels


def main():
    features = {"C3_C4": [], "FIXED_EIGHT": []}
    labels, subjects = [], []
    for subject in range(1, 90):
        for run in (4, 8, 12):
            path = DATA / f"S{subject:03d}" / f"S{subject:03d}R{run:02d}.edf"
            x, y = trial_features(path)
            for name in features:
                features[name].extend(x[name])
            labels.extend(y)
            subjects.extend([subject] * len(y))
    y = np.asarray(labels)
    group = np.asarray(subjects)
    train, validation = group <= 70, group >= 71
    report = {}
    for name, feature_rows in features.items():
        x = np.asarray(feature_rows)
        per_subject, _, _, _ = evaluate_model(x[train], y[train], x[validation],
                                               y[validation], group[validation],
                                               list(range(x.shape[1])))
        values = [row["balanced_accuracy"] for row in per_subject]
        report[name] = {"mean_subject_balanced_accuracy": float(np.mean(values)),
                        "subject_bootstrap_95_ci": bootstrap_ci(values, 20260930),
                        "per_subject": per_subject}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "development_only.json").write_text(json.dumps({
        "feature": "two-band log covariance on full-record causal filters",
        "bands_hz": BANDS, "train_subjects": [1, 70],
        "validation_subjects": [71, 89], "test_subjects_touched": False,
        "results": report,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print({name: value["mean_subject_balanced_accuracy"] for name, value in report.items()})


if __name__ == "__main__":
    main()
