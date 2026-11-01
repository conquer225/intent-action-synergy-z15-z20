"""Predeclared GAMEEMO model comparison with participant-level development/test separation.

Four-class labels mean game condition, not independently verified felt emotion.
The six-channel layout is the overlap with the current Cyton montage. The
eight-channel layout contains AF3/AF4, which are not on the current Cyton cap.
"""

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.metrics import accuracy_score, balanced_accuracy_score, f1_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC
from threadpoolctl import threadpool_limits

from gameemo_8ch_baseline import CHANNELS_8, DEFAULT_DATA, discover_records
from train_gameemo_shared_montage import CHANNELS, prepare


HERE = Path(__file__).resolve().parent
DEV_SUBJECTS = tuple(range(1, 22))
TEST_SUBJECTS = tuple(range(22, 29))
METHODS = ("lda", "rbf_c1", "rbf_c10")
LAYOUTS = ("six_shared", "eight_gameemo")
WINDOWS = (4, 12)


def model(name):
    if name == "lda":
        estimator = LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto")
    else:
        estimator = SVC(kernel="rbf", C=1 if name == "rbf_c1" else 10)
    return make_pipeline(StandardScaler(), estimator)


def features_for_window(x, y, groups, rows, seconds):
    if seconds == 4:
        return x, y, groups, rows
    selected_x, selected_y, selected_groups, selected_rows = [], [], [], []
    by_record = {}
    for index, row in enumerate(rows):
        by_record.setdefault(row[:2], []).append(index)
    for (subject, game), indices in by_record.items():
        for block in range(len(indices) // 3):
            members = indices[block * 3:(block + 1) * 3]
            selected_x.append(np.mean(x[members], axis=0))
            selected_y.append(y[members[0]])
            selected_groups.append(subject)
            selected_rows.append((subject, game, block))
    return (np.asarray(selected_x), np.asarray(selected_y),
            np.asarray(selected_groups), selected_rows)


def select_layout(x, layout):
    if layout == "eight_gameemo":
        return x
    columns = [band * 8 + CHANNELS_8.index(ch)
               for band in range(4) for ch in CHANNELS]
    return x[:, columns]


def scores(y, prediction, groups):
    per_subject = [{"subject": int(subject),
                    "balanced_accuracy": float(balanced_accuracy_score(
                        y[groups == subject], prediction[groups == subject]))}
                   for subject in np.unique(groups)]
    return {"accuracy": float(accuracy_score(y, prediction)),
            "balanced_accuracy": float(balanced_accuracy_score(y, prediction)),
            "macro_f1": float(f1_score(y, prediction, average="macro", zero_division=0)),
            "subject_mean_ba": float(np.mean([row["balanced_accuracy"] for row in per_subject])),
            "subject_sd_ba": float(np.std([row["balanced_accuracy"] for row in per_subject])),
            "per_subject": per_subject}


def trial_scores(y, prediction, rows):
    votes = {}
    for label, estimate, (subject, game, _window) in zip(y, prediction, rows):
        votes.setdefault((subject, game, int(label)), []).append(int(estimate))
    actual, predicted = [], []
    for (_subject, _game, label), estimates in sorted(votes.items()):
        actual.append(label)
        predicted.append(int(np.bincount(estimates, minlength=4).argmax()))
    return {"trials": len(actual), "accuracy": float(accuracy_score(actual, predicted)),
            "balanced_accuracy": float(balanced_accuracy_score(actual, predicted))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--output", type=Path, default=HERE / "output" / "gameemo_cross_subject_v1")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    protocol = {
        "hypothesis": "Longer aggregation and non-linear decision boundaries improve unseen-participant four-game classification.",
        "falsification": "No candidate improves over the six-channel 4-second LDA on dev LOSO subject-mean balanced accuracy.",
        "target": "Four GAMEEMO game conditions; not subjective emotion ground truth",
        "primary_metric": "per-participant mean four-class balanced accuracy on 4- or 12-second nonoverlapping windows",
        "secondary_metric": "one majority-vote decision per complete game trial (not online)",
        "selection": "Select by 21-subject development LOSO only; evaluate selected configuration once on subjects 22-28",
        "development_subjects": DEV_SUBJECTS, "held_out_subjects": TEST_SUBJECTS,
        "candidate_methods": METHODS, "candidate_layouts": {
            "six_shared": CHANNELS, "eight_gameemo": CHANNELS_8},
        "candidate_window_seconds": WINDOWS,
        "window_12_definition": "mean of three consecutive nonoverlapping 4-second log-band-power vectors, per recording",
        "preprocessing": "GAMEEMO vendor-preprocessed EEG, resampled 128->250 Hz; same causal filter/features as Cyton runtime",
        "selection_limitations": "Prior baseline results already inspected all 28 subjects; held-out set is a new model-comparison split, not pristine first-ever external validation",
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    (args.output / "protocol.json").write_text(json.dumps(protocol, indent=2), encoding="utf-8")
    cache = args.output / "features_4s.npz"
    if cache.exists():
        data = np.load(cache)
        x, y, groups = data["x"], data["y"], data["groups"]
        rows = [tuple(int(v) for v in row) for row in data["rows"]]
    else:
        x, y, groups, rows, _fixture = prepare(discover_records(args.data))
        np.savez_compressed(cache, x=x, y=y, groups=groups, rows=np.asarray(rows))
    if tuple(np.unique(groups)) != DEV_SUBJECTS + TEST_SUBJECTS:
        raise RuntimeError("subject inventory differs from predeclared split")
    report = {"protocol_sha256": hashlib.sha256((args.output / "protocol.json").read_bytes()).hexdigest(),
              "feature_cache_sha256": hashlib.sha256(cache.read_bytes()).hexdigest(),
              "development": [], "held_out": {}, "full_loso_exploratory": {}}
    prepared = {}
    with threadpool_limits(limits=1):
        for seconds in WINDOWS:
            data = features_for_window(x, y, groups, rows, seconds)
            for layout in LAYOUTS:
                xx = select_layout(data[0], layout)
                yy, gg, rr = data[1:]
                prepared[(seconds, layout)] = xx, yy, gg, rr
                for method in METHODS:
                    dev_pred = np.full(len(yy), -1, dtype=int)
                    for subject in DEV_SUBJECTS:
                        train = np.isin(gg, DEV_SUBJECTS) & (gg != subject)
                        test = gg == subject
                        fitted = model(method).fit(xx[train], yy[train])
                        dev_pred[test] = fitted.predict(xx[test])
                    dev = np.isin(gg, DEV_SUBJECTS)
                    summary = {"seconds": seconds, "layout": layout, "method": method,
                               "windows": int(dev.sum()),
                               "window": scores(yy[dev], dev_pred[dev], gg[dev]),
                               "trial_vote": trial_scores(yy[dev], dev_pred[dev],
                                                          [row for row, keep in zip(rr, dev) if keep])}
                    report["development"].append(summary)
                    print("DEV", seconds, layout, method,
                          round(summary["window"]["subject_mean_ba"], 4), flush=True)
        report["selection"] = {}
        for layout in LAYOUTS:
            best = max((entry for entry in report["development"] if entry["layout"] == layout),
                       key=lambda item: (item["window"]["subject_mean_ba"],
                                         item["window"]["macro_f1"]))
            xx, yy, gg, rr = prepared[(best["seconds"], layout)]
            train, test = np.isin(gg, DEV_SUBJECTS), np.isin(gg, TEST_SUBJECTS)
            final = model(best["method"]).fit(xx[train], yy[train])
            predicted = final.predict(xx[test])
            test_rows = [row for row, keep in zip(rr, test) if keep]
            report["selection"][layout] = {key: best[key] for key in ("seconds", "layout", "method")}
            report["held_out"][layout] = {"windows": int(test.sum()),
                                          "window": scores(yy[test], predicted, gg[test]),
                                          "trial_vote": trial_scores(yy[test], predicted, test_rows)}
            with (args.output / f"held_out_predictions_{layout}.csv").open(
                    "w", newline="", encoding="utf-8") as stream:
                writer = csv.writer(stream)
                writer.writerow(("subject", "game", "window", "target_game_condition", "prediction"))
                writer.writerows((*row, int(target), int(estimate))
                                 for row, target, estimate in zip(test_rows, yy[test], predicted))
            print("HELD_OUT", layout, report["selection"][layout],
                  report["held_out"][layout]["window"], flush=True)
            baseline_x, baseline_y, baseline_groups, baseline_rows = prepared[(12, layout)]
            for method in ("lda", "rbf_c1"):
                baseline_prediction = np.empty(len(baseline_y), dtype=int)
                for subject in DEV_SUBJECTS + TEST_SUBJECTS:
                    fold_train = baseline_groups != subject
                    fold_test = baseline_groups == subject
                    fitted = model(method).fit(baseline_x[fold_train], baseline_y[fold_train])
                    baseline_prediction[fold_test] = fitted.predict(baseline_x[fold_test])
                key = f"{layout}_{method}_12s"
                report["full_loso_exploratory"][key] = {
                    "window": scores(baseline_y, baseline_prediction, baseline_groups),
                    "trial_vote": trial_scores(baseline_y, baseline_prediction, baseline_rows)}
                print("FULL_LOSO_BASELINE", key,
                      report["full_loso_exploratory"][key]["window"]["subject_mean_ba"], flush=True)
    (args.output / "results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
