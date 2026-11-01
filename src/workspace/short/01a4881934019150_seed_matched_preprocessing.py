"""Frozen LOSO comparison of SEED features with the actual board conditioning code."""
import csv
import json
import platform
import sys
import time
from pathlib import Path

import numpy as np
import scipy
import sklearn
from scipy import signal
from scipy.io import loadmat
from sklearn.metrics import accuracy_score, balanced_accuracy_score, f1_score
from threadpoolctl import threadpool_limits

from .emotion_baseline import sha256
from .seed_causal_normalization import past_center
from .seed_covariance_diagnosis import INITIAL, model_for
from .seed_fixed8_experiment import INDICES, extract_trial, trial_names

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pynq_guardianloop"))
from seed_replay_check import CausalResampler
from cyton_sqi import CausalEEGFilter

OUTPUT = Path(__file__).parent / "output/seed_matched_preprocessing_20260926"


def to_simulated_250(raw):
    """Causal 5/4 interpolation for this experiment, NOT recovered raw Cyton."""
    up = np.zeros((len(raw)*5, 8))
    up[::5] = raw
    taps = 5 * signal.firwin(101, .2, window=("kaiser", 5))
    return signal.lfilter(taps, [1.], up, axis=0)[::4]


def matched_features(raw):
    simulated = to_simulated_250(raw)
    control = CausalResampler().process(simulated)[:len(raw)]
    conditioned = CausalEEGFilter().process(simulated)
    matched = CausalResampler().process(conditioned)[:len(raw)]
    return extract_trial(control.T)[1], extract_trial(matched.T)[1]


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    if (OUTPUT / "protocol.json").exists():
        raise FileExistsError("Preserve existing experiment; use a new explicit output for reruns")
    started = time.time()
    original = json.loads((INITIAL / "results.json").read_text())
    source_manifest = json.loads((INITIAL / "manifest.json").read_text())
    feature_path = INITIAL / "features.npz"
    assert sha256(feature_path) == original["hashes"][str(feature_path)]
    data = dict(np.load(feature_path, allow_pickle=False))
    protocol = {"hypothesis": "past-only adaptation gain survives matched board conditioning; matched retraining avoids train/test preprocessing shift",
        "montage": source_manifest["montage"], "folds": source_manifest["folds"],
        "model": "unchanged StandardScaler(training-only), equal-prior auto-shrinkage LDA, no hyperparameter search",
        "pipeline": "SEED200 -> causal synthetic250 -> board CausalEEGFilter (50Hz Q5 + fourth-order1-45Hz, first-value subtraction) -> board causal4/5 resampler -> original five-band feature extraction",
        "control": "same causal200->250->200 roundtrip without CausalEEGFilter",
        "windows": "identical original keys/labels, 2s per-trial warmup, 12s nonoverlap; first5 session windows excluded everywhere",
        "delay": "synthetic interpolation50ms plus board downsampling50ms; causal delayed support, no future correction; same nominal window indices",
        "state": "continuous within each trial, reset at unavailable inter-trial gaps; adaptive feature mean persists within session",
        "primary_tests": {"matched_adapt_minus_matched_plain": "gain>=.02 and simultaneous bootstrap lower>0",
            "matched_adapt_minus_original_adapt": "retention: lower simultaneous paired CI > -.02 (two-point noninferiority margin)"},
        "statistics": "15 participant pairs; bootstrap20000 seed20260926; 97.5% individual intervals for two primary comparisons",
        "budget": "5 methods x15 fits, no target-label tuning; deterministic models",
        "limitations": ["SEED upstream0-75Hz preprocessing and reference not undone", "synthetic interpolation cannot simulate real Cyton ADC/electrode effects",
            "missing rest periods prevent full-session continuous raw filtering", "same exploratory cohort as model discovery", "no SQI gating or accuracy claim on wearer"],
        "software": {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__, "sklearn": sklearn.__version__},
        "source_hashes": {str(p): sha256(p) for p in [Path(__file__), feature_path, INITIAL / "manifest.json",
            Path(__file__).parent / "seed_fixed8_experiment.py", Path(__file__).parent / "seed_causal_normalization.py",
            Path(__file__).parent / "seed_covariance_diagnosis.py", ROOT / "pynq_guardianloop/seed_replay_check.py", ROOT / "pynq_guardianloop/cyton_sqi.py"]}}
    (OUTPUT / "protocol.json").write_text(json.dumps(protocol, indent=2), encoding="utf-8")
    controls, matched, keys, targets = [], [], [], []
    with threadpool_limits(limits=2):
        for record in source_manifest["records"]:
            path = Path(record["path"])
            if sha256(path) != record["sha256"]:
                raise ValueError("Source changed: " + str(path))
            content = loadmat(path)
            for trial, name in enumerate(trial_names(content), 1):
                raw = np.asarray(content[name][list(INDICES)], dtype=float).T
                control, features = matched_features(raw)
                controls.append(control); matched.append(features)
                keys.extend((record["subject"], int(record["session"]), trial, w) for w in range(len(features)))
                targets.extend([source_manifest["labels"][trial-1]] * len(features))
            print("EXTRACTED", path.name, round(time.time()-started, 1), flush=True)
    keys, y = np.asarray(keys), np.asarray(targets)
    np.testing.assert_array_equal(keys, data["keys"])
    np.testing.assert_array_equal(y, data["targets"])
    features = {"original": data["logcov"], "roundtrip": np.concatenate(controls), "matched": np.concatenate(matched)}
    assert all(np.isfinite(v).all() for v in features.values())
    np.savez_compressed(OUTPUT / "features.npz", **features, keys=keys, targets=y)
    adapted = {name: np.empty_like(x) for name, x in features.items()}
    eligible = np.ones(len(y), dtype=bool)
    for subject, session in np.unique(keys[:, :2], axis=0):
        idx = np.flatnonzero((keys[:, 0] == subject) & (keys[:, 1] == session))
        idx = idx[np.lexsort((keys[idx, 3], keys[idx, 2]))]
        eligible[idx[:5]] = False
        for name, x in features.items():
            adapted[name][idx] = past_center(x[idx], "expanding")
    methods = {"original_adapt": (adapted["original"], adapted["original"]),
        "roundtrip_adapt": (adapted["roundtrip"], adapted["roundtrip"]),
        "matched_plain": (features["matched"], features["matched"]),
        "matched_adapt": (adapted["matched"], adapted["matched"]),
        "old_model_new_processing": (adapted["original"], adapted["matched"])}
    reports = {}
    with (OUTPUT / "predictions.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["method", "subject", "session", "trial", "window", "target", "prediction"])
        for name, (train_x, test_x) in methods.items():
            scores = []
            for subject in range(1,16):
                train, test = eligible & (keys[:,0] != subject), eligible & (keys[:,0] == subject)
                with threadpool_limits(limits=2):
                    prediction = model_for("lda").fit(train_x[train], y[train]).predict(test_x[test])
                scores.append({"subject": subject, "balanced_accuracy": float(balanced_accuracy_score(y[test], prediction)),
                    "accuracy": float(accuracy_score(y[test], prediction)), "macro_f1": float(f1_score(y[test], prediction, average="macro"))})
                writer.writerows([name,*key,target,pred] for key,target,pred in zip(keys[test],y[test],prediction))
            reports[name] = {"participants": scores, "mean_balanced_accuracy": float(np.mean([s["balanced_accuracy"] for s in scores]))}
            print("RESULT", name, reports[name]["mean_balanced_accuracy"], flush=True)
    values = {name: np.array([p["balanced_accuracy"] for p in r["participants"]]) for name,r in reports.items()}
    draws = np.random.default_rng(20260926).integers(0,15,(20000,15))
    comparisons = {}
    for control in ("matched_plain", "original_adapt"):
        difference = values["matched_adapt"] - values[control]
        interval = np.quantile(difference[draws].mean(axis=1), [.0125,.9875])
        comparisons[control] = {"mean_gain": float(difference.mean()), "paired_ci975": interval.tolist(),
            "passes": bool(difference.mean() >= .02 and interval[0] > 0) if control == "matched_plain" else bool(interval[0] > -.02)}
    report = {"methods": reports, "primary_comparisons": comparisons, "eligible_windows": int(eligible.sum()),
        "elapsed_seconds": time.time()-started, "board_changed": False,
        "hashes": {str(p): sha256(p) for p in [OUTPUT / "protocol.json", OUTPUT / "features.npz", OUTPUT / "predictions.csv"]}}
    (OUTPUT / "results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("COMPARISONS", comparisons, flush=True)


if __name__ == "__main__":
    main()
