"""Export a local research candidate; never changes the Z15 service or overlay."""

import json
from pathlib import Path

import numpy as np
from threadpoolctl import threadpool_limits

from .emotion_baseline import sha256
from .seed_causal_normalization import past_center
from .seed_covariance_diagnosis import INITIAL, model_for

OUTPUT = Path(__file__).parent / "output/seed_causal_candidate_20260926"


def linear_parameters(model):
    scaler, lda = model
    weight = lda.coef_ / scaler.scale_[None, :]
    bias = lda.intercept_ - weight @ scaler.mean_
    return weight, bias


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    if (OUTPUT / "manifest.json").exists():
        raise FileExistsError("Candidate already exported")
    data_path = INITIAL / "features.npz"
    original = json.loads((INITIAL / "results.json").read_text())
    assert sha256(data_path) == original["hashes"][str(data_path)]
    data = dict(np.load(data_path, allow_pickle=False))
    x, y, keys = data["logcov"], data["targets"], data["keys"]
    normalized = np.empty_like(x)
    eligible = np.ones(len(x), dtype=bool)
    for subject, session in np.unique(keys[:, :2], axis=0):
        indices = np.flatnonzero((keys[:, 0] == subject) & (keys[:, 1] == session))
        indices = indices[np.lexsort((keys[indices, 3], keys[indices, 2]))]
        eligible[indices[:5]] = False
        normalized[indices] = past_center(x[indices], "expanding")
    checks = []
    with threadpool_limits(limits=2):
        for subject in range(1, 16):
            train = eligible & (keys[:, 0] != subject)
            test = eligible & (keys[:, 0] == subject)
            model = model_for("lda").fit(normalized[train], y[train])
            weight, bias = linear_parameters(model)
            score32 = normalized[test].astype(np.float32) @ weight.astype(np.float32).T + bias.astype(np.float32)
            expected = model.decision_function(normalized[test])
            predicted = model[-1].classes_[score32.argmax(axis=1)]
            checks.append({"subject": subject, "windows": int(test.sum()),
                           "max_score_abs_error": float(np.max(np.abs(score32 - expected))),
                           "class_disagreements": int(np.count_nonzero(predicted != model.predict(normalized[test])))})
        final = model_for("lda").fit(normalized[eligible], y[eligible])
    weight, bias = linear_parameters(final)
    np.savez(OUTPUT / "linear_weights.npz", weight=weight.astype(np.float32),
             bias=bias.astype(np.float32), classes=final[-1].classes_)
    manifest = {"status": "local research candidate; NOT installed on board",
        "task": "SEED film positive/neutral/negative, not GAMEEMO or DEAP task",
        "channels": original["montage"], "features": "frozen SEED 200Hz causal five-band 12s covariance log vectors, 180 values",
        "state": "first5 complete windows initialize mean; predict on x-mean then update mean with current x; reset each recording",
        "classifier": "argmax(weight @ centered_logcov + bias), classes -1/0/1",
        "weights_bytes": int(weight.astype(np.float32).nbytes + bias.astype(np.float32).nbytes),
        "training": "all 15 SEED people only AFTER LOSO experiments; full-fit predictions are not test accuracy",
        "checks": checks,
        "not_validated": ["Cyton 250Hz to 200Hz resampling", "reference and upstream preprocessing mismatch",
                          "SQI rejection and missing channels", "stream float32 accumulation", "ARM end-to-end latency",
                          "posterior probability calibration", "independent cohort"],
        "hardware": "linear classifier has 540 multiply-accumulates; feature eigen-decompositions separate; no measured PL speedup",
        "hashes": {str(p): sha256(p) for p in [Path(__file__), data_path, OUTPUT / "linear_weights.npz"]}}
    (OUTPUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("EXPORT", "disagreements", sum(c["class_disagreements"] for c in checks),
          "max_score_error", max(c["max_score_abs_error"] for c in checks), flush=True)


if __name__ == "__main__":
    main()
