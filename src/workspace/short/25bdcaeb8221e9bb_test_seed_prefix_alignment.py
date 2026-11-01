import unittest

import numpy as np

from .fixed8_deap_experiment import matrix_log_vectors
from .seed_prefix_alignment import align_session, covariance_from_logs


class PrefixAlignmentTest(unittest.TestCase):
    def setUp(self):
        a = np.random.default_rng(4).normal(size=(12, 5, 8, 8))
        self.cov = a @ a.swapaxes(-1, -2) + np.eye(8)
        self.x = matrix_log_vectors(self.cov)

    def test_roundtrip(self):
        np.testing.assert_allclose(covariance_from_logs(self.x), self.cov, atol=1e-11)

    def test_prefix_only(self):
        for mode in ("prefix_center", "prefix_ea"):
            np.testing.assert_allclose(align_session(self.x, mode)[:8],
                                       align_session(self.x[:8], mode), atol=1e-12)

    def test_reference_identity(self):
        aligned = covariance_from_logs(align_session(self.x, "prefix_ea"))
        np.testing.assert_allclose(aligned[:5].mean(axis=0), np.broadcast_to(np.eye(8), (5, 8, 8)), atol=1e-12)


if __name__ == "__main__":
    unittest.main()
