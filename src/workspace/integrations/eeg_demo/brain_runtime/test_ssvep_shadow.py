import json
import tempfile
import time
import unittest
from pathlib import Path

import numpy as np

from ssvep_shadow import SSVEPShadow, CHANNELS, LIVE_PATH
from ssvep_stream import SSVEPStream
from guardianloop_web import ssvep_payload


HERE = Path(__file__).resolve().parent
# Deployment stages the frozen research assets beside this module.
ASSETS = HERE if (HERE/'ssvep_causal_protocol.json').exists() else HERE.parent/'eeg_apps_z15'
SOS = (HERE/'ssvep_candidate_sos.npy' if (HERE/'ssvep_candidate_sos.npy').exists()
       else ASSETS/'output/ssvep_causal_20260926/candidate_sos.npy')


class ShadowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/'status.json'
        self.protocol = ASSETS/'ssvep_causal_protocol.json'
        self.shadow = SSVEPShadow(self.protocol, SOS, CHANNELS, source='replay', status_path=self.path)
        t = np.arange(2200)/250
        self.samples = np.zeros((len(t), 8))
        self.samples[:, 6] = 12*np.sin(2*np.pi*10*t) + np.sin(2*np.pi*17*t)
        self.samples[:, 7] = 9*np.sin(2*np.pi*10*t+.3) + np.sin(2*np.pi*19*t)

    def tearDown(self):
        self.temp.cleanup()

    def feed(self, start=0, end=1000):
        events = []
        for i in range(start, end):
            events.extend(self.shadow.packet(self.samples[i], i%256, now=i/250))
        return events

    def test_wrap_and_numerical_parity(self):
        events = self.feed()
        stream = SSVEPStream(json.loads(self.protocol.read_text()), np.load(SOS))
        expected = stream.push(self.samples[:1000], 0)
        self.assertEqual(len(events), len(expected))
        self.assertEqual(self.shadow.gaps, 0)
        for a, b in zip(events, expected):
            self.assertEqual(a['state'], 'candidate_only')
            self.assertEqual(a['frequency_hz'], b['frequency_hz'])
            np.testing.assert_allclose(a['scores'], b['scores'], atol=1e-12)
            self.assertFalse(a['control_enabled'])
            self.assertEqual(a['source'], 'replay')

    def test_gap_reset_and_full_warmup(self):
        self.feed(0, 700)
        self.shadow.packet(self.samples[702], 702%256, now=702/250)
        self.assertIsNone(self.shadow.latest['frequency_hz'])
        self.assertEqual(self.shadow.gaps, 1)
        self.assertFalse(self.feed(703, 1361))
        self.assertEqual(len(self.feed(1361, 1362)), 1)

    def test_candidate_persists_between_hops_without_false_warmup(self):
        self.feed(0, 660)
        event = self.shadow.latest
        self.assertEqual(event['state'], 'candidate_only')
        self.assertFalse(self.feed(660, 700))
        self.assertIs(self.shadow.latest, event)
        self.assertEqual(self.shadow.latest['state'], 'candidate_only')

    def test_duplicate_malformed_and_timing(self):
        for kind in ('duplicate', 'malformed', 'timing', 'backwards'):
            self.shadow.disconnect()
            self.feed(0, 700)
            seq = 699%256 if kind == 'duplicate' else 700%256
            now = 4 if kind == 'timing' else (0 if kind == 'backwards' else 2.8)
            self.shadow.packet(self.samples[700], seq, kind == 'malformed', now=now)
            self.assertIsNone(self.shadow.latest['frequency_hz'])
            self.assertIsNone(self.shadow.stream.latest)

    def test_idle_clears_then_requires_full_window(self):
        self.feed(0, 700)
        self.shadow.idle(now=4)
        self.assertEqual(self.shadow.latest['state'], 'no_data')
        self.assertFalse(self.feed(700, 1359))
        self.assertEqual(len(self.feed(1359, 1360)), 1)

    def test_startup_silence_is_explicit_and_does_not_repeatedly_reset(self):
        self.shadow.idle(now=1)
        event = self.shadow.latest
        self.assertEqual(event['reason'], 'waiting_for_cyton')
        self.assertIsNone(self.shadow.idle(now=5))
        self.assertIs(self.shadow.latest, event)
        self.assertFalse(self.feed(0, 659))
        self.assertEqual(len(self.feed(659, 660)), 1)

    def test_selected_nonfinite_and_rail(self):
        self.feed(0, 700)
        x = self.samples[700].copy(); x[6] = np.nan
        self.shadow.packet(x, 700%256, now=2.8)
        self.assertEqual(self.shadow.latest['state'], 'signal_invalid')
        self.shadow.packet(self.samples[701], 701%256, now=2.804, adc_rails=[False, True])
        self.assertIsNone(self.shadow.latest['frequency_hz'])

    def test_unused_bad_channels_do_not_gate(self):
        self.samples[:, :6] = np.nan
        self.assertTrue(all(e['state'] == 'candidate_only' for e in self.feed()))

    def test_flat_and_excess_amplitude_are_rejected(self):
        self.samples[:, 6] = 12345
        self.assertTrue(all(e['state'] == 'signal_invalid' for e in self.feed()))
        self.shadow.disconnect()
        self.samples[:, 6] = 500*np.sin(2*np.pi*10*np.arange(len(self.samples))/250)
        events = self.feed()
        self.assertTrue(all(e['frequency_hz'] is None for e in events))
        self.assertTrue(events[-1]['quality']['hard_bad'])

    def test_raw_mains_warns_without_changing_thresholds(self):
        self.samples[:, 6:8] += 60*np.sin(2*np.pi*50*np.arange(len(self.samples))/250)[:, None]
        events = self.feed()
        self.assertTrue(events[-1]['quality']['warning'])
        self.assertFalse(events[-1]['control_enabled'])

    def test_montage_and_replay_path_guard(self):
        with self.assertRaises(ValueError):
            SSVEPShadow(self.protocol, SOS, CHANNELS[::-1], status_path=self.path)
        with self.assertRaises(ValueError):
            SSVEPShadow(self.protocol, SOS, CHANNELS, source='replay', status_path=LIVE_PATH)

    def test_web_hides_stale_wrong_source_and_invalid(self):
        self.feed()
        event = self.shadow.latest.copy()
        replay_path = Path(self.temp.name)/'replay.json'
        for updates in ({'source':'replay'}, {'updated_monotonic':time.monotonic()-5},
                        {'input_age_seconds':1}, {'state':'signal_invalid'}):
            row = dict(event, source='live', updated_monotonic=time.monotonic(),
                       updated_at=time.time(), input_age_seconds=0)
            row.update(updates)
            self.path.write_text(json.dumps(row))
            result = ssvep_payload(self.path, replay_path)
            self.assertIsNone(result['live']['frequency_hz'])
            self.assertFalse(result['live']['valid'])


if __name__ == '__main__':
    unittest.main()
