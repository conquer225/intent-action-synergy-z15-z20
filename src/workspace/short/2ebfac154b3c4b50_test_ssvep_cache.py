"""The scalar CCA implementation remains the independent numerical reference."""
import unittest
from unittest.mock import patch
import numpy as np
import ssvep_core as core
from cyton_sqi import channel_sqi, _sqi_spectral_constants


class CachedCCATests(unittest.TestCase):
    def test_scores_match_reference(self):
        for seed in (0, 11, 42):
            rng = np.random.default_rng(seed)
            for n in (250, 500):
                refs = core.reference_bank((8,10,12,14), samples=n)
                cache = core.CachedCCA(refs)
                for channels in (1,2,8):
                    noise = rng.normal(size=(channels,n))
                    for x in (noise, noise*1e-6, noise*1e6+1e8, np.zeros_like(noise),
                              np.repeat(noise[:1],channels,axis=0),
                              noise+5*np.sin(2*np.pi*10*np.arange(n)/250)):
                        old = [core.canonical_correlation(x, ref) for ref in refs]
                        new = cache.scores(x)
                        np.testing.assert_allclose(new,old,atol=1e-9,rtol=1e-7)
                        if sorted(old)[-1]-sorted(old)[-2] > 1e-8:
                            self.assertEqual(int(np.argmax(new)),int(np.argmax(old)))

    def test_only_one_eeg_whitening_per_window(self):
        refs = core.reference_bank((8,10,12,14),samples=500)
        with patch.object(core,'_inverse_sqrt',wraps=core._inverse_sqrt) as inv:
            cache = core.CachedCCA(refs)
            self.assertEqual(inv.call_count,4)
            cache.scores(np.random.default_rng(7).normal(size=(2,500)))
            self.assertEqual(inv.call_count,5)

    def test_invalid_input(self):
        cache = core.CachedCCA(core.reference_bank((8,10),samples=500))
        for values in (np.zeros((2,499)),np.full((2,500),np.nan)):
            with self.assertRaises(ValueError): cache.scores(values)
        with self.assertRaises(ValueError): core.CachedCCA(np.zeros((2,4)))

    def test_sqi_subset_is_identical_and_cache_is_immutable(self):
        for n in (250,500,2000):
            for seed in (0,11,42):
                x=np.random.default_rng(seed).normal(size=(n,8))
                full=channel_sqi(x)
                np.testing.assert_array_equal(channel_sqi(x,channel_indices=(0,1,2,3)),full[:4])
                np.testing.assert_array_equal(channel_sqi(x),full)
        for value in _sqi_spectral_constants(500,250):
            self.assertFalse(value.flags.writeable)


if __name__=='__main__':
    unittest.main()
