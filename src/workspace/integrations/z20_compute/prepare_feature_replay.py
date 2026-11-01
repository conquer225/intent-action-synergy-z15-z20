"""Tap actual classifier inputs from the frozen original preprocessing."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from z20_compute.legacy_eeg import LegacyEEGFeatures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recording', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    data = np.load(args.recording, allow_pickle=False)
    adapter, records = LegacyEEGFeatures(), []
    for offset in range(0, len(data), 500):
        for record in adapter.feed(data[offset:offset+500]):
            if record['features'] is not None:
                record['features'] = record['features'].tolist()
                record['end_sample'] = offset+500
                records.append(record)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(dict(
        source='LEMON recorded EEG; no emotion/fatigue truth labels',
        source_sha256=hashlib.sha256(args.recording.read_bytes()).hexdigest(),
        sample_rate_hz=250, records=records)), encoding='utf-8')
    print(json.dumps(dict(records=len(records), output=str(args.output))))


if __name__ == '__main__': main()
