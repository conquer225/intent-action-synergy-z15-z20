"""Isolated timing of production SSVEP substeps on a non-wear bench trace."""
import json
from pathlib import Path
import time

import numpy as np

from ssvep_shadow import SSVEPShadow


def main():
    base = Path(__file__).resolve().parent
    prod = Path('/home/xilinx/jupyter_notebooks/guardianloop_pynq')
    with np.load(base / 'input.npz') as data:
        values, sequence = data['recorded'], data['recorded_seq']
    shadow = SSVEPShadow(prod/'ssvep_causal_protocol.json', prod/'ssvep_candidate_sos.npy',
                         ('F3','F4','C3','C4','T7','T8','O1','O2'),
                         source='replay', status_path=base/'detail_status.json')
    stats = {}

    def wrap(owner, name, label):
        original = getattr(owner, name)
        row = stats[label] = {'calls': 0, 'wall_s': 0.0, 'cpu_s': 0.0, 'max_wall_ms': 0.0}

        def measured(*args, **kwargs):
            start, cpu = time.perf_counter(), time.thread_time()
            try:
                return original(*args, **kwargs)
            finally:
                duration = time.perf_counter() - start
                row['calls'] += 1
                row['wall_s'] += duration
                row['cpu_s'] += time.thread_time() - cpu
                row['max_wall_ms'] = max(row['max_wall_ms'], duration*1000)

        setattr(owner, name, measured)

    for owner, method, label in ((shadow, '_quality', 'quality'),
                                  (shadow.stream, 'push', 'stream_push'),
                                  (shadow.stream, '_decision', 'decision')):
        wrap(owner, method, label)
    import ssvep_shadow
    wrap(ssvep_shadow, 'atomic_json', 'write_event')
    if hasattr(shadow.stream, 'cca'):
        wrap(shadow.stream.cca, 'scores', 'cca_scores')
    else:
        import ssvep_stream
        wrap(ssvep_stream, 'canonical_correlation', 'cca_scalar')
    started = time.perf_counter()
    for index, (sample, seq) in enumerate(zip(values, sequence)):
        shadow.packet(sample, int(seq), now=index/250, adc_rails=(False, False))
    output = {'source': 'non-wear bench, isolated component, not paced',
              'samples': len(values), 'total_wall_s': time.perf_counter()-started,
              'steps': stats, 'filter_wall_s': shadow.stream.filter_seconds,
              'decision_wall_s': shadow.stream.decode_seconds}
    (base/'detail_report.json').write_text(json.dumps(output, indent=2))
    print(json.dumps(output), flush=True)


if __name__ == '__main__':
    main()
