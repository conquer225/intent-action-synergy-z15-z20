"""Numerical and source-layout checks for the offline wearable-SSVEP pilot."""

import unittest

import numpy as np

from ssvep_core import canonical_correlation, reference_bank
from ssvep_wearable_baseline import _format_trials, _reference_q, cca_scores


class WearableBaselineTests(unittest.TestCase):
    def test_batched_cca_matches_portable_core(self) -> None:
        fs, n = 250, 500
        frequencies = [9.25, 11.25, 13.25]
        t = np.arange(n) / fs
        eeg = np.stack([np.sin(2 * np.pi * 11.25 * t), np.cos(2 * np.pi * 11.25 * t)])
        q = _reference_q(frequencies, n, fs, 5)
        actual, valid = cca_scores(eeg[None], q)
        references = reference_bank(frequencies, sample_rate_hz=fs, samples=n, harmonics=5)
        expected = [canonical_correlation(eeg, ref) for ref in references]
        self.assertTrue(valid[0])
        np.testing.assert_allclose(actual[0], expected, atol=1e-5)
        self.assertEqual(int(actual.argmax(axis=1)[0]), 1)

    def test_invalid_trial_is_rejected(self) -> None:
        q = _reference_q([9.25, 11.25], 250, 250, 3)
        flat = np.zeros((1, 2, 250))
        scores, valid = cca_scores(flat, q)
        self.assertFalse(valid[0])
        self.assertTrue(np.isnan(scores).all())

    def test_block_target_axis_order(self) -> None:
        data = np.zeros((2, 710, 2, 10, 12))
        for block in range(10):
            for target in range(12):
                data[:, :, 0, block, target] = block * 12 + target
        trials = _format_trials(data, 160, 250, 0)
        self.assertEqual(trials.shape, (120, 2, 250))
        self.assertEqual(float(trials[0, 0, 0]), 0.0)
        self.assertEqual(float(trials[13, 1, 0]), 13.0)
        self.assertEqual(float(trials[-1, 0, 0]), 119.0)


if __name__ == "__main__":
    unittest.main()
