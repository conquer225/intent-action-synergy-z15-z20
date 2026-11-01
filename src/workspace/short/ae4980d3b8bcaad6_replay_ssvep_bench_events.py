"""Collect deterministic SSVEP event fields from isolated non-wear NPZ replay."""
import argparse
import json
from pathlib import Path

import numpy as np

from ssvep_shadow import CHANNELS, SSVEPShadow


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    production = Path('/home/xilinx/jupyter_notebooks/guardianloop_pynq')
    shadow = SSVEPShadow(production/'ssvep_causal_protocol.json',
                         production/'ssvep_candidate_sos.npy', CHANNELS,
                         source='replay', status_path=args.output/'status.json')
    with np.load(args.input) as data:
        samples, sequences = data['recorded'], data['recorded_seq']
    events = []
    for index, (row, sequence) in enumerate(zip(samples, sequences)):
        results = shadow.packet(row, int(sequence), now=index/250,
                                adc_rails=np.abs(row[6:8]) >= 187500*.99)
        for event in results:
            events.append({key: event.get(key) for key in
                ('state','reason','window_start_index','window_end_index_exclusive',
                 'frequency_hz','target_index','scores','margin','quality',
                 'control_enabled','sequence_gaps')})
    (args.output/'events.json').write_text(json.dumps(events, allow_nan=False))
    print(json.dumps({'samples': len(samples), 'events': len(events),
                      'gaps': shadow.gaps, 'final_state': shadow.latest['state']}), flush=True)


if __name__ == '__main__':
    main()
