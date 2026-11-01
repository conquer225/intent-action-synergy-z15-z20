import unittest

import numpy as np

from .fixed8_deap_experiment import matrix_log_vectors
from .seed_covariance_diagnosis import remove_log_scale


class ShapeFeaturesTest(unittest.TestCase):
    def test_scale_invariance(self):
        rng = np.random.default_rng(7)
        a = rng.normal(size=(3, 5, 8, 8))
        cov = a @ a.swapaxes(-1, -2) + np.eye(8)
        scales = np.exp(rng.normal(size=(3, 5, 1, 1)))
        np.testing.assert_allclose(remove_log_scale(matrix_log_vectors(cov)),
            remove_log_scale(matrix_log_vectors(cov * scales)), atol=1e-12)

    def test_future_independence_and_no_mutation(self):
        x = np.random.default_rng(9).normal(size=(12, 180))
        original = x.copy()
        np.testing.assert_array_equal(remove_log_scale(x)[:4], remove_log_scale(x[:4]))
        np.testing.assert_array_equal(x, original)


if __name__ == "__main__":
    unittest.main()
