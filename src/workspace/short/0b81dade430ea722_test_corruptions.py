from __future__ import annotations

import unittest

import numpy as np

from corruptions import CorruptionSpec, apply_feature_corruption, sample_training_corruption


class CorruptionTests(unittest.TestCase):
    def setUp(self) -> None:
        rng = np.random.default_rng(7)
        self.features = rng.normal(size=(120, 8, 5)).astype(np.float64)

    def test_does_not_mutate_and_is_deterministic(self) -> None:
        original = self.features.copy()
        spec = CorruptionSpec("broadband_noise", 0.7, (1, 6), 10, 50)
        first = apply_feature_corruption(self.features, spec, seed=22)
        second = apply_feature_corruption(self.features, spec, seed=22)
        np.testing.assert_array_equal(self.features, original)
        np.testing.assert_array_equal(first.features, second.features)
        np.testing.assert_array_equal(first.quality, second.quality)

    def test_only_selected_channels_change(self) -> None:
        spec = CorruptionSpec("mains_noise", 0.6, (2, 5), 20, 40)
        result = apply_feature_corruption(self.features, spec, seed=1)
        untouched = [0, 1, 3, 4, 6, 7]
        np.testing.assert_array_equal(result.features[:, untouched], self.features[:, untouched])
        self.assertTrue(np.all(result.corruption_mask[20:60, (2, 5)]))
        self.assertFalse(np.any(result.corruption_mask[:20]))
        self.assertFalse(np.any(result.corruption_mask[60:]))

    def test_flatline_removes_temporal_variation(self) -> None:
        result = apply_feature_corruption(
            self.features, CorruptionSpec("flatline", 1.0, (3,), 15, 70), seed=9
        )
        self.assertTrue(np.all(np.std(result.features[15:85, 3, :], axis=0) < 1.0e-12))
        self.assertTrue(np.all(result.quality[15:85, 3] == 0.05))

    def test_burst_marks_only_burst_windows(self) -> None:
        result = apply_feature_corruption(
            self.features, CorruptionSpec("burst", 0.8, (0, 7), 5, 100), seed=4
        )
        changed = np.any(result.features != self.features, axis=2)
        np.testing.assert_array_equal(changed, result.corruption_mask)
        self.assertGreater(np.count_nonzero(changed), 0)
        self.assertLess(np.count_nonzero(changed), 200)

    def test_channel_swap_is_exact_and_evaluation_only(self) -> None:
        result = apply_feature_corruption(
            self.features, CorruptionSpec("channel_swap", 1.0, (1, 4), 10, 20), seed=5
        )
        np.testing.assert_array_equal(result.features[10:30, 1], self.features[10:30, 4])
        np.testing.assert_array_equal(result.features[10:30, 4], self.features[10:30, 1])
        self.assertTrue(np.all(result.quality == 1.0))
        self.assertFalse(result.metadata["training_allowed"])

    def test_stronger_broadband_severity_has_larger_effect(self) -> None:
        mild = apply_feature_corruption(
            self.features, CorruptionSpec("broadband_noise", 0.2, (6,), 0, 120), seed=2
        )
        severe = apply_feature_corruption(
            self.features, CorruptionSpec("broadband_noise", 1.0, (6,), 0, 120), seed=2
        )
        mild_delta = np.mean(np.abs(mild.features - self.features))
        severe_delta = np.mean(np.abs(severe.features - self.features))
        self.assertGreater(severe_delta, mild_delta)
        self.assertLess(float(severe.quality.min()), float(mild.quality.min()))

    def test_sample_training_corruption_contract(self) -> None:
        result = sample_training_corruption(self.features, seed=123, max_channels=3)
        self.assertEqual(result.features.shape, self.features.shape)
        self.assertEqual(result.quality.shape, self.features.shape[:2])
        self.assertEqual(result.corruption_mask.shape, self.features.shape[:2])
        self.assertTrue(result.metadata["training_allowed"])
        self.assertTrue(np.all((0.0 <= result.quality) & (result.quality <= 1.0)))


if __name__ == "__main__":
    unittest.main()
