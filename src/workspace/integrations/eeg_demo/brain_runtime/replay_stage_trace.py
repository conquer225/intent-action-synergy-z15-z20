"""Opt-in instrumentation for isolated replay, never a live-service dependency."""
from collections import defaultdict
import functools
import json
import time


class StageTrace:
    def __init__(self, slow_seconds=.020, max_slow_events=5000, thread_resources=False):
        if slow_seconds < 0 or max_slow_events < 0:
            raise ValueError('Trace limits must be nonnegative')
        self.started = time.monotonic()
        self.slow_seconds = slow_seconds
        self.max_slow_events = max_slow_events
        self.thread_usage = None
        if thread_resources:
            import resource
            self.thread_usage = functools.partial(resource.getrusage, resource.RUSAGE_THREAD)
        self.packet_index = -1
        self.stack = []
        self.totals = defaultdict(lambda: dict(calls=0, wall_s=0., cpu_s=0.,
                                               exclusive_wall_s=0., max_wall_s=0.))
        self.slow = []
        self.omitted = 0

    def wrap(self, owner, attribute, label, resource_counts=True):
        original = getattr(owner, attribute)

        @functools.wraps(original)
        def measured(*args, **kwargs):
            wall = time.monotonic()
            cpu = time.thread_time()
            usage = self.thread_usage() if resource_counts and self.thread_usage else None
            frame = [0.]
            self.stack.append(frame)
            try:
                return original(*args, **kwargs)
            finally:
                elapsed = time.monotonic() - wall
                compute = time.thread_time() - cpu
                after = self.thread_usage() if usage is not None else None
                self.stack.pop()
                if self.stack:
                    self.stack[-1][0] += elapsed
                item = self.totals[label]
                item['calls'] += 1
                item['wall_s'] += elapsed
                item['cpu_s'] += compute
                item['exclusive_wall_s'] += elapsed - frame[0]
                new_maximum = elapsed > item['max_wall_s']
                if new_maximum or elapsed >= self.slow_seconds:
                    event = dict(stage=label, packet=self.packet_index,
                        start_monotonic=wall, wall_ms=elapsed*1000,
                        thread_cpu_ms=compute*1000, non_cpu_ms=max(0.,elapsed-compute)*1000)
                    if usage is not None:
                        event.update(voluntary_switches=after.ru_nvcsw-usage.ru_nvcsw,
                            involuntary_switches=after.ru_nivcsw-usage.ru_nivcsw,
                            minor_faults=after.ru_minflt-usage.ru_minflt,
                            major_faults=after.ru_majflt-usage.ru_majflt)
                    if new_maximum:
                        item['max_wall_s'] = elapsed
                        item['max_wall_call'] = event
                if elapsed >= self.slow_seconds:
                    if len(self.slow) < self.max_slow_events:
                        self.slow.append(event)
                    else:
                        self.omitted += 1
        setattr(owner, attribute, measured)

    def save(self, path):
        path.write_text(json.dumps(dict(stages=dict(self.totals), slow=self.slow,
            omitted_slow_events=self.omitted,
            slow_seconds=self.slow_seconds, max_slow_events=self.max_slow_events,
            thread_resources=self.thread_usage is not None,
            scope='Wall minus thread CPU includes scheduling, I/O and synchronization; '
                  'it does not uniquely identify scheduler delay. Nested stages overlap.'), indent=2))


def install_primary(live, covariance_class, recorder_class):
    """No global NumPy/print hooks or worker/web tracing; save only at replay end."""
    trace = StageTrace(slow_seconds=.050, max_slow_events=256, thread_resources=True)
    targets = (
        (live.CausalEEGFilter, 'process', 'primary_filter'),
        (live.CytonSQIMonitor, 'process', 'primary_sqi'),
        (live, 'segmented_sqi', 'raw_sqi'),
        (live, 'primary_windows', 'primary_window_snapshot'),
        (covariance_class, 'append', 'emotion_band_filters'),
        (covariance_class, 'feature', 'emotion_feature'),
        (live.CovarianceSVM, 'predict', 'emotion_predict'),
        (live.CovarianceSVM, 'predict_feature', 'emotion_svm'),
        (live.FourChannelFatigue, 'append', 'fatigue_bands'),
        (live.FourChannelFatigue, 'process_window', 'fatigue_window'),
        (live.TelemetryWriter, 'submit', 'telemetry_enqueue'),
        (live, 'publish_result', 'primary_publish'),
        (recorder_class, 'poll', 'recorder_poll'),
    )
    for owner, attribute, label in targets:
        trace.wrap(owner, attribute, label, resource_counts=label!='recorder_poll')
    return trace


class TracedGeneration:
    """Parent-only proxy; the child retains its original synchronized array."""
    def __init__(self, value, trace):
        self.value = value
        trace.wrap(self, 'read', 'primary_submit_generation_read')

    def read(self, index):
        return self.value[index]

    def __getitem__(self, index):
        return self.read(index)

    def __setitem__(self, index, value):
        self.value[index] = value

    def get_lock(self):
        return self.value.get_lock()


def install_fast_path(live, *, detailed_submit=False):
    """Parent-only blocking diagnosis for the isolated asynchronous candidate."""
    from async_primary import AsyncPrimaryWorker
    trace = StageTrace(slow_seconds=.050, max_slow_events=256, thread_resources=True)
    for owner, name, label in (
            (live.CausalEEGFilter, 'process', 'primary_filter'),
            (live.TelemetryWriter, 'submit', 'telemetry_enqueue'),
            (live, 'publish_result', 'primary_publish'),
            (AsyncPrimaryWorker, 'poll', 'primary_worker_poll'),
            (AsyncPrimaryWorker, 'submit', 'primary_worker_enqueue')):
        trace.wrap(owner, name, label)
    if detailed_submit:
        import async_primary
        from types import SimpleNamespace
        # Local module binding only: do not patch the shared NumPy module.
        local_numpy = SimpleNamespace(array=async_primary.np.array, sum=async_primary.np.sum)
        trace.wrap(local_numpy, 'array', 'primary_submit_array_copy')
        async_primary.np = local_numpy
        original_init = AsyncPrimaryWorker.__init__

        @functools.wraps(original_init)
        def initialized(worker, *args, **kwargs):
            original_init(worker, *args, **kwargs)
            worker.generation = TracedGeneration(worker.generation, trace)
            trace.wrap(worker, 'check_alive', 'primary_submit_liveness')
            trace.wrap(worker.pending, 'put_nowait', 'primary_submit_queue_put')
        AsyncPrimaryWorker.__init__ = initialized
    return trace


class TracedReplayLog:
    """Only the replay's redirected log, not a global print hook."""
    def __init__(self, stream, trace):
        self.stream = stream
        trace.wrap(self, 'write', 'primary_log_write')
        trace.wrap(self, 'flush', 'primary_log_flush')

    def write(self, value):
        return self.stream.write(value)

    def flush(self):
        return self.stream.flush()


def install(live, seed_class, recorder_class):
    import builtins
    import numpy as np
    from async_seed_candidate import AsyncSeedShadow
    import ssvep_core
    import ssvep_stream
    from ssvep_stream import SSVEPStream
    from ssvep_shadow import SSVEPShadow
    trace = StageTrace()
    targets = [
        (np, 'stack', 'array_stack'),
        (builtins, 'print', 'primary_log_write'),
        (AsyncSeedShadow, 'packet', 'async_seed_packet'),
        (SSVEPShadow, 'packet', 'ssvep_packet'),
        (SSVEPShadow, 'publish', 'ssvep_publish'),
        (SSVEPShadow, '_quality', 'ssvep_quality'),
        (SSVEPStream, 'push', 'ssvep_stream_push'),
        (SSVEPStream, '_decision', 'ssvep_decision'),
        (seed_class, 'packet', 'seed_packet'),
        (live.CausalEEGFilter, 'process', 'primary_filter'),
        (live.KernelOwnedCausalFilter, 'process', 'pl_primary_filter'),
        (live.CytonSQIMonitor, 'process', 'primary_sqi'),
        (live, 'segmented_sqi', 'raw_sqi'),
        (live, 'primary_windows', 'primary_window_snapshot'),
        (live.CovarianceFeatureStream, 'append', 'emotion_band_filters'),
        (live.CovarianceFeatureStream, 'feature', 'emotion_feature'),
        (live.CovarianceSVM, 'predict', 'emotion_predict'),
        (live.CovarianceSVM, 'predict_feature', 'emotion_svm'),
        (live.FourChannelFatigue, 'append', 'fatigue_bands'),
        (live.FourChannelFatigue, 'process_window', 'fatigue_window'),
        (live.TelemetryWriter, 'submit', 'telemetry_enqueue'),
        (live, 'publish_result', 'primary_publish'),
        (recorder_class, 'poll', 'recorder_poll'),
        (recorder_class, 'append', 'recorder_append'),
        (recorder_class, 'flush', 'recorder_flush'),
        (recorder_class, 'record_window', 'recorder_window'),
    ]
    if hasattr(SSVEPShadow, 'write_event'):
        targets.append((SSVEPShadow, 'write_event', 'ssvep_write_event'))
    if hasattr(ssvep_core, 'CachedCCA'):
        targets.append((ssvep_core.CachedCCA, 'scores', 'ssvep_cca_scores'))
    else:
        targets.append((ssvep_stream, 'canonical_correlation', 'ssvep_cca_single'))
    for owner, attribute, name in targets:
        trace.wrap(owner, attribute, name)
    return trace


def traced_telemetry_worker(pending, destination):
    import cyton_guardianloop as live
    trace = StageTrace()
    trace.wrap(live, 'publish_telemetry', 'telemetry_serialize_write')
    try:
        live._telemetry_worker_original(pending)
    finally:
        trace.save(destination)


class NoTelemetryWriter:
    """Diagnostic ablation only: primary processing and publication are unchanged."""
    skipped = 0

    def submit(self, *args, **kwargs):
        pass

    def close(self):
        pass
