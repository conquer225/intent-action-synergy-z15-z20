"""Audit licensed DEAP Python files for the Z15's immutable eight-electrode montage.

Run only on DEAP files obtained under the dataset's signed user agreement.
No fitting, normalization, or feature selection is done by this preflight.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import re
from pathlib import Path

import numpy as np


# Geneva order in DEAP's preprocessed Python files, as used by the TSception
# authors' DEAP preparation code. Never substitute the GAMEEMO channel order.
DEAP_CHANNELS = (
    "Fp1", "AF3", "F3", "F7", "FC5", "FC1", "C3", "T7",
    "CP5", "CP1", "P3", "P7", "PO3", "O1", "Oz", "Pz",
    "Fp2", "AF4", "Fz", "F4", "F8", "FC6", "FC2", "Cz",
    "C4", "T8", "CP6", "CP2", "P4", "P8", "PO4", "O2",
)
CYTON_CHANNELS = ("F3", "F4", "C3", "C4", "T7", "T8", "O1", "O2")
DEAP_INDICES = tuple(DEAP_CHANNELS.index(name) for name in CYTON_CHANNELS)
EXPECTED_DATA_SHAPE = (40, 40, 8064)
EXPECTED_LABEL_SHAPE = (40, 4)
TASK_COLUMNS = {"valence": 0, "arousal": 1}
DEV_SUBJECTS = tuple(range(1, 25))
HOLDOUT_SUBJECTS = tuple(range(25, 33))


def subject_paths(root: Path) -> list[Path]:
    if not root.is_dir():
        raise FileNotFoundError(f"DEAP directory not found: {root}")
    paths = sorted(root.glob("s[0-9][0-9].dat"))
    numbers = [int(re.fullmatch(r"s(\d{2})\.dat", path.name).group(1))
               for path in paths]
    if numbers != list(range(1, 33)):
        missing = sorted(set(range(1, 33)) - set(numbers))
        extra = sorted(set(numbers) - set(range(1, 33)))
        raise ValueError(f"expected DEAP s01.dat–s32.dat; missing={missing}, extra={extra}")
    return paths


def rating_counts(labels: np.ndarray, column: int) -> dict[str, int]:
    values = labels[:, column]
    return {"low": int(np.count_nonzero(values < 5)),
            "neutral_5_excluded": int(np.count_nonzero(values == 5)),
            "high": int(np.count_nonzero(values > 5))}


def inspect_subject(path: Path, reveal_ratings: bool = True) -> dict:
    # Python pickle can execute code: accept only the official, trusted archive.
    with path.open("rb") as stream:
        payload = pickle.load(stream, encoding="latin1")
    if not isinstance(payload, dict) or "data" not in payload or "labels" not in payload:
        raise ValueError(f"{path}: expected data/labels arrays")
    data = np.asarray(payload["data"])
    labels = np.asarray(payload["labels"])
    if data.shape != EXPECTED_DATA_SHAPE or labels.shape != EXPECTED_LABEL_SHAPE:
        raise ValueError(f"{path}: unexpected shapes {data.shape}, {labels.shape}")
    selected = data[:, DEAP_INDICES, :]
    if not np.isfinite(selected).all() or not np.isfinite(labels).all():
        raise ValueError(f"{path}: non-finite selected EEG or ratings")
    if np.any((labels < 1) | (labels > 9)):
        raise ValueError(f"{path}: ratings outside DEAP's 1–9 range")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    record = {"subject": int(path.stem[1:]), "filename": path.name,
              "sha256": digest.hexdigest(), "data_shape": list(data.shape),
              "selected_shape": list(selected.shape)}
    if reveal_ratings:
        record["ratings"] = {task: rating_counts(labels, column)
                             for task, column in TASK_COLUMNS.items()}
    return record


def audit(root: Path) -> dict:
    records = [inspect_subject(path, reveal_ratings=int(path.stem[1:]) in DEV_SUBJECTS)
               for path in subject_paths(root)]
    for record in records:
        if record["subject"] not in DEV_SUBJECTS:
            continue
        for task, counts in record["ratings"].items():
            if min(counts["low"], counts["high"]) == 0:
                raise ValueError(f"{task} development subject {record['subject']}: "
                                 f"one class is absent: {counts}")
    return {"dataset": "DEAP preprocessed Python, licensed copy",
            "montage": list(CYTON_CHANNELS), "deap_zero_based_indices": list(DEAP_INDICES),
            "reference_warning": "DEAP common-average reference differs from Cyton SRB2",
            "label_policy": "separate valence/arousal; <5 low, >5 high, 5 excluded",
            "development_subjects": list(DEV_SUBJECTS),
            "untouched_holdout_subjects": list(HOLDOUT_SUBJECTS),
            "holdout_rating_counts": "withheld until final evaluation",
            "records": records}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_dir", type=Path,
                        help="directory containing the licensed s01.dat ... s32.dat files")
    parser.add_argument("--output", type=Path,
                        default=Path(__file__).with_name("output") / "deap_fixed8" / "data_manifest.json")
    args = parser.parse_args()
    report = audit(args.data_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"DEAP_FIXED8_PREFLIGHT_OK: {len(report['records'])} subjects; "
          f"channels={','.join(CYTON_CHANNELS)}; manifest={args.output}")


if __name__ == "__main__":
    main()
