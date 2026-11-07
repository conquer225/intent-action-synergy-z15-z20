"""Bounded comparison consumer of the existing single Cyton packet reader."""
import math
import queue
import threading
import time
import numpy as np

from .fixed import quantize_samples_uv


class EEGComparison:
    def __init__(self, engine, *, microvolts_per_count=1., now=time.monotonic, publish=None, ttl=2.):
        if not math.isfinite(microvolts_per_count) or microvolts_per_count <= 0:
            raise ValueError('EEG conversion scale')
        self.engine, self.multiplier, self.now, self.publish, self.ttl = engine, microvolts_per_count, now, publish, ttl
        self.lock = threading.RLock()
        self.pending, self.previous, self.last_at = [], None, None
        self.state = dict(valid=False, label=None, class_id=None, reason='warming_up', control_enabled=False)

    def _publish(self, **state):
        self.state = dict(state, control_enabled=False, updated_at=time.time())
        if self.publish:self.publish(dict(self.state))

    def invalidate(self, reason):
        with self.lock:
            self.engine.reset();self.pending.clear();self.previous = None;self.last_at = None
            self._publish(valid=False, label=None, class_id=None, reason=reason)

    def ingest(self, counts, sequence, *, received_at, malformed=False):
        with self.lock:
            values = np.asarray(counts)
            if (malformed or values.shape != (8,) or values.dtype.kind not in 'iu'
                    or not isinstance(sequence, (int, np.integer)) or not 0 <= sequence <= 255
                    or not math.isfinite(received_at) or received_at > self.now()+.01):
                self.invalidate('malformed_input');return
            if self.now()-received_at > self.ttl:
                self.invalidate('stale_input');return
            if self.previous is not None and ((int(sequence)-self.previous) & 255) != 1:
                self.invalidate('sequence_gap')
            if self.last_at is not None and (received_at < self.last_at or received_at-self.last_at > .25):
                self.invalidate('timing_gap')
            self.previous, self.last_at = int(sequence), received_at
            self.pending.append(values.copy())
            batch = min(50, self.engine.model.hop)
            if len(self.pending) == batch:
                samples = quantize_samples_uv(np.asarray(self.pending, np.float64)*self.multiplier)
                self.pending.clear()
                for result in self.engine.feed(samples):
                    if result.get('clipped', 0):
                        self.invalidate('signal_clipping')
                        break
                    self._publish(**dict(result, reason='prediction' if result['valid'] else 'signal_quality',
                                         received_monotonic=received_at))

    def snapshot(self):
        with self.lock:
            state = dict(self.state)
            if self.last_at is not None and self.now()-self.last_at > self.ttl:
                state.update(valid=False, label=None, class_id=None, reason='stale_input')
            return state


class LiveEEGTap:
    """IPC sink plus one private worker; offer() remains owned by the serial reader."""
    def __init__(self, comparison, reader_sink, decoder):
        self.comparison, self.reader_sink, self.decoder = comparison, reader_sink, decoder
        self.stopped, self.error = threading.Event(), None
        self.control_lock = threading.Lock()
        self.pending_interrupt = None
        self.worker = threading.Thread(target=self._run, name='pl-eeg-comparison', daemon=True)
        self.worker.start()

    def interrupt(self, reason):
        """Request reset from acquisition; the private worker retains hardware ownership."""
        with self.control_lock:
            self.pending_interrupt = (self.comparison.now(), str(reason))

    def _run(self):
        previous = 0
        discard_before = -float('inf')
        def reset_if_requested():
            nonlocal discard_before
            with self.control_lock:
                requested, self.pending_interrupt = self.pending_interrupt, None
            if requested is not None:
                discard_before, reason = requested
                self.comparison.invalidate(reason)
        try:
            while not self.stopped.is_set():
                reset_if_requested()
                try:message = self.reader_sink.pending.get(timeout=.1)
                except queue.Empty:
                    if self.comparison.snapshot().get('reason') == 'stale_input':
                        self.comparison.invalidate('stale_input')
                    continue
                batch = message if isinstance(message[0], tuple) else (message,)
                for ordinal, packet, malformed, received_at in batch:
                    reset_if_requested()
                    if received_at <= discard_before:
                        previous = ordinal
                        continue
                    if ordinal != previous+1:self.comparison.invalidate('queue_gap')
                    previous = ordinal
                    self.comparison.ingest(self.decoder(packet), int(packet[1]),
                                           received_at=received_at, malformed=bool(malformed))
        except Exception as exc:
            self.error = type(exc).__name__+': '+str(exc)
            try:self.comparison.invalidate('backend_error')
            except Exception as status_error:
                self.error += '; status: '+str(status_error)

    def close(self):
        self.stopped.set();self.worker.join(5)
        if self.worker.is_alive():raise RuntimeError('EEG comparison worker still owns its command')
        try:self.comparison.invalidate('stopped')
        finally:
            self.reader_sink.close()
            close = getattr(self.comparison.engine, 'close', None)
            if close:close()


def open_pynq_eeg(model, ip_name, *, hwh=None):
    from pynq import MMIO, PL, allocate
    from .backend import EEGHardware
    from .metadata import eeg_aperture
    info = eeg_aperture(hwh, ip_name) if hwh is not None else PL.ip_dict.get(ip_name)
    if not info or int(info.get('addr_range', 0)) < 0x50:
        raise ValueError('integrated EEG IP is absent from the loaded hardware description')
    registers = MMIO(info['phys_addr'], info['addr_range'])
    return EEGHardware(model, registers, allocate)
