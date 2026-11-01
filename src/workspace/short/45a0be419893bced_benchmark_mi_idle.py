"""Generated idle MI workload; no acquisition, web server, PL or model accuracy."""
import argparse
import hashlib
import json
import time

import numpy as np

from mi_rms_live_virtual import RMSVirtualSession


class Clock:
    value = 100.

    def __call__(self):
        return self.value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--defer-snapshot', action='store_true')
    args = parser.parse_args()
    clock = Clock()
    # An idle session never calls logits; a sentinel enables the same quality gate.
    session = RMSVirtualSession(object(), source='replay', clock=clock)
    indexes = np.arange(25000)
    values = 10*np.sin(2*np.pi*indexes[:, None]/250*np.arange(8, 16)[None])
    observations = []
    cpu = []
    wall = []
    for batch, start in enumerate(range(0, len(values), 50)):
        clock.value += .2
        before_wall, before_cpu = time.perf_counter(), time.process_time()
        options = dict(return_snapshot=False) if args.defer_snapshot else {}
        session.feed(values[start:start+50], indexes[start:start+50] % 256, **options)
        current = None
        # Match 2.5 Hz browser observation plus 1 Hz status observation.
        for query in (batch % 2 == 0, batch % 5 == 0):
            if query:
                current = session.snapshot()
        cpu.append((time.process_time()-before_cpu)*1000)
        wall.append((time.perf_counter()-before_wall)*1000)
        if current is not None:
            observations.append(current)
    encoded = json.dumps(observations, sort_keys=True, separators=(',', ':')).encode()
    print(json.dumps(dict(deferred=args.defer_snapshot, batches=500,
        represented_input_seconds=100, cpu_seconds=sum(cpu)/1000,
        cpu_percent_of_one_core=sum(cpu)/1000, cpu_batch_p50_ms=float(np.median(cpu)),
        cpu_batch_p95_ms=float(np.quantile(cpu, .95)), wall_batch_p95_ms=float(np.quantile(wall, .95)),
        observations=len(observations), snapshot_sha256=hashlib.sha256(encoded).hexdigest(),
        raw_sha256=hashlib.sha256(session.raw.tobytes()).hexdigest(),
        filtered_sha256=hashlib.sha256(session.filtered.tobytes()).hexdigest(),
        source='generated_idle_not_accuracy', usb_opened=False, pl_loaded=False)))


if __name__ == '__main__':
    main()
