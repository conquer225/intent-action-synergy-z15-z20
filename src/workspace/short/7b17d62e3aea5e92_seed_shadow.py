"""Shadow-only packet bridge. Separate live and replay status files."""
import time
from pathlib import Path

import numpy as np

from cyton_trial_recorder import atomic_json
from seed_quality_runtime import CHANNELS
from seed_shadow_policy import ShadowPolicy, POLICY_VERSION

LIVE_PATH = Path('/tmp/guardianloop-seed-shadow.json')
REPLAY_PATH = Path('/tmp/guardianloop-seed-replay.json')


class SeedShadow:
    def __init__(self, model_path, channel_map, source='live', status_path=None):
        if source not in ('live', 'replay'):
            raise ValueError('Invalid source')
        self.source = source
        if tuple(channel_map) != CHANNELS:
            raise ValueError('Fixed channel order is required')
        self.path = Path(status_path) if status_path else (LIVE_PATH if source == 'live' else REPLAY_PATH)
        with np.load(model_path, allow_pickle=False) as data:
            self.runtime = ShadowPolicy(dict(data))
        self.previous = None
        self.pending = []
        self.last_packet = None
        self.gaps = 0
        self.idle_published = False
        self.last_gap = None
        self.publish({'state':'no_data','valid':False,'accepted_windows':0})

    def publish(self, event):
        atomic_json(self.path, {**event, 'source':self.source, 'shadow':True,
                    'policy_version':POLICY_VERSION, 'last_gap':self.last_gap,
                    'updated_at':time.time(), 'sequence_gaps':self.gaps})

    def idle(self, now=None):
        now = time.monotonic() if now is None else now
        if self.last_packet is not None and now-self.last_packet > .5 and not self.idle_published:
            self.runtime.last_prediction = None
            self.publish({'state':'no_data','valid':False,'reason':'waiting_for_packets',
                          'accepted_windows':self.runtime.accepted_windows})
            self.idle_published = True

    def disconnect(self, reason='disconnect'):
        self.pending.clear()
        self.previous = None
        self.last_packet = None
        self.last_gap = {'baseline_retained':False,'reason':reason}
        event = self.runtime.disconnect(reason)
        self.publish(event)
        return event

    def packet(self, samples_uv, sequence, malformed=False, now=None, timing_verified=False):
        now = time.monotonic() if now is None else now
        delta = (int(sequence)-self.previous)%256 if self.previous is not None else 1
        interval = now-self.last_packet if self.last_packet is not None else 0
        gap = self.previous is not None and delta != 1
        silence = self.last_packet is not None and interval > .25
        backwards = self.last_packet is not None and interval < 0
        if gap or malformed or silence or backwards:
            self.gaps += 1
            # Reader timestamps, not slow inference/queue-consumption timestamps.
            expected = round(interval*250) % 256
            counter_error = min((delta-expected)%256, (expected-delta)%256)
            bounded = timing_verified and .25 < interval <= 5 and counter_error <= 8 and not malformed and not backwards
            partial_seconds = len(self.pending)/250
            self.pending.clear()
            if bounded:
                self.runtime.clock_seconds += partial_seconds
                event = self.runtime.gap(interval)
                self.last_gap = {'baseline_retained':event['baseline_retained'],'seconds':interval,
                                 'reason':'reader_timing_and_counter_consistent'}
                self.publish(event)
            else:
                self.disconnect('unknown_or_long_gap_or_malformed')
        self.previous, self.last_packet = int(sequence), now
        self.idle_published = False
        if malformed:
            return []
        self.pending.append(samples_uv)
        if len(self.pending) < 500:
            return []
        batch, self.pending = self.pending, []
        events = self.runtime.feed_block(np.asarray(batch))
        if events:
            self.publish(events[-1])
        return events
