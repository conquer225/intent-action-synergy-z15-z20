import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import guardianloop_startup as startup
import guardianloop_web as web


class StartupTests(unittest.TestCase):
    def release(self, root):
        (root / 'code.py').write_bytes(b'code')
        (root / 'guardianloop_pynq.bit').write_bytes(b'bit')
        (root / 'guardianloop_pynq.hwh').write_bytes(b'hwh')
        manifest = {'release_id': 'test', 'channels': list(startup.CHANNELS),
                    'files': {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                              for name in ('code.py', 'guardianloop_pynq.bit', 'guardianloop_pynq.hwh')}}
        path = root / 'manifest.json'
        path.write_text(json.dumps(manifest))
        return manifest, path

    def test_corrupt_release_prevents_any_pl_load_and_records_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest, path = self.release(root)
            (root / 'code.py').write_bytes(b'changed')
            with patch.object(startup, 'BIT_SHA256', manifest['files']['guardianloop_pynq.bit']), \
                    patch.object(startup, 'HWH_SHA256', manifest['files']['guardianloop_pynq.hwh']), \
                    patch.object(startup, 'boot_id', return_value='boot'), \
                    patch.object(startup, 'load_production_pl') as load:
                with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                    startup.run(root, path, root / 'status.json')
                load.assert_not_called()
                status = json.loads((root / 'status.json').read_text())
                self.assertEqual(status['state'], 'failed')
                self.assertEqual(status['stage'], 'release')
                self.assertFalse(status['pl']['loaded'])

    def test_model_failure_prevents_pl_load(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            _, path = self.release(root)
            with patch.object(startup, 'verify_files', return_value=3), \
                    patch.object(startup, 'boot_id', return_value='boot'), \
                    patch.object(startup, 'verify_models', side_effect=ValueError('model contract')), \
                    patch.object(startup, 'load_production_pl') as load:
                with self.assertRaisesRegex(ValueError, 'model contract'):
                    startup.run(root, path, root / 'status.json')
                load.assert_not_called()
                self.assertEqual(json.loads((root / 'status.json').read_text())['stage'], 'arm_models')

    def test_pl_failure_cannot_publish_ready(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            _, path = self.release(root)
            with patch.object(startup, 'verify_files', return_value=3), \
                    patch.object(startup, 'boot_id', return_value='boot'), \
                    patch.object(startup, 'verify_models', return_value={'fatigue': {'backend': 'arm'}}), \
                    patch.object(startup, 'load_production_pl', side_effect=RuntimeError('wrong ID')):
                with self.assertRaisesRegex(RuntimeError, 'wrong ID'):
                    startup.run(root, path, root / 'status.json')
                status = json.loads((root / 'status.json').read_text())
                self.assertEqual(status['state'], 'failed')
                self.assertEqual(status['stage'], 'pl_load')

    def test_web_ignores_selftest_from_another_boot(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'boot').write_text('new-boot')
            (root / 'status').write_text(json.dumps({'state': 'ready', 'boot_id': 'old-boot'}))
            with patch.object(web, 'STARTUP_PATH', root / 'status'), \
                    patch.object(web, 'BOOT_ID_PATH', root / 'boot'):
                self.assertEqual(web.startup_status(), {'state': 'not_checked'})
                (root / 'status').write_text(json.dumps({'state': 'ready', 'boot_id': 'new-boot'}))
                self.assertEqual(web.startup_status()['state'], 'ready')


if __name__ == '__main__':
    unittest.main()
