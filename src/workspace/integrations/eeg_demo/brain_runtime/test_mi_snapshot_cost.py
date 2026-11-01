"""Deferred MI observations must not defer safety checks or change predictions."""
import unittest
from unittest.mock import patch

import numpy as np

from mi_rms_live_virtual import RMSVirtualSession
from test_mi_cued import Clock, Model


class SnapshotCostTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.sessions = [RMSVirtualSession(Model(), source='replay', clock=self.clock)
                         for _ in range(2)]
        self.index = 0

    def feed(self, count=50, gain=10):
        for offset in range(0, count, 50):
            width = min(50, count-offset)
            indexes = np.arange(self.index, self.index+width)
            values = gain*np.sin(2*np.pi*indexes[:, None]/250*np.arange(8, 16)[None])
            self.clock.value += width/250
            self.sessions[0].feed(values, indexes % 256)
            returned = self.sessions[1].feed(values, indexes % 256, return_snapshot=False)
            self.assertIsNone(returned)
            self.index += width
            for session in self.sessions:
                if session.trial and session.trial['state'] == 'active':
                    session.command(dict(action='heartbeat', id=session.trial['id']))

    def start(self, target='right'):
        for session in self.sessions:
            state = session.command(dict(action='start', target=target, virtual_control=True))
            session.command(dict(action='presented', id=state['id'],
                                 browser_onset_ms=100, browser_send_ms=101))

    def assert_same(self):
        first, second = [session.snapshot() for session in self.sessions]
        for state in (first, second):
            state.pop('id')
            if state['virtual_hand']['last_command']:
                state['virtual_hand']['last_command'].pop('trial_id')
        self.assertEqual(first, second)
        for name in ('raw', 'filtered', 'band_zi'):
            np.testing.assert_array_equal(getattr(self.sessions[0], name),
                                          getattr(self.sessions[1], name))
        self.assertEqual(self.sessions[0].model.calls, self.sessions[1].model.calls)

    def test_idle_feed_omits_only_observation(self):
        session = self.sessions[1]
        with patch.object(session, 'snapshot', wraps=session.snapshot) as observed:
            session.feed(np.ones((50, 8)), np.arange(50), return_snapshot=False)
            observed.assert_not_called()
        self.sessions[0].feed(np.ones((50, 8)), np.arange(50))
        self.index = 50
        self.feed(1000)
        self.assert_same()
        self.assertEqual(session.model.calls, 0)

    def test_trial_and_post_prediction_quality_withdrawal_are_identical(self):
        self.feed(750)
        self.start()
        self.feed(650)
        self.assert_same()
        self.assertEqual(self.sessions[1].snapshot()['result']['label'], 'left')
        self.feed(50, gain=2000)
        self.assert_same()
        self.assertIsNone(self.sessions[1].snapshot()['result'])
        self.assertEqual(self.sessions[1].snapshot()['reason'], 'signal_invalid')

    def test_gap_late_batch_and_expiry_withdraw_without_observation(self):
        self.feed(750)
        self.start()
        self.feed(650)
        self.clock.value += .51
        for session, observe in zip(self.sessions, (True, False)):
            session.feed(np.ones((50, 8)), np.arange(self.index, self.index+50) % 256,
                         received_monotonic=self.clock.value-.6, return_snapshot=observe)
        self.assert_same()
        self.assertEqual(self.sessions[1].index, 0)
        self.feed(750)
        self.index += 1
        self.feed()
        self.assert_same()
        self.assertEqual(self.sessions[1].index, 0)

    def test_quality_cache_is_input_bound_and_freshness_is_not_cached(self):
        self.feed(750)
        session = self.sessions[1]
        session._quality_input = None
        from mi_rms_live_virtual import hard_quality
        with patch('mi_rms_live_virtual.hard_quality', wraps=hard_quality) as quality:
            for _ in range(5):
                self.assertTrue(session.snapshot()['quality']['ready'])
            self.assertEqual(quality.call_count, 1)
            indexes = np.arange(self.index, self.index+50)
            values = 10*np.sin(2*np.pi*indexes[:, None]/250*np.arange(8, 16)[None])
            self.clock.value += .2
            session.feed(values, indexes % 256, return_snapshot=False)
            self.assertTrue(session.snapshot()['quality']['ready'])
            self.assertEqual(quality.call_count, 2)
            self.clock.value += .51
            state = session.snapshot()
            self.assertEqual(state['input_state'], 'no_data')
            self.assertFalse(state['quality']['ready'])
            self.assertEqual(quality.call_count, 2)
            session.disconnect()
            self.assertIsNone(session._quality_input)

    def test_invalid_flag_and_nan_never_produce_a_result(self):
        session = self.sessions[1]
        with self.assertRaises(ValueError):
            session.feed(np.ones((50, 8)), np.arange(50), return_snapshot='false')
        with self.assertRaises(ValueError):
            session.feed(np.full((50, 8), np.nan), np.arange(50), return_snapshot=False)
        self.assertIsNone(session.snapshot()['result'])
        self.assertEqual(session.index, 0)


if __name__ == '__main__':
    unittest.main()
