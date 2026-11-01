import unittest

import numpy as np

from .deap_normalization_ablation import baseline_statistics, baseline_whiten, relative_power


class NormalizationTests(unittest.TestCase):
    def test_no_future_samples_enter_calibration(self):
        rng = np.random.default_rng(2)
        trial = rng.normal(size=(8, 8064))
        before = baseline_statistics(trial)
        trial[:, 384:] *= 1000
        after = baseline_statistics(trial)
        for a, b in zip(before, after):
            np.testing.assert_array_equal(a, b)

    def test_relative_power_removes_channel_scale(self):
        x = np.random.default_rng(2).normal(size=(5, 4, 8))
        offset = np.arange(8)[None, None, :]
        np.testing.assert_allclose(relative_power(x.reshape(5, 32)),
                                   relative_power((x + offset).reshape(5, 32)), atol=1e-12)

    def test_whitening_baseline_gives_identity(self):
        x = np.random.default_rng(2).normal(size=(5, 4, 8, 8))
        covariance = x @ x.swapaxes(-1, -2) + np.eye(8)
        whitened = baseline_whiten(covariance, covariance)
        np.testing.assert_allclose(whitened, np.broadcast_to(np.eye(8), whitened.shape), atol=1e-12)


if __name__ == "__main__":
    unittest.main()
