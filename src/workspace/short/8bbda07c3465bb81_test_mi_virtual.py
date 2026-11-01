import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from mi_cued import CuedMISession
import test_mi_cued as cued_tests


class VirtualTests(unittest.TestCase):
    setUp = cued_tests.CuedTests.setUp
    feed = cued_tests.CuedTests.feed
    command = cued_tests.CuedTests.command

    def begin(self, target='left', virtual=True):
        self.feed(750)
        self.session.command(dict(action='start', target=target, virtual_control=virtual))
        return self.command('presented', browser_onset_ms=100, browser_send_ms=101)

    def predict(self, target='left', virtual=True):
        self.begin(target, virtual)
        self.feed(650)
        return self.session.snapshot()

    def test_observation_default_and_invalid_boolean(self):
        self.begin(virtual=False)
        self.feed(650)
        hand = self.session.snapshot()['virtual_hand']
        self.assertEqual(hand['command_count'], 0)
        self.assertEqual(hand['position_percent'], 0)
        self.command('stop')
        for invalid in (1, 'true', None):
            with self.assertRaises(ValueError):
                self.session.command(dict(action='start', target='right', virtual_control=invalid))
        self.session.command(dict(action='start', target='right'))
        self.assertFalse(self.session.trial['virtual_control'])

    def test_opposite_cue_uses_model_and_only_once(self):
        self.model.score = (-1., 1.)
        state = self.predict('left')
        self.assertFalse(state['result']['matches_cue'])
        self.assertEqual(state['virtual_hand']['position_percent'], 20)
        self.assertEqual(state['virtual_hand']['last_command']['action'], 'close_step')
        for _ in range(10):
            self.command('heartbeat')
            self.session.snapshot()
        self.feed(100)
        self.assertEqual(self.model.calls, 1)
        self.assertEqual(self.session.snapshot()['virtual_hand']['command_count'], 1)
        self.assertFalse(state['control_enabled'])
        self.assertFalse(state['production_eligible'])
        self.assertFalse(state['virtual_hand']['control_enabled'])

    def test_both_directions_are_bounded(self):
        for _ in range(6):
            self.model.score = (-1., 1.)
            self.predict()
            self.command('stop')
        self.assertEqual(self.session.snapshot()['virtual_hand']['position_percent'], 100)
        for _ in range(6):
            self.model.score = (1., -1.)
            self.predict('right')
            self.command('stop')
        hand = self.session.snapshot()['virtual_hand']
        self.assertEqual(hand['position_percent'], 0)
        self.assertEqual(hand['command_count'], 12)

    def test_rest_never_calls_model_or_arms_virtual(self):
        self.begin('rest')
        self.feed(1000)
        state = self.session.snapshot()
        self.assertIsNone(state['result'])
        self.assertEqual(self.model.calls, 0)
        self.assertFalse(state['virtual_hand']['enabled'])
        self.assertEqual(state['virtual_hand']['command_count'], 0)

    def test_stop_hidden_closed_and_network_keep_pose_but_withdraw_command(self):
        self.model.score = (-1., 1.)
        for reason in ('user_stopped', 'page_hidden', 'page_closed', 'network_error'):
            self.predict()
            pose = self.session.snapshot()['virtual_hand']['position_percent']
            state = self.command('stop', reason=reason)
            hand = state['virtual_hand']
            self.assertFalse(hand['enabled'])
            self.assertEqual(hand['state'], 'stopped')
            self.assertEqual(hand['position_percent'], pose)
            self.assertIsNone(hand['last_command'])
            self.assertIsNone(state['result'])

    def test_no_data_while_waiting_disarms_without_inference(self):
        self.begin()
        self.clock.value += .51
        state = self.session.snapshot()
        self.assertEqual(state['reason'], 'no_fresh_data')
        self.assertFalse(state['virtual_hand']['enabled'])
        self.assertEqual(self.model.calls, 0)

    def test_gap_stale_fault_and_quality_do_not_reuse_old_command(self):
        for failure in ('gap', 'stale', 'disconnect', 'quality'):
            self.setUp()
            self.model.score = (-1., 1.)
            self.predict()
            if failure == 'gap':
                self.session.feed(np.ones((1, 8)), np.array([(self.count + 1) % 256]))
            elif failure == 'stale':
                self.clock.value += .51
            elif failure == 'disconnect':
                self.session.disconnect('replay_eof')
            else:
                self.feed(50, gain=2000)
            state = self.session.snapshot()
            self.assertFalse(state['virtual_hand']['enabled'])
            self.assertIsNone(state['virtual_hand']['last_command'])
            self.assertIsNone(state['result'])
            self.assertEqual(state['virtual_hand']['command_count'], 1)

    def test_heartbeat_and_timeout_disarm(self):
        for elapsed, reason in ((1.51, 'browser_heartbeat_lost'), (8, 'trial_timeout')):
            self.setUp()
            self.begin()
            self.clock.value += elapsed
            state = self.session.snapshot()
            self.assertEqual(state['reason'], reason)
            self.assertFalse(state['virtual_hand']['enabled'])
            self.assertEqual(state['virtual_hand']['command_count'], 0)

    def test_log_failure_does_not_apply_command(self):
        self.model.score = (-1., 1.)
        with tempfile.TemporaryDirectory() as directory:
            self.session.log_path = Path(directory) / 'events.jsonl'
            self.begin()
            original_log = self.session._log

            def fail_virtual(event, **fields):
                if event == 'virtual_command':
                    self.session.log_path = Path(directory) / 'missing' / 'events.jsonl'
                return original_log(event, **fields)

            with patch.object(self.session, '_log', side_effect=fail_virtual):
                with self.assertRaises(OSError):
                    self.feed(650)
            state = self.session.snapshot()
            self.assertFalse(state['virtual_hand']['enabled'])
            self.assertEqual(state['virtual_hand']['position_percent'], 0)
            self.assertEqual(state['virtual_hand']['command_count'], 0)
            self.assertIsNone(state['result'])

    def test_replay_audit_and_snapshot_are_not_writable_commands(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'events.jsonl'
            self.session = CuedMISession(self.model, source='replay', clock=self.clock, log_path=path)
            state = self.predict('right')
            state['virtual_hand']['position_percent'] = 98
            state['virtual_hand']['last_command']['position_after'] = 98
            self.assertEqual(self.session.snapshot()['virtual_hand']['position_percent'], 0)
            self.assertEqual(self.session.snapshot()['virtual_hand']['last_command']['position_after'], 0)
            events = [json.loads(line) for line in path.read_text().splitlines()]
            commands = [event for event in events if event['event'] == 'virtual_command']
            self.assertEqual(len(commands), 1)
            self.assertEqual(commands[0]['source'], 'replay')
            self.assertTrue(commands[0]['simulation'])
            self.assertFalse(commands[0]['control_enabled'])
            with self.assertRaises(ValueError):
                self.session.command(dict(action='virtual_move', position_percent=100))

    def test_new_session_has_no_old_pose_or_command(self):
        self.model.score = (-1., 1.)
        self.predict()
        restarted = CuedMISession(self.model, clock=self.clock).snapshot()
        self.assertEqual(restarted['virtual_hand']['position_percent'], 0)
        self.assertEqual(restarted['virtual_hand']['command_count'], 0)
        self.assertFalse(restarted['virtual_hand']['enabled'])


if __name__ == '__main__':
    unittest.main()
