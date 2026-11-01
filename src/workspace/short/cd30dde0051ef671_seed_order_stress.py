"""Stress frozen past-only normalization against independently shuffled film order."""

import csv
import json
from pathlib import Path

import numpy as np
from sklearn.metrics import balanced_accuracy_score
from threadpoolctl import threadpool_limits

from .emotion_baseline import sha256
from .seed_causal_normalization import past_center
from .seed_covariance_diagnosis import INITIAL, model_for

OUTPUT = Path(__file__).parent / "output/seed_order_stress_20260926"


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    if (OUTPUT / "results.json").exists():
        raise FileExistsError("Experiment already complete")
    feature_path = INITIAL / "features.npz"
    original = json.loads((INITIAL / "results.json").read_text())
    assert sha256(feature_path) == original["hashes"][str(feature_path)]
    data = dict(np.load(feature_path, allow_pickle=False))
    x, keys, y = data["logcov"], data["keys"], data["targets"]
    protocol = {"seeds": [20260926, 20260927, 20260928], "montage": original["montage"],
        "hypothesis": "gain persists when people do not share film order",
        "method": "freeze expanding-mean normalization and LDA; independently permute 15 whole trials in each subject/session, preserve within-trial order",
        "control": "raw model with identical first5-window exclusions; all 15 LOSO participants, source and target same policy",
        "caveat": "synthetic ordering of recorded data is a stress test, not new subjects or natural acquisition; boundary filtering unchanged",
        "acceptance": "positive gain for each seed; participant bootstrap on seed-averaged paired gains lower >0; no retuning"}
    (OUTPUT / "protocol.json").write_text(json.dumps(protocol, indent=2), encoding="utf-8")
    results = []
    permutations = []
    with (OUTPUT / "predictions.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["seed", "method", "subject", "session", "trial", "window", "target", "prediction"])
        for seed in protocol["seeds"]:
            rng = np.random.default_rng(seed)
            aligned = np.empty_like(x)
            eligible = np.ones(len(x), dtype=bool)
            for subject, session in np.unique(keys[:, :2], axis=0):
                selected = (keys[:, 0] == subject) & (keys[:, 1] == session)
                trials = rng.permutation(np.unique(keys[selected, 2]))
                parts = []
                for trial in trials:
                    indices = np.flatnonzero(selected & (keys[:, 2] == trial))
                    parts.append(indices[np.argsort(keys[indices, 3])])
                order = np.concatenate(parts)
                eligible[order[:5]] = False
                aligned[order] = past_center(x[order], "expanding")
                permutations.append({"seed": seed, "subject": int(subject), "session": int(session), "trials": trials.tolist()})
            seed_scores = {}
            for mode, features in {"raw": x, "expanding": aligned}.items():
                scores = []
                for subject in range(1, 16):
                    train = eligible & (keys[:, 0] != subject)
                    test = eligible & (keys[:, 0] == subject)
                    with threadpool_limits(limits=2):
                        prediction = model_for("lda").fit(features[train], y[train]).predict(features[test])
                    scores.append(float(balanced_accuracy_score(y[test], prediction)))
                    writer.writerows([seed, mode, *key, target, pred] for key, target, pred in zip(keys[test], y[test], prediction))
                seed_scores[mode] = scores
            results.append({"seed": seed, "scores_subject1_to15": seed_scores})
            print(seed, {k: float(np.mean(v)) for k, v in seed_scores.items()}, flush=True)
    delta = np.array([np.array(r["scores_subject1_to15"]["expanding"]) - r["scores_subject1_to15"]["raw"] for r in results])
    average = delta.mean(axis=0)
    draws = np.random.default_rng(17).integers(0, 15, (20000, 15))
    ci = np.quantile(average[draws].mean(axis=1), [.025, .975])
    (OUTPUT / "orders.json").write_text(json.dumps(permutations, indent=2), encoding="utf-8")
    report = {"seeds": results, "mean_paired_gain": float(average.mean()), "participant_ci95": ci.tolist(),
        "passes_stress": bool(np.all(delta.mean(axis=1) > 0) and ci[0] > 0),
        "hashes": {str(p): sha256(p) for p in [Path(__file__), feature_path, OUTPUT / "protocol.json", OUTPUT / "orders.json", OUTPUT / "predictions.csv"]}}
    (OUTPUT / "results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
