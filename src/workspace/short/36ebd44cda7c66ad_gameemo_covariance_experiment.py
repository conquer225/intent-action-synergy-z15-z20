"""Exploratory cross-subject spatial-covariance features for GAMEEMO.

This is a different feature-family check, not a reproduction of a WST paper.
Subjects 22-28 were inspected in the earlier comparison, so this follow-up is
exploratory rather than a pristine confirmatory test.
"""

import argparse
import hashlib
import csv
import json
from pathlib import Path

import numpy as np
import joblib
import sklearn
from scipy import signal
from scipy.io import loadmat
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC
from threadpoolctl import threadpool_limits

from compare_gameemo_cross_subject import DEV_SUBJECTS, TEST_SUBJECTS, scores, trial_scores
from gameemo_8ch_baseline import CHANNELS_8, DEFAULT_DATA, discover_records

import sys
sys.path.insert(0, str(Path(__file__).parents[1] / "pynq_guardianloop"))
from cyton_sqi import CausalEEGFilter


BANDS = ((1, 4), (4, 8), (8, 13), (13, 30), (30, 43))
LAYOUTS = {"six_shared": ("F3", "F4", "T7", "T8", "O1", "O2"),
           "eight_gameemo": CHANNELS_8}
HERE = Path(__file__).resolve().parent


def log_covariance(section):
    covariance = np.cov(section, rowvar=False)
    dimension = covariance.shape[0]
    covariance += 0.05 * (np.trace(covariance) / dimension) * np.eye(dimension)
    eigenvalues, vectors = np.linalg.eigh(covariance)
    matrix_log = (vectors * np.log(np.maximum(eigenvalues, 1e-12))) @ vectors.T
    upper = np.triu_indices(dimension)
    features = matrix_log[upper]
    features[upper[0] != upper[1]] *= np.sqrt(2)
    return features


def extract(records):
    filters = [signal.butter(4, band, fs=250, btype="bandpass", output="sos")
               for band in BANDS]
    features = {layout: [] for layout in LAYOUTS}
    labels, groups, rows = [], [], []
    for count, record in enumerate(records, 1):
        contents = loadmat(record["path"], variable_names=list(CHANNELS_8))
        raw = np.column_stack([np.asarray(contents[channel]).ravel()
                               for channel in CHANNELS_8])
        conditioned = CausalEEGFilter().process(signal.resample_poly(raw, 125, 64, axis=0))
        bands = [signal.sosfilt(sos, conditioned, axis=0) for sos in filters]
        for index in range((len(conditioned) - 1000) // 3000):
            section = slice(1000 + index * 3000, 1000 + (index + 1) * 3000)
            for layout, names in LAYOUTS.items():
                columns = [CHANNELS_8.index(name) for name in names]
                features[layout].append(np.concatenate([
                    log_covariance(band[section][:, columns]) for band in bands]))
            labels.append(record["class_id"])
            groups.append(record["subject"])
            rows.append((record["subject"], record["game"], index))
        if count % 8 == 0:
            print("covariance features", count, "/", len(records), flush=True)
    return ({key: np.asarray(value) for key, value in features.items()},
            np.asarray(labels), np.asarray(groups), rows)


def build_model(name):
    classifier = (LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto")
                  if name == "lda" else SVC(kernel="rbf", C=1))
    return make_pipeline(StandardScaler(), classifier)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--output", type=Path, default=HERE / "output" / "gameemo_covariance_v1")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    protocol = {"hypothesis": "Bandwise spatial covariance captures cross-channel game-condition information missing from band powers",
                "falsification": "No development LOSO improvement over 12-second band-power LDA, for the same montage",
                "status": "exploratory after previous held-out subjects were seen",
                "channels": LAYOUTS, "bands_hz": BANDS, "window_seconds": 12,
                "warmup_excluded_seconds_per_record": 4,
                "feature": "per-band regularized covariance, matrix logarithm, upper triangle",
                "methods": ("lda", "rbf_c1"), "development_subjects": DEV_SUBJECTS,
                "evaluation_subjects": TEST_SUBJECTS,
                "primary_metric": "per-subject mean balanced accuracy on nonoverlapping 12-second windows",
                "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (args.output / "protocol.json").write_text(json.dumps(protocol, indent=2), encoding="utf-8")
    cache = args.output / "covariance_12s.npz"
    if cache.exists():
        data = np.load(cache)
        features = {key: data[key] for key in LAYOUTS}
        labels, groups = data["labels"], data["groups"]
        rows = [tuple(int(v) for v in row) for row in data["rows"]]
    else:
        features, labels, groups, rows = extract(discover_records(args.data))
        np.savez_compressed(cache, **features, labels=labels, groups=groups,
                            rows=np.asarray(rows))
    if tuple(np.unique(groups)) != DEV_SUBJECTS + TEST_SUBJECTS:
        raise RuntimeError("subject inventory differs from protocol")
    if not all(np.isfinite(value).all() for value in features.values()):
        raise RuntimeError("non-finite covariance features")
    if len(set(rows)) != len(rows):
        raise RuntimeError("duplicate subject/game/window keys")
    # Exact cross-participant duplicates would indicate a cache/data leak.
    hashes = {}
    for index, vector in enumerate(features["six_shared"]):
        fingerprint = hashlib.sha256(vector.tobytes()).hexdigest()
        if fingerprint in hashes and groups[hashes[fingerprint]] != groups[index]:
            raise RuntimeError("identical feature vectors across participants")
        hashes[fingerprint] = index
    report = {"protocol_sha256": hashlib.sha256((args.output / "protocol.json").read_bytes()).hexdigest(),
              "cache_sha256": hashlib.sha256(cache.read_bytes()).hexdigest(),
              "development": [], "exploratory_evaluation": {}, "full_loso_exploratory": {},
              "data_checks": {"windows": len(rows), "unique_keys": len(set(rows)),
                              "finite_features": True, "cross_subject_exact_duplicates": 0}}
    with threadpool_limits(limits=1):
        for layout, x in features.items():
            for method in protocol["methods"]:
                estimates = np.full(len(labels), -1, dtype=int)
                for subject in DEV_SUBJECTS:
                    train = np.isin(groups, DEV_SUBJECTS) & (groups != subject)
                    test = groups == subject
                    fitted = build_model(method).fit(x[train], labels[train])
                    estimates[test] = fitted.predict(x[test])
                dev = np.isin(groups, DEV_SUBJECTS)
                metric = scores(labels[dev], estimates[dev], groups[dev])
                report["development"].append({"layout": layout, "method": method,
                                              "window": metric,
                                              "trial_vote": trial_scores(labels[dev], estimates[dev],
                                                                         [row for row, keep in zip(rows, dev) if keep])})
                print("DEV", layout, method, metric["subject_mean_ba"], flush=True)
            best = max((entry for entry in report["development"] if entry["layout"] == layout),
                       key=lambda entry: (entry["window"]["subject_mean_ba"],
                                          entry["window"]["macro_f1"]))
            train, test = np.isin(groups, DEV_SUBJECTS), np.isin(groups, TEST_SUBJECTS)
            predicted = build_model(best["method"]).fit(x[train], labels[train]).predict(x[test])
            report["exploratory_evaluation"][layout] = {
                "selected_method": best["method"],
                "window": scores(labels[test], predicted, groups[test]),
                "trial_vote": trial_scores(labels[test], predicted,
                                           [row for row, keep in zip(rows, test) if keep])}
            print("EVALUATION", layout,
                  report["exploratory_evaluation"][layout]["window"]["subject_mean_ba"], flush=True)
            # The method was fixed by development subjects above. Full LOSO uses
            # 27 training participants per fold but is exploratory after selection.
            all_predicted = np.empty(len(labels), dtype=int)
            for subject in DEV_SUBJECTS + TEST_SUBJECTS:
                fold_train = groups != subject
                fold_test = groups == subject
                fitted = build_model(best["method"]).fit(x[fold_train], labels[fold_train])
                all_predicted[fold_test] = fitted.predict(x[fold_test])
            report["full_loso_exploratory"][layout] = {
                "method": best["method"],
                "window": scores(labels, all_predicted, groups),
                "trial_vote": trial_scores(labels, all_predicted, rows)}
            with (args.output / f"full_loso_predictions_{layout}.csv").open(
                    "w", newline="", encoding="utf-8") as stream:
                writer = csv.writer(stream)
                writer.writerow(("subject", "game", "window", "target_game_condition", "prediction"))
                writer.writerows((*row, int(target), int(prediction))
                                 for row, target, prediction in zip(rows, labels, all_predicted))
            print("FULL_LOSO", layout,
                  report["full_loso_exploratory"][layout]["window"]["subject_mean_ba"], flush=True)
        rng = np.random.default_rng(123)
        randomized = labels.copy()
        for subject in DEV_SUBJECTS + TEST_SUBJECTS:
            permutation = rng.permutation(4)
            mask = groups == subject
            randomized[mask] = permutation[labels[mask]]
        null_predicted = np.empty(len(labels), dtype=int)
        x = features["six_shared"]
        for subject in DEV_SUBJECTS + TEST_SUBJECTS:
            train, test = groups != subject, groups == subject
            fitted = build_model("rbf_c1").fit(x[train], randomized[train])
            null_predicted[test] = fitted.predict(x[test])
        report["negative_control"] = {
            "permutation": "random four-game label permutation within each participant, seed 123",
            "six_shared_window": scores(randomized, null_predicted, groups)}
        print("NEGATIVE_CONTROL", report["negative_control"]["six_shared_window"]["subject_mean_ba"], flush=True)
    (args.output / "results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    if report["negative_control"]["six_shared_window"]["subject_mean_ba"] > 0.35:
        raise RuntimeError("negative-control result too high; do not export")
    final = build_model("rbf_c1").fit(features["six_shared"], labels)
    model_path = args.output / "six_channel_covariance_svm.joblib"
    joblib.dump(final, model_path)
    export = {"artifact": str(model_path),
              "model_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
              "result_sha256": hashlib.sha256((args.output / "results.json").read_bytes()).hexdigest(),
              "trained_on": "all 28 GAMEEMO participants; deployment-only fit, no in-sample score",
              "status": "offline candidate only; not compatible with existing 4-second Cyton runtime",
              "channels": LAYOUTS["six_shared"], "bands_hz": BANDS,
              "window_seconds": 12, "feature": "per-band log covariance, upper triangle",
              "sklearn_version": sklearn.__version__}
    (args.output / "model_metadata.json").write_text(json.dumps(export, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
