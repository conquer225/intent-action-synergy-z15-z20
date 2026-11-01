"""USB trace fixtures prove observations cannot masquerade as device replies."""
import json
from pathlib import Path
import tempfile
import unittest

from usb_boot_trace import input_status, usb_devices


class BootTraceTests(unittest.TestCase):
    def test_recovery_and_runtime_modes_remain_distinct(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            eye = root/'1-1.2'
            eye.mkdir()
            (eye/'idVendor').write_text('2104\n')
            (eye/'idProduct').write_text('0102\n')
            (eye/'serial').write_text('eye-serial\n')
            self.assertEqual(usb_devices(root)[0]['idProduct'], '0102')
            (eye/'idProduct').write_text('0124\n')
            self.assertEqual(usb_devices(root)[0]['idProduct'], '0124')
            (eye/'idVendor').unlink()
            self.assertEqual(usb_devices(root), [])

    def test_status_whitelist_never_includes_eeg_or_model_features(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'status.json').write_text(json.dumps({'packets_seen': 42,
                'reason': 'CHANNEL_CONFIGURATION_UNCONFIRMED', 'samples': [123],
                'raw_samples': [456], 'sqi': {'quality': .5}, 'emotion': {'score': .4}}))
            (root/'telemetry.json').write_text('not-json-never-read')
            row = input_status(root)
            self.assertTrue(row['telemetry_present'])
            self.assertEqual(row['status']['packets_seen'], 42)
            self.assertEqual(set(row['status']), {
                'packets_seen', 'reason', 'serial_identity', 'updated_at'})

    def test_absent_and_malformed_status_do_not_invent_a_connection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(input_status(root), {
                'status_present': False, 'telemetry_present': False})
            (root/'status.json').write_text('{broken')
            self.assertEqual(input_status(root), {
                'status_error': 'invalid_json', 'telemetry_present': False})


if __name__ == '__main__':
    unittest.main()
