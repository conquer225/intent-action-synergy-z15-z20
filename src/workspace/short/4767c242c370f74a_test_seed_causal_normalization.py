import unittest

import numpy as np

from .seed_causal_normalization import past_center


class CausalNormalizationTest(unittest.TestCase):
    def test_past_only(self):
        x = np.random.default_rng(1).normal(size=(30, 180))
        for mode in ("expanding", "ema", "fixed"):
            np.testing.assert_array_equal(past_center(x, mode)[:15], past_center(x[:15], mode))
        result = past_center(x, "expanding")
        for i in range(5, len(x)):
            np.testing.assert_allclose(result[i], x[i] - x[:i].mean(axis=0), atol=1e-14)

    def test_no_mutation(self):
        x = np.random.default_rng(2).normal(size=(10, 180))
        expected = x.copy()
        past_center(x, "ema")
        np.testing.assert_array_equal(x, expected)


if __name__ == "__main__":
    unittest.main()
