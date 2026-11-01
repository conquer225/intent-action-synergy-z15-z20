"""Bounded nested participant selection on frozen SEED fixed-cap covariance features."""

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, balanced_accuracy_score, f1_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .emotion_baseline import sha256


HERE = Path(__file__).parent
INITIAL = HERE / "output/seed_fixed8_initial_20260926"
OUTPUT = HERE / "output/seed_fixed8_nested_20260926"
CANDIDATES = ("lda_auto", "lda_0.1", "lda_0.5", "logistic_0.1", "logistic_1")


def model_for(name):
    if name.startswith("lda_"):
        shrinkage = name.split("_", 1)[1]
        classifier = LinearDiscriminantAnalysis(solver="lsqr", priors=[1/3] * 3,
            shrinkage="auto" if shrinkage == "auto" else float(shrinkage))
    else:
        classifier = LogisticRegression(C=float(name.split("_", 1)[1]),
            class_weight="balanced", max_iter=2000, tol=1e-5)
    return make_pipeline(StandardScaler(), classifier)


def nested_splits(groups, heldout):
    outer_train = np.flatnonzero(groups != heldout)
    splits = []
    for train, valid in GroupKFold(n_splits=3).split(outer_train, groups=groups[outer_train]):
        splits.append((outer_train[train], outer_train[valid]))
    return outer_train, np.flatnonzero(groups == heldout), splits


def participant_score(target, prediction, groups):
    return {int(s): float(balanced_accuracy_score(target[groups == s], prediction[groups == s]))
            for s in np.unique(groups)}


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    if (OUTPUT / "results.json").exists():
        raise FileExistsError("Nested experiment already complete")
    original = json.loads((INITIAL / "results.json").read_text())
    feature_path = INITIAL / "features.npz"
    if sha256(feature_path) != original["hashes"][str(feature_path)]:
        raise ValueError("Feature hash differs from baseline")
    data = dict(np.load(feature_path, allow_pickle=False))
    x, y, keys = data["logcov"], data["targets"], data["keys"]
    groups = keys[:, 0]
    if set(groups) != set(range(1, 16)):
        raise ValueError("Expected exactly fifteen participants")
    all_splits = {s: nested_splits(groups, s) for s in range(1, 16)}
    protocol = {
        "hypothesis": "Training-participant-only selection improves over fixed logcov LDA",
        "montage": original["montage"], "candidates": CANDIDATES,
        "outer": "15-participant LOSO; all three sessions held out together",
        "inner": "GroupKFold(3) on remaining 14 people; score equals mean of 14 participant balanced accuracies",
        "preprocessing": "frozen original features; StandardScaler fitted only inside each training fold",
        "budget": "5 candidates x 3 inner folds x 15 outer folds +15 final refits; no grid expansion",
        "randomness": "deterministic linear solvers; bootstrap seed 20260926",
        "tie_break": "first candidate in fixed order",
        "acceptance": "mean paired gain >=.02 and participant bootstrap 95% lower bound >0",
        "limitation": "features and candidate families chosen after prior LOSO exploration on these people; nested parameter selection does not undo that reuse; not independent confirmation or wearer accuracy",
        "splits": {str(s): {"test": [s], "inner": [
            {"train": np.unique(groups[a]).tolist(), "validation": np.unique(groups[b]).tolist()}
            for a, b in splits[2]]} for s, splits in all_splits.items()},
    }
    (OUTPUT / "protocol.json").write_text(json.dumps(protocol, indent=2), encoding="utf-8")
    started = datetime.now(timezone.utc).isoformat()
    scores, selection = [], []
    with (OUTPUT / "predictions.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["subject", "session", "trial", "window", "target", "prediction", "selected"])
        for subject, (train, test, inner) in all_splits.items():
            candidates = {}
            for name in CANDIDATES:
                by_subject = {}
                for a, b in inner:
                    prediction = model_for(name).fit(x[a], y[a]).predict(x[b])
                    by_subject.update(participant_score(y[b], prediction, groups[b]))
                if set(by_subject) != set(range(1, 16)) - {subject}:
                    raise ValueError("Inner participant coverage mismatch")
                candidates[name] = {"mean": float(np.mean(list(by_subject.values()))), "participants": by_subject}
            chosen = max(CANDIDATES, key=lambda name: candidates[name]["mean"])
            prediction = model_for(chosen).fit(x[train], y[train]).predict(x[test])
            score = {"subject": subject, "selected": chosen, "windows": len(test),
                "balanced_accuracy": balanced_accuracy_score(y[test], prediction),
                "accuracy": accuracy_score(y[test], prediction),
                "macro_f1": f1_score(y[test], prediction, average="macro")}
            scores.append(score)
            selection.append({"outer_subject": subject, "candidates": candidates, "chosen": chosen})
            writer.writerows((*map(int, k), int(t), int(p), chosen)
                             for k, t, p in zip(keys[test], y[test], prediction))
            stream.flush()
            print(f"OUTER {subject} selected={chosen} BA={score['balanced_accuracy']:.4f}", flush=True)
    (OUTPUT / "selection.json").write_text(json.dumps(selection, indent=2), encoding="utf-8")
    values = np.array([s["balanced_accuracy"] for s in scores])
    baseline = np.array([s["balanced_accuracy"] for s in original["methods"]["logcov_lda"]["participants"]])
    difference = values - baseline
    rng = np.random.default_rng(20260926)
    draws = rng.integers(0, 15, (20000, 15))
    interval = np.quantile(difference[draws].mean(axis=1), [.025, .975])
    report = {"status": "complete exploratory nested selection; no deployment",
        "started_utc": started, "completed_utc": datetime.now(timezone.utc).isoformat(),
        "participants": scores, "mean_subject_balanced_accuracy": values.mean(),
        "mean_subject_accuracy": float(np.mean([s["accuracy"] for s in scores])),
        "mean_subject_macro_f1": float(np.mean([s["macro_f1"] for s in scores])),
        "balanced_accuracy_ci95": np.quantile(values[draws].mean(axis=1), [.025, .975]).tolist(),
        "paired_gain": difference.mean(), "paired_gain_ci95": interval.tolist(),
        "accept": bool(difference.mean() >= .02 and interval[0] > 0),
        "software": original["software"],
        "hashes": {str(p): sha256(p) for p in [Path(__file__), feature_path, INITIAL / "results.json",
            OUTPUT / "protocol.json", OUTPUT / "selection.json", OUTPUT / "predictions.csv"]}}
    (OUTPUT / "results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("COMPLETE", report["mean_subject_balanced_accuracy"], "gain", report["paired_gain"], "accept", report["accept"], flush=True)


if __name__ == "__main__":
    main()
