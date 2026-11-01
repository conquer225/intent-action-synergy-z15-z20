"""Fresh device/service metadata without altering EEG publication gates."""
import json
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import guardianloop_web as web


class SystemStatusTests(unittest.TestCase):
    def test_display_readiness_requires_current_running_snapshot(self):
        for row, ready in (
                ({'state':'menu','updated_monotonic':99}, True),
                ({'state':'playing','updated_monotonic':99}, True),
                ({'state':'menu','updated_monotonic':95}, False),
                ({'state':'menu','updated_monotonic':101}, False),
                ({'state':'menu','updated_monotonic':float('nan')}, False),
                ({'state':'menu','updated_monotonic':None}, False),
                ({'state':'error','updated_monotonic':99,'error':'Runtime guard heartbeat expired'}, False),
                ([], False), ({}, False)):
            with self.subTest(row=row), patch.object(web, 'read_json', return_value=row), \
                    patch.object(web.time, 'monotonic', return_value=100):
                result=web.hdmi_status()
                self.assertEqual(result['ready'], ready)
                if isinstance(row, dict) and row.get('state')=='error':
                    self.assertEqual(result['error'], row['error'])

    def test_status_timestamp_does_not_accept_future_nonfinite_or_nonobject(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/'status'
            for stamp, stale in ((100,False),(0,True),(-1,True),(101,True),
                                 (float('nan'),True),(float('inf'),True)):
                path.write_text(json.dumps({'updated_at':stamp}))
                with patch.object(web.time, 'time', return_value=100):
                    self.assertEqual(web.read_payload(path, 3)[1], stale)
            path.write_text('[]')
            self.assertEqual(web.read_payload(path,3), ({},True))

    def status(self, output, returncode=0):
        with patch.object(web.subprocess, 'run', return_value=SimpleNamespace(
                stdout=output, returncode=returncode)) as run, \
                patch.object(web, 'cyton_receiver_present', return_value=True), \
                patch.object(web, 'startup_status', return_value={'state': 'ready'}):
            value = web.system_status()
        self.assertEqual(run.call_count, 1)
        return value

    def test_unit_ids_not_response_order_determine_active_state(self):
        result = self.status('Id=guardianloop-cyton.service\nActiveState=active\n\n'
                             'ActiveState=failed\nId=guardianloop-ap.service\n')
        self.assertTrue(result['acquisition_active'])
        self.assertFalse(result['ap_active'])
        self.assertTrue(result['receiver_present'])
        self.assertEqual(result['startup'], {'state': 'ready'})

    def test_inactive_service_is_not_reported_active(self):
        result = self.status('Id=guardianloop-ap.service\nActiveState=active\n\n'
                             'Id=guardianloop-cyton.service\nActiveState=inactive\n')
        self.assertTrue(result['ap_active'])
        self.assertFalse(result['acquisition_active'])

    def test_failed_or_malformed_query_fails_closed(self):
        for output, code in (
                ('Id=guardianloop-ap.service\nActiveState=active\n', 0),
                ('Id=guardianloop-ap.service\nActiveState=active\n\n'
                 'Id=guardianloop-ap.service\nActiveState=active\n', 0),
                ('Id=foreign.service\nActiveState=active\n\n'
                 'Id=guardianloop-cyton.service\nActiveState=active\n', 0),
                ('ActiveState=active\n\nActiveState=active\n', 0),
                ('not property output', 0), ('', 1)):
            with self.subTest(output=output, returncode=code):
                result = self.status(output, code)
                self.assertFalse(result['ap_active'])
                self.assertFalse(result['acquisition_active'])

    def test_service_timeout_does_not_keep_previous_active_state(self):
        good = 'Id=guardianloop-ap.service\nActiveState=active\n\n' \
               'Id=guardianloop-cyton.service\nActiveState=active\n'
        with patch.object(web.subprocess, 'run', side_effect=[
                SimpleNamespace(stdout=good, returncode=0),
                subprocess.TimeoutExpired('systemctl', 1)]), \
                patch.object(web, 'cyton_receiver_present', return_value=False), \
                patch.object(web, 'startup_status', return_value={}):
            self.assertTrue(web.system_status()['acquisition_active'])
            result = web.system_status()
        self.assertFalse(result['ap_active'])
        self.assertFalse(result['acquisition_active'])

    def test_receiver_identity_is_the_live_service_identity_and_not_cached(self):
        identity = '/dev/serial/by-id/usb-FTDI_FT231X_USB_UART_D309LDXY-if00-port0'
        with patch.object(web, 'Path') as path:
            path.return_value.is_char_device.side_effect = [True, False]
            self.assertTrue(web.cyton_receiver_present())
            self.assertFalse(web.cyton_receiver_present())
        self.assertEqual([call.args[0] for call in path.call_args_list], [identity, identity])

    @unittest.skipUnless(Path('/dev/null').is_char_device(), 'Linux character-device fixture')
    def test_receiver_check_follows_udev_link_and_detects_removal(self):
        with TemporaryDirectory() as directory:
            receiver = Path(directory) / 'receiver'
            receiver.symlink_to('/dev/null')
            with patch.object(web, 'Path', return_value=receiver):
                self.assertTrue(web.cyton_receiver_present())
                receiver.unlink()
                self.assertFalse(web.cyton_receiver_present())
                receiver.touch()
                self.assertFalse(web.cyton_receiver_present())
                receiver.unlink()
                receiver.symlink_to(Path(directory) / 'missing')
                self.assertFalse(web.cyton_receiver_present())


if __name__ == '__main__':
    unittest.main()
