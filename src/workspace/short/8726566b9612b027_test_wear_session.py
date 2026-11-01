import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from wear_session import WearSession


class WearTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.now=100.
        self.wear=WearSession(self.tmp.name,lambda:self.now)
        self.ident=self.wear.initialize()

    def test_restart_and_continue_never_reset(self):
        reset=Mock()
        self.assertEqual(WearSession(self.tmp.name).initialize(),self.ident)
        self.wear.poll(reset);reset.assert_not_called()

    def test_explicit_new_wear_ack_and_duplicate_do_not_double_reset(self):
        result=self.wear.request_new(self.ident);reset=Mock()
        self.wear.poll(reset)
        state=self.wear.snapshot()
        reset.assert_called_once_with(state['id'])
        self.assertNotEqual(state['id'],self.ident)
        self.assertEqual(state['last_command'],result['command_id'])
        self.assertEqual(state['command_state'],'applied')
        self.now+=1;self.wear.poll(reset);reset.assert_called_once()
        with self.assertRaises(ValueError):self.wear.request_new(self.ident)

    def test_recording_or_expired_request_cannot_reset(self):
        for recording in (True,False):
            result=self.wear.request_new(self.ident)
            if not recording:self.now+=31
            reset=Mock();self.wear.poll(reset,recording=recording)
            reset.assert_not_called()
            self.assertEqual(self.wear.snapshot()['last_command'],result['command_id'])
            self.assertEqual(self.wear.snapshot()['id'],self.ident)
            self.now+=1

    def test_pending_request_not_overwritten(self):
        self.wear.request_new(self.ident)
        before=self.wear.command_path.read_bytes()
        with self.assertRaises(ValueError):self.wear.request_new(self.ident)
        self.assertEqual(self.wear.command_path.read_bytes(),before)

    def test_boot_change_gets_new_identity_without_old_baseline(self):
        self.wear.boot='other-boot'
        self.assertNotEqual(self.wear.initialize(),self.ident)

    def test_reset_failure_not_acknowledged_as_success(self):
        self.wear.request_new(self.ident)
        with self.assertRaises(OSError):self.wear.poll(Mock(side_effect=OSError('disk')))
        self.assertEqual(self.wear.snapshot()['id'],self.ident)
        self.assertIsNone(self.wear.snapshot()['last_command'])
