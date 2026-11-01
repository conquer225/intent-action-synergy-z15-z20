"""Isolated SSVEP component timing on the already-staged non-wear bench input."""
import json
from pathlib import Path
import time

import numpy as np

from ssvep_shadow import SSVEPShadow


def main():
    base = Path(__file__).resolve().parent
    production = Path('/home/xilinx/jupyter_notebooks/guardianloop_pynq')
    with np.load(base / 'input.npz') as data:
        values = data['recorded']
        sequence = data['recorded_seq']
    status = base / 'micro_ssvep_status.json'
    candidate = SSVEPShadow(production / 'ssvep_causal_protocol.json',
                            production / 'ssvep_candidate_sos.npy',
                            ('F3','F4','C3','C4','T7','T8','O1','O2'),
                            source='replay', status_path=status)
    started = time.perf_counter()
    events = 0
    for index, (row, seq) in enumerate(zip(values, sequence)):
        events += len(candidate.packet(row, int(seq), now=index / 250,
                       adc_rails=(False, False)))
    elapsed = time.perf_counter() - started
    result = {'source': '2026-09-20 non-wear bench; no live USB or PL',
              'samples': len(values), 'events': events,
              'packet_loop_wall_s': elapsed,
              'stream_filter_wall_s': candidate.stream.filter_seconds,
              'stream_decision_wall_s': candidate.stream.decode_seconds,
              'other_wall_s': elapsed-candidate.stream.filter_seconds-candidate.stream.decode_seconds,
              'final_state': candidate.latest['state']}
    (base / 'micro_ssvep_report.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
