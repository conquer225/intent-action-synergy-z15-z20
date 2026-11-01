"""Build audited fixed-eight MPD-DF features and boundary-safe labels."""

import argparse
import bisect
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from scipy.signal import butter, iirnotch, resample_poly, sosfilt, tf2sos


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "vendor"))
sys.path.insert(0, str(Path(r"D:\ican\ican_fpga_project\software\pc_fatigue_reference")))
import edfio
from fatigue_reference import DEPLOYMENT_DE_BANDS, extract_band_de_features


VERSION = "mpddf250_notch50q5_bp1-45_de5_fixed8_v1"
CHANNELS = ("F3", "F4", "C3", "C4", "T7", "T8", "O1", "O2")
ROOT = Path(r"D:\ican\datasets\MPD-DF\raw_eeg")
OUTPUT = HERE / "output" / "mpddf_fixed_cap_v1" / "feature_cache"


def md5(path):
    result = hashlib.md5()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def parse_annotations(path):
    times, labels = [], []
    mapping = {"Signal Abnormality": 8, "Severe Artifacts": 9}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        time_text, _, label_text = line.split(",", 2)
        hour, minute, second = [int(value) for value in time_text.split(":")]
        times.append(hour * 3600 + minute * 60 + second)
        labels.append(mapping.get(label_text.strip(), int(label_text) if label_text.strip().isdigit() else -1))
    if not times or times != sorted(set(times)):
        raise ValueError(f"Invalid annotation times: {path}")
    return times, labels


def align_labels(times, labels, start_sec, window_count):
    # Use only windows that lie wholly inside one annotation interval.
    window_labels = np.full(window_count, -1, dtype=np.int8)
    reason = {"before_annotation": 0, "boundary": 0, "artifact_or_unknown": 0}
    for index in range(window_count):
        start = start_sec + 8 * index
        stop = start + 8
        interval = bisect.bisect_right(times, start) - 1
        if interval < 0:
            reason["before_annotation"] += 1
        elif interval + 1 < len(times) and stop > times[interval + 1]:
            reason["boundary"] += 1
        elif labels[interval] not in (0, 1, 2, 3, 4):
            reason["artifact_or_unknown"] += 1
        else:
            window_labels[index] = labels[interval]
    return window_labels, reason


def prepare_one(identifier, root, output, item_lookup):
    name = f"MPDDF_raw_{identifier}"
    eeg_path = root / f"{name}_EEG.edf"
    label_path = root / f"{name}_Annotation.txt"
    target = output / f"subject_{identifier}.npz"
    expected = [item_lookup[path.name] for path in (eeg_path, label_path)]
    for path, item in zip((eeg_path, label_path), expected):
        if path.stat().st_size != item["size"] or md5(path) != item["computed_md5"]:
            raise ValueError(f"Unverified source: {path}")
    if target.is_file():
        with np.load(target, allow_pickle=False) as item:
            if (str(item["version"].item()) == VERSION and
                tuple(item["source_md5"].tolist()) == tuple(x["computed_md5"] for x in expected)):
                return {"subject": identifier, "windows": len(item["labels"]),
                        "valid": int(np.sum(item["labels"] >= 0)),
                        "cache_sha256": hashlib.sha256(target.read_bytes()).hexdigest()}

    edf = edfio.read_edf(eeg_path, lazy_load_data=True)
    if not set(CHANNELS).issubset(edf.labels):
        raise ValueError(f"Required channels missing for {identifier}: {edf.labels}")
    if any(edf.get_signal(channel).sampling_frequency != 500 for channel in CHANNELS):
        raise ValueError(f"Unexpected sample rate for {identifier}")
    length = min(len(edf.get_signal(channel).data) for channel in CHANNELS)
    eeg = np.column_stack([edf.get_signal(channel).data[:length] for channel in CHANNELS])
    eeg250 = resample_poly(eeg, 1, 2, axis=0)
    window_count = len(eeg250) // 2000
    eeg250 = eeg250[:window_count * 2000]
    notch_b, notch_a = iirnotch(50.0, 5.0, 250)
    sos = np.vstack((tf2sos(notch_b, notch_a),
                     butter(4, (1.0, 45.0), btype="bandpass", fs=250, output="sos")))
    filtered = sosfilt(sos, eeg250, axis=0)
    del eeg, eeg250
    features = extract_band_de_features(
        filtered, channel_names=CHANNELS, sample_rate_hz=250,
        window_samples=2000, bands=DEPLOYMENT_DE_BANDS).values
    times, labels = parse_annotations(label_path)
    start = edf.startdatetime
    start_sec = start.hour * 3600 + start.minute * 60 + start.second
    aligned, reasons = align_labels(times, labels, start_sec, window_count)
    if not np.any(aligned >= 0) or not np.all(np.isfinite(features)):
        raise ValueError(f"No valid aligned features for {identifier}")
    np.savez_compressed(target, version=VERSION, subject=identifier,
                        channels=CHANNELS, source_md5=[x["computed_md5"] for x in expected],
                        features=features, labels=aligned,
                        window_start_seconds=start_sec + 8 * np.arange(window_count),
                        excluded_reasons=json.dumps(reasons))
    return {"subject": identifier, "windows": window_count,
            "valid": int(np.sum(aligned >= 0)), "labels": np.unique(aligned, return_counts=True),
            "excluded_reasons": reasons,
            "cache_sha256": hashlib.sha256(target.read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--ids", nargs="*", default=None)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((args.root / "manifest.json").read_text(encoding="utf-8"))
    lookup = {item["name"]: item for item in manifest["files"]}
    ids = [f"{int(value):02d}" for value in args.ids] if args.ids else [f"{i:02d}" for i in range(1, 51)]
    for identifier in ids:
        result = prepare_one(identifier, args.root, args.output, lookup)
        print(f"PREPARED {identifier} windows={result['windows']} valid={result['valid']} "
              f"sha256={result['cache_sha256'][:16]}", flush=True)


if __name__ == "__main__":
    main()
