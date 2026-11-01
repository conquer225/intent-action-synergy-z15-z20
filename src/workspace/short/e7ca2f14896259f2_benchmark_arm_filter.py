"""Read-only component microbenchmark; run with production module on sys.path."""
import argparse
import json
import platform
import sys
import time

import numpy as np


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--production', required=True)
    p.add_argument('--input', required=True)
    args = p.parse_args()
    sys.path.insert(0, args.production)
    from cyton_sqi import CausalEEGFilter
    with np.load(args.input) as z:
        raw = z['recorded']
    result = dict(scope='ARM primary-filter-only microbenchmark; production service NOT stopped; no DMA or PL',
                  python=platform.python_version(), machine=platform.machine(), samples=len(raw),
                  sos=CausalEEGFilter().sos.tolist(), batch_samples=10, rounds=[])
    for _ in range(3):
        filt = CausalEEGFilter()
        elapsed, cpu = [], []
        quantization = []
        for start in range(0,len(raw),10):
            block = raw[start:start+10]
            began, cpu_start = time.perf_counter(), time.process_time()
            filt.process(block)
            elapsed.append(time.perf_counter()-began)
            cpu.append(time.process_time()-cpu_start)
            # Candidate PS packing estimate only: 64-bit words for signed 40-bit data.
            began = time.perf_counter()
            scaled = (block-raw[0])*65536
            packed = np.copysign(np.floor(np.abs(scaled)+.5), scaled).astype(np.int64)
            if packed.shape != block.shape:
                raise AssertionError('Packing shape')
            quantization.append(time.perf_counter()-began)
        result['rounds'].append(dict(cpu_s=sum(cpu),wall_s=sum(elapsed),
            filter_batch_p50_us=float(np.quantile(elapsed,.5)*1e6),
            filter_batch_p95_us=float(np.quantile(elapsed,.95)*1e6),
            pack_batch_p50_us=float(np.quantile(quantization,.5)*1e6),
            pack_batch_p95_us=float(np.quantile(quantization,.95)*1e6)))
    print(json.dumps(result))


if __name__ == '__main__':
    main()
