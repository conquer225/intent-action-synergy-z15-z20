"""Device-identity recovery checks without physical USB or EEG acquisition."""
import contextlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import guardianloop_acquisition as entry


class USBRecoveryTests(unittest.TestCase):
    def test_service_uses_pinned_identity_and_explicit_port_wins(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'GL_CYTON_PORT': '/dev/serial/by-id/accepted'}):
            root = Path(folder)
            args = entry.acquisition_args(['--windows', '0'], root, root/'off')
            self.assertEqual(args[args.index('--port')+1], '/dev/serial/by-id/accepted')
            for explicit in (['--port', '/dev/test'], ['--port=/dev/test']):
                self.assertEqual(entry.acquisition_args(explicit, root, root/'off'),
                                 explicit+['--wait-for-data'])

    def test_missing_identity_waits_without_fallback_and_revokes_prediction(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            identity = root/'receiver'
            status = root/'status.json'
            status.write_text('{"valid":true,"score":0.8,"emotion":{"valid":true}}')
            probes = []
            sleeps = []
            real_stat = Path.stat

            def probe(path, *args, **kwargs):
                if path != identity:
                    return real_stat(path, *args, **kwargs)
                probes.append(str(path))
                if len(probes) <= 2:
                    raise FileNotFoundError(path)
                return SimpleNamespace(st_mode=stat.S_IFCHR)

            def sleep(seconds):
                sleeps.append(seconds)
                payload = json.loads(status.read_text())
                self.assertFalse(payload['valid'])
                self.assertFalse(payload['emotion']['valid'])
                self.assertIsNone(payload['score'])
                self.assertEqual(payload['reason'], 'WAITING_FOR_USB_RECEIVER')

            with patch.object(Path, 'stat', probe), patch.object(Path, 'resolve', return_value=Path('/dev/ttyUSB1')), \
                    patch.object(entry.time, 'sleep', sleep), contextlib.redirect_stdout(io.StringIO()) as output:
                entry.wait_for_receiver(['--port', str(identity), '--status-file', str(status)])
            self.assertEqual(sleeps, [1, 1])
            self.assertEqual(output.getvalue().count('CYTON_USB_WAITING:'), 1)
            self.assertIn('node='+str(Path('/dev/ttyUSB1')), output.getvalue())

    def test_non_device_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'not-a-device'
            path.write_text('fixture')
            with self.assertRaisesRegex(ValueError, 'character device'):
                entry.wait_for_receiver(['--port', str(path)])

    @unittest.skipUnless(os.name == 'posix', 'Linux character devices and symlinks')
    def test_same_identity_resolves_again_after_node_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            identity = Path(folder)/'receiver'
            identity.symlink_to('/dev/null')
            with contextlib.redirect_stdout(io.StringIO()) as output:
                entry.wait_for_receiver(['--port', str(identity)])
                identity.unlink()
                identity.symlink_to('/dev/zero')
                entry.wait_for_receiver(['--port', str(identity)])
            self.assertIn('node=/dev/null', output.getvalue())
            self.assertIn('node=/dev/zero', output.getvalue())


if __name__ == '__main__':
    unittest.main()
