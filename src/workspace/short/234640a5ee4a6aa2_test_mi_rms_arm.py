"""Pure NumPy transform checks for the actual ARM dependency versions."""
import unittest
import numpy as np
from mi_window_rms import shared_window_rms


class ARMSharedRMSTests(unittest.TestCase):
    def setUp(self):
        self.waves = np.random.default_rng(42).normal(size=(4,8,500))

    def test_unit_shared_rms(self):
        np.testing.assert_allclose(np.mean(shared_window_rms(self.waves)**2,axis=(1,2)),1,atol=1e-14)

    def test_positive_gain_invariance(self):
        for gain in (.03125,.125,.5,2,32):
            np.testing.assert_array_equal(shared_window_rms(self.waves*gain), shared_window_rms(self.waves))

    def test_relative_channel_energy(self):
        before = np.mean(self.waves**2,axis=2)
        after = np.mean(shared_window_rms(self.waves)**2,axis=2)
        np.testing.assert_allclose(before/before.sum(1,keepdims=True),after/after.sum(1,keepdims=True),atol=1e-14)

    def test_c3_c4_not_individually_equalized(self):
        waves = self.waves.copy()
        waves[:,2] *= 2
        waves[:,3] *= 7
        normalized = shared_window_rms(waves)
        np.testing.assert_allclose(np.mean(waves[:,2]**2,axis=1)/np.mean(waves[:,3]**2,axis=1),
                                   np.mean(normalized[:,2]**2,axis=1)/np.mean(normalized[:,3]**2,axis=1),atol=1e-14)

    def test_sign_and_input_unchanged(self):
        original = self.waves.copy()
        np.testing.assert_array_equal(np.sign(shared_window_rms(self.waves)),np.sign(original))
        np.testing.assert_array_equal(self.waves,original)

    def test_invalid_refused(self):
        for waves in (np.zeros((1,8,500)),np.full((1,8,500),np.nan),
                      np.full((1,8,500),1e-14),np.ones((8,500)),np.empty((0,8,500))):
            with self.assertRaises(ValueError): shared_window_rms(waves)

    def test_frozen_fp32_boundary(self):
        waves = self.waves.astype(np.float32)
        mean, scale = np.arange(8)[None,:,None]*.1,np.arange(1,9)[None,:,None]
        a = ((shared_window_rms(waves)-mean)/scale).astype(np.float32)
        b = ((shared_window_rms(waves*.03125)-mean)/scale).astype(np.float32)
        np.testing.assert_array_equal(a,b)


if __name__=='__main__': unittest.main()
