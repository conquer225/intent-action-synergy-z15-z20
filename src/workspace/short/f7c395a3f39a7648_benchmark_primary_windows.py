"""Recorded-path array conversion benchmark; no acquisition or PL construction."""
from collections import deque
import json
import time

import numpy as np

from cyton_sqi import primary_windows, segmented_sqi
from test_primary_windows import reference, sequential_sqi


def main():
    rng = np.random.default_rng(49)
    raw = deque(rng.integers(-2**23, 2**23, (2000, 8)), maxlen=2000)
    filtered = deque(rng.normal(0, 50, (2000, 8)), maxlen=2000)
    for before, after in zip(reference(raw, filtered, .022351744455),
                             primary_windows(raw, filtered, .022351744455)):
        np.testing.assert_array_equal(after, before)
    samples = dict(reference=[], candidate=[])
    for _ in range(24):
        for label, function in (('reference', reference), ('candidate', primary_windows)):
            start = time.thread_time()
            function(raw, filtered, .022351744455)
            samples[label].append((time.thread_time() - start) * 1000)
    result = dict(exact_parity=True, repeats_per_case=24,
        conversion_cpu_ms={key:dict(median=float(np.median(value)),
            p95=float(np.quantile(value, .95))) for key, value in samples.items()},
        scope='Array snapshots and SQI descriptors only; not full service timing or recognition accuracy')
    values = np.asarray(filtered)
    samples = dict(reference=[], candidate=[])
    for _ in range(24):
        for label, function in (('reference', sequential_sqi), ('candidate', segmented_sqi)):
            start = time.thread_time()
            function(values, 500)
            samples[label].append((time.thread_time() - start) * 1000)
    result.update(descriptor_max_error=float(np.max(np.abs(
        sequential_sqi(values, 500) - segmented_sqi(values, 500)))),
        sqi_cpu_ms={key:dict(median=float(np.median(value)), p95=float(np.quantile(value, .95)))
            for key, value in samples.items()})
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
