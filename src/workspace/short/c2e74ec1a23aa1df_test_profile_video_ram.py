import unittest
from unittest.mock import patch

import numpy as np

import profile_video_ram as p


class TimingTests(unittest.TestCase):
    def test_wall_and_thread_cpu_are_distinct_and_summarized(self):
        wall = iter((1., 1.2, 2., 2.1))
        cpu = iter((0., .01, .1, .12))
        trace = p.Timings(lambda: next(wall), lambda: next(cpu))
        for _ in range(2):
            with trace.measure('test'):
                pass
        result = trace.summary()['test']
        self.assertEqual(result['calls'], 2)
        self.assertAlmostEqual(result['wall_median_ms'], 150.)
        self.assertAlmostEqual(result['thread_cpu_total_ms'], 30.)
        self.assertAlmostEqual(result['wall_max_ms'], 200.)

    def test_nested_measurements_are_kept_not_subtracted(self):
        trace = p.Timings(wall=lambda: 0., cpu=lambda: 0.)
        with trace.measure('outer'):
            with trace.measure('inner'):
                pass
        self.assertEqual(set(trace.summary()), {'outer', 'inner'})

    def test_failed_phase_is_still_recorded_and_error_propagates(self):
        trace = p.Timings()
        with self.assertRaises(ValueError):
            with trace.measure('failure'):
                raise ValueError('test')
        self.assertEqual(trace.summary()['failure']['calls'], 1)

    def test_plain_ram_flush_is_explicitly_no_dma(self):
        buffer = np.zeros((2, 3, 3), dtype=np.uint8).view(p.RamBuffer)
        buffer[0].flush()
        self.assertFalse(hasattr(buffer, 'physical_address'))

    def test_pin_mismatch_refuses_profile(self):
        with patch.object(p.Path, 'read_bytes', return_value=b'not-the-pinned-software'):
            with self.assertRaisesRegex(ValueError, 'audited display payload'):
                p.verify_pins()


if __name__ == '__main__':
    unittest.main()
