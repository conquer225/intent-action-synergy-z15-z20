"""Exact parity with the former deque-stack path, including transport edge cases."""
from collections import deque
import unittest
from unittest.mock import patch

import numpy as np

from cyton_sqi import primary_windows, segmented_sqi, channel_sqi, CytonSQIMonitor


def reference(raw_rows, filtered_rows, multiplier):
    counts = np.stack(raw_rows).astype(np.float64)
    raw_uv = (counts - counts.mean(axis=0)) * multiplier
    filtered = np.stack(filtered_rows)
    return counts, raw_uv, filtered - filtered.mean(axis=0)


class PrimaryWindowTests(unittest.TestCase):
    def compare(self, raw, filtered):
        rows, bands = deque(maxlen=2000), deque(maxlen=2000)
        for row, output in zip(raw, filtered):
            rows.append(row.copy())
            bands.append(output.copy())
        expected = reference(rows, bands, .022351744455)
        actual = primary_windows(rows, bands, .022351744455)
        for before, after in zip(expected, actual):
            np.testing.assert_array_equal(after, before)
            self.assertEqual(after.dtype, np.float64)
        # Snapshots may be passed to consumers after the ring advances.
        rows[-1][:] = 0
        bands[-1][:] = 0
        for before, after in zip(expected, actual):
            np.testing.assert_array_equal(after, before)

    def test_random_and_ring_wrap(self):
        rng = np.random.default_rng(49)
        for count in (2000, 2501, 7000):
            with self.subTest(count=count):
                self.compare(rng.integers(-2**23, 2**23, size=(count, 8)),
                             rng.normal(0, 50, (count, 8)))

    def test_dc_flat_rail_and_transport_nonfinite_values(self):
        counts = np.full((2000, 8), 2**23 - 1)
        counts[::2, 4] = -2**23
        filtered = counts.astype(float) * .001
        filtered[:3, 5] = np.nan
        with np.errstate(invalid='ignore'):
            self.compare(counts, filtered)


def sequential_sqi(values, segment_samples, sample_rate_hz=250):
    count = len(values) // segment_samples
    return np.stack([channel_sqi(section, sample_rate_hz) for section in
        values[:count * segment_samples].reshape(count, segment_samples, 8)])


class SegmentedSQITests(unittest.TestCase):
    def test_descriptors_match_independent_segments(self):
        rng = np.random.default_rng(50)
        for count in (500, 2000, 2073):
            values = rng.normal(0, 30, (count, 8))
            values[:, 0] = 0
            values[::2, 1] = 900
            values[:, 2] += np.sin(np.arange(count) * 2*np.pi*50/250) * 300
            np.testing.assert_allclose(segmented_sqi(values, 500),
                sequential_sqi(values, 500), rtol=0, atol=1e-12)

    def test_monitor_outputs_and_calibration_gates_match(self):
        rng = np.random.default_rng(51)
        monitors = [CytonSQIMonitor(calibration_windows=2) for _ in range(2)]
        t = np.arange(2000) / 250
        clean = np.stack([20*np.sin(2*np.pi*(8+i)*t) for i in range(8)], axis=1)
        for index in range(8):
            values = clean + rng.normal(0, 1, clean.shape)
            if index == 3:
                values[:, 6] = 0
            if index == 4:
                values[::2, 4] = 800
            transport = [True] * 7 + [index != 5]
            with patch('cyton_sqi.segmented_sqi', sequential_sqi):
                expected = monitors[0].process(values, transport)
            self.assertEqual(monitors[1].process(values, transport), expected)
        for name in ('center', 'scale', 'threshold'):
            np.testing.assert_allclose(getattr(monitors[0], name), getattr(monitors[1], name),
                rtol=0, atol=1e-12)

    def test_short_and_wrong_width_rejected(self):
        for values in (np.zeros((499, 8)), np.zeros((2000, 7))):
            with self.assertRaises(ValueError):
                segmented_sqi(values, 500)


if __name__ == '__main__':
    unittest.main()
