import importlib
import json
from pathlib import Path
from types import ModuleType
import unittest
from unittest.mock import patch


fake_pynq = ModuleType('pynq')
fake_pynq.PL = None
with patch.dict('sys.modules', {'pynq':fake_pynq, 'fcntl':ModuleType('fcntl')}):
    diagnostic = importlib.import_module('eye_usb_hold')


class DisplayOwnerTests(unittest.TestCase):
    unit = 'eye-usb-menu-20261007-06.service'

    def check_owner(self, *, fields=None, argv=None, status=None, expected_pid=None):
        fields = fields or 'MainPID=17111\nActiveState=active\n'
        argv = argv or [str(diagnostic.BASE/'media_player.py'),
                        str(diagnostic.BASE/(self.unit[:-8]+'.json'))]
        status = status or dict(session_id=self.unit[:-8], state='menu',
            updated_monotonic=9.5, system=dict(page='home', eye={}, physical_output_enabled=False))
        with patch.object(diagnostic.subprocess, 'check_output', return_value=fields), \
             patch.object(Path, 'read_bytes', return_value=b'\0'.join(word.encode() for word in argv)), \
             patch.object(Path, 'read_text', return_value=json.dumps(status)), \
             patch.object(diagnostic.time, 'monotonic', return_value=10.):
            return diagnostic.display_owner(self.unit, 'home', expected_pid)

    def test_exact_active_owner_is_accepted(self):
        self.assertEqual(self.check_owner(expected_pid=17111), 17111)

    def test_stopped_or_replaced_owner_is_rejected(self):
        with self.assertRaises(RuntimeError):
            self.check_owner(fields='MainPID=0\nActiveState=inactive\n')
        with self.assertRaises(RuntimeError):
            self.check_owner(expected_pid=42)

    def test_foreign_process_or_state_file_is_rejected(self):
        for argv in (['/tmp/foreign.py'], [str(diagnostic.BASE/'media_player.py'), '/tmp/state.json']):
            with self.subTest(argv=argv), self.assertRaises(RuntimeError):
                self.check_owner(argv=argv)

    def test_stale_wrong_page_or_controlling_status_is_rejected(self):
        baseline = dict(session_id=self.unit[:-8], state='menu', updated_monotonic=9.5,
                        system=dict(page='home', eye={}, physical_output_enabled=False))
        for change in (dict(updated_monotonic=1.), dict(session_id='wrong'), dict(state='stopped'),
                       dict(system=dict(page='video', eye={}, physical_output_enabled=False)),
                       dict(system=dict(page='home', eye={'connected':True}, physical_output_enabled=False)),
                       dict(system=dict(page='home', eye={}, physical_output_enabled=True))):
            with self.subTest(change=change), self.assertRaises(RuntimeError):
                self.check_owner(status={**baseline, **change})

    def test_unrelated_unit_is_rejected_before_process_read(self):
        with patch.object(diagnostic.subprocess, 'check_output') as read:
            with self.assertRaises(ValueError):
                diagnostic.display_owner('guardianloop-cyton.service', 'home')
            read.assert_not_called()


class SampleFreshnessTests(unittest.TestCase):
    def test_startup_has_finite_grace(self):
        diagnostic.check_sample_freshness(None, 10., 0.)
        with self.assertRaisesRegex(RuntimeError, 'no samples'):
            diagnostic.check_sample_freshness(None, 10.01, 0.)

    def test_recent_samples_keep_session_live(self):
        diagnostic.check_sample_freshness(100., 100.5, 0.)
        diagnostic.check_sample_freshness(100., 103., 0.)

    def test_silent_stream_fails_even_with_live_process(self):
        with self.assertRaisesRegex(RuntimeError, 'silent'):
            diagnostic.check_sample_freshness(100., 103.01, 0.)


if __name__ == '__main__':
    unittest.main()
