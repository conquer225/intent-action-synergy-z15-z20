import tempfile
import unittest
from pathlib import Path

import numpy as np

from mi_rms_live_virtual import RMSVirtualSession, create_session, page_bytes
from test_mi_cued import Clock, Model


class RMSLiveVirtualTests(unittest.TestCase):
    def setUp(self):
        self.clock, self.model = Clock(), Model(score=(-1, 1))
        self.session = RMSVirtualSession(self.model, clock=self.clock)
        self.count = 0

    def feed(self, count=750, gain=10):
        for _ in range(count // 50):
            samples = np.arange(self.count, self.count + 50)
            self.clock.value += .2
            values = gain * np.sin(2*np.pi*samples[:, None]/250*np.arange(8, 16))
            self.session.feed(values, samples % 256)
            self.count += 50
            if self.session.trial and self.session.trial['state'] == 'active':
                self.session.command(dict(action='heartbeat', id=self.session.trial['id']))

    def test_no_data_warmup_and_bad_quality_cannot_arm(self):
        for count, gain in ((0, 10), (250, 10), (750, 1000)):
            self.session = RMSVirtualSession(self.model, clock=self.clock)
            self.count = 0
            self.feed(count, gain)
            with self.assertRaises(ValueError):
                self.session.command(dict(action='start', target='left', virtual_control=True))
            self.assertFalse(self.session.snapshot()['virtual_hand']['enabled'])
            self.assertEqual(self.model.calls, 0)

    def test_opposite_cue_uses_model_and_once_then_disconnect_withdraws(self):
        self.feed()
        trial = self.session.command(dict(action='start', target='left', virtual_control=True))['id']
        self.session.command(dict(action='presented', id=trial, browser_onset_ms=1, browser_send_ms=2))
        self.feed(650)
        state = self.session.snapshot()
        self.assertEqual(state['result']['label'], 'right')
        self.assertFalse(state['result']['matches_cue'])
        self.assertEqual(state['virtual_hand']['position_percent'], 20)
        self.assertEqual(state['virtual_hand']['command_count'], 1)
        self.assertFalse(state['candidate_model']['personal_head_enabled'])
        self.feed(50)
        self.assertEqual(self.model.calls, 1)
        self.session.disconnect()
        state = self.session.snapshot()
        self.assertIsNone(state['result'])
        self.assertFalse(state['quality']['ready'])
        self.assertFalse(state['virtual_hand']['enabled'])

    def test_observation_default_and_rest_manual(self):
        self.feed()
        trial = self.session.command(dict(action='start', target='left'))['id']
        self.session.command(dict(action='presented', id=trial, browser_onset_ms=1, browser_send_ms=2))
        self.feed(650)
        self.assertEqual(self.session.snapshot()['virtual_hand']['command_count'], 0)
        self.session.disconnect()
        self.session.command(dict(action='start', target='rest', virtual_control=True))
        self.assertFalse(self.session.snapshot()['virtual_hand']['enabled'])

    def test_stale_quality_and_forced_answer_refused(self):
        self.feed()
        with self.assertRaises(ValueError):
            self.session.command(dict(action='start', target='left', result='right'))
        self.clock.value += .6
        self.assertFalse(self.session.snapshot()['quality']['ready'])
        with self.assertRaises(ValueError):
            self.session.command(dict(action='start', target='left'))

    def test_wrong_checksum_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'wrong.npz'
            path.write_bytes(b'wrong')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                create_session(path, source='replay', log_path=None)

    def test_private_page_uses_existing_safe_controller(self):
        page = page_bytes().decode('utf-8')
        self.assertIn('个人适配头已停用', page)
        self.assertIn('canStart = false', page)
        self.assertIn("data.quality?.ready === true", page)
        self.assertNotIn('study_begin', page)
        self.assertNotIn('type="checkbox" checked', page)


if __name__ == '__main__':
    unittest.main()
