"""Post-result exploratory channel-pair diagnosis; NOT a model-selection result.

This inspects the same 12 participants after the frozen eight-versus-two result
was known. Any apparent winner needs independent participants/dataset.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from ssvep_wang_fixed8 import DATASET, PROTOCOL, _filter_window, _load_subject, _read_frequency_order
from ssvep_wearable_baseline import _reference_q, cca_scores


MONTAGES = {
    "O1_O2": [6, 7],
    "O1_O2_plus_F3_F4": [0, 1, 6, 7],
    "O1_O2_plus_C3_C4": [2, 3, 6, 7],
    "O1_O2_plus_T7_T8": [4, 5, 6, 7],
    "fixed_eight": list(range(8)),
}


def run(dataset: Path, protocol_path: Path) -> dict:
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    frequencies = _read_frequency_order(dataset / "Freq_Phase.mat", protocol)
    seconds = protocol["primary_task"]["window_seconds"]
    fs = protocol["sample_rate_hz"]
    refs = _reference_q(frequencies.tolist(), seconds * fs, fs, protocol["cca_harmonics"])
    target_ids = np.array(protocol["primary_task"]["target_indices_zero_based"])
    truth = np.tile(np.arange(40), 6)
    eligible = np.isin(truth, target_ids)
    result = []
    for subject in protocol["evaluation_subjects_predeclared"]:
        eeg = _filter_window(_load_subject(dataset / f"S{subject}.mat", protocol), seconds, protocol)
        entry = {"subject": subject}
        for name, indices in MONTAGES.items():
            scores, valid = cca_scores(eeg[:, indices, :], refs)
            prediction = target_ids[np.argmax(np.nan_to_num(scores[:, target_ids], nan=-1), axis=1)]
            entry[name] = float(np.mean((prediction[eligible] == truth[eligible]) & valid[eligible]))
        result.append(entry)
    baseline = np.array([row["O1_O2"] for row in result])
    summaries = []
    for name in MONTAGES:
        observed = np.array([row[name] for row in result])
        difference = observed - baseline
        summaries.append({"montage": name, "mean_accuracy": float(observed.mean()),
                          "mean_difference_from_O1_O2": float(difference.mean()),
                          "subjects_improved": int(np.count_nonzero(difference > 0)),
                          "subjects_worsened": int(np.count_nonzero(difference < 0))})
    return {"status": "exploratory_posthoc_not_confirmatory", "per_subject": result,
            "summary": summaries,
            "warning": "These montages were evaluated after seeing the frozen result; do not deploy a selected pair from this output without independent confirmation."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--protocol", type=Path, default=PROTOCOL)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.dataset, args.protocol)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
