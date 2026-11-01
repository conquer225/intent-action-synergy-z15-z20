"""Small numerical checks for the offline amplitude audit, not model accuracy."""
import unittest

import numpy as np

from mi_live_scale_diagnostic import PACKETS, energy_summary, quantiles, source_groups


class ScaleDiagnosticTests(unittest.TestCase):
    def test_centering_energy_and_stable_ties(self):
        waves = np.zeros((100, 8, 500))
        waves[4] = 10
        waves[7] = 10
        energy, order, fraction = energy_summary(waves, np.zeros(8))
        self.assertEqual(order[:2].tolist(), [4, 7])
        self.assertEqual(energy[4], 400000)
        self.assertEqual(fraction, .5)

    def test_energy_invariant_to_common_origin(self):
        rng = np.random.default_rng(42)
        waves = rng.normal(size=(100, 8, 500))
        first = energy_summary(waves, np.zeros(8))
        second = energy_summary(waves + 7, np.full(8, 7))
        np.testing.assert_allclose(first[0], second[0], rtol=1e-14)
        np.testing.assert_array_equal(first[1], second[1])

    def test_quantiles_axis_and_units(self):
        values = np.array([[1, 10], [3, 30], [5, 50]])
        self.assertEqual(quantiles(values)['median'], [3, 30])

    def test_amplitude_bins_do_not_select_labels(self):
        waveform = np.tile(np.array([-1., 1.]), 250)
        waves = np.arange(1, 9)[:, None, None] * np.tile(waveform, (1, 8, 1))
        subjects = np.repeat([2, 3], 4)
        labels = np.tile([0, 1], 4)
        logits = np.tile([.2, -.2], (8, 1))
        summary = source_groups(waves, subjects, labels, logits, np.zeros(8), np.ones(8))
        self.assertEqual([row['count'] for row in summary['amplitude_quartile_responses']], [2] * 4)
        self.assertTrue(all(row['left_prediction_fraction'] == 1 for row in summary['amplitude_quartile_responses']))
        self.assertTrue(all(row['true_left_fraction'] == .5 for row in summary['amplitude_quartile_responses']))

    def test_binary_capture_layout(self):
        self.assertEqual(PACKETS.itemsize, 53)
        self.assertEqual(PACKETS.fields['adc'][1], 21)


if __name__ == '__main__':
    unittest.main()
