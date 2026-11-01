"""Physical NPU integer checks; fixed vectors are diagnostics, not trained models."""
import argparse
import json
from pathlib import Path
import statistics
import time
import numpy as np
from .npu import QuantizedMLP
from .backend import HardwareNPU
from .linux import UioRegisters, UioDmaAllocator


def check_vectors():
    w1 = np.zeros((32, 2), np.int8)
    w1[:4] = [[2, 1], [-1, 2], [100, -100], [1, -1]]
    b1 = np.zeros(32, np.int32); b1[1] = 1
    w2 = np.zeros((3, 32), np.int8)
    w2[0, 0], w2[1, 1:3], w2[2, 3] = 1, [1, 1], -1
    vectors = [(QuantizedMLP(w1, b1, w2, np.array([1, -2, 0], np.int32), hidden_shift=1),
                np.array([3, -2], np.int8), (3, 125, -3))]
    for size, shift, expected in [(20, 0, (-59, 247, -9)), (40, 2, (-91, 247, 1)),
                                   (180, 4, (-88, 247, 0)), (1024, 6, (-11, 121, -5))]:
        values = (np.arange(size) % 5-1).astype(np.int8)
        w1 = np.zeros((32, size), np.int8); w1[0] = 1; w1[1] = 2
        b1 = np.zeros(32, np.int32); b1[1:3] = [3, 4096]
        w2 = np.zeros((3, 32), np.int8)
        w2[0, :3] = [1, 1, -1]; w2[1, 2] = 2; w2[2, 0] = -1
        vectors.append((QuantizedMLP(w1, b1, w2, np.array([5, -7, 11], np.int32),
                                    hidden_shift=shift), values, expected))
    return vectors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repeat', type=int, default=10)
    args = parser.parse_args()
    if not 1 <= args.repeat <= 100: parser.error('repeat must be in 1..100')
    def device(name):
        candidates = [p for p in Path('/sys/class/uio').glob('uio*')
                      if (p/'name').read_text().strip() == name]
        if len(candidates) != 1: raise ValueError('expected one UIO device: '+name)
        return candidates[0]
    regdev, ramdev = device('navigator-mlp'), device('navigator-npu-dma')
    regs = UioRegisters('/dev/'+regdev.name, regdev/'maps/map0', expected_address=0x40000000)
    pool = UioDmaAllocator('/dev/'+ramdev.name, ramdev/'maps/map0',
                           '/proc/device-tree/reserved-memory/npu@2000000')
    accelerator = HardwareNPU(regs, pool, timeout=2)
    report = dict(board_executed=True, backend=accelerator.name, passed=False,
                  diagnostic_vectors=True, trained_classification_verified=False, cases=[])
    try:
        for model, values, expected in check_vectors():
            ps, pl, kernel = [], [], []
            for _ in range(args.repeat):
                start = time.monotonic(); reference = model.infer(values)
                ps.append(time.monotonic()-start)
                result = accelerator.infer(model, values)
                if result.tolist() != list(expected) or reference.tolist() != list(expected):
                    raise ValueError('integer mismatch at dimension '+str(len(values)))
                pl.append(accelerator.last_timing['total_seconds'])
                kernel.append(accelerator.last_timing['launch_to_done_seconds'])
            report['cases'].append(dict(dimension=len(values), output=list(expected),
                runs=args.repeat, ps_median_seconds=statistics.median(ps),
                pl_total_median_seconds=statistics.median(pl),
                launch_to_done_median_seconds=statistics.median(kernel)))
        accelerator.close(); pool.close(); regs.close()
        report['passed'] = True
    except BaseException as exc:
        report['error'] = type(exc).__name__+': '+str(exc)
        report['dma_ownership_unresolved'] = accelerator.poisoned
        # Do not release RAM after an unresolved hardware timeout.
        raise
    finally:
        args.output.write_text(json.dumps(report, indent=2))
        print(json.dumps(report), flush=True)


if __name__ == '__main__': main()
