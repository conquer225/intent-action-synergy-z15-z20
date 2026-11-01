"""Read-only screening of saved GUI EEG; never treats unlabelled CHs as verified cap sites."""
import json
import hashlib
import sys
from pathlib import Path

import numpy as np

from run_soak_stage import ROOT
from cyton_sqi import CausalEEGFilter, CytonSQIMonitor, channel_sqi


SOURCE = Path(r"C:\Users\lenovo\Documents\OpenBCI_GUI\Recordings")
OUT = ROOT / "eeg_apps_z15/output/gui_recording_inventory_20260927"
GROUPS = {"emotion6": (0, 1, 4, 5, 6, 7),
          "fatigue4": (4, 5, 6, 7), "ssvep2": (6, 7),
          "seed8": tuple(range(8))}
SEGMENT = 500


def longest_run(flags):
    best = current = 0
    for good in flags:
        current = current + 1 if good else 0
        best = max(best, current)
    return best


def inspect(path):
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if path.stat().st_size < 1024:
        return {"path": str(path), "sha256": digest, "bytes": path.stat().st_size,
                "sample_rate_hz_header": 250, "samples": 0, "duration_seconds": 0,
                "sequence_discontinuities": 0,
                "raw_adc_near_rail_fraction_by_ch": [None] * 8,
                "nonfinite_fraction_by_ch": [None] * 8,
                "screening_note": "header-only file; no EEG samples",
                "groups": {key: {"good_segments_2s": 0,
                                 "longest_contiguous_good_seconds": 0}
                           for key in GROUPS}}
    data = np.loadtxt(path, delimiter=",", skiprows=5, usecols=range(9))
    if data.ndim == 1:
        data = data[None, :]
    samples = data[:, 1:9]
    packet = data[:, 0].astype(np.int64)
    gaps = np.flatnonzero(np.diff(packet) % 256 != 1) + 1
    # This is only a screening proxy: the live service evaluates overlapping
    # 8-second windows with independent calibration and gap-reset policies.
    n = len(samples) // SEGMENT
    filtered = CausalEEGFilter().process(samples)
    monitor = CytonSQIMonitor()
    good = np.zeros((n, 8), dtype=bool)
    raw_rails = np.mean(np.abs(samples) >= .95 * 187500, axis=0)
    invalid = np.mean(~np.isfinite(samples), axis=0)
    for i in range(n):
        raw = samples[i * SEGMENT:(i + 1) * SEGMENT]
        processed = filtered[i * SEGMENT:(i + 1) * SEGMENT]
        if not np.isfinite(raw).all() or not np.isfinite(processed).all():
            continue
        descriptor = channel_sqi(processed)
        quality = monitor._heuristic_quality(descriptor)
        hard_bad = (descriptor[:, 2] >= .95) | (descriptor[:, 3] > .001)
        raw_rail = np.any(np.abs(raw) >= .95 * 187500, axis=0)
        segment_gap = np.any((gaps > i * SEGMENT) & (gaps < (i + 1) * SEGMENT))
        good[i] = (quality >= .5) & ~hard_bad & ~raw_rail & ~segment_gap
    groups = {}
    for name, indices in GROUPS.items():
        flag = np.all(good[:, indices], axis=1)
        groups[name] = {"good_segments_2s": int(flag.sum()),
                        "longest_contiguous_good_seconds": 2 * longest_run(flag)}
    return {"path": str(path), "sha256": digest, "bytes": path.stat().st_size,
            "sample_rate_hz_header": 250, "samples": len(samples),
            "duration_seconds": len(samples) / 250,
            "sequence_discontinuities": len(gaps),
            "raw_adc_near_rail_fraction_by_ch": np.round(raw_rails, 6).tolist(),
            "nonfinite_fraction_by_ch": np.round(invalid, 6).tolist(),
            "screening_note": "2s nonoverlap heuristic only; not exact live calibration or labels",
            "groups": groups}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    files = sorted(SOURCE.rglob("OpenBCI-RAW-*.txt"))
    # September 20 is documented as bench contact/rail experiments. Only the
    # September 23 18:59 file has a previous user-declared fixed-cap mapping;
    # the GUI headers themselves never prove electrode positions.
    other = "--other" in sys.argv[1:]
    bench = "--bench" in sys.argv[1:]
    if other and bench:
        raise SystemExit("Choose only one inventory subset")
    if bench:
        files = [file for file in files if "2026-09-20" in str(file)]
    elif other:
        files = [file for file in files if "2026-09-23" not in str(file)
                 and "2026-09-20" not in str(file)]
    else:
        files = [file for file in files if "2026-09-23" in str(file)]
    result = [inspect(file) for file in files]
    name = "bench_screening.json" if bench else ("other_screening.json" if other else "sep23_screening.json")
    (OUT / name).write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    for item in result:
        print(json.dumps({"file": Path(item["path"]).name,
                          "session": Path(item["path"]).parent.name,
                          "seconds": item["duration_seconds"],
                          "gaps": item["sequence_discontinuities"],
                          "max_good_s": {key: value["longest_contiguous_good_seconds"]
                                         for key, value in item["groups"].items()}},
                         ensure_ascii=False))


if __name__ == "__main__":
    main()
