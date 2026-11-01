"""Framing diagnostics must preserve counters even when input goes silent."""
from contextlib import ExitStack, redirect_stdout
import io
import json
import os
import unittest
from unittest.mock import patch

if os.name == 'posix':
    import diagnose_stream_transport as diagnostic


@unittest.skipUnless(os.name == 'posix', 'Linux serial diagnostic')
class TransportDiagnosticTests(unittest.TestCase):
    def run_probe(self, reader, clocks):
        output = io.StringIO()
        with ExitStack() as stack:
            stack.enter_context(patch.object(diagnostic.sys, 'argv',
                ['diagnose', '--port', '/dev/test-cyton', '--seconds', '1']))
            stack.enter_context(patch.object(diagnostic.os, 'open', return_value=17))
            close = stack.enter_context(patch.object(diagnostic.os, 'close'))
            stack.enter_context(patch.object(diagnostic, 'configure_serial'))
            stack.enter_context(patch.object(diagnostic.termios, 'tcflush'))
            commands = stack.enter_context(patch.object(diagnostic, 'write_command'))
            packets = stack.enter_context(patch.object(diagnostic, 'packets', return_value=reader))
            stack.enter_context(patch.object(diagnostic.time, 'sleep'))
            stack.enter_context(patch.object(diagnostic.time, 'monotonic', side_effect=clocks))
            stack.enter_context(redirect_stdout(output))
            error = None
            try:
                diagnostic.main()
            except TimeoutError as exc:
                error = exc
        close.assert_called_once_with(17)
        self.assertEqual([call.args[1] for call in commands.call_args_list], [b's', b'b', b's'])
        self.assertEqual(packets.call_args.kwargs['reader_batch_samples'], 10)
        return json.loads(output.getvalue()), error

    def test_complete_run_reports_framing_and_delivery_separately(self):
        reader = (row for row in [(bytes([0xA0, 255]), 0, 10.0),
                                 (bytes([0xA0, 0]), 3, 10.4)])
        result, error = self.run_probe(reader, [10., 10.05, 11.05])
        self.assertIsNone(error)
        self.assertTrue(result['completed'])
        self.assertEqual(result['frames'], 2)
        self.assertEqual(result['sequence_gaps'], 0)
        self.assertEqual(result['malformed_bytes'], 3)
        self.assertEqual(result['receive_gaps_over_250ms'], 1)
        self.assertAlmostEqual(result['max_delivery_age_ms'], 650.)
        self.assertNotIn('samples', result)

    def test_silence_keeps_partial_counters_and_propagates_failure(self):
        def silence():
            yield bytes([0xA0, 1]), 7, 10.
            raise TimeoutError('No complete Cyton packet')

        result, error = self.run_probe(silence(), [10., 10.01, 13.01])
        self.assertIsInstance(error, TimeoutError)
        self.assertFalse(result['completed'])
        self.assertEqual(result['error_type'], 'TimeoutError')
        self.assertEqual(result['frames'], 1)
        self.assertEqual(result['malformed_bytes'], 7)
        self.assertAlmostEqual(result['duration_s'], 3.01)


if __name__ == '__main__':
    unittest.main()
