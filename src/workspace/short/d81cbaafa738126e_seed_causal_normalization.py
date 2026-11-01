"""Past-only session drift correction, evaluated after identical 60 s warmup."""

import csv
import json
from pathlib import Path

import numpy as np
from sklearn.metrics import balanced_accuracy_score, f1_score
from threadpoolctl import threadpool_limits

from .emotion_baseline import sha256
from .seed_covariance_diagnosis import INITIAL, model_for

OUTPUT = Path(__file__).parent / "output/seed_causal_normalization_20260926"


def past_center(features, mode, prefix=5):
    if len(features) <= prefix:
        raise ValueError("Need calibration and prediction windows")
    reference = features[:prefix].mean(axis=0)
    result = np.zeros_like(features)
    for index in range(prefix, len(features)):
        result[index] = features[index] - reference
        if mode == "expanding":
            reference += (features[index] - reference) / (index + 1)
        elif mode == "ema":
            reference += .04 * (features[index] - reference)
        elif mode != "fixed":
            raise ValueError(mode)
    return result


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    if (OUTPUT / "results.json").exists():
        raise FileExistsError("Experiment already complete")
    original = json.loads((INITIAL / "results.json").read_text())
    feature_path = INITIAL / "features.npz"
    assert sha256(feature_path) == original["hashes"][str(feature_path)]
    data = dict(np.load(feature_path, allow_pickle=False))
    x, keys, y = data["logcov"], data["keys"], data["targets"]
    protocol = {"montage": original["montage"],
        "methods": ["expanding_lda", "ema_lda", "fixed_rbf"],
        "hypothesis": "causal ongoing centering reduces drift, or nonlinear boundary improves prefix-normalized data",
        "reference": "first5 windows; expanding or alpha=.04 updates AFTER producing each feature; fixed has no updates",
        "evaluation": "same 12105 windows and 15 LOSO as prefix experiment; no target labels or future EEG",
        "baseline": "previous fixed-prefix LDA, not the weaker unadapted baseline",
        "acceptance": "gain >=.02 over fixed-prefix LDA and three-comparison simultaneous bootstrap lower >0",
        "caveat": "same shared film order; exploratory sequential model selection on reused cohort; not independent validation",
        "budget": "45 fits, no parameter search, no deployment"}
    (OUTPUT / "protocol.json").write_text(json.dumps(protocol, indent=2), encoding="utf-8")
    features = {mode: np.empty_like(x) for mode in ("expanding", "ema", "fixed")}
    eligible = np.ones(len(x), dtype=bool)
    for subject, session in np.unique(keys[:, :2], axis=0):
        indices = np.flatnonzero((keys[:, 0] == subject) & (keys[:, 1] == session))
        indices = indices[np.lexsort((keys[indices, 3], keys[indices, 2]))]
        eligible[indices[:5]] = False
        for mode in features:
            features[mode][indices] = past_center(x[indices], mode)
    reference_path = OUTPUT.parent / "seed_prefix_alignment_20260926/results.json"
    previous = json.loads(reference_path.read_text())["methods"]["prefix_center"]["participants"]
    baseline = np.array([v["balanced_accuracy"] for v in previous])
    draws = np.random.default_rng(20260926).integers(0, 15, (20000, 15))
    results = {}
    with (OUTPUT / "predictions.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["method", "subject", "session", "trial", "window", "target", "prediction"])
        for method in protocol["methods"]:
            mode, classifier = method.split("_")
            x_current = features[mode]
            scores = []
            for subject in range(1, 16):
                train = eligible & (keys[:, 0] != subject)
                test = eligible & (keys[:, 0] == subject)
                with threadpool_limits(limits=2):
                    prediction = model_for(classifier).fit(x_current[train], y[train]).predict(x_current[test])
                scores.append({"subject": subject, "balanced_accuracy": float(balanced_accuracy_score(y[test], prediction)),
                               "macro_f1": float(f1_score(y[test], prediction, average="macro"))})
                writer.writerows([method, *key, target, pred] for key, target, pred in zip(keys[test], y[test], prediction))
                f.flush()
                print(method, subject, scores[-1]["balanced_accuracy"], flush=True)
            values = np.array([s["balanced_accuracy"] for s in scores])
            difference = values - baseline
            ci = np.quantile(difference[draws].mean(axis=1), [.05/6, 1-.05/6])
            results[method] = {"participants": scores, "mean_balanced_accuracy": float(values.mean()),
                "paired_gain_over_prefix": float(difference.mean()), "paired_simultaneous_ci": ci.tolist(),
                "accept_exploratory": bool(difference.mean() >= .02 and ci[0] > 0)}
            print("SUMMARY", method, results[method]["mean_balanced_accuracy"], ci, flush=True)
    (OUTPUT / "results.json").write_text(json.dumps({"methods": results, "deployment": "unchanged",
        "hashes": {str(p): sha256(p) for p in [Path(__file__), feature_path, reference_path,
                    OUTPUT / "protocol.json", OUTPUT / "predictions.csv"]}}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
