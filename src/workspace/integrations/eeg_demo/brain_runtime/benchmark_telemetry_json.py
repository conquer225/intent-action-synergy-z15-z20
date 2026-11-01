"""Alternating full/cache publication using generated waveforms, without USB/PL."""
import json
from pathlib import Path
import tempfile
import time

import numpy as np

from cyton_guardianloop import publish_telemetry
from telemetry_json import WaveformJSONCache


def main():
    repeats = 24
    values = np.random.default_rng(54).normal(0, 50, (625+repeats*63, 8))
    samples = {'full': [], 'cache': []}
    cache = WaveformJSONCache()
    with tempfile.TemporaryDirectory(prefix='gl-telemetry-json-', dir='/dev/shm') as directory:
        path = Path(directory)/'waveforms.json'
        for index in range(repeats+1):
            start = index*63
            rows = values[start:start+625]
            payloads = []
            for name, encoder in (('full', None), ('cache', cache)):
                cpu, wall = time.thread_time(), time.monotonic()
                publish_telemetry(rows, rows*1000, start+625, path, start*2+1250,
                                  0, 0, 0, 0, 0, None, None, 100.+index, {},
                                  waveform_cache=encoder)
                elapsed = dict(cpu_ms=(time.thread_time()-cpu)*1000,
                               wall_ms=(time.monotonic()-wall)*1000)
                if index:
                    samples[name].append(elapsed)
                payloads.append(json.loads(path.read_text()))
            assert payloads[0] == payloads[1]
        assert cache.reused_rows == 562
    result = dict(exact_decoded_payload_parity=True, repeats_per_case=repeats,
                  reused_rows_of_625=cache.reused_rows,
                  scope='Generated waveform publication to private tmpfs only; not whole-service or optical timing',
                  timings={name:{metric:dict(median=float(np.median([v[metric] for v in times])),
                                            p95=float(np.quantile([v[metric] for v in times], .95)))
                                 for metric in ('cpu_ms', 'wall_ms')}
                           for name, times in samples.items()})
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
