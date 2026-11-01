import json
import unittest

import numpy as np

from telemetry_json import WaveformJSONCache


class WaveformJSONTests(unittest.TestCase):
    def setUp(self):
        self.cache = WaveformJSONCache()
        self.values = np.random.default_rng(52).normal(0, 50, (1500, 8))
        self.raw = self.values * 1000

    def compare(self, start, size=625, index=None, samples=None, raw=None):
        samples = self.values[start:start+size].copy() if samples is None else samples
        raw = self.raw[start:start+size].copy() if raw is None else raw
        encoded = self.cache.encode(samples, raw, start+size if index is None else index)
        for text, values in zip(encoded, (samples, raw)):
            self.assertEqual(json.loads(text), np.round(values, 3).tolist())

    def test_overlap_reuse_and_skipped_publications(self):
        self.compare(0)
        self.assertEqual(self.cache.reused_rows, 0)
        for delta, start in ((63, 63), (125, 188), (0, 188), (625, 813)):
            self.compare(start)
            self.assertEqual(self.cache.reused_rows, 625-delta)

    def test_reset_and_changed_overlap_rebuild(self):
        self.compare(0)
        self.compare(0, index=0)
        self.assertEqual(self.cache.reused_rows, 0)
        for lane in ('filtered', 'raw'):
            self.compare(0)
            samples, raw = self.values[63:688].copy(), self.raw[63:688].copy()
            (samples if lane == 'filtered' else raw)[0, 0] += 1
            self.compare(63, samples=samples, raw=raw)
            self.assertEqual(self.cache.reused_rows, 0)

    def test_growing_windows_and_rounding_edges(self):
        for size in (1, 64, 125, 625):
            self.compare(0, size)
        values = np.array([-0., .0005, .0015, -.0025, 1e12, -1e12, 3.14159, -2.71828])[None, :]
        self.compare(0, 1, samples=values, raw=-values)

    def test_snapshot_is_owned(self):
        values, raw = self.values[:625].copy(), self.raw[:625].copy()
        self.compare(0, samples=values, raw=raw)
        values[:] = raw[:] = 0
        self.compare(63)
        self.assertEqual(self.cache.reused_rows, 562)

    def test_invalid_input_does_not_change_last_success(self):
        self.compare(0)
        for bad in (np.nan, np.inf, -np.inf):
            values = self.values[63:688].copy()
            values[-1, 0] = bad
            with self.assertRaises(ValueError):
                self.cache.encode(values, self.raw[63:688], 688)
        for values, raw in ((np.zeros((10, 7)), np.zeros((10, 7))),
                            (np.zeros((10, 8)), np.zeros((11, 8)))):
            with self.assertRaises(ValueError):
                self.cache.encode(values, raw, 688)
        self.compare(63)
        self.assertEqual(self.cache.reused_rows, 562)


if __name__ == '__main__':
    unittest.main()
