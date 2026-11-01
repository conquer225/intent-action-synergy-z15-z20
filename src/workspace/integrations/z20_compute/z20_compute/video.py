"""Analysis sidecar. There is deliberately no display/present/start/stop callback."""
from dataclasses import dataclass
import threading
import time
import numpy as np


@dataclass(frozen=True)
class RingState:
    writer_index: int
    completed_index: int
    write_epoch: int
    completed_sequence: int
    captured_ns: int = 0


@dataclass(frozen=True)
class FrameSnapshot:
    sequence: int
    captured_ns: int
    pixels: np.ndarray


class SnapshotReader:
    """Copy-only adapter. state must expose every DMA write-start generation.

    A cyclic buffer index alone is insufficient: a writer can lap a slow copy.
    copy_frame must invalidate a non-coherent DMA cache before reading pixels.
    This class neither parks nor changes the capture/display DMA.
    """
    def __init__(self, state, copy_frame, *, ring_size=3):
        self.state, self.copy_frame, self.ring_size = state, copy_frame, ring_size
        self.last_sequence = -1

    def latest(self):
        before = self.state()
        if not (0 <= before.writer_index < self.ring_size and 0 <= before.completed_index < self.ring_size):
            raise ValueError("DMA index outside ring")
        if before.writer_index == before.completed_index or before.completed_sequence <= self.last_sequence:
            return None
        pixels = np.array(self.copy_frame(before.completed_index), copy=True)
        after = self.state()
        if before != after:
            return None
        pixels.flags.writeable = False
        self.last_sequence = before.completed_sequence
        return FrameSnapshot(before.completed_sequence, before.captured_ns, pixels)


@dataclass(frozen=True)
class AnalysisResult:
    sequence: int
    epoch: int
    completed_at: float
    value: object
    valid: bool = True
    state: str = "ready"
    submitted_at: float = 0.0


class AnalysisWorker:
    """One running job and at most one pending latest job; submit never waits."""
    def __init__(self, analyze, *, now=time.monotonic, ttl=2.0):
        self.analyze, self.now, self.ttl = analyze, now, ttl
        self.lock = threading.Lock()
        self.wake = threading.Event()
        self.changed = threading.Event()
        self.pending = None
        self.current = None
        self.epoch = 0
        self.dropped = 0
        self.stopping = False
        self.thread = threading.Thread(target=self._run, daemon=True, name="z20-analysis")
        self.thread.start()

    def submit(self, sequence, payload):
        if not self.lock.acquire(blocking=False):
            self.dropped += 1
            return False
        try:
            if self.stopping:
                return False
            if self.pending is not None:
                self.dropped += 1
            self.pending = (sequence, self.epoch, payload, self.now())
            self.wake.set()
            return True
        finally:
            self.lock.release()

    def _run(self):
        while True:
            self.wake.wait()
            with self.lock:
                if self.stopping:
                    return
                job, self.pending = self.pending, None
                self.wake.clear()
            if job is None:
                continue
            sequence, epoch, payload, submitted_at = job
            try:
                value = self.analyze(payload)
                result = AnalysisResult(sequence, epoch, self.now(), value, submitted_at=submitted_at)
            except Exception as exc:
                result = AnalysisResult(sequence, epoch, self.now(), None, False, type(exc).__name__, submitted_at)
            with self.lock:
                if epoch == self.epoch and not self.stopping:
                    self.current = result
                    self.changed.set()

    def result(self):
        with self.lock:
            if self.current is None or self.now() - self.current.submitted_at > self.ttl:
                return None
            return self.current

    def invalidate(self):
        with self.lock:
            self.epoch += 1
            self.pending = self.current = None
            self.changed.set()

    def wait_for_sequence(self, sequence, timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.changed.clear()
            result = self.result()
            if result is not None and result.sequence == sequence:
                return True
            self.changed.wait(max(0, deadline - time.monotonic()))
        return False

    def close(self, timeout=2.0):
        with self.lock:
            self.stopping = True
            self.pending = self.current = None
            self.wake.set()
        self.thread.join(timeout)
        return not self.thread.is_alive()
