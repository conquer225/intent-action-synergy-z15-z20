"""Synthetic numerical/structure tests, never reported as emotion accuracy."""

import unittest

import numpy as np

from eeg_apps_z15.fixed8_deap_experiment import (
    BANDS_HZ, evaluate_development, fold_features, matrix_log_vectors, tangent_vectors,
    trial_features,
)


class Fixed8DeapExperimentTests(unittest.TestCase):
    def test_trial_feature_dimensions(self):
        rng = np.random.default_rng(17)
        trial = rng.normal(size=(8, 63 * 128))
        power, covariance = trial_features(trial)
        self.assertEqual(power.shape, (5, len(BANDS_HZ) * 8))
        self.assertEqual(covariance.shape, (5, len(BANDS_HZ), 8, 8))
        self.assertTrue(np.isfinite(power).all())
        self.assertTrue((np.linalg.eigvalsh(covariance) > 0).all())

    def test_log_vectors_preserve_channel_relationships(self):
        cov = np.broadcast_to(np.eye(8), (2, 4, 8, 8)).copy()
        cov[1, :, 0, 1] = cov[1, :, 1, 0] = 0.25
        features = matrix_log_vectors(cov)
        self.assertEqual(features.shape, (2, 4 * 36))
        self.assertFalse(np.allclose(features[0], features[1]))

    def test_tangent_reference_is_training_only(self):
        cov = np.broadcast_to(np.eye(8), (4, 4, 8, 8)).copy()
        cov[0] *= 2
        cov[1] *= 3
        data = {"covariances": cov}
        train = np.array([True, True, False, False])
        test = ~train
        before, _ = fold_features("tangent_linear", data, train, test)
        data["covariances"][test] *= 100
        after, _ = fold_features("tangent_linear", data, train, test)
        np.testing.assert_allclose(before, after, atol=1e-12)
        self.assertEqual(tangent_vectors(cov, cov[:2]).shape, (4, 4 * 36))

    def test_participant_disjoint_development_run(self):
        groups = np.repeat(np.arange(1, 25), 4)
        classes = np.tile((0, 1, 0, 1), 24)
        keys = np.column_stack((groups, np.tile((0, 0, 1, 1), 24),
                                np.tile((0, 1, 0, 1), 24)))
        rng = np.random.default_rng(41)
        power = rng.normal(size=(len(groups), len(BANDS_HZ) * 8))
        power[:, 0] += classes
        covariance = np.broadcast_to(np.eye(8), (len(groups), len(BANDS_HZ), 8, 8)).copy()
        covariance[:, :, 0, 0] += classes[:, None] * 0.2
        ratings = np.column_stack((np.where(classes, 8, 2), np.where(classes, 7, 3)))
        report, predictions = evaluate_development(
            {"power": power, "covariances": covariance,
             "ratings": ratings, "keys": keys})
        self.assertEqual(len(predictions), 2 * 3 * len(groups))
        self.assertEqual(len(report["valence"]["tangent_linear"]["participants"]), 24)


if __name__ == "__main__":
    unittest.main()
