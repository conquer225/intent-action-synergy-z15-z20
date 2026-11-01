"""Read-only observer parsing checks; no board connection."""
from pathlib import Path
import unittest
from unittest.mock import patch

from prewear_observe import process_progress


class ProcessProgressTests(unittest.TestCase):
    def test_main_thread_ticks_and_context_switches(self):
        fields = ['0'] * 20
        fields[11], fields[12] = '123', '7'
        payloads = dict(stat='900 (python worker) ' + ' '.join(fields),
            status='Name:\tpython3\nvoluntary_ctxt_switches:\t10\nnonvoluntary_ctxt_switches:\t3\n')
        with patch.object(Path, 'read_text', lambda path: payloads[path.name]), \
                patch('prewear_observe.os.sysconf', return_value=100, create=True):
            value = process_progress(900)
        self.assertEqual(value, dict(pid=900, main_thread_cpu_ticks=130,
            clock_ticks_per_second=100, voluntary_ctxt_switches=10,
            nonvoluntary_ctxt_switches=3))

    def test_missing_process_is_not_reported_as_zero_cpu(self):
        with patch.object(Path, 'read_text', side_effect=FileNotFoundError):
            with self.assertRaises(FileNotFoundError):
                process_progress(900)


if __name__ == '__main__':
    unittest.main()
