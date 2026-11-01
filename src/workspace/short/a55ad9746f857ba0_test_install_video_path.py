"""Display-only installation checks using temporary files, never board hardware."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import install_video_path as installer


class InstallationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.display, self.candidate = root / 'display', root / 'candidate'
        self.display.mkdir()
        self.candidate.mkdir()
        for name in installer.FILES:
            (self.display / name).write_bytes(b'old')
            (self.candidate / name).write_bytes(b'new')
        (self.display / 'boot-pins.json').write_text(json.dumps({'files': {
            str(self.display / n): installer.digest(self.display / n) for n in installer.FILES}}))
        (self.candidate / 'candidate-hashes.json').write_text(json.dumps({
            n: installer.digest(self.candidate / n) for n in installer.FILES}))
        for item in (patch.object(installer, 'DISPLAY', self.display),
                     patch.object(installer, 'protected', return_value={'hashes': {}, 'boot': 'same'}),
                     patch.object(installer, 'assert_stopped', return_value='old-owner'),
                     patch.object(installer, 'replace', side_effect=lambda p, data, *args: p.write_bytes(data))):
            item.start()
            self.addCleanup(item.stop)

    def test_install_and_rollback(self):
        installer.prepare(self.candidate)
        self.assertTrue(installer.operate(self.candidate)['installed'])
        self.assertTrue(installer.operate(self.candidate, True)['rolled_back'])
        self.assertEqual((self.display / installer.FILES[0]).read_bytes(), b'old')

    def test_changed_candidate_rejected_before_writes(self):
        installer.prepare(self.candidate)
        (self.candidate / installer.FILES[-1]).write_bytes(b'changed')
        with self.assertRaises(ValueError):
            installer.operate(self.candidate)
        self.assertEqual((self.display / installer.FILES[0]).read_bytes(), b'old')

    def test_changed_active_target_rejected_before_writes(self):
        installer.prepare(self.candidate)
        (self.display / installer.FILES[-1]).write_bytes(b'other')
        with self.assertRaises(ValueError):
            installer.operate(self.candidate)
        self.assertEqual((self.display / installer.FILES[0]).read_bytes(), b'old')

    def test_failed_second_replace_restores_first(self):
        installer.prepare(self.candidate)
        calls = []
        def fail(path, data, *args):
            calls.append(path)
            if len(calls) == 2:
                raise OSError('injected failure')
            path.write_bytes(data)
        with patch.object(installer, 'replace', side_effect=fail):
            with self.assertRaises(OSError):
                installer.operate(self.candidate)
        self.assertEqual((self.display / installer.FILES[0]).read_bytes(), b'old')

    def test_protected_state_change_rejected(self):
        installer.prepare(self.candidate)
        with patch.object(installer, 'protected', return_value={'changed': True}):
            with self.assertRaises(ValueError):
                installer.operate(self.candidate)


if __name__ == '__main__':
    unittest.main()
