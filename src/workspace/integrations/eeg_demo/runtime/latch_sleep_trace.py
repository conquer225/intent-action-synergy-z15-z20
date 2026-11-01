"""ctypes adapter for the isolated, observation-only nanosleep interceptor."""
import ctypes as C
import os
from pathlib import Path


class SleepStats(C.Structure):
    _fields_ = [(name, C.c_uint64) for name in (
        'calls', 'interrupted', 'requested_ns', 'actual_ns', 'max_actual_ns',
        'max_requested_ns', 'max_start_ns', 'max_end_ns', 'cpu_ns',
        'voluntary_switches', 'involuntary_switches')]
    _fields_.append(('bins', C.c_uint64 * 8))


class SleepTrace:
    def __init__(self, path):
        if os.environ.get('LD_PRELOAD') != str(Path(path)):
            raise RuntimeError('Trace must be preloaded into this isolated process only')
        self.lib = C.CDLL(str(path))
        self.lib.gl_trace_ready.restype = C.c_int
        self.lib.gl_trace_begin.argtypes = []
        self.lib.gl_trace_begin.restype = None
        self.lib.gl_trace_end.argtypes = [C.POINTER(SleepStats)]
        self.lib.gl_trace_end.restype = None
        if not self.lib.gl_trace_ready():
            raise RuntimeError('Original nanosleep symbol did not resolve')

    def begin(self):
        self.lib.gl_trace_begin()

    def end(self):
        stats = SleepStats()
        self.lib.gl_trace_end(C.byref(stats))
        result = {name: int(getattr(stats, name)) for name, _ in stats._fields_ if name != 'bins'}
        result['bins'] = list(stats.bins)
        return result


def selftest(path):
    """No hardware: verify interposition, requested duration and thread locality."""
    import json
    import threading
    import time
    trace = SleepTrace(path)
    libc = C.CDLL(None)
    class Timespec(C.Structure):
        _fields_ = [('tv_sec', C.c_long), ('tv_nsec', C.c_long)]
    libc.nanosleep.argtypes = [C.POINTER(Timespec), C.POINTER(Timespec)]
    libc.nanosleep.restype = C.c_int
    request = Timespec(0, 100000)
    started = time.monotonic_ns()
    trace.begin()
    for _ in range(100):
        if libc.nanosleep(C.byref(request), None):
            raise RuntimeError('Original nanosleep failed in software test')
    result = trace.end()
    wall_ns = time.monotonic_ns() - started
    if (result['calls'] != 100 or result['requested_ns'] != 10000000
            or sum(result['bins']) != 100 or result['actual_ns'] < result['requested_ns']
            or not 0 < result['actual_ns'] <= wall_ns):
        raise RuntimeError('Interposition accounting self-test failed')
    trace.begin()
    worker = threading.Thread(target=lambda:libc.nanosleep(C.byref(request), None))
    worker.start()
    worker.join()
    if trace.end()['calls'] != 0:
        raise RuntimeError('Sleep accounting leaked across threads')
    print(json.dumps(dict(software_only=True, result=result, wall_ns=wall_ns,
                          thread_local=True, original_sleep_unchanged=True)))


if __name__ == '__main__':
    import sys
    selftest(sys.argv[1])
