"""Bounded synthetic pipe throughput; excludes EEG calculations and display."""
import json
import multiprocessing
import os
import resource
import time

from cyton_guardianloop import CytonReaderError, packets


def run(batch_samples, count=20000):
    r, w = os.pipe()

    def produce():
        os.close(r)
        for first in range(0, count, 10):
            block = b''.join(bytes((0xA0, i % 256))+bytes(30)+bytes((0xC0,))
                             for i in range(first, first+10))
            view = memoryview(block)
            while view:
                view = view[os.write(w, view):]
        os.close(w)

    parent_before = time.process_time()
    children_before = resource.getrusage(resource.RUSAGE_CHILDREN)
    started = time.monotonic()
    producer = multiprocessing.get_context('fork').Process(target=produce)
    producer.start()
    os.close(w)
    # This unpaced benchmark may enqueue the whole finite input. Production
    # keeps its original capacity; queue saturation is tested separately.
    reader = packets(r, 2, with_timing=True, queue_capacity=count,
                     reader_batch_samples=batch_samples)
    consumed = 0
    report = None
    try:
        while True:
            try:
                frame, malformed, received_at = next(reader)
            except CytonReaderError as exc:
                if exc.report['kind'] != 'serial_eof':
                    raise
                report = exc.report
                break
            if frame[1] != consumed % 256 or malformed or received_at > time.monotonic():
                raise AssertionError('IPC changed packet order, flags, or timestamps')
            consumed += 1
    finally:
        reader.close(); os.close(r)
        producer.join(timeout=2)
        if producer.is_alive():
            producer.terminate(); producer.join(timeout=2)
            raise RuntimeError('Synthetic producer exceeded its deadline')
    if consumed != count or producer.exitcode != 0:
        raise AssertionError('Synthetic input incomplete')
    children_after = resource.getrusage(resource.RUSAGE_CHILDREN)
    return dict(batch_samples=batch_samples, packets=consumed,
                queue_dispatches=report['queue_dispatches'],
                wall_seconds=time.monotonic()-started,
                parent_cpu_seconds=time.process_time()-parent_before,
                children_cpu_seconds=(children_after.ru_utime+children_after.ru_stime
                                      -children_before.ru_utime-children_before.ru_stime))


if __name__ == '__main__':
    print(json.dumps(dict(scope='Synthetic pipe IPC only; not live latency or video performance',
                         runs=[run(size) for size in (1, 10, 1, 10)]), indent=2))
