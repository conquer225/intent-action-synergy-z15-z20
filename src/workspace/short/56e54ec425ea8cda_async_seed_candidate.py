"""Bounded optional SEED lane; overflow never blocks the primary packet loop.

Replay is the default. Live use requires an explicit source and status path.
This module does not select or replace the primary emotion/fatigue models.
"""

import multiprocessing as mp
import math
import queue
import time
from pathlib import Path

import numpy as np
from cyton_trial_recorder import atomic_json

BATCH_SAMPLES = 50


def _run_shadow(model_path, channel_map, status_path, audit_path, source, work, ready, abort,
                page_policy_path=None,policy_mode='live_readonly_hdmi',standalone_enabled=False):
    from seed_shadow import SeedShadow
    if audit_path:
        from audited_seed_shadow import AuditedSeedShadow
        shadow=AuditedSeedShadow(model_path,channel_map,status_path=status_path,audit_path=audit_path)
    else:
        shadow=SeedShadow(model_path,channel_map,source=source,status_path=status_path)
    if page_policy_path:
        from page_policy import ScheduledLane
        shadow=ScheduledLane(shadow,page_policy_path,'seed_candidate',mode=policy_mode,
                             standalone_tasks=('seed_candidate',) if standalone_enabled else ())
    ready.set()
    while True:
        if abort.is_set():
            shadow.disconnect('bounded_queue_overflow')
            break
        try:
            item = work.get(timeout=.1)
        except queue.Empty:
            shadow.idle()
            continue
        if item[0] == 'stop':
            shadow.disconnect(item[1])
            break
        _, samples, sequences, malformed, timestamps, timing_verified = item
        if page_policy_path and not shadow.refresh():continue
        if batch_expired(timestamps[0], time.monotonic()):
            shadow.disconnect('shadow_input_expired')
            continue
        for sample, sequence, bad, received in zip(samples, sequences, malformed, timestamps):
            shadow.packet(sample, sequence, bad, now=received,
                          timing_verified=timing_verified)


def batch_expired(last_timestamp, current_time):
    age=current_time-last_timestamp
    return not math.isfinite(age) or not 0 <= age <= .5


class AsyncSeedShadow:
    """Separate bounded process; never a source of primary predictions."""

    def __init__(self, model_path, channel_map, *, status_path, audit_path=None, source='replay',
                 page_policy_path=None,standalone_enabled=False):
        if source not in ('live', 'replay') or (audit_path and source != 'replay'):
            raise ValueError('Invalid SEED source/audit combination')
        self.path = Path(status_path)
        self.source = source
        self.closed = False
        self.lease=None
        policy_mode='live_readonly_hdmi' if source=='live' else 'scripted_hdmi_replay'
        if page_policy_path:
            from page_policy import PageLease
            self.lease=PageLease(page_policy_path,mode=policy_mode,
                                 standalone_tasks=('seed_candidate',) if standalone_enabled else ())
        context = mp.get_context('spawn')
        self.work = context.Queue(maxsize=16)
        self.ready = context.Event()
        self.abort = context.Event()
        self.pending = []
        self.failed = False
        self.worker = context.Process(
            target=_run_shadow,
            args=(str(model_path), tuple(channel_map), str(status_path),
                  str(audit_path) if audit_path else None, source,
                  self.work, self.ready, self.abort, str(page_policy_path) if page_policy_path else None,
                  policy_mode,standalone_enabled),
            daemon=True,
        )
        self.worker.start()
        if not self.ready.wait(timeout=12) or not self.worker.is_alive():
            self.disconnect('seed_worker_startup_failed')
            raise OSError('SEED worker failed to start')

    def packet(self, samples_uv, sequence, malformed=False, now=None, timing_verified=False):
        if self.failed or not self.worker.is_alive():
            raise ValueError('Isolated SEED worker unavailable')
        if self.lease and not self.lease.enabled('seed_candidate'):
            self.pending.clear()
            return []
        self.pending.append((np.asarray(samples_uv, dtype=np.float64).copy(),
                             int(sequence), bool(malformed),
                             time.monotonic() if now is None else float(now)))
        if len(self.pending) < BATCH_SAMPLES:
            return []
        samples, sequences, flags, timestamps = zip(*self.pending)
        self.pending.clear()
        try:
            self.work.put_nowait(('samples', np.stack(samples), sequences,
                                  flags, timestamps, bool(timing_verified)))
        except queue.Full:
            self.failed = True
            self.abort.set()
            raise ValueError('Isolated SEED queue full; candidate invalidated')
        return []

    def idle(self, now=None):
        if not self.worker.is_alive() and not self.failed:
            self.failed = True
            self.publish({'state': 'error', 'valid': False,
                          'reason': 'isolated_seed_worker_stopped'})

    def publish(self, event):
        atomic_json(self.path, {**event, 'source': self.source, 'shadow': True,
                                'updated_at': time.time()})

    def disconnect(self, reason='disconnect'):
        if self.closed:
            return None
        self.closed = True
        self.pending.clear()
        if self.worker.is_alive() and not self.failed:
            try:
                self.work.put_nowait(('stop', reason))
            except queue.Full:
                self.abort.set()
        self.worker.join(timeout=3)
        if self.worker.is_alive():
            self.abort.set()
            self.worker.join(timeout=2)
        if self.worker.is_alive():
            self.worker.terminate()
            self.worker.join(timeout=2)
        self.work.cancel_join_thread()
        self.work.close()
        self.publish({'state':'no_data', 'valid':False, 'reason':reason})
        return None
