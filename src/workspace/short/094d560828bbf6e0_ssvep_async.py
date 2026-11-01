"""Bounded SSVEP-only process. Primary EEG never passes through this queue."""
import multiprocessing as mp
import os
from pathlib import Path
import queue
import time

import numpy as np

from cyton_trial_recorder import atomic_json
from ssvep_shadow import CHANNELS, LIVE_PATH, REPLAY_PATH, SSVEPShadow


def _worker(config, sos, channels, source, pending, results, epoch, stop, ready, counts):
    generation = -1
    if hasattr(os, 'nice'):
        os.nice(10)  # Acquisition retains the normal scheduler priority.

    class QueuedShadow(SSVEPShadow):
        def write_event(self, event):
            if generation != epoch.value:
                return
            event['input_received_monotonic'] = self.last_packet
            try:
                results.put_nowait((generation, event))
            except queue.Full:
                counts[2] += 1  # Display-only result skipped, never raw acquisition.

    try:
        shadow = QueuedShadow(config, sos, channels, source=source)
        values = np.zeros(8)
        ready.set()
        while not stop.is_set():
            try:
                current, batch = pending.get(timeout=.1)
            except queue.Empty:
                continue
            if current != epoch.value:
                counts[1] += len(batch)
                continue
            if current != generation:
                generation = current
                shadow.disconnect('async_epoch_reset')
            for offset, (o1, o2, seq, malformed, stamp, r1, r2) in enumerate(batch):
                if current != epoch.value:
                    counts[1] += len(batch)-offset
                    break
                values[6], values[7] = o1, o2
                shadow.packet(values, seq, malformed, now=stamp, adc_rails=(r1,r2))
                counts[0] += 1
    except (OSError, ValueError, KeyError, FloatingPointError, np.linalg.LinAlgError) as exc:
        try:
            results.put((epoch.value, dict(state='error', valid=False, reason=str(exc))), timeout=.1)
        except queue.Full:
            pass
    finally:
        ready.set()
        results.cancel_join_thread()


class AsyncSSVEPShadow:
    """Single parent publisher prevents late worker output resurrecting an old epoch."""
    def __init__(self, protocol_path, coefficients_path, channel_map, source='live', status_path=None):
        if tuple(channel_map) != CHANNELS or source not in ('live', 'replay'):
            raise ValueError('Invalid fixed montage or source')
        self.source = source
        self.path = Path(status_path) if status_path else (LIVE_PATH if source == 'live' else REPLAY_PATH)
        if source == 'replay' and self.path == LIVE_PATH:
            raise ValueError('Replay cannot publish live status')
        ctx = mp.get_context('spawn')
        # Absorb brief bursts when the primary model finishes a window. No waiting
        # to fill this buffer; candidates older than 500ms still cannot go live.
        self.pending = ctx.Queue(maxsize=32)  # Hard bound: 1.28 seconds of samples.
        self.results = ctx.Queue(maxsize=8)
        self.epoch = ctx.Value('L', 0, lock=False)  # One writer: acquisition parent.
        self.counts = ctx.Array('L', 3, lock=False)  # One writer: worker.
        self.stop, self.ready = ctx.Event(), ctx.Event()
        self.worker = ctx.Process(target=_worker, args=(str(protocol_path), str(coefficients_path),
            tuple(channel_map), source, self.pending, self.results, self.epoch,
            self.stop, self.ready, self.counts), name='cyton-ssvep-worker', daemon=True)
        self.batch = []
        self.previous = self.last_packet = None
        self.received = self.skipped = self.resets = self.rejected_results = 0
        self.closed = False
        self.latest = None
        self._status('no_data', 'async_startup')
        self.worker.start()
        # Initialization is before Cyton's start/flush commands, never in the packet loop.
        if not self.ready.wait(20):
            self.disconnect('async_startup_timeout')
            raise TimeoutError('SSVEP worker did not initialize within 20 seconds')
        if not self.worker.is_alive():
            self.disconnect('async_startup_failed')
            raise ValueError('SSVEP worker initialization failed')

    def _publish(self, event):
        event = dict(event)
        event.update(source=self.source, control_enabled=False, shadow=True,
                     confidence_validated=False, async_worker=True, epoch=int(self.epoch.value),
                     received_packets=self.received, skipped_ssvep_samples=self.skipped,
                     worker_processed_samples=int(self.counts[0]),
                     worker_skipped_samples=int(self.counts[1]), skipped_result_updates=int(self.counts[2]),
                     rejected_late_results=self.rejected_results, async_resets=self.resets)
        atomic_json(self.path, event)
        self.latest = event

    def _status(self, state, reason):
        self._publish(dict(state=state, reason=reason, valid=False, frequency_hz=None,
            scores=None, target_index=None, margin=None, channels=['O1','O2'],
            updated_at=time.time(), updated_monotonic=time.monotonic(), input_age_seconds=0.))

    def _reset(self, reason):
        self.epoch.value += 1
        self.resets += 1
        self.skipped += len(self.batch)
        self.batch.clear()
        self._status('warmup', reason)

    def poll(self):
        newest = None
        for _ in range(8):
            try:
                generation, event = self.results.get_nowait()
            except queue.Empty:
                break
            age = time.monotonic()-event.get('updated_monotonic', time.monotonic())
            if generation != self.epoch.value or (self.source == 'live' and
                    age+event.get('input_age_seconds', 0.) > .5):
                self.rejected_results += 1
                continue
            newest = event
        if newest is not None:
            self._publish(newest)  # Keep worker timestamp; never refresh an old candidate's age.
        if not self.closed and not self.worker.is_alive():
            if self.latest.get('reason') != 'async_worker_stopped':
                self._status('error', 'async_worker_stopped')
        return newest

    def packet(self, samples_uv, sequence, malformed=False, now=None, adc_rails=None):
        if self.closed:
            return []
        if not self.worker.is_alive():
            self.poll()
            return []
        stamp = time.monotonic() if now is None else float(now)
        seq = int(sequence)
        if self.previous is not None and ((seq-self.previous)%256 != 1 or
                stamp-self.last_packet > .25 or stamp < self.last_packet):
            self._reset('sequence_or_timing_gap')
        if malformed:
            self._reset('malformed_packet')
        self.previous, self.last_packet = seq, stamp
        self.received += 1
        rails = (False,False) if adc_rails is None else adc_rails
        self.batch.append((float(samples_uv[6]), float(samples_uv[7]), seq, bool(malformed), stamp,
                           bool(rails[0]), bool(rails[1])))
        if len(self.batch) == 10:
            try:
                self.pending.put_nowait((int(self.epoch.value), self.batch))
                self.batch = []
            except queue.Full:
                self._reset('ssvep_queue_overflow')
            self.poll()
        return []

    def idle(self, now=None):
        stamp = time.monotonic() if now is None else now
        if self.last_packet is not None and stamp-self.last_packet > .5:
            self._reset('packet_timeout')
            self.previous = self.last_packet = None
            self._status('no_data', 'packet_timeout')
        self.poll()

    def disconnect(self, reason='service_stopped_or_stream_timeout'):
        if self.closed:
            return
        self.closed = True
        self.epoch.value += 1
        self.stop.set()
        self.worker.join(timeout=2)
        if self.worker.is_alive():
            self.worker.terminate()
            self.worker.join(timeout=1)
        for channel in (self.pending, self.results):
            channel.cancel_join_thread()
            channel.close()
        self._status('no_data', reason)
