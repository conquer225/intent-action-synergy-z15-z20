"""Isolated cue-locked MI plumbing, with no actuator or production eligibility."""
import json
from copy import copy
import math
import secrets
import threading
import time
from pathlib import Path

import numpy as np
from scipy import signal

from cyton_sqi import CausalEEGFilter, TRANSPORT_LIMIT_UV
from mi_features import CHANNELS

TARGETS = ('left', 'right', 'rest')
MAX_TRIAL_SECONDS = 8.0
HEARTBEAT_SECONDS = 1.5
FRESH_SECONDS = .5
WARMUP_SAMPLES = 500
CUE_OFFSET_SAMPLES = 125
WINDOW_SAMPLES = 500


def hard_quality(samples_uv):
    """The same three hard SQI columns, without unused spectral descriptors."""
    values = np.asarray(samples_uv, dtype=np.float64).T
    absolute = np.abs(values - np.median(values, axis=-1, keepdims=True))
    p99 = np.quantile(absolute, .99, axis=-1)
    flat = np.mean(np.abs(np.diff(values, axis=-1)) <= 1e-3, axis=-1)
    clipped = np.mean(absolute >= TRANSPORT_LIMIT_UV - .01, axis=-1)
    return np.stack((p99, flat, clipped), axis=-1)


def hard_invalid(samples_uv):
    sqi = hard_quality(samples_uv)
    return bool(np.any(sqi[:, 1] >= .8) or np.any(sqi[:, 2] > 0)
                or np.any(sqi[:, 0] > 100))


class CuedMISession:
    def __init__(self, model=None, *, source='live', clock=time.monotonic, log_path=None):
        if source not in ('live', 'replay'):
            raise ValueError('Explicit live or replay source required')
        self.model, self.source, self.clock = model, source, clock
        self.log_path = Path(log_path) if log_path else None
        self.lock = threading.RLock()
        self.trial = None
        self.virtual_hand = dict(position_percent=0, command_count=0, enabled=False,
                                 state='stopped', reason='not_armed', last_command=None,
                                 simulation=True, control_enabled=False)
        self._reset_stream()

    def _stop_virtual(self, reason):
        self.virtual_hand.update(enabled=False, state='stopped', reason=reason,
                                 last_command=None)

    def _apply_virtual(self, trial, label):
        if not trial['virtual_control']:
            return
        before = self.virtual_hand['position_percent']
        after = min(100, max(0, before + (-20 if label == 'left' else 20)))
        command = dict(trial_id=trial['id'], label=label,
                       action='open_step' if label == 'left' else 'close_step',
                       position_before=before, position_after=after,
                       sequence=self.virtual_hand['command_count'] + 1,
                       source=self.source, simulation=True, control_enabled=False)
        self._log('virtual_command', **command)
        self.virtual_hand.update(position_percent=after, command_count=command['sequence'],
                                 state='applied', reason='one_command_per_trial',
                                 last_command=command)

    def _reset_stream(self):
        if not hasattr(self, 'conditioner'):
            self.conditioner = CausalEEGFilter()
            self.band_sos = signal.butter(4, (8, 30), fs=250, btype='bandpass', output='sos')
        else:
            self.conditioner = copy(self.conditioner)
            self.conditioner.zi = np.zeros_like(self.conditioner.zi)
            self.conditioner.origin = None
        self.band_zi = np.zeros((len(self.band_sos), 2, 8))
        self.index = 0
        self.previous_sequence = None
        self.last_received = None
        self.raw = np.empty((0, 8))
        self.filtered = np.empty((0, 8))

    def _log(self, event, **fields):
        if self.log_path is not None:
            row = dict(schema='mi-cued-local-v1', event=event, monotonic_s=self.clock(), **fields)
            row.update(source=self.source, control_enabled=False)
            try:
                with self.log_path.open('a', encoding='utf-8') as stream:
                    stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n')
            except OSError:
                self._stop_virtual('audit_log_failed')
                if self.trial:
                    self.trial.update(state='rejected', reason='audit_log_failed', result=None)
                self._reset_stream()
                raise

    def _reject(self, reason, *, terminal=False):
        self._stop_virtual(reason)
        if self.trial is not None:
            self.trial.update(result=None, reason=reason)
            if terminal:
                self.trial['state'] = 'rejected'
            self._log('withdraw', trial_id=self.trial['id'], reason=reason)

    def disconnect(self, reason='transport_disconnected'):
        with self.lock:
            try:
                self._reject(reason, terminal=True)
            finally:
                self._reset_stream()

    def _expire(self):
        t, now = self.trial, self.clock()
        if t is None or t['state'] not in ('awaiting_presentation', 'active'):
            return
        if now - t['started'] >= MAX_TRIAL_SECONDS:
            self._reject('trial_timeout', terminal=True)
        elif now - t['heartbeat'] > HEARTBEAT_SECONDS:
            self._reject('browser_heartbeat_lost', terminal=True)
        elif (t['result'] or (t['state'] == 'active' and t['virtual_control'])) and (
                self.last_received is None or now - self.last_received > FRESH_SECONDS):
            self._reject('no_fresh_data', terminal=True)

    def command(self, request):
        with self.lock:
            self._expire()
            action, now = request.get('action'), self.clock()
            if action == 'start':
                target = request.get('target')
                if target not in TARGETS:
                    raise ValueError('target must be left, right or rest')
                virtual = request.get('virtual_control', False)
                if type(virtual) is not bool:
                    raise ValueError('virtual_control must be a boolean')
                if self.trial and self.trial['state'] in ('awaiting_presentation', 'active'):
                    raise ValueError('A trial is already active')
                trial = dict(id=secrets.token_hex(16), target=target, started=now,
                             heartbeat=now, state='awaiting_presentation', result=None,
                             reason='waiting_for_display', anchor=None, attempted=False,
                             virtual_control=virtual and target != 'rest')
                self._log('trial_start', trial_id=trial['id'], target=target,
                          model_status='experimental_unpromoted' if self.model else 'unavailable')
                self.trial = trial
                self._stop_virtual('rest_no_inference' if target == 'rest' else 'not_armed')
                if trial['virtual_control']:
                    self.virtual_hand.update(enabled=True, state='waiting',
                                             reason='waiting_for_model_candidate')
            else:
                t = self.trial
                if t is None or request.get('id') != t['id']:
                    raise ValueError('Unknown or old trial ID')
                if action == 'stop':
                    reason = request.get('reason', 'user_stopped')
                    if reason not in ('user_stopped', 'page_hidden', 'page_closed', 'network_error'):
                        raise ValueError('Unknown stop reason')
                    self._reject(reason, terminal=True)
                    t['state'] = 'stopped'
                elif action == 'presented':
                    if t['state'] != 'awaiting_presentation':
                        raise ValueError('Trial is not waiting for presentation')
                    onset, sent = request.get('browser_onset_ms'), request.get('browser_send_ms')
                    if (type(onset) not in (int, float) or type(sent) not in (int, float)
                            or not math.isfinite(onset) or not math.isfinite(sent)
                            or not 0 <= onset <= sent <= onset + 1000):
                        raise ValueError('Invalid browser presentation timestamps')
                    t.update(state='active', heartbeat=now, anchor=self.index,
                             reason='rest_no_inference' if t['target'] == 'rest' else 'collecting_window')
                    self._log('presentation_receipt', trial_id=t['id'], anchor=self.index,
                              browser_onset_ms=onset, browser_send_ms=sent,
                              optical_onset_verified=False, clocks_synchronized=False)
                    if t['target'] != 'rest':
                        if self.model is None:
                            self._reject('model_unavailable', terminal=True)
                        elif self.index < WARMUP_SAMPLES:
                            self._reject('filter_warmup_required', terminal=True)
                        elif self.last_received is None or now - self.last_received > FRESH_SECONDS:
                            self._reject('no_fresh_data', terminal=True)
                elif action == 'heartbeat':
                    if t['state'] == 'active':
                        t['heartbeat'] = now
                    elif t['state'] not in ('rejected', 'stopped'):
                        raise ValueError('Trial is not active')
                else:
                    raise ValueError('Unknown action')
            return self.snapshot()

    def feed(self, raw_uv, sequences, *, received_monotonic=None):
        """Trusted Python acquisition adapter only; HTTP cannot upload EEG/results."""
        with self.lock:
            self._expire()
            now = self.clock()
            received = now if received_monotonic is None else received_monotonic
            values, seq = np.asarray(raw_uv, dtype=np.float64), np.asarray(sequences)
            if (values.ndim != 2 or values.shape[1] != 8 or not 0 < len(values) <= 250
                    or not np.isfinite(values).all() or seq.shape != (len(values),)
                    or not np.issubdtype(seq.dtype, np.integer)
                    or np.any((seq < 0) | (seq > 255))):
                self.disconnect('invalid_packet_batch')
                raise ValueError('Finite 1..250×8 data and integer byte sequences required')
            if (type(received) not in (int, float) or not math.isfinite(received)
                    or received > now or now - received > FRESH_SECONDS
                    or (self.last_received is not None and received < self.last_received)):
                self.disconnect('late_or_reordered_batch')
                return self.snapshot()
            expected = (seq[:-1] + 1) % 256
            if (not np.array_equal(seq[1:], expected)
                    or (self.previous_sequence is not None and int(seq[0]) != (self.previous_sequence + 1) % 256)
                    or (self.last_received is not None and received - self.last_received > FRESH_SECONDS)):
                self.disconnect('sequence_gap_or_stall')
                return self.snapshot()
            car = values - values.mean(axis=1, keepdims=True)
            conditioned = self.conditioner.process(car)
            filtered, self.band_zi = signal.sosfilt(self.band_sos, conditioned, axis=0, zi=self.band_zi)
            self.raw = np.concatenate((self.raw, conditioned))[-1000:]
            self.filtered = np.concatenate((self.filtered, filtered))[-1000:]
            self.index += len(values)
            self.previous_sequence = int(seq[-1])
            self.last_received = received
            t = self.trial
            if t and t['result'] is not None:
                if hard_invalid(self.raw[-WINDOW_SAMPLES:]):
                    self._reject('signal_invalid', terminal=True)
            if t and t['state'] == 'active' and t['target'] != 'rest' and not t['attempted']:
                start = t['anchor'] + CUE_OFFSET_SAMPLES
                stop = start + WINDOW_SAMPLES
                if self.index >= stop:
                    t['attempted'] = True
                    offset = self.index - len(self.filtered)
                    if start < offset:
                        self._reject('window_buffer_expired', terminal=True)
                    else:
                        window = self.filtered[start-offset:stop-offset]
                        quality_window = self.raw[start-offset:stop-offset]
                        if hard_invalid(quality_window):
                            self._reject('signal_invalid', terminal=True)
                        else:
                            try:
                                logits = np.asarray(self.model.logits(window.T[None]))
                            except (ValueError, FloatingPointError):
                                self._reject('inference_invalid', terminal=True)
                                raise
                            if logits.shape != (1, 2) or not np.isfinite(logits).all():
                                self._reject('inference_invalid', terminal=True)
                                raise ValueError('Invalid two-class model output')
                            label = ('left', 'right')[int(np.argmax(logits[0]))]
                            result = dict(label=label, logits=logits[0].tolist(),
                                          matches_cue=label == t['target'],
                                          window_start=start, window_end_exclusive=stop,
                                          source=self.source, control_enabled=False)
                            self._log('candidate', trial_id=t['id'], **result)
                            t.update(result=result, reason='experimental_candidate')
                            self._apply_virtual(t, label)
            return self.snapshot()

    def snapshot(self):
        with self.lock:
            self._expire()
            t = self.trial
            reason = t['reason'] if t else 'cue_required'
            if self.last_received is None:
                input_state = 'no_data'
            elif self.clock() - self.last_received > FRESH_SECONDS:
                input_state = 'no_data'
            elif self.index < WARMUP_SAMPLES:
                input_state = 'warmup'
            else:
                input_state = 'ready'
            virtual = dict(self.virtual_hand)
            if virtual['last_command'] is not None:
                virtual['last_command'] = dict(virtual['last_command'])
            return dict(id=t['id'] if t else None, state=t['state'] if t else 'idle',
                        target=t['target'] if t else None, reason=reason,
                        result=t['result'] if t else None, source=self.source,
                        input_state=input_state, received_samples=self.index,
                        channels=list(CHANNELS), control_enabled=False, production_eligible=False,
                        virtual_hand=virtual,
                        model_status='experimental_unpromoted' if self.model else 'unavailable',
                        onset_alignment='server_receipt_watermark_not_optical_sync')
