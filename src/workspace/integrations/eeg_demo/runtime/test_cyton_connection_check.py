"""Real PTY bytes exercise the finite stream probe; no physical receiver."""
import contextlib
import io
import json
import os
from pathlib import Path
import pty
import select
import subprocess
import tempfile
import termios
import threading
import unittest
from unittest.mock import patch

import cyton_connection_check as diagnostic


class ConnectionCheckTests(unittest.TestCase):
    def check_start(self, answer, fail_read=False):
        master, slave = pty.openpty()
        real_open = os.open
        real_ioctl = diagnostic.fcntl.ioctl
        real_read = diagnostic.read_for
        sent = bytearray()
        stop = threading.Event()

        def device():
            while not stop.is_set():
                if not select.select([master], [], [], .05)[0]:
                    continue
                command = os.read(master, 64)
                sent.extend(command)
                if b'b' in command and answer:
                    os.write(master, b'\xa0\x01'+bytes(30)+b'\xc0')

        def open_serial(path, flags):
            return real_open(os.ttyname(slave), flags)

        def ioctl(fd, request, *args):
            if request == termios.TIOCMGET:
                args[0][0] = 6
                return 0
            return real_ioctl(fd, request, *args)

        def read(fd, seconds):
            if fail_read and seconds == 3:
                raise OSError('simulated disconnect after start')
            return real_read(fd, .15)

        worker = threading.Thread(target=device)
        worker.start()
        try:
            with tempfile.TemporaryDirectory() as folder:
                with patch.object(diagnostic, '__file__', str(Path(folder)/'probe.py')), \
                     patch.dict(os.environ, {'INVOCATION_ID': 'test'}), \
                     patch.object(diagnostic.sys, 'argv', ['probe.py', '--start-only']), \
                     patch.object(diagnostic.os, 'open', side_effect=open_serial), \
                     patch.object(diagnostic.fcntl, 'ioctl', side_effect=ioctl), \
                     patch.object(diagnostic, 'read_for', side_effect=read), \
                     patch.object(diagnostic.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)), \
                     patch.object(diagnostic.subprocess, 'check_output', side_effect=['0\n', 'active\n']), \
                     contextlib.redirect_stdout(io.StringIO()):
                    try:
                        diagnostic.main()
                        error = None
                    except OSError as caught:
                        error = str(caught)
                row = json.loads((Path(folder)/'connection-report.json').read_text())
            stop.wait(.05)
            return row, bytes(sent), error
        finally:
            stop.set()
            worker.join(timeout=1)
            os.close(master)
            os.close(slave)

    def test_start_only_counts_frames_without_query_or_reset(self):
        row, sent, error = self.check_start(True)
        self.assertIsNone(error)
        self.assertEqual(sent, b'sbs')
        self.assertEqual(row['queries'], [])
        self.assertEqual(row['start_only']['frames'], 1)
        self.assertTrue(row['restored'])
        self.assertFalse(row['eeg_saved'])

    def test_no_reply_is_recorded_as_zero_not_success(self):
        row, sent, error = self.check_start(False)
        self.assertIsNone(error)
        self.assertEqual(sent, b'sbs')
        self.assertEqual(row['start_only']['bytes'], 0)
        self.assertEqual(row['start_only']['frames'], 0)
        self.assertTrue(row['restored'])

    def test_read_failure_still_stops_and_restores(self):
        row, sent, error = self.check_start(False, fail_read=True)
        self.assertIn('simulated disconnect', error)
        self.assertEqual(sent, b'sbs')
        self.assertTrue(row['restored'])


if __name__ == '__main__':
    unittest.main()
