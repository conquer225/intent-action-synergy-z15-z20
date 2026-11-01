import unittest

import numpy as np

from .seed_matched_preprocessing import matched_features, to_simulated_250
from seed_replay_check import replay


class MatchedPipelineTest(unittest.TestCase):
    def test_no_future_input(self):
        x = np.random.default_rng(4).normal(size=(5500, 8))
        prefix = to_simulated_250(x[:1000])
        np.testing.assert_allclose(prefix, to_simulated_250(x)[:len(prefix)], atol=1e-12)
        full = matched_features(x)
        early = matched_features(x[:2800])
        for a, b in zip(full, early):
            np.testing.assert_allclose(a[:1], b, atol=1e-10)

    def test_same_as_board_replay(self):
        x = np.random.default_rng(5).normal(size=(5400, 8))
        control, matched = matched_features(x)
        weights = {"weight": np.zeros((3, 180)), "bias": np.zeros(3)}
        control_stream, _, _ = replay(to_simulated_250(x), weights, 250, False, chunks=137)
        matched_stream, _, _ = replay(to_simulated_250(x), weights, 250, True, chunks=137)
        np.testing.assert_allclose(control, control_stream, atol=1e-10)
        np.testing.assert_allclose(matched, matched_stream, atol=1e-10)


if __name__ == "__main__":
    unittest.main()
