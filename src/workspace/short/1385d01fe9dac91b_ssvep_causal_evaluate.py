"""Frozen unseen-participant causal-versus-offline comparison; no board writes."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

import numpy as np
import scipy
from scipy.signal import butter, iirnotch, tf2sos

from ssvep_core import canonical_correlation, reference_bank
from ssvep_stream import SSVEPStream
from ssvep_wang_fixed8 import DATASET, _filter_window, _load_subject, _sha256, _verify_channel_locations, _read_frequency_order
from ssvep_wearable_baseline import _reference_q, cca_scores

HERE = Path(__file__).resolve().parent
PROTOCOL = HERE / "ssvep_causal_protocol.json"


def design_coefficients(config):
    band = butter(config["butterworth_order"], config["bandpass_hz"], btype="bandpass",
                  fs=config["sample_rate_hz"], output="sos")
    notch = tf2sos(*iirnotch(config["notch_hz"], config["notch_q"], config["sample_rate_hz"]))
    return band, np.vstack((notch, band))


def verify_downloads(dataset, subjects):
    with urlopen("https://zenodo.org/api/records/14865172", timeout=30) as response:
        metadata = json.load(response)
    files = {item["key"]: item for item in metadata["files"]}
    manifest = []
    for subject in subjects:
        path = dataset / ("S%d.mat" % subject)
        expected = files[path.name]
        md5 = hashlib.md5()
        sha256 = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1 << 20), b""):
                md5.update(chunk)
                sha256.update(chunk)
        if path.stat().st_size != expected["size"] or "md5:" + md5.hexdigest() != expected["checksum"]:
            raise ValueError("Download verification failed: " + str(path))
        manifest.append({"file": path.name, "bytes": path.stat().st_size,
                         "source_md5": expected["checksum"], "verified": True,
                         "sha256": sha256.hexdigest()})
    return manifest


def summarize(rows, config):
    methods = ["offline_qr", "offline_portable", "causal_band_only", "causal_notch_band"]
    per_subject = []
    for subject in config["evaluation_subjects"]:
        one = {"subject": subject}
        for method in methods:
            group = [r for r in rows if r["subject"] == subject and r["method"] == method]
            one[method] = float(np.mean([r["correct"] for r in group]))
            if len(group) != 24:
                raise ValueError("Expected 24 paired trials per subject")
        per_subject.append(one)
    baseline = np.array([r["offline_qr"] for r in per_subject])
    rng = np.random.default_rng(config["statistics"]["bootstrap_seed"])
    resamples = rng.integers(0, len(baseline), (config["statistics"]["participant_resamples"], len(baseline)))
    summary = {}
    for method in methods:
        values = np.array([r[method] for r in per_subject])
        diff = values - baseline
        summary[method] = {"mean_accuracy": float(values.mean()), "subject_sd": float(values.std(ddof=1)),
                           "paired_delta": float(diff.mean()),
                           "paired_ci95": np.quantile(diff[resamples].mean(axis=1), [.025, .975]).tolist(),
                           "participants": len(values), "trials_per_participant": 24}
    candidate = summary["causal_notch_band"]
    passes = candidate["mean_accuracy"] >= .70 and candidate["paired_ci95"][0] >= -.05
    return {"per_subject": per_subject, "summary": summary, "board_replay_gate_passed": bool(passes)}


def run(dataset, output):
    config = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    previous = json.loads((HERE / "ssvep_wang_fixed8_protocol.json").read_text(encoding="utf-8"))
    if set(config["evaluation_subjects"]) & set(config["development_subjects_already_seen"]):
        raise ValueError("Participant overlap")
    _verify_channel_locations(dataset / "64-channels.loc", previous)
    frequencies = _read_frequency_order(dataset / "Freq_Phase.mat", previous)
    targets = config["target_indices_zero_based"]
    np.testing.assert_allclose(frequencies[targets], config["frequencies_hz"])
    output.mkdir(parents=True, exist_ok=True)
    (output / "protocol.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    manifest = verify_downloads(dataset, config["evaluation_subjects"])
    (output / "download_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    band, candidate = design_coefficients(config)
    np.save(output / "candidate_sos.npy", candidate, allow_pickle=False)
    start, stop = config["warmup_samples"], config["warmup_samples"] + config["window_samples"]
    refs = reference_bank(config["frequencies_hz"], sample_rate_hz=config["sample_rate_hz"],
                          samples=config["window_samples"], harmonics=config["harmonics"])
    qr_refs = _reference_q(config["frequencies_hz"], config["window_samples"], config["sample_rate_hz"], config["harmonics"])
    rows = []
    for subject in config["evaluation_subjects"]:
        trials = _load_subject(dataset / ("S%d.mat" % subject), previous)
        ids = np.array([b * 40 + t for b in range(6) for t in targets])
        selected = trials[ids]
        filtered = _filter_window(selected[:, [6,7]], 2, previous)
        qr_scores, valid = cca_scores(filtered, qr_refs)
        for i, trial_id in enumerate(ids):
            raw = selected[i].T
            truth = targets.index(int(trial_id % 40))
            values = {"offline_qr": qr_scores[i] if valid[i] else None,
                      "offline_portable": np.array([canonical_correlation(filtered[i], r) for r in refs])}
            for method, sos in (("causal_band_only", band), ("causal_notch_band", candidate)):
                stream = SSVEPStream(config, sos)
                events = []
                for k in range(0, stop, config["batch_samples"]):
                    events.extend(stream.push(raw[k:min(k+config["batch_samples"], stop)], k))
                if len(events) != 1 or events[0]["window_start_index"] != start:
                    raise AssertionError("First-window alignment failed")
                values[method] = events[0]["scores"]
            for method, scores in values.items():
                prediction = int(np.argmax(scores)) if scores is not None else -1
                rows.append({"subject": subject, "block": int(trial_id // 40 + 1),
                             "target_index_zero_based": int(trial_id % 40), "truth": truth,
                             "method": method, "predicted": prediction, "correct": int(prediction == truth),
                             "scores": np.asarray(scores).tolist() if scores is not None else None})
        if subject == config["evaluation_subjects"][0]:
            np.savez_compressed(output / "replay_input.npz", raw=selected.transpose(0,2,1),
                                original_trial_ids=ids, subject=np.array(subject))
        print("S%d completed; no parameter changes" % subject, flush=True)
    result = {**summarize(rows, config), "predictions": rows, "manifest": manifest,
              "completed_utc": datetime.now(timezone.utc).isoformat(),
              "runtime": {"python":sys.version,"numpy":np.__version__,"scipy":scipy.__version__,"machine":platform.platform()},
              "source_hashes": {name:_sha256(HERE/name) for name in
                                (PROTOCOL.name,"ssvep_stream.py","ssvep_core.py","ssvep_causal_evaluate.py",
                                 "ssvep_wang_fixed8.py","ssvep_wearable_baseline.py")}}
    (output / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"summary":result["summary"],"board_replay_gate_passed":result["board_replay_gate_passed"]},indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.dataset, args.output)
