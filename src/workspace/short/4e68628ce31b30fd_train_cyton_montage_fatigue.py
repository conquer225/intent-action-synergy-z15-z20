"""Train/evaluate SEED-VIG fatigue on the Cyton montage's four real overlaps.

Preprocessing mirrors the live 250 Hz Cyton ARM stream: continuous 50 Hz notch,
1–45 Hz bandpass, then a continuous five-band DE filter bank. The four physical
inputs are CH5=T7, CH6=T8, CH7=O1, CH8=O2. No missing channel is relabelled.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import scipy
from scipy.signal import butter, iirnotch, resample_poly, sosfilt, tf2sos
from threadpoolctl import threadpool_limits


HERE = Path(__file__).resolve().parent
REFERENCE = Path(r"D:\ican\ican_fpga_project\software\pc_fatigue_reference")
sys.path.insert(0, str(REFERENCE))
from fatigue_reference import (DEPLOYMENT_DE_BANDS, channel_indices,
                               extract_band_de_features, load_seedvig_subject)
from validate_seedvig_loso import DEFAULT_DATASET_ROOT, discover_pairs
from train_seedvig_8ch_calibrated_loso import (CALIBRATION_WINDOWS,
                                               MODEL_PARAMETERS, make_model)
from evaluate_fixed_cyton_fatigue import evaluate
from train_seedvig_8ch_calibrated_loso import portable_predict


CHANNELS = ("T7", "T8", "O1", "O2")
VERSION = "cyton250_notch50q5_bp1-45_de5_overlap4_v1"


def preprocess(eeg, source_rate):
    if source_rate != 200:
        raise ValueError(f"Expected SEED-VIG 200 Hz source, got {source_rate}")
    values = resample_poly(eeg, 5, 4, axis=0)
    notch_b, notch_a = iirnotch(50.0, 5.0, 250)
    sos = np.vstack((tf2sos(notch_b, notch_a),
                     butter(4, (1.0, 45.0), btype="bandpass", fs=250, output="sos")))
    return sosfilt(sos, values, axis=0)


def make_cache(root, cache_dir):
    cache_dir.mkdir(parents=True, exist_ok=True)
    manifest = []
    for name, raw_path, label_path in discover_pairs(root):
        target = cache_dir / f"{name}.npz"
        signatures = (hashlib.sha256(raw_path.read_bytes()).hexdigest(),
                      hashlib.sha256(label_path.read_bytes()).hexdigest())
        if target.is_file():
            with np.load(target, allow_pickle=False) as item:
                if (str(item["version"].item()) == VERSION and
                    tuple(item["source_sha256"].tolist()) == signatures):
                    manifest.append({"recording": name, "source_sha256": signatures,
                                     "cache_sha256": hashlib.sha256(target.read_bytes()).hexdigest()})
                    continue
        subject = load_seedvig_subject(raw_path, label_path)
        if subject.window_seconds != 8:
            raise ValueError(f"Unexpected window length for {name}: {subject.window_seconds}")
        eeg = subject.eeg[:, channel_indices(subject.channel_names, CHANNELS)]
        filtered = preprocess(eeg, subject.sample_rate_hz)
        features = extract_band_de_features(
            filtered, channel_names=CHANNELS, sample_rate_hz=250,
            window_samples=2000, bands=DEPLOYMENT_DE_BANDS).values
        if features.shape != (len(subject.perclos), 20):
            raise ValueError(f"Feature/label mismatch for {name}")
        np.savez_compressed(target, version=VERSION, channels=CHANNELS,
                            source_sha256=signatures, features=features,
                            perclos=subject.perclos)
        manifest.append({"recording": name, "source_sha256": signatures,
                         "cache_sha256": hashlib.sha256(target.read_bytes()).hexdigest()})
        print(f"FEATURES {name} {features.shape}", flush=True)
    return manifest


def load_recordings(cache_dir):
    from train_seedvig_8ch_calibrated_loso import calibrate_recording, smooth_features
    recordings = {}
    for path in sorted(cache_dir.glob("*.npz")):
        with np.load(path, allow_pickle=False) as item:
            if str(item["version"].item()) != VERSION or tuple(item["channels"]) != CHANNELS:
                raise ValueError(f"Wrong feature cache: {path}")
            features = np.asarray(item["features"], dtype=np.float64)
            target = np.asarray(item["perclos"], dtype=np.float64)
        calibrated, _, _ = calibrate_recording(features)
        recordings[path.stem] = {
            "participant": path.stem.split("_", 1)[0],
            "target": target[CALIBRATION_WINDOWS:],
            "features": {"overlap4": smooth_features(calibrated[CALIBRATION_WINDOWS:])},
        }
    return recordings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_ROOT)
    parser.add_argument("--output", type=Path,
                        default=HERE / "output" / "cyton_montage_fatigue_v2")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = make_cache(args.dataset, args.output / "feature_cache")
    recordings = load_recordings(args.output / "feature_cache")
    protocol = {
        "version": VERSION, "participants": len({r["participant"] for r in recordings.values()}),
        "recordings": len(recordings), "channels": CHANNELS,
        "physical_channels": ("CH5", "CH6", "CH7", "CH8"),
        "validation": "participant-grouped LOSO; 15 calibration windows excluded",
        "preprocessing": "200-to-250 Hz resample; continuous 50 Hz Q5 notch; continuous 1-45 Hz order-4 bandpass; continuous five-band order-4 DE",
        "model": "HistGradientBoostingRegressor", "parameters": MODEL_PARAMETERS,
        "numpy": np.__version__, "scipy": scipy.__version__,
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "manifest": manifest,
    }
    (args.output / "protocol.json").write_text(json.dumps(protocol, indent=2), encoding="utf-8")
    result = evaluate(recordings, "overlap4", args.output)
    (args.output / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"mean_subject": result["mean_subject"],
                      "pooled": result["pooled"]}, indent=2), flush=True)
    if result["mean_subject"]["pcc"] <= 0:
        return
    x = np.concatenate([r["features"]["overlap4"] for r in recordings.values()])
    y = np.concatenate([r["target"] for r in recordings.values()])
    with threadpool_limits(limits=1):
        model = make_model().fit(x, y)
    joblib.dump(model, args.output / "overlap4_deployment_candidate.joblib")
    trees = []
    for stage in model._predictors:
        nodes = stage[0].nodes
        trees.append([[float(node["value"]), int(node["feature_idx"]),
                       float(node["num_threshold"]), int(node["left"]),
                       int(node["right"]), bool(node["missing_go_to_left"]),
                       bool(node["is_leaf"])] for node in nodes])
    portable = {
        "format": "cyton_fatigue_hgb_v1", "version": VERSION,
        "channels": CHANNELS, "physical_indices": (4, 5, 6, 7),
        "bands_hz": DEPLOYMENT_DE_BANDS,
        "calibration_windows": CALIBRATION_WINDOWS,
        "window_seconds": 8, "hop_seconds": 8,
        "ema_alpha": 0.25, "thresholds": (0.35, 0.70),
        "baseline_prediction": float(model._baseline_prediction[0, 0]),
        "trees": trees,
    }
    candidate = x[:200]
    expected = model.predict(candidate)
    actual = portable_predict(model, candidate)
    if not np.allclose(expected, actual, rtol=0, atol=1e-11):
        raise AssertionError("Portable HGB traversal differs from sklearn")
    path = args.output / "cyton_fatigue_overlap4.json"
    path.write_text(json.dumps(portable, separators=(",", ":")), encoding="utf-8")
    print(f"PORTABLE_MODEL: {path} bytes={path.stat().st_size} "
          f"parity_max_abs={float(np.max(np.abs(expected - actual))):.3g}", flush=True)


if __name__ == "__main__":
    main()
