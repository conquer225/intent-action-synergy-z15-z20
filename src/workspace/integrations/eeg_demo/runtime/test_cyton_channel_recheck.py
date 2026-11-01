"""Run the one-shot initializer against a pseudo-terminal; no physical devices."""
import contextlib
import errno
import importlib.util
import io
import json
import os
from pathlib import Path
import pty
import select
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch


class ChannelRecheckTests(unittest.TestCase):
    def check(self, soft_initialize, defaults_ok=True):
        master, slave = pty.openpty()
        stop = threading.Event()
        commands = []

        def device():
            pending = bytearray()
            while not stop.is_set():
                if not select.select([master], [], [], .05)[0]:
                    continue
                try:
                    pending.extend(os.read(master, 4096))
                except OSError as error:
                    if error.errno == errno.EIO:
                        return
                    raise
                while pending:
                    size = 9 if pending[0] == ord('x') else 1
                    if len(pending) < size:
                        break
                    command = bytes(pending[:size])
                    del pending[:size]
                    commands.append(command.decode('ascii'))
                    response = None
                    if command == b'v':
                        response = b'OpenBCI V3\nADS1299 Device ID: 0x3E\nFirmware: v3.1.1$$$'
                    elif command == b'd':
                        response = (b'updating channel settings to default$$$' if defaults_ok
                                    else b'Failure: default configuration$$$')
                    elif command == b'?':
                        response = b'CH1SET, 0x05, 0x68\nBIAS_SENSP, 0x0D, 0xFF\n$$$'
                    elif command.startswith(b'x'):
                        response = b'Success: Channel set for ' + command[1:2] + b'$$$'
                    if response is not None:
                        os.write(master, response)

        thread = threading.Thread(target=device)
        try:
            with tempfile.TemporaryDirectory(prefix='gl-cyton-channels-20261011-') as folder:
                source = Path(folder) / 'cyton_channel_recheck.py'
                shutil.copyfile(Path(__file__).with_name(source.name), source)
                spec = importlib.util.spec_from_file_location('private_channel_recheck', source)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                module.PORT = os.ttyname(slave)
                sys.path.insert(0, str(module.FORMAL))
                import cyton_guardianloop  # Load the real serial helpers before mocking systemctl.
                thread.start()
                argv = [str(source)] + (['--soft-initialize'] if soft_initialize else [])

                def service_state(args, **_):
                    return '0\n' if args[1] == 'show' else 'active\n'

                with patch.object(sys, 'argv', argv), \
                     patch.object(subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)), \
                     patch.object(subprocess, 'check_output', side_effect=service_state), \
                     contextlib.redirect_stdout(io.StringIO()):
                    try:
                        module.main()
                        code = 0
                    except SystemExit as error:
                        code = error.code
                report = json.loads((Path(folder) / 'report.json').read_text())
                return code, report, commands
        finally:
            stop.set()
            if thread.is_alive():
                thread.join(timeout=1)
            os.close(master)
            os.close(slave)

    def test_default_does_not_add_a_soft_reset(self):
        code, report, sent = self.check(False)
        self.assertEqual(code, 0)
        self.assertNotIn('v', sent)
        self.assertNotIn('d', sent)
        self.assertTrue(report['all_acknowledged'])
        self.assertTrue(report['restored'])

    def test_soft_initialize_once_then_restores_fixed_eight(self):
        code, report, sent = self.check(True)
        self.assertEqual(code, 0)
        self.assertEqual(sent[:4], ['s', 'v', 'd', '?'])
        self.assertEqual(sent.count('v'), 1)
        self.assertEqual([x for x in sent if x.startswith('x')],
                         [f'x{channel}060110X' for channel in range(1, 9)])
        self.assertTrue(report['after']['complete'])
        self.assertTrue(report['all_acknowledged'])
        self.assertTrue(report['restored'])
        self.assertFalse(report['raw_eeg_saved'])

    def test_failed_defaults_stop_configuration_and_restore_service(self):
        code, report, sent = self.check(True, defaults_ok=False)
        self.assertEqual(code, 1)
        self.assertEqual(sent, ['s', 'v', 'd'])
        self.assertIn('did not confirm default', report['error'])
        self.assertTrue(report['restored'])


if __name__ == '__main__':
    unittest.main()
