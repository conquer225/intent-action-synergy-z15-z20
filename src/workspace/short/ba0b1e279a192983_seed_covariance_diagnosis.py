"""Fixed-budget, label-free feature ablations on the frozen SEED LOSO cohort."""

import csv
import json
import time
from pathlib import Path

import numpy as np
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.metrics import accuracy_score, balanced_accuracy_score, f1_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC
from threadpoolctl import threadpool_limits

from .emotion_baseline import sha256

HERE = Path(__file__).parent
INITIAL = HERE / "output/seed_fixed8_initial_20260926"
OUTPUT = HERE / "output/seed_covariance_diagnosis_20260926"


def remove_log_scale(features):
    """Remove each window/band log-determinant; no session or future statistics."""
    result = np.array(features, dtype=float, copy=True).reshape(-1, 5, 36)
    rows, cols = np.triu_indices(8)
    diagonal = rows == cols
    result[..., diagonal] -= result[..., diagonal].mean(axis=-1, keepdims=True)
    return result.reshape(len(features), -1)


def model_for(name):
    classifier = (SVC(C=1, kernel="rbf", gamma="scale", class_weight="balanced", cache_size=512)
                  if name.endswith("rbf") else
                  LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto", priors=[1/3]*3))
    return make_pipeline(StandardScaler(), classifier)


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    if (OUTPUT / "results.json").exists():
        raise FileExistsError("Do not overwrite completed experiment")
    baseline = json.loads((INITIAL / "results.json").read_text())
    feature_path = INITIAL / "features.npz"
    assert sha256(feature_path) == baseline["hashes"][str(feature_path)]
    data = dict(np.load(feature_path, allow_pickle=False))
    keys, y = data["keys"], data["targets"]
    methods = {"logcov_rbf": data["logcov"],
               "shape_lda": remove_log_scale(data["logcov"]),
               "shape_rbf": remove_log_scale(data["logcov"])}
    protocol = {
        "montage": baseline["montage"], "methods": list(methods),
        "split": "15 LOSO people; all three sessions held out; original windows unchanged",
        "hypotheses": ["nonlinear decision boundary", "windowwise scale nuisance"],
        "shape": "log(C) minus trace(log(C))/8 times identity, independently for each window and band",
        "preprocessing": "frozen causal filter features; scaler fit on training people only",
        "selection": "C=1 gamma=scale; no target normalization or labels; 45 fits total",
        "acceptance": "paired mean balanced accuracy gain >=.02 and simultaneous bootstrap interval lower >0",
        "interval": "participant bootstrap 20000 draws; Bonferroni three comparisons, 98.333% each",
        "limitation": "exploratory reuse of SEED participants and films; not independent confirmation",
    }
    (OUTPUT / "protocol.json").write_text(json.dumps(protocol, indent=2), encoding="utf-8")
    reports = {}
    baseline_scores = {p["subject"]: p["balanced_accuracy"] for p in baseline["methods"]["logcov_lda"]["participants"]}
    draws = np.random.default_rng(20260926).integers(0, 15, (20000, 15))
    with (OUTPUT / "predictions.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["method", "subject", "session", "trial", "window", "target", "prediction"])
        for name, x in methods.items():
            scores = []
            for subject in range(1, 16):
                test = keys[:, 0] == subject
                start = time.perf_counter()
                with threadpool_limits(limits=2):
                    model = model_for(name).fit(x[~test], y[~test])
                    prediction = model.predict(x[test])
                scores.append({"subject": subject,
                    "balanced_accuracy": float(balanced_accuracy_score(y[test], prediction)),
                    "accuracy": float(accuracy_score(y[test], prediction)),
                    "macro_f1": float(f1_score(y[test], prediction, average="macro")),
                    "seconds": time.perf_counter() - start,
                    "support_vectors": int(sum(model[-1].n_support_)) if name.endswith("rbf") else 0})
                for key, target, pred in zip(keys[test], y[test], prediction):
                    writer.writerow([name, *key, target, pred])
                stream.flush()
                print(name, subject, scores[-1]["balanced_accuracy"], flush=True)
            values = np.array([p["balanced_accuracy"] for p in scores])
            difference = values - np.array([baseline_scores[s] for s in range(1, 16)])
            ci = np.quantile(difference[draws].mean(axis=1), [.05/6, 1-.05/6])
            reports[name] = {"participants": scores, "mean_balanced_accuracy": float(values.mean()),
                "paired_gain": float(difference.mean()), "paired_simultaneous_ci": ci.tolist(),
                "accept_exploratory": bool(difference.mean() >= .02 and ci[0] > 0)}
            print("SUMMARY", name, reports[name]["mean_balanced_accuracy"], ci, flush=True)
    report = {"methods": reports, "deployment": "unchanged", "hashes": {
        str(p): sha256(p) for p in [Path(__file__), feature_path, OUTPUT / "protocol.json", OUTPUT / "predictions.csv"]}}
    (OUTPUT / "results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
