"""Raw Cyton packet adapter for an observation-only SSVEP candidate.

No actuator output, PL transport, personal calibration or non-target detection.
Quality thresholds are engineering checks, not validated SSVEP confidence gates.
"""
import json
import math
import time
from pathlib import Path

import numpy as np

from cyton_sqi import channel_sqi
from cyton_trial_recorder import atomic_json
from ssvep_stream import SSVEPStream

CHANNELS = ('F3', 'F4', 'C3', 'C4', 'T7', 'T8', 'O1', 'O2')
LIVE_PATH = Path('/tmp/guardianloop-ssvep-shadow.json')
REPLAY_PATH = Path('/tmp/guardianloop-ssvep-replay.json')
POLICY_VERSION = 'ssvep-shadow-engineering-v1'


class SSVEPShadow:
    def __init__(self, protocol_path, coefficients_path, channel_map, source='live', status_path=None,
                 event_sink=None):
        if tuple(channel_map) != CHANNELS:
            raise ValueError('SSVEP requires the fixed eight-channel order')
        if source not in ('live', 'replay'):
            raise ValueError('Invalid SSVEP source')
        self.source = source
        self.event_sink = event_sink
        self.path = Path(status_path) if status_path else (LIVE_PATH if source == 'live' else REPLAY_PATH)
        if source == 'replay' and self.path == LIVE_PATH:
            raise ValueError('Replay cannot publish to the live path')
        config = json.loads(Path(protocol_path).read_text(encoding='utf-8'))
        if (tuple(config['fixed_cap']) != CHANNELS or config['selected_cap_indices'] != [6, 7]
                or config['sample_rate_hz'] != 250 or config['batch_samples'] != 10
                or config['window_samples'] != 500 or config['hop_samples'] != 50
                or config['warmup_samples'] != 160):
            raise ValueError('Unsupported SSVEP stream contract')
        self.stream = SSVEPStream(config, np.load(coefficients_path, allow_pickle=False))
        self.pending = []
        self.raw = np.empty((500, 2), dtype=np.float64)
        self.raw_cursor = 0
        self.previous = self.last_packet = None
        self.index = 0
        self.gaps = 0
        self.packet_count = 0
        self.last_publish = -float('inf')
        self.latest = None
        self.invalid_rail = False
        self.publish('no_data', reason='startup')

    def publish(self, state, **fields):
        now = time.monotonic()
        lag = max(0., now-self.last_packet) if self.source == 'live' and self.last_packet is not None else 0.
        event = dict(state=state, valid=state == 'candidate_only', frequency_hz=None,
                     scores=None, target_index=None, margin=None, reason=None)
        event.update(fields)
        event.update(source=self.source, shadow=True, control_enabled=False,
                     policy_version=POLICY_VERSION, channels=['O1', 'O2'],
                     sequence_gaps=self.gaps, packets_seen=self.packet_count,
                     warmup_samples=min(self.stream.seen, 660), required_samples=660,
                     input_age_seconds=lag, updated_at=time.time(),
                     updated_monotonic=now, confidence_validated=False)
        if self.source == 'live' and lag > .5 and state == 'candidate_only':
            event.update(state='no_data', valid=False, frequency_hz=None, scores=None,
                         target_index=None, margin=None, reason='input_backlog')
        self.write_event(event)
        self.latest = event
        self.last_publish = now
        if self.event_sink is not None:
            self.event_sink(event)
        return event

    def write_event(self, event):
        atomic_json(self.path, event)

    def disconnect(self, reason='disconnect', publish=True):
        self.pending.clear()
        self.raw_cursor = 0
        self.previous = self.last_packet = None
        self.invalid_rail = False
        self.stream.reset(reason)
        if publish:
            return self.publish('no_data', reason=reason)
        return None

    def idle(self, now=None):
        now = time.monotonic() if now is None else now
        if self.last_packet is not None and now-self.last_packet > .5:
            return self.disconnect('packet_timeout')
        if self.last_packet is None and self.latest.get('reason') == 'startup':
            return self.publish('no_data', reason='waiting_for_cyton')
        return None

    def _quality(self):
        # Raw/filtered O1/O2 share the same descriptor implementation as the
        # primary path, but unused padding columns need no FFT or quantiles.
        # The first decision follows 660 fresh samples, so every ring slot is
        # overwritten after startup/reset before it can enter a quality window.
        raw = np.concatenate((self.raw[self.raw_cursor:], self.raw[:self.raw_cursor]))
        combined = np.zeros((500, 8), dtype=np.float64)
        combined[:, :2] = raw
        combined[:, 2:4] = self.stream.buffer
        descriptors = channel_sqi(combined, channel_indices=(0,1,2,3))
        raw_sqi, clean_sqi = descriptors[:2], descriptors[2:4]
        channels = []
        for j, name in enumerate(('O1', 'O2')):
            r, f = raw_sqi[j], clean_sqi[j]
            hard, warnings = [], []
            if r[2] >= .95 or f[2] >= .95: hard.append('flatline')
            if f[1] > 100: hard.append('filtered_amplitude_over_100uv')
            if r[4] > .2: warnings.append('raw_mains')
            if r[1] > 100: warnings.append('raw_amplitude')
            if r[6] > 40: warnings.append('raw_step')
            if f[4] > .2: warnings.append('residual_mains')
            channels.append(dict(channel=name, hard_reasons=hard, warnings=warnings,
                                 raw_p99_uv=float(r[1]), filtered_p99_uv=float(f[1]),
                                 raw_mains_ratio=float(r[4]), raw_flat_ratio=float(r[2])))
        return dict(policy='fixed engineering checks; no personal baseline',
                    hard_bad=any(c['hard_reasons'] for c in channels),
                    warning=any(c['warnings'] for c in channels), channels=channels)

    def packet(self, samples_uv, sequence, malformed=False, now=None, adc_rails=None):
        now = time.monotonic() if now is None else float(now)
        values = np.asarray(samples_uv, dtype=np.float64)
        if values.shape != (8,) or not 0 <= int(sequence) <= 255 or not math.isfinite(now):
            raise ValueError('Invalid Cyton sample/sequence/time')
        rails = (False, False) if adc_rails is None else adc_rails
        if len(rails) != 2:
            raise ValueError('Expected O1/O2 ADC rail flags')
        delta = (int(sequence)-self.previous) % 256 if self.previous is not None else 1
        interval = now-self.last_packet if self.last_packet is not None else 0.
        if malformed or delta != 1 or interval > .25 or interval < 0:
            self.gaps += 1
            self.disconnect('malformed_or_sequence_or_timing_gap')
        self.previous, self.last_packet = int(sequence), now
        self.packet_count += 1
        if malformed:
            return []
        if not (math.isfinite(values[6]) and math.isfinite(values[7])) or rails[0] or rails[1]:
            new_invalid = not self.invalid_rail
            if new_invalid:
                self.disconnect('nonfinite_or_adc_rail', publish=False)
                self.previous, self.last_packet = int(sequence), now
                self.invalid_rail = True
            # The first rail immediately revokes a candidate; repeated rails
            # refresh the invalid endpoint without writing every EEG packet.
            if new_invalid or time.monotonic()-self.last_publish >= .5:
                return [self.publish('signal_invalid', reason='nonfinite_or_adc_rail')]
            return []
        self.invalid_rail = False
        # Other cap channels do not gate this two-channel candidate.
        selected = np.zeros(8)
        selected[6:8] = values[6:8]
        self.pending.append(selected)
        # Rail/nonfinite samples were rejected above and reset the stream;
        # they cannot reach a complete quality window and need no history scan.
        self.raw[self.raw_cursor] = values[6:8]
        self.raw_cursor = (self.raw_cursor+1) % 500
        self.index += 1
        if len(self.pending) < 10:
            return []
        batch, self.pending = np.asarray(self.pending), []
        events = self.stream.push(batch, self.index-len(batch))
        output = []
        for event in events:
            quality = self._quality()
            state = 'signal_invalid' if quality['hard_bad'] else event['status']
            fields = {k: event[k] for k in ('window_start_index', 'window_end_index_exclusive')}
            if state == 'candidate_only':
                fields.update({k: event[k] for k in ('frequency_hz', 'target_index', 'scores', 'margin')})
            output.append(self.publish(state, quality=quality, **fields))
        if not events and self.stream.status == 'warmup' and (
                self.latest['state'] != 'warmup' or time.monotonic()-self.last_publish >= .5):
            self.publish('warmup', reason=self.stream.reset_reason)
        return output
