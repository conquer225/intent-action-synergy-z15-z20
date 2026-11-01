"""Paired O1/O2 versus fixed-cap eight-channel SSVEP evaluation on Wang2016.

The JSON protocol is frozen independently of evaluation EEG. Nothing here is
deployed to the Z15; the zero-phase filter is deliberately labelled offline.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.io import loadmat, whosmat
from scipy.signal import butter, sosfiltfilt

from ssvep_wearable_baseline import _reference_q, cca_scores


HERE = Path(__file__).resolve().parent
PROTOCOL = HERE / "ssvep_wang_fixed8_protocol.json"
DATASET = Path(r"D:\ican\datasets\SSVEP\Wang2016")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_frequency_order(path: Path, protocol: dict) -> np.ndarray:
    frequencies = np.asarray(loadmat(path)["freqs"], dtype=float).ravel()
    if frequencies.shape != (40,) or not np.isfinite(frequencies).all():
        raise ValueError("Frequency metadata must contain exactly 40 finite entries")
    expected_order = np.array([8.0 + major + 0.2 * minor
                               for minor in range(5) for major in range(8)])
    if not np.allclose(frequencies, expected_order, atol=1e-8):
        raise ValueError("Full 40-target frequency order disagrees with MOABB event map")
    primary = protocol["primary_task"]
    observed = frequencies[primary["target_indices_zero_based"]]
    if not np.allclose(observed, primary["expected_frequencies_hz"], atol=1e-8):
        raise ValueError(f"Target order mismatch: {observed}")
    return frequencies


def _verify_channel_locations(path: Path, protocol: dict) -> None:
    locations = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        fields = line.split()
        if len(fields) >= 4:
            locations[int(fields[0]) - 1] = fields[-1]
    for channel, index in zip(protocol["channel_order"], protocol["channel_indices_zero_based"]):
        if locations.get(index) != channel:
            raise ValueError(f"Channel mapping mismatch at {index}: expected {channel}, got {locations.get(index)}")


def _load_subject(path: Path, protocol: dict) -> np.ndarray:
    header = whosmat(path)
    if not any(name == "data" and tuple(shape) == tuple(protocol["epoch_shape"]) for name, shape, _ in header):
        raise ValueError(f"Unexpected MATLAB contents in {path}: {header}")
    eeg = loadmat(path, variable_names=["data"])["data"]
    selected = eeg[protocol["channel_indices_zero_based"]]
    # Exact original trial index is retained: (block, target, channel, sample).
    return np.ascontiguousarray(selected.transpose(3, 2, 0, 1).reshape(240, 8, 1500))


def _filter_window(trials: np.ndarray, seconds: int, protocol: dict) -> np.ndarray:
    fs = protocol["sample_rate_hz"]
    start = protocol["analysis_start_sample"]
    stop = start + seconds * fs
    params = protocol["filter"]
    sos = butter(params["order"], [params["low_hz"], params["high_hz"]],
                 btype="bandpass", fs=fs, output="sos")
    # Restrict the noncausal offline filter to observed samples up to this window.
    filtered = sosfiltfilt(sos, trials[:, :, :stop], axis=-1)
    return filtered[:, :, start:stop]


def _rows_for_subject(subject: int, trials: np.ndarray, frequencies: np.ndarray,
                      protocol: dict) -> list[dict]:
    truth = np.tile(np.arange(40, dtype=int), 6)
    if not np.array_equal(truth[:40], np.arange(40)):
        raise AssertionError("Unexpected trial order")
    tasks = {
        "four_spaced_targets": np.array(protocol["primary_task"]["target_indices_zero_based"], dtype=int),
        "all_40_targets": np.arange(40, dtype=int),
    }
    rows: list[dict] = []
    for seconds in protocol["window_seconds"]:
        data = _filter_window(trials, seconds, protocol)
        refs = _reference_q(frequencies.tolist(), seconds * protocol["sample_rate_hz"],
                            protocol["sample_rate_hz"], protocol["cca_harmonics"])
        for montage, indices in protocol["montages"].items():
            scores, valid = cca_scores(data[:, indices, :], refs)
            for task, targets in tasks.items():
                eligible = np.isin(truth, targets)
                guess = targets[np.argmax(np.nan_to_num(scores[:, targets], nan=-1), axis=1)]
                guess = np.where(valid, guess, -1)
                for trial in np.flatnonzero(eligible):
                    rows.append({
                        "subject": subject,
                        "block": int(trial // 40 + 1),
                        "target_index_1based": int(truth[trial] + 1),
                        "target_hz": float(frequencies[truth[trial]]),
                        "task": task,
                        "window_s": seconds,
                        "montage": montage,
                        "predicted_index_1based": int(guess[trial] + 1) if guess[trial] >= 0 else -1,
                        "correct": int(guess[trial] == truth[trial]),
                        "valid": int(valid[trial]),
                    })
    return rows


def _summary(rows: list[dict], protocol: dict) -> dict:
    grouped: dict[tuple, list[int]] = {}
    for row in rows:
        key = (row["subject"], row["task"], row["window_s"], row["montage"])
        grouped.setdefault(key, []).append(row["correct"])
    subject_rows = [
        {"subject": k[0], "task": k[1], "window_s": k[2], "montage": k[3],
         "accuracy": float(np.mean(v)), "trials": len(v)}
        for k, v in sorted(grouped.items())
    ]
    paired = []
    rng = np.random.default_rng(20260926)
    for task in ("four_spaced_targets", "all_40_targets"):
        for seconds in protocol["window_seconds"]:
            subjects = protocol["evaluation_subjects_predeclared"]
            one = np.array([np.mean(grouped[(s, task, seconds, "O1_O2")]) for s in subjects])
            eight = np.array([np.mean(grouped[(s, task, seconds, "fixed_eight")]) for s in subjects])
            difference = eight - one
            resample = rng.integers(0, len(subjects), size=(10000, len(subjects)))
            ci = np.quantile(difference[resample].mean(axis=1), [0.025, 0.975])
            paired.append({
                "task": task, "window_s": seconds, "subjects": len(subjects),
                "o1_o2_mean": float(one.mean()), "fixed_eight_mean": float(eight.mean()),
                "paired_gain_mean": float(difference.mean()),
                "paired_95pct_bootstrap_ci": ci.tolist(),
                "subjects_improved": int(np.count_nonzero(difference > 0)),
                "subjects_worsened": int(np.count_nonzero(difference < 0)),
                "subjects_tied": int(np.count_nonzero(difference == 0)),
            })
    primary = next(r for r in paired if r["task"] == "four_spaced_targets" and
                   r["window_s"] == protocol["primary_task"]["window_seconds"])
    success = primary["paired_gain_mean"] >= 0.05 and primary["paired_95pct_bootstrap_ci"][0] > 0
    return {"per_subject": subject_rows, "paired": paired,
            "predeclared_success_rule_met": bool(success)}


def run(dataset: Path, output: Path, protocol_path: Path = PROTOCOL) -> dict:
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    expected = set(protocol["evaluation_subjects_predeclared"])
    if len(expected) != len(protocol["evaluation_subjects_predeclared"]):
        raise ValueError("Duplicate subjects in predeclared protocol")
    frequencies = _read_frequency_order(dataset / "Freq_Phase.mat", protocol)
    _verify_channel_locations(dataset / "64-channels.loc", protocol)
    output.mkdir(parents=True, exist_ok=True)
    (output / "protocol.json").write_text(json.dumps(protocol, indent=2, ensure_ascii=False), encoding="utf-8")
    manifest = [{"file": "Freq_Phase.mat", "sha256": _sha256(dataset / "Freq_Phase.mat")},
                {"file": "64-channels.loc", "sha256": _sha256(dataset / "64-channels.loc")}]
    rows = []
    for subject in protocol["evaluation_subjects_predeclared"]:
        path = dataset / f"S{subject}.mat"
        if not path.is_file():
            raise FileNotFoundError(f"Missing predeclared subject: {path}")
        trials = _load_subject(path, protocol)
        rows.extend(_rows_for_subject(subject, trials, frequencies, protocol))
        manifest.append({"file": path.name, "bytes": path.stat().st_size, "sha256": _sha256(path)})
        print(f"S{subject}: scored", flush=True)
    with (output / "predictions.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    result = {"dataset": str(dataset), "source_manifest": manifest, **_summary(rows, protocol),
              "interpretation_limit": "Offline Wang2016 clinical-EEG benchmark, not Cyton or Z15 accuracy."}
    (output / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, default=PROTOCOL)
    args = parser.parse_args()
    result = run(args.dataset, args.output, args.protocol)
    print(json.dumps(result["paired"], ensure_ascii=False, indent=2))
    print("PREDECLARED_SUCCESS_RULE_MET", result["predeclared_success_rule_met"])
