"""Fixed-budget classifier-family comparison on the original DEAP power features."""

import csv
import json
from pathlib import Path

import numpy as np
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import balanced_accuracy_score, f1_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .deap_normalization_ablation import INITIAL
from .fixed8_deap_experiment import file_hash
from .fixed8_deap_preflight import DEV_SUBJECTS, TASK_COLUMNS


def main():
    output = Path(__file__).parent / "output/deap_classifier_20260926"
    output.mkdir(parents=True, exist_ok=True)
    protocol = {
        "hypothesis": "Shrinkage discriminant analysis or nonlinear trees improve over power logistic regression",
        "input": "unchanged original 32 band-power features and fixed eight channels",
        "split": "s01-s24 LOSO; s25-s32 unopened",
        "models": {"shrinkage_lda": "lsqr, shrinkage=auto, equal priors",
                   "hgb": "100 iterations, learning_rate=.1, max_leaf_nodes=15, min_samples_leaf=30, l2=1, no early stopping"},
        "seeds": "HGB random_state=20260926; no stochastic subsampling or early stopping; deterministic configuration",
        "budget": "2 classifiers x 2 tasks x 24 folds; no parameter search",
        "decision": "gain >=.02 and four-comparison-adjusted participant bootstrap interval excludes zero",
        "status": "exploratory development comparison, not confirmatory holdout",
    }
    (output / "protocol.json").write_text(json.dumps(protocol, indent=2), encoding="utf-8")
    original = json.loads((INITIAL / "development_results.json").read_text())
    path = INITIAL / "development_features.npz"
    assert file_hash(path) == original["features_sha256"]
    data = dict(np.load(path, allow_pickle=False))
    assert set(data["keys"][:, 0]) == set(DEV_SUBJECTS)
    predictions, tasks = [], {}
    rng = np.random.default_rng(20260926)
    for task, column in TASK_COLUMNS.items():
        tasks[task] = {}
        eligible = data["ratings"][:, column] != 5
        targets = (data["ratings"][:, column] > 5).astype(int)
        for method in ("shrinkage_lda", "hgb"):
            scores = []
            for subject in DEV_SUBJECTS:
                train = eligible & (data["keys"][:, 0] != subject)
                test = eligible & (data["keys"][:, 0] == subject)
                if method == "shrinkage_lda":
                    model = make_pipeline(StandardScaler(), LinearDiscriminantAnalysis(
                        solver="lsqr", shrinkage="auto", priors=[.5, .5]))
                    model.fit(data["power"][train], targets[train])
                else:
                    model = HistGradientBoostingClassifier(max_iter=100, max_leaf_nodes=15,
                        min_samples_leaf=30, l2_regularization=1, early_stopping=False, random_state=20260926)
                    counts = np.bincount(targets[train], minlength=2)
                    weight = train.sum() / (2 * counts[targets[train]])
                    model.fit(data["power"][train], targets[train], sample_weight=weight)
                predicted = model.predict(data["power"][test])
                scores.append({"subject": subject, "balanced_accuracy": balanced_accuracy_score(targets[test], predicted),
                               "macro_f1": f1_score(targets[test], predicted, average="macro")})
                predictions.extend((task, method, *map(int, key), int(y), int(p))
                                   for key, y, p in zip(data["keys"][test], targets[test], predicted))
            values = np.array([s["balanced_accuracy"] for s in scores])
            old = np.array([s["balanced_accuracy"] for s in original["tasks"][task]["power_linear"]["participants"]])
            difference = values - old
            interval = np.quantile(difference[rng.integers(0, 24, (20000, 24))].mean(axis=1), [.05/8, 1-.05/8])
            tasks[task][method] = {"mean_subject_balanced_accuracy": values.mean(), "participants": scores,
                "gain": difference.mean(), "adjusted_interval": interval.tolist(),
                "continue": bool(difference.mean() >= .02 and interval[0] > 0)}
            print(task, method, values.mean(), "continue", tasks[task][method]["continue"], flush=True)
    with (output / "predictions.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["task", "method", "subject", "trial", "window", "target", "prediction"])
        writer.writerows(predictions)
    report = {"tasks": tasks, "software": original["software"],
              "hashes": {str(p): file_hash(p) for p in [Path(__file__), path,
                  output / "protocol.json", output / "predictions.csv"]}}
    (output / "results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
