import unittest

import numpy as np

from mi_spatial import normalized_covariance, projected_features, linear_scores


class SpatialMathTests(unittest.TestCase):
    def setUp(self):
        self.rng=np.random.default_rng(20261001)

    def test_covariance_dc_and_scale_invariant(self):
        x=self.rng.normal(size=(750,8))
        np.testing.assert_allclose(normalized_covariance(x),normalized_covariance(20*x+1000),atol=1e-12)

    def test_projection_matches_sample_domain_variance(self):
        x=self.rng.normal(size=(750,8))
        w=self.rng.normal(size=(4,8))
        cov=normalized_covariance(x)
        expected=np.log(np.var(x@w.T,axis=0,ddof=1)/np.var(x,axis=0,ddof=1).sum())
        actual=projected_features(cov[None,None],w[None])[0]
        np.testing.assert_allclose(actual,expected,atol=1e-12)

    def test_batch_scalar_linear_parity(self):
        cov=np.stack([normalized_covariance(self.rng.normal(size=(750,8))) for _ in range(5)])[:,None]
        filters=self.rng.normal(size=(1,4,8))
        mean=self.rng.normal(size=4);scale=np.ones(4);coef=self.rng.normal(size=4)
        scores=linear_scores(cov,filters,mean,scale,coef,.3)
        for index,score in enumerate(scores):
            expected=((projected_features(cov[index:index+1],filters)[0]-mean)/scale)@coef+.3
            self.assertAlmostEqual(score,expected,places=12)

    def test_flat_nonfinite_and_wrong_cap_rejected(self):
        for x in (np.zeros((750,8)),np.full((750,8),np.nan),np.zeros((750,7))):
            with self.assertRaises(ValueError):normalized_covariance(x)
        with self.assertRaises(ValueError):
            linear_scores(np.eye(8)[None,None],np.eye(8)[None],np.zeros(8),np.zeros(8),np.ones(8),0)


if __name__=='__main__':unittest.main()
