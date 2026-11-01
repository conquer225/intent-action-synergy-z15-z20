"""Run the frozen, O1/O2-only wearable-SSVEP pilot; no board deployment.

All parameters are read from ssvep_wearable_protocol.json. No subject data are
used for fitting, threshold selection, or method selection. The PDF supplied
with the dataset defines target order; the paper defines EEG channel order.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import time
from pathlib import Path

import numpy as np
from scipy.io import loadmat
from scipy.signal import butter, sosfiltfilt

from ssvep_core import reference_bank


HERE = Path(__file__).resolve().parent
PROTOCOL = HERE / "ssvep_wearable_protocol.json"


def _reference_q(frequencies: list[float], samples: int, fs: int, harmonics: int) -> np.ndarray:
    refs = reference_bank(frequencies, sample_rate_hz=fs, samples=samples, harmonics=harmonics)
    refs = np.moveaxis(refs, 2, 1)
    refs -= refs.mean(axis=1, keepdims=True)
    q, _ = np.linalg.qr(refs)
    return q


def cca_scores(batch: np.ndarray, refs_q: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Batch canonical correlations via principal angles of orthonormal bases.

    batch: (trials, channels, samples); refs_q: (targets, samples, terms).
    A singular/flat channel pair gets NaN scores and counts as incorrect.
    """
    x = np.moveaxis(np.asarray(batch, dtype=np.float64), 2, 1)
    finite = np.isfinite(x).all(axis=(1, 2))
    x = np.where(np.isfinite(x), x, 0.0)
    x -= x.mean(axis=1, keepdims=True)
    q, r = np.linalg.qr(x)
    eig = np.linalg.svd(r, compute_uv=False)
    good = finite & (eig[:, -1] > 1e-8 * eig[:, 0])
    cross = np.einsum("nti,ftj->nfij", q, refs_q, optimize=True)
    scores = np.linalg.svd(cross, compute_uv=False)[..., 0]
    scores[~good] = np.nan
    return scores, good


def _format_trials(filtered: np.ndarray, start: int, samples: int, electrode: int) -> np.ndarray:
    # Input: (channels, 710 points, 2 electrode types, 10 blocks, 12 targets).
    x = filtered[:, start : start + samples, electrode, :, :]
    return x.transpose(2, 3, 0, 1).reshape(-1, filtered.shape[0], samples)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _bandpass(data: np.ndarray, fs: int, low: int, high: int, order: int) -> np.ndarray:
    sos = butter(order, [low, high], btype="bandpass", fs=fs, output="sos")
    return sosfiltfilt(sos, data, axis=1)


def _load_protocol(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    parent_name = data.pop("extends", None)
    if parent_name is not None:
        parent = _load_protocol(path.parent / parent_name)
        parent.update(data)
        return parent
    return data


def run(dataset: Path, output: Path, protocol_path: Path = PROTOCOL) -> dict:
    protocol = _load_protocol(protocol_path)
    output.mkdir(parents=True, exist_ok=True)
    (output / "protocol.json").write_text(json.dumps(protocol, ensure_ascii=False, indent=2), encoding="utf-8")
    p = protocol["preprocessing"]
    fs = protocol["sampling_rate_hz"]
    start = protocol["analysis_start_sample"]
    targets = protocol["frequencies_hz"]
    harmonics = p["harmonics"]
    windows = protocol["window_seconds"]
    refs = {s: _reference_q(targets, int(s * fs), fs, harmonics) for s in windows}
    bands = [p["cca_band_hz"]] + [[low, p["fbcca_high_edge_hz"]] for low in p["fbcca_low_edges_hz"]]
    weights = np.array([i ** -1.25 + 0.25 for i in range(1, len(bands))], dtype=float)
    labels = np.tile(np.arange(len(targets)), 10)
    rows: list[dict] = []
    manifest: list[dict] = []
    began = time.perf_counter()

    for subject in protocol.get("subject_ids", protocol["pilot_subjects"]):
        path = dataset / f"S{subject:03d}.mat"
        if not path.is_file():
            raise FileNotFoundError(f"Missing predeclared pilot subject: {path}")
        raw = loadmat(path)["data"]
        if list(raw.shape) != protocol["epoch_shape"]:
            raise ValueError(f"Unexpected shape for {path.name}: {raw.shape}")
        manifest.append({"name": path.name, "bytes": path.stat().st_size, "sha256": _sha256(path)})
        selected = raw[protocol["channels_zero_based"], :, :, :, :]
        filtered = [_bandpass(selected, fs, low, high, p["butterworth_order"]) for low, high in bands]
        for seconds in windows:
            samples = seconds * fs
            for electrode, name in enumerate(protocol.get("electrode_axis_names", ("wet", "dry"))):
                band_scores = []
                band_valid = []
                for signal in filtered:
                    scores, valid = cca_scores(_format_trials(signal, start, samples, electrode), refs[seconds])
                    band_scores.append(scores)
                    band_valid.append(valid)
                all_valid = np.logical_and.reduce(band_valid)
                aggregate = np.tensordot(weights, np.square(np.stack(band_scores[1:])), axes=1)
                for method, scores in (("cca", band_scores[0]), ("fbcca", aggregate)):
                    tasks = {"12-class": list(range(len(targets)))}
                    tasks.update(protocol.get("candidate_subsets", {}))
                    for task, target_ids in tasks.items():
                        target_ids = np.array(target_ids, dtype=int)
                        if not np.all((target_ids >= 0) & (target_ids < len(targets))):
                            raise ValueError(f"Invalid target subset {task}: {target_ids}")
                        eligible = np.isin(labels, target_ids)
                        local = np.argmax(np.nan_to_num(scores[:, target_ids], nan=-1), axis=1)
                        predicted = np.where(all_valid, target_ids[local], -1)
                        for trial in np.flatnonzero(eligible):
                            truth, guess = labels[trial], predicted[trial]
                            rows.append({
                            "task": task,
                            "subject": subject,
                            "electrode": name,
                            "window_s": seconds,
                            "method": method,
                            "block": trial // len(targets) + 1,
                            "target_index": int(truth) + 1,
                            "target_hz": targets[truth],
                            "predicted_index": int(guess) + 1 if guess >= 0 else -1,
                            "predicted_hz": targets[guess] if guess >= 0 else "",
                            "correct": int(guess == truth),
                            "valid": int(all_valid[trial]),
                            "scores": json.dumps([float(value) for value in scores[trial]]),
                            })
        print(f"subject {subject:03d} done", flush=True)

    with (output / "predictions.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    groups: dict[tuple, list[dict]] = {}
    for row in rows:
        key = (row["task"], row["subject"], row["electrode"], row["window_s"], row["method"])
        groups.setdefault(key, []).append(row)
    subjects = [{
        "task": key[0], "subject": key[1], "electrode": key[2], "window_s": key[3], "method": key[4],
        "accuracy": sum(r["correct"] for r in items) / len(items),
        "invalid": sum(not r["valid"] for r in items), "trials": len(items),
    } for key, items in sorted(groups.items())]
    summary = []
    for task in ("12-class", *protocol.get("candidate_subsets", {})):
        for electrode in protocol.get("electrode_axis_names", ("wet", "dry")):
            for seconds in windows:
                for method in ("cca", "fbcca"):
                    vals = np.array([r["accuracy"] for r in subjects if (r["task"], r["electrode"], r["window_s"], r["method"]) == (task, electrode, seconds, method)])
                    summary.append({"task": task, "electrode": electrode, "window_s": seconds, "method": method,
                                    "subjects": len(vals), "mean_subject_accuracy": float(vals.mean()),
                                    "subject_sd": float(vals.std(ddof=1))})
    result = {"protocol": str(protocol_path), "dataset": str(dataset), "elapsed_pc_s": time.perf_counter() - began,
              "manifest": manifest, "summary": summary, "per_subject": subjects,
              "note": "PC offline pilot only; not Cyton or Z15 real-time validation."}
    (output / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=Path(r"D:\ican\datasets\SSVEP\WearableSSVEP102"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, default=PROTOCOL)
    args = parser.parse_args()
    result = run(args.dataset, args.output, args.protocol)
    for item in result["summary"]:
        print(item)


if __name__ == "__main__":
    main()
