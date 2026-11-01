"""Exercise the real CLI against a Linux pseudo-terminal, not a Cyton device."""
import errno
import json
import os
from pathlib import Path
import pty
import select
import subprocess
import sys
import time
import unittest


class SerialProbeTests(unittest.TestCase):
    def probe(self, query_only, response):
        master, slave = pty.openpty()
        command = [sys.executable, str(Path(__file__).with_name('cyton_usb_probe.py')),
                   '--port', os.ttyname(slave), '--timeout', '.4']
        if query_only:
            command.append('--query-only')
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        sent = bytearray()
        answered = False
        try:
            deadline = time.monotonic() + 3
            while process.poll() is None and time.monotonic() < deadline:
                if not select.select([master], [], [], .05)[0]:
                    continue
                try:
                    sent.extend(os.read(master, 4096))
                except OSError as error:
                    if error.errno == errno.EIO:
                        break
                    raise
                expected = b'V' if query_only else b'v'
                if expected in sent and response and not answered:
                    os.write(master, response)
                    answered = True
            output, errors = process.communicate(timeout=1)
            self.assertFalse(errors, errors)
            return process.returncode, output, bytes(sent)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=1)
            os.close(master)
            os.close(slave)

    def test_query_receives_version_without_soft_reset(self):
        code, output, sent = self.probe(True, b'v3.1.1$$$')
        self.assertEqual(code, 0)
        self.assertEqual(sent, b'sV')
        row = next(json.loads(line) for line in output.splitlines() if line.startswith('{'))
        self.assertEqual(row['response_bytes'], 9)
        self.assertEqual(row['tx_queued_bytes'], 0)
        self.assertFalse(row['soft_reset'])
        self.assertIn('CYTON_SERIAL_HANDSHAKE_OK', output)

    def test_no_response_finishes_without_retrying_or_resetting(self):
        code, output, sent = self.probe(True, b'')
        self.assertEqual(code, 2)
        self.assertEqual(sent, b'sV')
        self.assertIn('CYTON_SERIAL_HANDSHAKE_NO_RESPONSE', output)

    def test_default_keeps_existing_reset_mode(self):
        code, output, sent = self.probe(False, b'OpenBCI V3$$$')
        self.assertEqual(code, 0)
        self.assertEqual(sent, b'sv')
        self.assertIn('CYTON_SERIAL_HANDSHAKE_OK', output)


if __name__ == '__main__':
    unittest.main()
