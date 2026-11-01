"""Exploratory subject-calibrated TRCA, five training blocks/one held-out block.

Adapted from the algorithm described by Nakanishi et al. (2018) and their
public TRCA-SSVEP MATLAB source. This is *not* calibration-free or a board model.
The only comparison is O1/O2 versus the exact existing fixed-eight cap.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from scipy.linalg import eigh

from ssvep_wang_fixed8 import DATASET, PROTOCOL, _filter_window, _load_subject


def _train_trca(train: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return dominant spatial filter and template for (trials, channels, time)."""
    centered = train - train.mean(axis=2, keepdims=True)
    n_trials, n_channels, samples = centered.shape
    if n_trials < 2 or samples < 4:
        raise ValueError("TRCA requires repeated time-aligned trials")
    s = np.zeros((n_channels, n_channels))
    for i in range(n_trials - 1):
        for j in range(i + 1, n_trials):
            s += centered[i] @ centered[j].T + centered[j] @ centered[i].T
    stacked = centered.transpose(1, 0, 2).reshape(n_channels, -1)
    q = stacked @ stacked.T
    # Fixed 1% diagonal loading only stabilizes near-collinear EEG channels.
    q += np.eye(n_channels) * (0.01 * np.trace(q) / n_channels)
    eigenvalues, eigenvectors = eigh(s, q)
    return eigenvectors[:, int(np.argmax(eigenvalues))], centered.mean(axis=0)


def _correlation(a: np.ndarray, b: np.ndarray) -> float:
    left = a.ravel() - np.mean(a)
    right = b.ravel() - np.mean(b)
    denominator = np.linalg.norm(left) * np.linalg.norm(right)
    return float(left @ right / denominator) if denominator else -1.0


def run(dataset: Path, protocol_path: Path) -> dict:
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    seconds = protocol["primary_task"]["window_seconds"]
    targets = np.array(protocol["primary_task"]["target_indices_zero_based"])
    montages = protocol["montages"]
    records = []
    for subject in protocol["evaluation_subjects_predeclared"]:
        # Shape: block, target, channel, sample. Blocks, never trials, define CV.
        all_trials = _load_subject(dataset / f"S{subject}.mat", protocol)
        data = _filter_window(all_trials, seconds, protocol).reshape(6, 40, 8, -1)
        for held_block in range(6):
            train_blocks = np.array([i for i in range(6) if i != held_block])
            for name, channels in montages.items():
                spatial = []
                templates = []
                for target in targets:
                    w, template = _train_trca(data[train_blocks, target][:, channels, :])
                    spatial.append(w)
                    templates.append(template)
                for target in targets:
                    test = data[held_block, target][channels]
                    scores = [_correlation(w @ test, w @ template)
                              for w, template in zip(spatial, templates)]
                    guess = int(targets[np.argmax(scores)])
                    records.append({"subject": subject, "held_block": held_block + 1,
                                    "target_index_1based": int(target + 1),
                                    "montage": name, "predicted_index_1based": guess + 1,
                                    "correct": int(guess == target)})
        print(f"S{subject}: calibrated block-CV scored", flush=True)
    per_subject = []
    for subject in protocol["evaluation_subjects_predeclared"]:
        entry = {"subject": subject}
        for name in montages:
            entry[name] = float(np.mean([r["correct"] for r in records
                                         if r["subject"] == subject and r["montage"] == name]))
        per_subject.append(entry)
    one = np.array([r["O1_O2"] for r in per_subject])
    eight = np.array([r["fixed_eight"] for r in per_subject])
    rng = np.random.default_rng(20260926)
    diffs = eight - one
    resamples = rng.integers(0, len(diffs), (10000, len(diffs)))
    ci = np.quantile(diffs[resamples].mean(axis=1), [0.025, 0.975]).tolist()
    return {
        "status": "exploratory_posthoc_not_confirmatory",
        "method": "Nakanishi-style TRCA with fixed 1% covariance diagonal loading and one 6-45Hz band",
        "comparison": "Exact same four frequencies, subject, training blocks and held-out block for both montages",
        "calibration": "5 labelled training trials for each of 4 targets per subject; one entire block held out",
        "per_subject": per_subject, "predictions": records,
        "summary": {"o1_o2_mean": float(one.mean()), "fixed_eight_mean": float(eight.mean()),
                    "paired_gain_mean": float(diffs.mean()), "paired_95pct_bootstrap_ci": ci,
                    "subjects_improved": int(np.count_nonzero(diffs > 0)),
                    "subjects_worsened": int(np.count_nonzero(diffs < 0))},
        "warning": "After-seeing-primary exploratory method. Subject-specific labels and calibration are required. Do not treat as cross-subject zero-calibration performance or deploy from this result."
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--protocol", type=Path, default=PROTOCOL)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.dataset, args.protocol)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
