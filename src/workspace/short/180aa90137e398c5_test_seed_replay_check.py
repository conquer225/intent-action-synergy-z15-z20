import unittest

import numpy as np
from seed_replay_check import CausalResampler, FeatureStream


class ReplayTests(unittest.TestCase):
    def test_resampling_chunk_phase_and_future(self):
        x = np.random.default_rng(11).normal(size=(4000, 8))
        batch = CausalResampler().process(x)
        stream = CausalResampler()
        chunked = np.concatenate([stream.process(x[i:i+37]) for i in range(0, len(x), 37)])
        np.testing.assert_allclose(batch, chunked, atol=1e-12)
        prefix = CausalResampler().process(x[:991])
        np.testing.assert_allclose(prefix, batch[:len(prefix)], atol=1e-12)
        self.assertEqual(len(batch), 3200)

    def test_band_state_survives_chunks(self):
        x = np.random.default_rng(12).normal(size=(5400, 8))
        expected = FeatureStream().process(x)
        stream = FeatureStream()
        actual = []
        for i in range(0, len(x), 137):
            actual.extend(stream.process(x[i:i+137]))
        self.assertEqual(len(actual), 2)
        np.testing.assert_allclose(actual, expected, atol=1e-12)


if __name__ == "__main__":
    unittest.main()
