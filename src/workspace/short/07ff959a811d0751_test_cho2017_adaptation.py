import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

from cho2017_adaptation import METHODS, alignment_reference, align_covariances, log_power_ratio, fit, predict
from cho2017_features import trial_covariances, trial_statistics
from cho2017_training_diagnostic import validate_protocol, read_training_person, paired_comparison, passes_gate

HERE = Path(__file__).resolve().parent


class ChoAdaptationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = json.loads((HERE / 'cho2017_protocol.json').read_text())
        cls.diagnostic = json.loads((HERE / 'cho2017_training_diagnostic_protocol.json').read_text())
        snapshot = HERE / 'output/cho2017_fixed8_dev_20261001/code_snapshot/cho2017_features.py'
        spec = importlib.util.spec_from_file_location('cho_features_before_refactor', snapshot)
        cls.old_features = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.old_features)

    def setUp(self):
        self.rng = np.random.default_rng(20261001)
        self.samples = self.rng.normal(size=(3584, 8)) * 20
        data = self.rng.normal(size=(100, 30, 8))
        data -= data.mean(axis=2, keepdims=True)
        self.covariance = data.transpose(0, 2, 1) @ data
        self.covariance /= np.trace(self.covariance, axis1=1, axis2=2)[:, None, None]
        self.order = np.arange(len(data))

    def test_old_default_covariance_is_byte_identical(self):
        expected = self.old_features.trial_covariances(self.samples, 1023, self.original)
        actual = trial_covariances(self.samples, 1023, self.original)
        np.testing.assert_array_equal(actual, expected)
        np.testing.assert_array_equal(trial_statistics(self.samples, 1023, self.original)[0], expected)

    def test_task_and_baseline_features_are_causal(self):
        expected = trial_statistics(self.samples, 1023, self.original)
        changed = self.samples.copy()
        changed[2308:] = self.rng.normal(size=changed[2308:].shape) * 1e6
        for first, second in zip(expected, trial_statistics(changed, 1023, self.original)):
            np.testing.assert_array_equal(first, second)

    def test_postcue_samples_cannot_change_precue_baseline(self):
        expected = trial_statistics(self.samples, 1023, self.original)
        changed = self.samples.copy()
        changed[1023:] *= 100
        actual = trial_statistics(changed, 1023, self.original)
        np.testing.assert_array_equal(expected[1], actual[1])
        self.assertFalse(np.allclose(expected[2], actual[2]))

    def test_new_statistics_do_not_share_epoch_state(self):
        expected = trial_statistics(self.samples, 1023, self.original)
        trial_statistics(self.samples * 100, 1023, self.original)
        for first, second in zip(expected, trial_statistics(self.samples, 1023, self.original)):
            np.testing.assert_array_equal(first, second)

    def test_unnormalized_variances_preserve_relative_power(self):
        baseline = np.ones((2, 7, 8)) * 3
        task = baseline * 4
        np.testing.assert_allclose(log_power_ratio(baseline, task), np.log(4))
        np.testing.assert_array_equal(log_power_ratio(baseline * 10, task * 10), log_power_ratio(baseline, task))
        self.assertEqual(log_power_ratio(baseline, task).shape, (2, 16))

    def test_ratio_numerical_floor_and_invalid_values(self):
        zeros = np.zeros((1, 7, 8))
        np.testing.assert_array_equal(log_power_ratio(zeros, zeros), np.zeros((1, 16)))
        for bad in (np.full_like(zeros, np.nan), zeros - 1):
            with self.assertRaises(ValueError):
                log_power_ratio(bad, zeros)
        with self.assertRaises(ValueError):
            trial_statistics(np.zeros((3584, 8)), 1023, self.original)

    def test_alignment_is_prefix_only_even_when_later_data_is_invalid(self):
        expected = alignment_reference(self.covariance, self.order)
        changed = self.covariance.copy()
        changed[60:] = np.nan
        for first, second in zip(expected, alignment_reference(changed, self.order)):
            np.testing.assert_array_equal(first, second)

    def test_reference_uses_original_order_not_storage_order(self):
        expected = alignment_reference(self.covariance, self.order)
        permutation = self.rng.permutation(len(self.order))
        for first, second in zip(expected, alignment_reference(self.covariance[permutation], self.order[permutation])):
            np.testing.assert_array_equal(first, second)
        with self.assertRaises(ValueError):
            alignment_reference(self.covariance[1:], self.order[1:])

    def test_whitening_regularization_and_positive_semidefinite_trace(self):
        reference, whitening = alignment_reference(self.covariance, self.order)
        np.testing.assert_allclose(whitening @ reference @ whitening.T, np.eye(8), atol=1e-12)
        aligned = align_covariances(self.covariance, whitening)
        np.testing.assert_allclose(np.trace(aligned, axis1=1, axis2=2), 1, atol=1e-12)
        self.assertGreaterEqual(np.linalg.eigvalsh(aligned).min(), -1e-12)
        self.assertGreater(np.linalg.eigvalsh(reference).min(), 0)

    def test_alignment_rejects_invalid_calibration_or_zero_energy(self):
        for bad in (np.zeros_like(self.covariance), self.covariance * -1, np.full_like(self.covariance, np.nan)):
            with self.assertRaises((ValueError, AssertionError)):
                alignment_reference(bad, self.order)
        with self.assertRaises(ValueError):
            align_covariances(np.zeros_like(self.covariance), np.eye(8))

    def test_four_models_portable_scoring_and_feature_dimensions(self):
        covs = np.repeat(self.covariance[:, None], 7, axis=1)
        ratios = self.rng.normal(size=(100, 16))
        labels = np.tile([0, 1], 50)
        for method, dimensions in zip(METHODS, (4, 16, 4, 20)):
            fitted = fit(covs[:80], ratios[:80], labels[:80], method)
            predicted, scores, error = predict(covs[80:], ratios[80:], fitted)
            self.assertEqual(len(fitted.scaler.mean_), dimensions)
            self.assertEqual(predicted.shape, (20,))
            self.assertTrue(np.isfinite(scores).all())
            self.assertLess(error, 1e-10)
        with self.assertRaises(ValueError):
            fit(covs, ratios, labels, 'unlocked_method')

    def test_training_only_protocol_and_file_read_guard(self):
        allowed = validate_protocol(self.original, self.diagnostic)
        self.assertEqual(len(allowed), 30)
        changed = dict(self.diagnostic, participants=allowed + [6])
        with self.assertRaises(ValueError):
            validate_protocol(self.original, changed)
        with patch('cho2017_training_diagnostic.load_subject') as loader:
            for forbidden in self.diagnostic['forbidden_eeg_participants']:
                with self.assertRaises(ValueError):
                    read_training_person(forbidden, Path('unused'), allowed)
            loader.assert_not_called()

    def test_paired_gate_requires_all_locked_conditions(self):
        baseline = [dict(subject=i, balanced_accuracy=.58) for i in range(30)]
        candidate = [dict(subject=i, balanced_accuracy=.62) for i in range(30)]
        comparison = paired_comparison(candidate, baseline, 20261001)
        gate = self.diagnostic['continuation_gate']
        self.assertTrue(passes_gate({'mean_subject_balanced_accuracy': .62}, comparison, gate))
        self.assertFalse(passes_gate({'mean_subject_balanced_accuracy': .59}, comparison, gate))
        self.assertFalse(passes_gate({'mean_subject_balanced_accuracy': .62}, dict(comparison, mean_ba_gain=.02), gate))
        self.assertFalse(passes_gate({'mean_subject_balanced_accuracy': .62},
                                    dict(comparison, three_comparison_adjusted_98_3333_ci=[0, .1]), gate))


if __name__ == '__main__':
    unittest.main()
