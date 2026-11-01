"""Bounded, ordered ARM primary-window worker; USB and PL stay with the parent."""
import multiprocessing
from multiprocessing.queues import Queue as ProcessQueue
from collections import deque
import math
import os
import queue
import threading
import time

import numpy as np


class _StagedPrimaryQueue(ProcessQueue):
    """Reserve capacity on the producer; wait for the feeder only off-thread."""
    def __init__(self, *, maxsize, ctx):
        super().__init__(maxsize=maxsize, ctx=ctx)
        self._incoming = deque()
        self._dispatch_thread = None
        self._dispatch_stop = False
        self._dispatch_error = None

    def prepare(self):
        if self._dispatch_thread is not None:
            raise RuntimeError('Primary dispatcher already prepared')
        with self._notempty:
            if self._thread is None:
                self._start_thread()
        self._dispatch_thread = threading.Thread(target=self._dispatch,
            name='primary-queue-dispatch', daemon=True)
        self._dispatch_thread.start()

    def _dispatch(self):
        try:
            while not self._dispatch_stop:
                try:
                    value = self._incoming.popleft()
                except IndexError:
                    time.sleep(.002)
                    continue
                with self._notempty:
                    self._buffer.append(value)
                    self._notempty.notify()
        except BaseException as error:
            self._dispatch_error = error

    def put_nowait(self, value):
        if self._closed:
            raise ValueError('Primary handoff queue is closed')
        if self._dispatch_thread is None:
            raise RuntimeError('Primary dispatcher was not prepared')
        if self._dispatch_error is not None:
            raise RuntimeError('Primary dispatcher failed') from self._dispatch_error
        if not self._sem.acquire(False):
            raise queue.Full
        try:
            # CPython deque append/popleft are atomic; this private fork lane has
            # one producer and one dispatcher. The original consumer frees slots.
            self._incoming.append(value)
        except BaseException:
            self._sem.release()
            raise

    def close(self):
        self._dispatch_stop = True
        if self._dispatch_thread is not None:
            self._dispatch_thread.join(timeout=2)
            if self._dispatch_thread.is_alive():
                raise RuntimeError('Primary dispatcher did not stop')
        super().close()


def _worker(processor, pending, replies, generation, progress, stopped, cpus,
            calibration_session, wear_identity):
    if cpus is not None:
        os.sched_setaffinity(0, cpus)
    epoch = wear = 0
    replies.put(('ready', dict(pid=os.getpid(), cpus=sorted(os.sched_getaffinity(0)),
                              nice=os.getpriority(os.PRIO_PROCESS, 0))))
    def apply_generation():
        nonlocal epoch, wear
        with generation.get_lock():
            current = tuple(generation[:])
            if current != (epoch, wear):
                if current[1] != wear:
                    processor.new_wearing()
                    if calibration_session is not None:
                        calibration_session.context['wear_id'] = bytes(wear_identity[:]).decode('ascii')
                        calibration_session.last_progress = None
                else:
                    processor.reset_stream()
                epoch, wear = current

    try:
        while not stopped.is_set():
            apply_generation()
            try:
                batch = pending.get(timeout=.05)
            except queue.Empty:
                continue
            # A generation can change while get() waits. Do not lose the first
            # fresh batch merely because the worker had not observed it yet.
            apply_generation()
            batch_epoch, raw, filtered, bad, counters, received_at = batch
            if batch_epoch != epoch:
                continue
            for row, clean, broken in zip(raw, filtered, bad):
                window_started = time.monotonic()
                result = processor.append(row, clean, bool(broken), counters)
                if result is not None:
                    compute_ms = (time.monotonic() - window_started) * 1000.
                    with generation.get_lock():
                        if tuple(generation[:]) != (epoch, wear):
                            break
                        if calibration_session is not None:
                            try:
                                calibration_session.save(processor.sqi_monitor,
                                                         processor.four_channel_fatigue)
                            except (OSError, ValueError) as exc:
                                progress[4] += 1
                                print('CALIBRATION_CHECKPOINT_WRITE_FAILED: ' + str(exc), flush=True)
                        progress[:3] = (processor.calibration_progress,
                                        int(processor.calibration_ready),
                                        int(np.sum(processor.sqi_monitor.calibrated_channels)))
                    replies.put_nowait(('result', dict(epoch=epoch, result=result,
                        calibrated=processor.calibration_ready, received_at=received_at,
                        compute_ms=compute_ms)))
            with generation.get_lock():
                if tuple(generation[:]) == (epoch, wear):
                    progress[3] = received_at
    except BaseException as exc:
        try:
            replies.put_nowait(('error', dict(type=type(exc).__name__, detail=str(exc))))
        except queue.Full:
            pass
        raise


class AsyncPrimaryWorker:
    def __init__(self, processor, *, cpus=None, capacity=32, calibration_session=None):
        if processor.engine is not None or processor.filter_backend != 'arm':
            raise ValueError('Primary worker cannot own a PL engine')
        if capacity < 1:
            raise ValueError('Primary queue capacity must be positive')
        self.calibration_session = calibration_session
        identity = None if calibration_session is None else calibration_session.context['wear_id']
        if identity is not None:
            self.validate_wear_id(identity)
        context = multiprocessing.get_context('fork')
        self.wear_identity = context.Array('c', (identity or '0' * 32).encode('ascii'))
        self.pending = _StagedPrimaryQueue(maxsize=capacity, ctx=context)
        self.replies = context.Queue(maxsize=8)
        self.generation = context.Array('q', [0, 0])
        self.progress = context.Array('d', [processor.calibration_progress,
            int(processor.calibration_ready),
            int(np.sum(processor.sqi_monitor.calibrated_channels)), 0., 0.])
        self.stopped = context.Event()
        self.process = context.Process(target=_worker, name='primary-window-worker',
            args=(processor, self.pending, self.replies, self.generation,
                  self.progress, self.stopped, cpus, calibration_session, self.wear_identity))
        self.stats = dict(submitted_batches=0, queue_full=0, stale_replies=0,
                          old_epoch_replies=0, accepted_replies=0, epochs=0,
                          publication_stale=0, handoff_busy=0)
        self.last_submit_rejection = None
        self.process.start()
        try:
            kind, self.identity = self.replies.get(timeout=5)
            if kind != 'ready':
                raise RuntimeError('Primary worker startup protocol failed')
            self.pending.prepare()
        except BaseException:
            self.close()
            raise

    @property
    def calibration_progress(self):
        return int(self.progress[0])

    @property
    def calibration_ready(self):
        return bool(self.progress[1])

    @property
    def checkpoint_write_failures(self):
        return int(self.progress[4])

    @staticmethod
    def validate_wear_id(identifier):
        if (not isinstance(identifier, str) or len(identifier) != 32
                or any(c not in '0123456789abcdef' for c in identifier)):
            raise ValueError('Checkpoint wearing identity must be 32 lowercase hex characters')

    def check_alive(self):
        if not self.process.is_alive():
            raise RuntimeError('Primary window worker exited: %s' % self.process.exitcode)

    def submit(self, raw, filtered, bad, counters, received_at):
        self.last_submit_rejection = None
        self.check_alive()
        if not math.isfinite(received_at):
            raise ValueError('Primary input timestamp must be finite')
        # Queue feeder serialization happens later: own every submitted array.
        batch = (self.generation[0], np.array(raw, copy=True),
                 np.array(filtered, copy=True), np.array(bad, dtype=bool, copy=True),
                 dict(counters), received_at)
        try:
            self.pending.put_nowait(batch)
        except queue.Full:
            self.stats['queue_full'] += 1
            self.last_submit_rejection = 'PRIMARY_WORKER_QUEUE_FULL'
            return False
        self.stats['submitted_batches'] += 1
        return True

    def invalidate(self, *, new_wearing=False, wear_id=None):
        if wear_id is not None and (not new_wearing or self.calibration_session is None):
            raise ValueError('Wearing identity requires an explicit checkpoint-backed reset')
        if new_wearing and self.calibration_session is not None:
            self.validate_wear_id(wear_id)
        with self.generation.get_lock():
            if new_wearing and self.calibration_session is not None:
                # Serialize deletion with worker commits: an old in-flight window
                # must not recreate another wearing's checkpoint after this reset.
                self.calibration_session.path.unlink(missing_ok=True)
                self.calibration_session.context['wear_id'] = wear_id
                self.calibration_session.last_progress = None
                self.wear_identity[:] = wear_id.encode('ascii')
            self.generation[0] += 1
            if new_wearing:
                self.generation[1] += 1
                self.progress[:3] = (0, 0, 0)
            self.progress[3] = 0.
        self.stats['epochs'] += 1

    def poll(self, now=None, max_age=.5):
        self.check_alive()
        now = time.monotonic() if now is None else now
        if not math.isfinite(now) or not math.isfinite(max_age) or max_age <= 0:
            raise ValueError('Primary freshness limit must be finite and positive')
        output = []
        while True:
            try:
                kind, message = self.replies.get_nowait()
            except queue.Empty:
                break
            if kind == 'error':
                raise RuntimeError('Primary worker error: %s' % message)
            if kind != 'result':
                raise RuntimeError('Unexpected primary worker reply')
            if message['epoch'] != self.generation[0]:
                self.stats['old_epoch_replies'] += 1
                continue
            age = now - message['received_at']
            if not math.isfinite(age) or age < 0 or age > max_age:
                self.stats['stale_replies'] += 1
                continue
            message['input_age_seconds'] = age
            self.stats['accepted_replies'] += 1
            output.append(message)
        return output

    def lag(self, now):
        completed = self.progress[3]
        return max(0., now-completed) if completed else 0.

    def close(self):
        self.stopped.set()
        self.process.join(timeout=2)
        if self.process.is_alive():
            self.process.terminate()
            self.process.join(timeout=2)
        # A stopped child will not drain a full feeder pipe.
        self.pending.cancel_join_thread()
        self.pending.close()
        self.replies.close()
