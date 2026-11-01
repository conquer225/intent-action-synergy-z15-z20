import unittest

from mi_comparison_models import normalized_tensor
import numpy as np
from mi_window_rms import shared_window_rms


class WindowRMSTests(unittest.TestCase):
    def setUp(self):
        self.waves = np.random.default_rng(42).normal(size=(4, 8, 500))

    def test_one_unit_rms_per_window(self):
        result = shared_window_rms(self.waves)
        np.testing.assert_allclose(np.mean(result**2, axis=(1,2)), 1, atol=1e-14)

    def test_positive_gain_invariance(self):
        expected = shared_window_rms(self.waves)
        for gain in (.03125,.125,.5,2,32):
            np.testing.assert_array_equal(shared_window_rms(self.waves*gain), expected)

    def test_relative_channel_power_preserved(self):
        before = np.mean(self.waves**2, axis=2)
        after = np.mean(shared_window_rms(self.waves)**2, axis=2)
        np.testing.assert_allclose(before/before.sum(axis=1,keepdims=True),
                                   after/after.sum(axis=1,keepdims=True), atol=1e-14)

    def test_not_independent_channel_standardization(self):
        waves = self.waves.copy()
        waves[:,2]*=2
        waves[:,3]*=7
        normalized = shared_window_rms(waves)
        ratio = np.mean(waves[:,2]**2,axis=1)/np.mean(waves[:,3]**2,axis=1)
        actual = np.mean(normalized[:,2]**2,axis=1)/np.mean(normalized[:,3]**2,axis=1)
        np.testing.assert_allclose(actual,ratio,atol=1e-14)

    def test_preserves_sign_and_input(self):
        original=self.waves.copy()
        np.testing.assert_array_equal(np.sign(shared_window_rms(self.waves)),np.sign(self.waves))
        np.testing.assert_array_equal(self.waves,original)

    def test_degenerate_and_invalid_refused(self):
        for value in (np.zeros((1,8,500)),np.full((1,8,500),1e-14),
                      np.full((1,8,500),np.nan),np.ones((8,500)),np.empty((0,8,500))):
            with self.assertRaises(ValueError): shared_window_rms(value)

    def test_same_fp32_boundary_after_scaling(self):
        waves=self.waves.astype(np.float32)
        mean=np.arange(8)*.1
        scale=np.arange(1,9)
        expected=normalized_tensor(shared_window_rms(waves),mean,scale,'cpu').numpy()
        actual=normalized_tensor(shared_window_rms(waves*.03125),mean,scale,'cpu').numpy()
        np.testing.assert_array_equal(actual,expected)


if __name__=='__main__': unittest.main()
